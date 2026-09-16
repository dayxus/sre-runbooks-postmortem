---
id: obs-silent-failure
title: Falha silenciosa sem alerta nem erro visível
severity: critical
services: [observability]
slo_impact: error-rate
last_reviewed: 2026-09-15
owner: observability
---

# Falha silenciosa sem alerta nem erro visível

O pior tipo de incidente: o serviço está quebrado funcionalmente, retorna
sucesso, e nenhum alerta dispara. Quem descobre é o usuário, geralmente por
reclamação em canal de suporte.

## Sintomas

- Dashboards verdes, taxa de erro do balanceador baixa, e ainda assim dados não chegam ao destino.
- Fila consumindo devagar ou parada, com lag crescendo e sem alerta de erro.
- Requisições retornando `200` com corpo de erro interno ou lista vazia.
- Automação que "roda com sucesso" mas não produz efeito observável.

## Impacto no SLO

`error-rate` funcional pode ser total sem nenhum sinal técnico: a requisição dá
certo do ponto de vista do protocolo. Quanto mais tempo passa até a detecção,
maior o `freshness` perdido e maior o trabalho de reconciliação posterior.

## Detecção

**Alerta:** `BusinessKpiStalled`

```promql
increase(orders_confirmed_total[30m]) == 0
and on() (sum(rate(http_requests_total{job="checkout-api"}[30m])) > 0)
```

**Alerta:** `QueueLagGrowing`

```promql
predict_linear(queue_messages_visible[1h], 3600) > 1000
```

## Diagnóstico

1. Valide o efeito ponta a ponta, não o status HTTP.

   ```bash
   curl -sS -X POST https://api.lab.internal/checkout -H 'Content-Type: application/json' -d '{"item":"probe-1"}' -w '\nhttp_code=%{http_code}\n'
   ```

   Depois confirme que o pedido existe no destino, não só a resposta. Tempo: ~2 min.

2. Procure erros engolidos por tratamento genérico de exceção.

   ```bash
   kubectl -n prod logs deploy/checkout-api --tail=300 | grep -Ei 'swallow|caught|ignored|retrying|skipping' | head -20
   ```

   Tempo: ~30 s.

3. Cheque o lag e o consumo da fila (onde a falha costuma ficar invisível).

   ```bash
   kubectl -n prod exec deploy/payments-worker -- sh -c 'echo "lag=${QUEUE_LAG:-unknown}"'
   ```

   Tempo: ~20 s.

4. Verifique se a instrumentação de erro existe e se está sendo incrementada.

   ```promql
   rate(http_requests_total{job="checkout-api", status=~"5.."}[5m])
   rate(business_operation_failed_total{job="checkout-api"}[5m])
   ```

   Contador de negócio zerado enquanto a operação falha significa métrica ausente. Tempo: ~5 min.

5. Confirme se o contrato de saída mudou (campo renomeado, validação que passou a rejeitar silenciosamente).

   ```bash
   kubectl -n prod get deploy checkout-api -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
   kubectl -n prod rollout history deploy/checkout-api | tail -3
   ```

   Tempo: ~15 s.

6. Rode a verificação de reconciliação: diferença entre origem e destino.

   ```sql
   SELECT count(*) AS missing FROM source_orders s
   LEFT JOIN destination_orders d ON d.id = s.id
   WHERE s.created_at > now() - interval '2 hours' AND d.id IS NULL;
   ```

   Tempo: ~30 s.

## Mitigação

**Risco:** reprocessar o que ficou para trás pode duplicar efeitos; confirme a
idempotência do consumidor antes de reenfileirar.

1. Verifique se o consumidor está de pé e drenando antes de mexer em dados.

   ```bash
   kubectl -n prod get deploy payments-worker
   kubectl -n prod logs deploy/payments-worker --tail=50
   ```

2. Reprocesse a janela afetada usando a chave de idempotência (seguro quando o consumidor é idempotente).

   ```bash
   kubectl -n prod exec deploy/payments-worker -- payments-cli replay --from 2026-09-15T00:00:00Z --to 2026-09-15T02:00:00Z --idempotent
   ```

3. Restaure o caminho de escrita bloqueado pelo bug recente.

   ```bash
   kubectl -n prod rollout undo deploy/checkout-api
   kubectl -n prod rollout status deploy/checkout-api --timeout=120s
   ```

4. Adicione verificação sintética imediata enquanto a instrumentação não é corrigida.

   ```bash
   kubectl -n prod create job synthetic-check --image=curlimages/curl --restart=Never -- curl -fsS -X POST https://api.lab.internal/checkout -d '{"item":"canary"}'
   ```

## Escalonamento

- Acione o time de plantão do serviço imediatamente: falha silenciosa exige conhecer o fluxo de negócio.
- Acione o time de plantão de observabilidade quando métrica de negócio estiver faltando ou errada.
- Acione o time de suporte/comercial quando houver impacto em usuário final já visível, para dimensionar o alcance.

## Verificação

1. A reconciliação entre origem e destino não encontra mais registros faltantes na janela afetada.

   ```sql
   SELECT count(*) AS missing FROM source_orders s
   LEFT JOIN destination_orders d ON d.id = s.id
   WHERE s.created_at > now() - interval '2 hours' AND d.id IS NULL;
   ```

2. O contador de negócio voltou a crescer junto com o tráfego.

   ```promql
   increase(orders_confirmed_total[10m]) > 0
   ```

3. Um erro injetado no laboratório agora gera alerta — teste o detector, não só a ausência de erro.

## Prevenção

- Tenha pelo menos um SLO de resultado (negócio), não apenas de recurso (CPU, latência HTTP).
- Instrumente falhas de negócio com contador próprio e alerte sobre ausência de progresso.
- Proíba tratamento genérico de exceção sem log estruturado e métrica.
- Rode teste sintético ponta a ponta em intervalo curto para fluxos críticos.

## Referências

- [Google SRE Book: monitoring distributed systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Google SRE Workbook: alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Google SRE Book: postmortem culture](https://sre.google/sre-book/postmortem-culture/)
- [Prometheus: querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
