---
id: obs-missing-metrics
title: Métricas ausentes para um serviço ativo
severity: high
services: [observability]
slo_impact: freshness
last_reviewed: 2026-09-15
owner: observability
---

# Métricas ausentes para um serviço ativo

O serviço responde, os usuários não reclamam, mas os gráficos estão vazios. Aqui
o incidente é na confiança do diagnóstico: sem série temporal não há SLO, não há
error budget e qualquer alerta é palpite.

## Sintomas

- Painel do serviço mostra `No data` mesmo com tráfego real no load balancer.
- Alerta de disponibilidade silencioso por horas (não dispara: o alvo está ausente).
- `up == 0` ou ausência total da série, dependendo do coletor.
- Cardinalidade do coletor caiu de repente e ninguém notou.

## Impacto no SLO

Sem métricas, o SLO não é calculável e a degradação passa sem detecção: o
`freshness` do monitoramento cai a zero e o time perde a capacidade de decidir.
Na prática é um incidente de observabilidade com risco imediato de incidente
cego de disponibilidade.

## Detecção

**Alerta:** `ScrapeTargetDown`

```promql
up{job=~"checkout-api|payments-worker"} == 0
```

**Alerta:** `MetricSeriesDisappeared`

```promql
absent_over_time(http_requests_total{job="checkout-api"}[10m])
```

## Diagnóstico

1. Separe ausência de coleta de ausência de série.

   ```promql
   count(up{job="checkout-api"})
   count(http_requests_total{job="checkout-api"})
   ```

   `up` presente com série ausente significa que o coletor scrapeia e não há tráfego instrumentado. Tempo: ~2 min.

2. Confirme se o endpoint de métricas responde direto do pod.

   ```bash
   kubectl -n prod exec deploy/checkout-api -- wget -qO- http://localhost:8080/metrics | head -20
   ```

   Tempo: ~20 s.

3. Verifique se o ServiceMonitor/ServiceDiscovery continua correspondendo aos labels atuais.

   ```bash
   kubectl -n prod get servicemonitor checkout-api -o jsonpath='{.spec.selector.matchLabels}{"\n"}'
   kubectl -n prod get svc checkout-api --show-labels
   ```

   Label renomeado em um deploy quebra a descoberta sem nenhum erro de aplicação. Tempo: ~15 s.

4. Cheque se o coletor está rejeitando as amostras (limite de cardinalidade ou memória).

   ```bash
   kubectl -n observability logs statefulset/prometheus --tail=200 | grep -Ei 'out of order|too many|limit|samples'
   ```

   Tempo: ~30 s.

5. Confirme se a regra de scrape ainda existe e com o intervalo esperado.

   ```bash
   kubectl -n observability get prometheus -o jsonpath='{.items[*].spec.scrapeInterval}{"\n"}'
   curl -sS http://localhost:9090/api/v1/targets | head -40
   ```

   Tempo: ~20 s.

6. Descarte autenticação/rede entre coletor e pod.

   ```bash
   kubectl -n observability get networkpolicy -o custom-columns=NAME:.metadata.name,PODSELECTOR:.spec.podSelector
   curl -sS -o /dev/null -w 'http_code=%{http_code}\n' http://checkout-api.prod.svc.cluster.local:8080/metrics
   ```

   Tempo: ~15 s.

## Mitigação

**Risco:** registrar o alvo manualmente (`additionalScrapeConfigs`) resolve o
gráfico mas cria configuração fora do Git; registre a dívida no mesmo dia.

1. Reaproxime o label do serviço ao selector do ServiceMonitor quando o deploy renomeou labels.

   ```bash
   kubectl -n prod label svc checkout-api app.kubernetes.io/name=checkout-api --overwrite
   kubectl -n prod get servicemonitor checkout-api -o jsonpath='{.spec.selector}{"\n"}'
   ```

2. Reinicie o agente de coleta do pod se o endpoint responde mas o coletor não recebe.

   ```bash
   kubectl -n prod rollout restart deploy/checkout-api
   kubectl -n prod rollout status deploy/checkout-api --timeout=120s
   ```

3. Aplique a configuração extra como objeto versionado quando a descoberta não puder ser corrigida na hora.

   ```bash
   kubectl -n observability create secret generic prometheus-extra-scrape --from-file=extra.yaml=scrape-extra.yaml --dry-run=client -o yaml | kubectl apply -f -
   ```

4. Alivie pressão de cardinalidade desligando labels explosivos no relabel antes de reiniciar o coletor.

   ```bash
   kubectl -n observability edit prometheus
   ```

## Escalonamento

- Acione o time de plantão de observabilidade sempre: o coletor é deles.
- Acione o time de plantão do serviço quando a instrumentação exportada ou os labels do workload mudaram.
- Abra incidente de severidade alta se mais de um serviço perdeu métricas ao mesmo tempo: indica falha do coletor, não do serviço.

## Verificação

1. A série voltou e cobre os últimos 15 minutos sem buracos.

   ```promql
   count_over_time(http_requests_total{job="checkout-api"}[15m]) > 0
   ```

2. O pai de `up` está presente em todos os alvos esperados.

   ```promql
   count(up{job="checkout-api"}) == on() group_left() count(kube_endpoint_info{namespace="prod", endpoint="checkout-api"})
   ```

3. O painel do serviço renderiza dados e o alerta de disponibilidade volta a ser capaz de disparar.

## Prevenção

- Alerte sobre `absent_over_time` das séries críticas, não apenas sobre `up == 0`.
- Use labels estáveis (`app.kubernetes.io/name`) como contrato entre workload e descoberta.
- Rode um smoke test de métricas no pipeline: suba o serviço e verifique que o alvo aparece.
- Monitore a taxa de amostras rejeitadas do coletor e limite cardinalidade por label.

## Referências

- [Prometheus: configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Prometheus: alerting practices](https://prometheus.io/docs/practices/alerting/)
- [Prometheus: querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Google SRE Workbook: alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
