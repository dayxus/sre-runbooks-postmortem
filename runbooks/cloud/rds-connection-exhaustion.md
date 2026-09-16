---
id: cloud-rds-connection-exhaustion
title: Esgotamento de conexões em banco relacional gerenciado
severity: critical
services: [database, cloud]
slo_impact: error-rate
last_reviewed: 2026-09-15
owner: data-platform
---

# Esgotamento de conexões em banco relacional gerenciado

O banco está de pé, o CPU está baixo e mesmo assim a aplicação recebe
`too many connections`. Aqui a fila é de conexões, não de queries — diagnosticar
pelo CPU do banco leva à conclusão errada.

## Sintomas

- Aplicação retorna `FATAL: sorry, too many clients already` ou erro equivalente do driver.
- `DatabaseConnections` no teto do parâmetro `max_connections` por mais de 5 minutos.
- Latência de aquisição de conexão sobe antes do erro aparecer.
- Connection pool do serviço com fila de espera crescendo e timeouts de aquisição.

## Impacto no SLO

`error-rate` sobe de forma abrupta e total quando o pool zera: sem conexão não há
query, então a queda não é gradual. `latency` também sobe mesmo antes, porque
cada requisição espera na fila do pool até estourar o timeout.

## Detecção

**Alerta:** `DatabaseConnectionSaturation`

```promql
sum(database_connections_active) / on(instance) max(database_connections_limit) > 0.85
```

**Alerta:** `PoolAcquisitionTimeout`

```promql
increase(pool_acquire_timeout_total[5m]) > 0
```

## Diagnóstico

1. Meça o uso real contra o limite do parâmetro, não contra a intuição.

   ```bash
   aws rds describe-db-instances --db-instance-identifier lab-orders-db \
     --query 'DBInstances[0].{class:DBInstanceClass,status:DBInstanceStatus,engine:Engine}' --output json
   aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DatabaseConnections \
     --dimensions Name=DBInstanceIdentifier,Value=lab-orders-db \
     --start-time 2026-09-15T00:00:00Z --end-time 2026-09-15T01:00:00Z --period 60 --statistics Maximum
   ```

   Tempo: ~30 s.

2. Compare com o limite configurado no parameter group.

   ```bash
   aws rds describe-db-parameters --db-parameter-group-name lab-orders-pg \
     --query "Parameters[?ParameterName=='max_connections']"
   ```

   Tempo: ~15 s.

3. Veja se o consumo é de muitas instâncias pequenas ou de poucas conexões idle.

   ```sql
   SELECT state, count(*) AS connections, max(now() - state_change) AS oldest_state_age
   FROM pg_stat_activity
   WHERE backend_type = 'client backend'
   GROUP BY state ORDER BY connections DESC;
   ```

   Tempo: ~10 s.

4. Encontre quem segura conexão sem trabalhar (idle in transaction é o pior caso).

   ```sql
   SELECT pid, usename, application_name, client_addr, state,
          now() - state_change AS idle_for
   FROM pg_stat_activity
   WHERE state IN ('idle', 'idle in transaction')
   ORDER BY idle_for DESC LIMIT 20;
   ```

   Tempo: ~10 s.

5. Cheque o tamanho máximo do pool de cada serviço e some-os.

   ```bash
   grep -R "max_pool_size\|maximum_pool_size\|pool_size" /etc/lab-orders/*.conf 2>/dev/null || echo "no pool config found on this host"
   ```

   Soma de pools maior que `max_connections` é a causa estrutural. Tempo: ~5 s.

6. Confirme se há failover ou restart recente do banco (multiplica conexões na reconexão).

   ```bash
   aws rds describe-events --source-identifier lab-orders-db --source-type db-instance --duration 180
   ```

   Tempo: ~15 s.

## Mitigação

**Risco:** `pg_terminate_backend` mata a sessão do usuário e pode abortar
transação em andamento; matar apenas conexões `idle` é seguro, `idle in
transaction` pode perder trabalho.

1. Libere conexões ociosas antigas (mitigação imediata e de baixo risco).

   ```sql
   SELECT pg_terminate_backend(pid), pid, state, now() - state_change AS idle_for
   FROM pg_stat_activity
   WHERE state = 'idle'
     AND now() - state_change > interval '10 minutes'
     AND pid <> pg_backend_pid();
   ```

2. Reduza o pool da aplicação antes de aumentar `max_connections` — mais conexões no banco piora contenção de memória.

   ```bash
   kubectl -n prod set env deploy checkout-api DB_POOL_MAX=20 DB_POOL_TIMEOUT_MS=2000
   ```

3. Se o banco tem folga de memória e o pico é real, suba o limite com consciência do custo.

   ```bash
   aws rds modify-db-parameter-group --db-parameter-group-name lab-orders-pg \
     --parameters "ParameterName=max_connections,ParameterValue=400,ApplyMethod=immediate"
   ```

4. Coloque um pooler na frente quando muitos clientes precisam de poucas conexões físicas.

   ```bash
   kubectl -n data set env deploy pgbouncer POOL_MODE=transaction DEFAULT_POOL_SIZE=60 MAX_CLIENT_CONN=800
   ```

5. Contenção de emergência: reduza concorrência do serviço para liberar conexões do caminho crítico.

   ```bash
   kubectl -n prod scale deploy checkout-api --replicas=6
   ```

## Escalonamento

- Acione o time de plantão do serviço dono do pool que estourou (o banco é vítima, não causa).
- Acione o time de plantão de plataforma de dados quando a mudança for de parameter group, failover ou pooler.
- Suba para o time de arquitetura se a soma dos pools de todos os serviços exceder `max_connections`.

## Verificação

1. Conexões ativas estabilizam abaixo de 70% do limite por 15 minutos.

   ```sql
   SELECT count(*) AS connections, max(setting::int) AS limit
   FROM pg_stat_activity, pg_settings WHERE name = 'max_connections';
   ```

2. Nenhum timeout de aquisição de pool novo por 10 minutos.

   ```bash
   grep -c "pool acquire timeout" /var/log/lab-orders/app.log 2>/dev/null || echo "0 timeouts recorded in app.log"
   ```

3. A aplicação responde no caminho crítico com latência no patamar anterior.

## Prevenção

- Trate `max_connections` como orçamento: documente quantas conexões cada serviço pode usar e alerte em 80%.
- Use pooler em modo transaction para serviços com muitas réplicas.
- Configure `idle_in_transaction_session_timeout` e `statement_timeout` no banco.
- Emitir métrica de conexões por `application_name` para atribuir consumo em segundos.

## Referências

- [PostgreSQL: connection configuration](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [PostgreSQL: monitoring statistics](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [AWS: best practices for Amazon RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html)
- [AWS CLI: RDS reference](https://docs.aws.amazon.com/cli/latest/reference/rds/)
