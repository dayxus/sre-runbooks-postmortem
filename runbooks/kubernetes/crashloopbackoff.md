---
id: k8s-crashloopbackoff
title: CrashLoopBackOff em workload de produção
severity: high
services: [kubernetes]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# CrashLoopBackOff em workload de produção

Resposta para pods que sobem, morrem e voltam em laço. A prioridade é separar
falha de configuração (rollback resolve) de dependência externa (rollback não
resolve) antes de tocar no cluster.

## Sintomas

- `kubectl get pods -n prod` mostra `CrashLoopBackOff` com contador de restarts crescendo.
- O alerta de disponibilidade abre para o serviço, mas o Deployment aparece com réplicas desejadas.
- Logs do container terminam de forma abrupta, sem stack trace, ou repetem a mesma linha de erro a cada tentativa.
- Latência no load balancer sobe apenas nos endpoints que apontam para os pods em laço.

## Impacto no SLO

`availability` cai na proporção de pods em laço: com 4 de 12 réplicas em
`CrashLoopBackOff` o erro visível é de 30% a 40%, dependendo do balanceamento.
O error budget queima enquanto o Kubernetes respeita o backoff (até 5 minutos
entre tentativas), então o pior caso é uma indisponibilidade parcial longa e silenciosa.

## Detecção

**Alerta:** `KubePodCrashLooping`

```promql
max_over_time(
  kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff", namespace="prod"}[10m]
) > 0
```

Consulta de log correspondente:

```logql
sum by (container) (rate({namespace="prod"} |= "panic" [5m])) > 0
```

## Diagnóstico

1. Confirme o estado, a razão da última terminação e o horário do primeiro restart.

   ```bash
   kubectl -n prod get pods -o wide --field-selector=status.phase=Running
   kubectl -n prod describe pod checkout-api-7d9c8f6b5-x4ltq | sed -n '/Last State/,/Events/p'
   ```

   Esperado: `Last State: Terminated / Reason: Error` (ou `OOMKilled`). Tempo: ~20 s.

2. Leia os logs do container **anterior**, não do atual — o atual costuma estar saudável por segundos.

   ```bash
   kubectl -n prod logs checkout-api-7d9c8f6b5-x4ltq --previous --tail=80
   ```

   Procure a última linha antes do silêncio: erro de conexão, `exec format error` ou falta de variável de ambiente. Tempo: ~15 s.

3. Decida se a falha é de inicialização ou de dependência.

   ```bash
   kubectl -n prod logs deploy/checkout-api --tail=200 | grep -Ei 'timeout|refused|denied|no such host|authentication'
   ```

   Se aparecer `no such host` ou `connection refused`, trate como dependência (passo 5) e não como imagem. Tempo: ~20 s.

4. Verifique se a última revisão do Deployment é a origem do problema.

   ```bash
   kubectl -n prod rollout history deploy/checkout-api
   kubectl -n prod get rs -l app=checkout-api -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas,CREATED:.metadata.creationTimestamp
   ```

   Se o ReplicaSet anterior está pronto e o novo não, a causa está na revisão nova. Tempo: ~15 s.

5. Cheque o que o pod precisa e não está recebendo: ConfigMap, Secret e limites.

   ```bash
   kubectl -n prod get pod checkout-api-7d9c8f6b5-x4ltq -o jsonpath='{.spec.containers[*].envFrom}{"\n"}{.spec.containers[*].resources}{"\n"}'
   kubectl -n prod get configmap checkout-api-config -o jsonpath='{.metadata.resourceVersion}'
   ```

   Tempo: ~20 s.

6. Se a terminação foi `OOMKilled`, confirme se o limite é menor que o pico real.

   ```bash
   kubectl -n prod get pod checkout-api-7d9c8f6b5-x4ltq -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}{"\n"}'
   kubectl -n prod top pod checkout-api-7d9c8f6b5-x4ltq --containers
   ```

   Tempo: ~20 s.

## Mitigação

**Risco:** rollback devolve a versão anterior mas deixa a migração de banco aplicada; confirme
com o passo 1 de Verificação antes de reabrir o tráfego.

1. Rollback do Deployment para a revisão estável (mitigação principal, ~40 s).

   ```bash
   kubectl -n prod rollout undo deploy/checkout-api
   kubectl -n prod rollout status deploy/checkout-api --timeout=120s
   ```

2. Se a falha for de ConfigMap/Secret aplicado errado, corrija o objeto antes de reiniciar — reiniciar sem corrigir só repete o laço.

   ```bash
   kubectl -n prod create configmap checkout-api-config --from-file=app.yaml --dry-run=client -o yaml | kubectl -n prod apply -f -
   kubectl -n prod rollout restart deploy/checkout-api
   ```

3. Se a causa for limite de memória, suba o limite proporcional ao consumo observado no passo 6 (não duplique "por segurança").

   ```bash
   kubectl -n prod patch deploy/checkout-api --type=strategic -p '{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"limits":{"memory":"1Gi"}}}]}}}}'
   ```

4. Pod preso em laço com erro de dependência e sem impacto total: escale as réplicas saudáveis para absorver o tráfego enquanto investiga.

   ```bash
   kubectl -n prod scale deploy/checkout-api --replicas=8
   ```

## Escalonamento

- Acione o time de plantão do serviço quando houver usuários afetados ou o rollback não estancar a queima de error budget.
- Suba para o time de plantão de plataforma quando a suspeita for node, CRD, admission webhook ou capacidade do cluster.
- Abra incidente formal (severidade alta) se o rollback falhar mais de uma vez ou se mais de um serviço entrar em laço no mesmo minuto.

## Verificação

1. Nenhum pod em `CrashLoopBackOff` e contagem de restarts parada por 10 minutos.

   ```bash
   kubectl -n prod get pods -l app=checkout-api -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount
   ```

2. O readiness probe responde de dentro do pod, provando que a aplicação aceita tráfego.

   ```bash
   kubectl -n prod exec deploy/checkout-api -- wget -qO- http://localhost:8080/healthz
   ```

3. O SLI de disponibilidade volta ao patamar anterior por pelo menos uma janela de 30 minutos antes de declarar resolvido.

## Prevenção

- Rode a versão nova no canário por 30 minutos antes do rollout completo; `CrashLoopBackOff` aparece em segundos.
- Adicione um `startupProbe` separado do `livenessProbe` para aplicações com bootstrap lento.
- Valide ConfigMap/Secret no pipeline antes do deploy (schema e chaves obrigatórias).
- Defina limites de recursos a partir do consumo medido em carga real, não de estimativas.

## Referências

- [Kubernetes: determine the reason for pod failure](https://kubernetes.io/docs/tasks/debug/debug-application/determine-reason-pod-failure/)
- [Kubernetes: configuring liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Kubernetes: managing resources for containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Google SRE Book: monitoring distributed systems](https://sre.google/sre-book/monitoring-distributed-systems/)
