---
id: k8s-pending-pods
title: Pods em Pending por tempo indefinido
severity: high
services: [kubernetes]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# Pods em Pending por tempo indefinido

Pod criado e nunca agendado. O scheduler registra o motivo no evento e nos
`Conditions`; a resposta correta depende de a causa ser capacidade, afinidade,
taint ou cota.

## Sintomas

- `kubectl get pods` mostra `Pending` sem passar para `ContainerCreating`.
- Réplicas desejadas maiores que as disponíveis, com o HPA no teto.
- Eventos repetem `FailedScheduling: 0/6 nodes are available`.
- Deploy novo nunca fica pronto e o `maxUnavailable` antigo ainda segura o tráfego.

## Impacto no SLO

Cada pod não agendado é capacidade removida do serviço. Se o Deployment roda no
limite, a perda de um pod reduz o `throughput` e aumenta latência por fila; em
serviços com `PodDisruptionBudget` apertado pode bloquear drain e manutenção.

## Detecção

**Alerta:** `KubePodPendingTooLong`

```promql
max by (namespace, pod) (
  kube_pod_status_phase{phase="Pending", namespace="prod"} == 1
  and on(namespace, pod) (time() - kube_pod_created{namespace="prod"} > 600)
) > 0
```

## Diagnóstico

1. Leia o motivo exato do scheduler — ele diz qual predicado falhou.

   ```bash
   kubectl -n prod describe pod checkout-api-7d9c8f6b5-x4ltq | sed -n '/Events/,$p'
   ```

   Esperado: `FailedScheduling` com `Insufficient cpu`, `node(s) had taint` ou `didn't match node selector`. Tempo: ~15 s.

2. Confirme a capacidade livre dos nós por zona.

   ```bash
   kubectl get nodes -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.topology\.kubernetes\.io/zone,CPU_ALLOC:.status.allocatable.cpu,MEM_ALLOC:.status.allocatable.memory
   kubectl top nodes
   ```

   Tempo: ~20 s.

3. Cheque cota de namespace e limite de recursos do namespace.

   ```bash
   kubectl -n prod describe quota
   kubectl -n prod get limitrange -o yaml
   ```

   `Used + Requested > Hard` explica o Pending sem nenhum nó lotado. Tempo: ~10 s.

4. Verifique taints, tolerations e afinidade do workload.

   ```bash
   kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints[*].key
   kubectl -n prod get deploy checkout-api -o jsonpath='{.spec.template.spec.tolerations}{"\n"}{.spec.template.spec.affinity}{"\n"}'
   ```

   Tempo: ~15 s.

5. Confirme se o cluster autoscaler está tentando e falhando.

   ```bash
   kubectl -n kube-system logs deploy/cluster-autoscaler --tail=100 | grep -Ei 'no node group|max size|scale up failed|cannot scale'
   ```

   Tempo: ~30 s.

6. Veja se PVCs pendentes bloqueiam o agendamento.

   ```bash
   kubectl -n prod get pvc -o custom-columns=NAME:.metadata.name,VOLUME:.spec.volumeName,STATUS:.status.phase,STORAGECLASS:.spec.storageClassName
   ```

   Tempo: ~10 s.

## Mitigação

**Risco:** relaxar afinidade ou toleration muda a topologia real do serviço e pode
concentrar réplicas em uma zona — só faça isso sabendo qual redundância resta.

1. Reduza a pressão de CPU/memória temporariamente via HPA se o gargalo for capacidade.

   ```bash
   kubectl -n prod get hpa checkout-api
   kubectl -n prod patch hpa checkout-api --type=merge -p '{"spec":{"maxReplicas":20}}'
   ```

2. Se o autoscaler está no teto do node group, aumente o limite.

   ```bash
   kubectl -n kube-system exec deploy/cluster-autoscaler -- printenv | grep -i 'max\|min'
   ```

3. Para nós drenados ou taint não intencional, libere o nó antes de mexer no workload.

   ```bash
   kubectl get nodes -o custom-columns=NAME:.metadata.name,UNSCHED:.spec.unschedulable,DRAINED:.metadata.labels.kubernetes\.io/role
   kubectl uncordon ip-10-0-14-23.us-east-1.compute.internal
   ```

4. Ajuste requests para valores que caibam de fato no maior bloco livre, quando o pedido é maior que qualquer nó.

   ```bash
   kubectl -n prod patch deploy checkout-api --type=strategic -p '{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"requests":{"cpu":"500m","memory":"512Mi"}}}]}}}}'
   ```

## Escalonamento

- Acione o time de plantão de plataforma quando a causa for capacidade de node group ou autoscaler no teto.
- Acione o time de plantão do serviço quando a causa for requests/afinidade específicos do workload.
- Suba para o dono da conta de nuvem se a quota do provedor (vCPU por região) bloquear o scale up.

## Verificação

1. O pod saiu de `Pending` e o Deployment declarou `available`.

   ```bash
   kubectl -n prod rollout status deploy/checkout-api --timeout=180s
   kubectl -n prod get pods -l app=checkout-api -o wide
   ```

2. Nenhum evento `FailedScheduling` novo nos últimos 10 minutos.

   ```bash
   kubectl -n prod get events --field-selector reason=FailedScheduling --sort-by=.lastTimestamp | tail -5
   ```

3. Capacity do HPA e do cluster ficou com folga de pelo menos um nó para o próximo pico.

## Prevenção

- Alerta sobre `Pending > 5 min` em vez de sobre `availableReplicas`, que demora mais para reagir.
- Fixe `min` do node group acima do pico de requests de todos os workloads críticos do namespace.
- Teste `kubectl drain` em ambiente de laboratório para descobrir atritos de PDB e afinidade antes da manutenção real.
- Prefira `topologySpreadConstraints` a afinidade manual por hostname: sobrevive a mudança de nós.

## Referências

- [Kubernetes: assigning pods to nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Kubernetes: pod disruption budgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
- [Kubernetes: resource quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/)
- [Kubernetes: nodes](https://kubernetes.io/docs/concepts/architecture/nodes/)
