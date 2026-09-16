---
id: db-connection-pool-saturation
title: Saturação do pool de conexões da aplicação
severity: high
services: [database, application]
slo_impact: latency
last_reviewed: 2026-09-15
owner: platform
---

# Saturação do pool de conexões da aplicação

O pool está cheio, as consultas são rápidas, e mesmo assim as requisições
esperam. Diferente de esgotar o limite do banco, aqui o gargalo está no cliente
e a solução costuma ser reduzir concorrência, não aumentar.

## Sintomas

- `pool_acquire_timeout_total` crescendo sem erro do banco.
- Latência p95 do serviço sobe enquanto o tempo de query no banco permanece igual.
- Threads/goroutines/event-loop com fila de espera; uso de CPU do app pode até cair.
- Erros aparecem como timeout de aplicação (`context deadline exceeded`) e não como erro de banco.

## Impacto no SLO

`latency` degrada em degrau e, ao estourar o timeout de aquisição, a requisição
vira erro. Requisições que esperam no pool consomem memória e conexões do cliente
HTTP, criando efeito cascata entre serviços.

## Detecção

**Alerta:** `PoolSaturation`

```promql
pool_connections_in_use / pool_connections_max > 0.9
```

**Alerta:** `PoolWaitTimeHigh`

```promql
histogram_quantile(0.95, sum by (le) (rate(pool_acquire_seconds_bucket[5m]))) > 0.5
```

## Diagnóstico

1. Compare a espera no pool com o tempo real de query: é isso que separa pool de banco.

   ```promql
   histogram_quantile(0.95, sum by (le) (rate(pool_acquire_seconds_bucket{service="checkout-api"}[5m])))
   histogram_quantile(0.95, sum by (le) (rate(db_query_seconds_bucket{service="checkout-api"}[5m])))
   ```

   Tempo: ~5 min.

2. Confirme a configuração efetiva do pool em execução (nem sempre é o que está no manifesto).

   ```bash
   kubectl -n prod exec deploy/checkout-api -- printenv | grep -Ei 'POOL|DB_MAX|CONN'
   ```

   Tempo: ~15 s.

3. Verifique se conexões ficam presas por transação aberta sem commit.

   ```promql
   increase(pool_connections_leaked_total{service="checkout-api"}[30m])
   ```

   Tempo: ~5 min.

4. Some o total de conexões que o serviço pode criar com todas as réplicas.

   ```bash
   kubectl -n prod get deploy checkout-api -o jsonpath='{.spec.replicas}{"\n"}'
   kubectl -n prod get deploy checkout-api -o jsonpath='{.spec.template.spec.containers[0].env}' | grep -o 'DB_POOL_MAX[^}]*'
   ```

   Réplicas multiplicadas pelo pool dão o teto real contra o `max_connections`. Tempo: ~10 s.

5. Olhe o endpoint mais lento para saber se o pool está sendo consumido por uma consulta pesada.

   ```promql
   topk(5, sum by (route, method) (rate(http_request_duration_seconds_sum{service="checkout-api"}[10m]))
     / sum by (route, method) (rate(http_request_duration_seconds_count{service="checkout-api"}[10m])))
   ```

   Tempo: ~5 min.

6. Verifique duplicação de pools: frameworks diferentes abrindo pools separados no mesmo processo.

   ```bash
   kubectl -n prod exec deploy/checkout-api -- sh -c 'grep -R "pool" /app/config/*.yaml 2>/dev/null | head -20'
   ```

   Tempo: ~20 s.

## Mitigação

**Risco:** aumentar o pool diminui a espera no cliente mas pressiona o banco;
reduzir timeout de aquisição transforma espera em erro mais cedo — escolha qual
falha você prefere explicar.

1. Reduza o timeout de aquisição para falhar rápido e liberar recursos do cliente.

   ```bash
   kubectl -n prod set env deploy/checkout-api DB_POOL_TIMEOUT_MS=1500
   ```

2. Limite a concorrência no caminho que monopoliza o pool (mitigação cirúrgica).

   ```bash
   kubectl -n prod set env deploy/checkout-api REPORT_CONCURRENCY=4
   ```

3. Aumente o pool em passo pequeno, respeitando o teto calculado no diagnóstico 4.

   ```bash
   kubectl -n prod patch deploy checkout-api --type=strategic -p '{"spec":{"template":{"spec":{"containers":[{"name":"app","env":[{"name":"DB_POOL_MAX","value":"25"}]}]}}}}'
   ```

4. Se o gargalo é uma consulta específica, cacheie o resultado em vez de aumentar concorrência.

   ```bash
   kubectl -n prod set env deploy/checkout-api CACHE_TTL_SECONDS=60
   ```

5. Para picos previsíveis, escale horizontalmente mantendo o pool por réplica pequeno.

   ```bash
   kubectl -n prod autoscale deploy checkout-api --min=6 --max=24 --cpu-percent=65
   ```

## Escalonamento

- Acione o time de plantão do serviço quando o pool saturado pertencer a um workload específico.
- Acione o time de plantão de plataforma de dados quando o teto de conexões do banco for o limitante real.
- Suba para o time de desenvolvimento quando a causa for consulta pesada, N+1 ou pool duplicado no código.

## Verificação

1. Conexões em uso ficam abaixo de 70% do pool durante um pico real.

   ```promql
   max_over_time(pool_connections_in_use{service="checkout-api"}[30m]) / pool_connections_max < 0.7
   ```

2. p95 de aquisição de pool volta para menos de 50 ms.

   ```promql
   histogram_quantile(0.95, sum by (le) (rate(pool_acquire_seconds_bucket{service="checkout-api"}[5m])))
   ```

3. Nenhum timeout de aquisição novo por 15 minutos, e a latência ponta a ponta acompanha a queda.

## Prevenção

- Defina pool por réplica como `max_connections / (replicas + margem)` e documente o cálculo no README do serviço.
- Meça e alerte sobre tempo de espera no pool, não só sobre conexões em uso.
- Configure `statement_timeout` no cliente e no servidor para impedir que uma consulta segure conexão indefinidamente.
- Carregue teste de carga com o número real de réplicas: pool saturado só aparece com concorrência real.

## Referências

- [PostgreSQL: connection configuration](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [PostgreSQL: libpq connection strings](https://www.postgresql.org/docs/current/libpq-connect.html)
- [PostgreSQL: resource consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html)
- [Google SRE Workbook: alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
