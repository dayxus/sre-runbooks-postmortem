---
id: db-replication-lag
title: Replication lag crescente entre primário e réplicas
severity: high
services: [database]
slo_impact: freshness
last_reviewed: 2026-09-15
owner: data-platform
---

# Replication lag crescente entre primário e réplicas

A replicação está de pé, mas a réplica atrasa minutos em relação ao primário.
Leituras em réplica devolvem dados velhos e, se o aplicativo não souber disso,
o usuário vê estado inconsistente.

## Sintomas

- `ReplicaLag` cresce de forma monotônica em vez de oscilar.
- Consultas de leitura em réplica retornam registros que já foram atualizados no primário.
- `pg_stat_replication` mostra `replay_lag` muito maior que `write_lag`.
- WAL acumulando no primário ou disco da réplica enchendo.

## Impacto no SLO

`freshness` degrada: relatórios e leituras consistentes ficam desatualizados por
minutos. Se a aplicação aceita leitura em réplica para caminhos de decisão, o
`error-rate` funcional aparece (decisão tomada com dado velho).

## Detecção

**Alerta:** `ReplicationLagHigh`

```promql
pg_replication_lag_seconds > 60
```

**Alerta:** `WALRetentionGrowing`

```promql
increase(pg_wal_segments_total[15m]) > 0
and on(instance) pg_replication_lag_seconds > 300
```

## Diagnóstico

1. Meça o lag com precisão e veja se é de escrita, de envio ou de replay.

   ```sql
   SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,
          write_lag, flush_lag, replay_lag
   FROM pg_stat_replication;
   ```

   `replay_lag` alto com `write_lag` baixo indica problema de aplicação do WAL na réplica. Tempo: ~10 s.

2. Confirme se a réplica está aplicando WAL e há quanto tempo está no mesmo LSN.

   ```sql
   SELECT pg_last_wal_receive_lsn() AS received, pg_last_wal_replay_lsn() AS replayed,
          now() - pg_last_xact_replay_timestamp() AS replay_age;
   ```

   Tempo: ~10 s.

3. Verifique conflitos de recuperação (conflito com query longa na réplica é causa clássica).

   ```sql
   SELECT conflict_type, count(*) FROM pg_stat_database_conflicts
   WHERE datname = current_database() GROUP BY conflict_type ORDER BY 2 DESC;
   ```

   `conflict_type = snapshot` com valor alto bloqueia o replay repetidamente. Tempo: ~10 s.

4. Cheque queries longas abertas na réplica que seguram o horizonte de snapshot.

   ```sql
   SELECT pid, now() - xact_start AS runtime, state, left(query, 80) AS query
   FROM pg_stat_activity
   WHERE backend_type = 'client backend' AND state <> 'idle'
   ORDER BY runtime DESC LIMIT 10;
   ```

   Tempo: ~10 s.

5. Olhe I/O e CPU da réplica, que normalmente aplica WAL em single thread.

   ```bash
   aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name ReadIOPS \
     --dimensions Name=DBInstanceIdentifier,Value=lab-orders-replica-1 \
     --start-time 2026-09-15T00:00:00Z --end-time 2026-09-15T01:00:00Z --period 60 --statistics Average
   ```

   Tempo: ~20 s.

6. Confirme se o lag começou junto com um lote de escrita pesado no primário.

   ```sql
   SELECT now() - xact_start AS runtime, state, left(query, 80) AS query
   FROM pg_stat_activity
   WHERE backend_type = 'client backend' AND state = 'active'
   ORDER BY runtime DESC LIMIT 5;
   ```

   Tempo: ~10 s.

## Mitigação

**Risco:** parar queries de leitura na réplica reduz lag mas aumenta a carga no
primário; redirecionar tráfego em massa para o primário pode derrubar o serviço inteiro.

1. Reduza a pressão de escrita no primário durante o pico (throttling do produtor, não do consumidor).

   ```bash
   kubectl -n prod set env deploy/payments-worker BATCH_WRITE_SLEEP_MS=25 MAX_BATCH_SIZE=200
   ```

2. Mate a query longa que bloqueia o replay, escolhendo pela idade e não pelo texto.

   ```sql
   SELECT pid, now() - xact_start AS runtime, state
   FROM pg_stat_activity WHERE state <> 'idle' ORDER BY runtime DESC LIMIT 3;
   SELECT pg_cancel_backend(4321);
   ```

3. Ajuste a tolerância a conflitos quando o ambiente permitir descartar work (só com decisão explícita de negócio).

   ```sql
   ALTER SYSTEM SET max_standby_streaming_delay = '60s';
   SELECT pg_reload_conf();
   ```

4. Desvie a aplicação para o primário apenas nas leituras críticas de consistência.

   ```bash
   kubectl -n prod set env deploy checkout-api DB_READ_REPLICA_ENABLED=false
   ```

5. Se a réplica não recupera, recrie-a a partir de snapshot em vez de tentar acelerar o replay.

   ```bash
   aws rds create-db-instance-read-replica --db-instance-identifier lab-orders-replica-2 \
     --source-db-instance-identifier lab-orders-db --db-instance-class db.r6g.large --region us-east-1
   ```

## Escalonamento

- Acione o time de plantão de plataforma de dados sempre: replicação é responsabilidade da plataforma de dados.
- Acione o time de plantão do serviço quando leituras de consistência estiverem impactando usuário.
- Suba para o time de performance quando o lag for consequência de um padrão de escrita patológico que exige mudança de aplicação.

## Verificação

1. `replay_lag` volta para segundos e se mantém por 15 minutos.

   ```sql
   SELECT client_addr, write_lag, flush_lag, replay_lag FROM pg_stat_replication;
   ```

2. Uma leitura de verificação enxerga o dado escrito no primário no tempo esperado.

   ```bash
   kubectl -n prod exec deploy/checkout-api -- psql "$DB_URL_REPLICA" -c "SELECT max(updated_at) FROM orders;"
   ```

3. Nenhum conflito de recuperação novo aparece nos últimos 10 minutos.

   ```sql
   SELECT conflict_type, count(*) FROM pg_stat_database_conflicts GROUP BY conflict_type;
   ```

## Prevenção

- Alerte em dois níveis: lag acima de 30 s (ticket) e acima de 5 min (página).
- Rode lotes de escrita com tamanho controlado e janelas conhecidas pelos consumidores de réplica.
- Mantenha timeout de query obrigatório nos clientes de réplica.
- Monitore WAL retido e espaço livre na réplica como indicador antecedente.

## Referências

- [PostgreSQL: log-shipping standby servers](https://www.postgresql.org/docs/current/warm-standby.html)
- [PostgreSQL: monitoring statistics](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [AWS: working with read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.html)
- [AWS CLI: RDS reference](https://docs.aws.amazon.com/cli/latest/reference/rds/)
