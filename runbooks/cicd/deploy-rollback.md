---
id: cicd-deploy-rollback
title: Deploy com degradação e decisão de rollback
severity: critical
services: [cicd, application]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# Deploy com degradação e decisão de rollback

Deploy acabou de sair e os indicadores pioraram. A pergunta não é "como voltar",
é "voltar agora ou seguir investigando": cada minuto de indecisão é error budget.

## Sintomas

- Erro ou latência sobem em até 15 minutos depois de um deploy concluído.
- Dashboards comparativos mostram a versão nova pior que a anterior no mesmo tráfego.
- Alertas de SLO disparam logo após o rollout terminar.
- Aumento de restarts, timeouts de dependência ou respostas de erro específicas de rota.

## Impacto no SLO

Todo o `availability` do serviço fica em risco proporcional ao tempo de decisão.
Rollback é uma ação de contenção (não resolve a causa) e devolve o serviço ao
patamar anterior; sem rollback, o error budget queima até o deploy ser corrigido.

## Detecção

**Alerta:** `DeployRegression`

```promql
sum(rate(http_requests_total{status=~"5..", service="checkout-api"}[5m]))
  / sum(rate(http_requests_total{service="checkout-api"}[5m])) > 0.02
```

**Alerta:** `PostDeployLatencyRegression`

```promql
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="checkout-api"}[5m]))) > 1.5
```

## Diagnóstico

1. Confirme o horário exato do deploy e o que mais mudou na janela.

   ```bash
   kubectl -n prod rollout history deploy/checkout-api
   kubectl -n prod get pods -l app=checkout-api -o custom-columns=NAME:.metadata.name,IMAGE:.spec.containers[*].image,START:.status.startTime
   ```

   Tempo: ~20 s.

2. Compare a taxa de erro entre a revisão nova e a anterior, no mesmo serviço e rota.

   ```promql
   sum by (revision) (rate(http_requests_total{service="checkout-api", status=~"5.."}[5m]))
   ```

   Se o erro está só na revisão nova, rollback é a resposta proporcional. Tempo: ~5 min.

3. Leia os logs de erro da versão nova procurando assinatura específica de código.

   ```bash
   kubectl -n prod logs deploy/checkout-api --since=15m | grep -Ei 'error|exception|panic' | sort | uniq -c | sort -rn | head -15
   ```

   Tempo: ~30 s.

4. Verifique dependências que mudaram junto (migração de banco, feature flag, configuração).

   ```bash
   kubectl -n prod get deploy checkout-api -o jsonpath='{.spec.template.spec.containers[0].imagePullPolicy}{" "}{.metadata.annotations}{"\n"}'
   kubectl -n prod get cm checkout-api-config -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}{"\n"}'
   ```

   Tempo: ~15 s.

5. Decida com três fatores: alcance do erro, reversibilidade da migração e disponibilidade da versão anterior.

   ```bash
   kubectl -n prod get rs -l app=checkout-api -o custom-columns=NAME:.metadata.name,REPLICAS:.spec.replicas,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[*].image
   ```

   Sem ReplicaSet anterior pronta, rollback não é instantâneo. Tempo: ~15 s.

6. Cheque se o erro também aparece no canário ou só no rollout completo.

   ```bash
   kubectl -n prod get svc checkout-api -o jsonpath='{.spec.selector}{"\n"}'
   kubectl -n prod get pods -l app=checkout-api -o wide --no-headers | wc -l
   ```

   Tempo: ~15 s.

## Mitigação

**Risco:** rollback de código não reverte migração de banco aplicada nem feature
flag já ligada; confirme a compatibilidade da revisão anterior com o schema
atual antes de declarar resolvido.

1. Rollback do Deployment (contenção padrão, ~1 min).

   ```bash
   kubectl -n prod rollout undo deploy/checkout-api
   kubectl -n prod rollout status deploy/checkout-api --timeout=180s
   ```

2. Desligue a feature flag nova quando o rollback de imagem não estiver disponível.

   ```bash
   kubectl -n prod set env deploy/checkout-api FEATURE_NEW_ROUTING=false
   ```

3. Reduza a exposição primeiro se o rollback completo for arriscado: mantenha poucas réplicas novas.

   ```bash
   kubectl -n prod scale deploy/checkout-api --replicas=4
   ```

4. Congele o deploy do serviço durante o incidente para evitar nova mudança de estado.

   ```bash
   kubectl -n prod annotate deploy checkout-api deploy.freeze/reason="incident" --overwrite
   ```

5. Se a migração de banco for incompatível, reaplique a compatibilidade antes de liberar rollback.

   ```bash
   kubectl -n prod exec deploy/checkout-rollback-job -- migrate --to-revision previous --backward-compatible
   ```

## Escalonamento

- Acione o time de plantão do serviço antes de decidir: quem conhece a migração está no plantão do serviço, não no de plataforma.
- Acione o time de plantão de plataforma quando o rollback falhar ou o cluster estiver bloqueando o rollout.
- Abra incidente formal (severidade crítica) se o rollback não estancar o erro ou a migração for irreversível.

## Verificação

1. A revisão anterior está pronta e a nova não está recebendo tráfego.

   ```bash
   kubectl -n prod rollout status deploy/checkout-api --timeout=60s
   kubectl -n prod get rs -l app=checkout-api -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,DESIRED:.spec.replicas
   ```

2. Taxa de erro e p95 voltaram ao patamar anterior por 30 minutos.

   ```promql
   sum(rate(http_requests_total{service="checkout-api", status=~"5.."}[5m]))
     / sum(rate(http_requests_total{service="checkout-api"}[5m]))
   ```

3. A migração de banco continua compatível com a versão em produção (teste de leitura e escrita no fluxo principal).

## Prevenção

- Deploy em canário com análise automática de erro antes do rollout completo.
- Migrações compatíveis para trás (expand/contract) como regra obrigatória.
- Botão de rollback documentado e testado no pipeline, com o mesmo caminho usado na emergência.
- Congelamento automático de deploy quando o SLO do serviço está queimando error budget.

## Referências

- [Kubernetes: rolling back a deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes: performing a rolling update](https://kubernetes.io/docs/tutorials/kubernetes-basics/update/update-intro/)
- [Google SRE Workbook: canarying releases](https://sre.google/workbook/canarying-releases/)
- [Google SRE Book: postmortem culture](https://sre.google/sre-book/postmortem-culture/)
