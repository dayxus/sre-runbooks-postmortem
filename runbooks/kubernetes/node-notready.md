---
id: k8s-node-notready
title: Node NotReady com workloads em risco
severity: critical
services: [kubernetes]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# Node NotReady com workloads em risco

Node deixa de reportar `Ready` e o controlador começa a marcar os pods para
eviction depois do toleration timeout. A decisão de cordon/drain precisa ser
tomada rápido, mas nunca sem checar PDB e capacidade restante.

## Sintomas

- `kubectl get nodes` mostra um nó `NotReady`, `Unknown` ou com `Ready=False`.
- Pods do nó entram em `Terminating` ou `Unknown` e o kubelet para de atualizar status.
- `kube_node_status_condition` muda para `NotReady` e o alerta dispara.
- Serviços com `topologySpreadConstraints` ficam desbalanceados.

## Impacto no SLO

Enquanto o nó está `NotReady`, os pods dele continuam no Service até o
`node-monitor-grace-period`, então uma fração do tráfego pode ir para réplicas
que não respondem. Depois do eviction, a capacidade cai de verdade e o
`error-rate` do serviço acompanha. Em clusters pequenos, um nó é uma fração
grande da capacidade total.

## Detecção

**Alerta:** `KubeNodeNotReady`

```promql
kube_node_status_condition{condition="Ready", status="true"} == 0
```

Correlacione com o volume de eventos de eviction:

```promql
sum by (node) (rate(kube_pod_status_phase{phase="Failed"}[10m])) > 0
```

## Diagnóstico

1. Identifique qual nó e há quanto tempo saiu do ar.

   ```bash
   kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,REASON:.status.conditions[-1].reason,LAST:.status.conditions[-1].lastTransitionTime
   ```

   Tempo: ~10 s.

2. Separe falha de rede/kubelet de pressão de recurso lendo as condições.

   ```bash
   kubectl describe node ip-10-0-14-23.us-east-1.compute.internal | sed -n '/Conditions:/,/Addresses:/p'
   ```

   `DiskPressure` ou `MemoryPressure = True` indica causa recuperável; ausência de heartbeat indica nó perdido. Tempo: ~15 s.

3. Cheque se o nó ainda responde no caminho de dados (o alerta pode ser falso positivo de kubelet).

   ```bash
   ping -c 3 ip-10-0-14-23.us-east-1.compute.internal
   ```

   Tempo: ~10 s.

4. Inventarie o que está rodando lá e o que tem PDB.

   ```bash
   kubectl get pods -A --field-selector spec.nodeName=ip-10-0-14-23.us-east-1.compute.internal -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PHASE:.status.phase
   kubectl get pdb -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,MIN:.spec.minAvailable,ALLOWED:.status.disruptionsAllowed
   ```

   Qualquer PDB com `disruptionsAllowed=0` bloqueia eviction. Tempo: ~20 s.

5. Confirme o tempo restante antes do eviction automático.

   ```bash
   kubectl -n kube-system get deploy kube-controller-manager -o jsonpath='{.spec.template.spec.containers[*].command}' | tr ',' '\n' | grep -Ei 'node-monitor|pod-eviction'
   ```

   Padrão: 40 s de grace e 5 min de toleration. Tempo: ~15 s.

6. Se o nó responde, leia o kubelet antes de tomar qualquer ação destrutiva.

   ```bash
   journalctl -u kubelet -n 200 --no-pager | grep -Ei 'error|failed|unable'
   ```

   Tempo: ~30 s.

## Mitigação

**Risco:** cordon sem eviction tira capacidade nova mas mantém os pods no ar;
drain remove os pods e pode violar PDB. Escolha pelo impacto no serviço, não pela pressa.

1. Impedir agendamento novo no nó imediatamente (seguro e reversível).

   ```bash
   kubectl cordon ip-10-0-14-23.us-east-1.compute.internal
   ```

2. Eviction respeitando PDB quando a capacidade restante aguenta.

   ```bash
   kubectl drain ip-10-0-14-23.us-east-1.compute.internal --ignore-daemonsets --delete-emptydir-data --timeout=180s
   ```

3. Se o drain travar em PDB, aumente temporariamente as réplicas do serviço antes de insistir.

   ```bash
   kubectl -n prod get pdb
   kubectl -n prod scale deploy checkout-api --replicas=10
   kubectl drain ip-10-0-14-23.us-east-1.compute.internal --ignore-daemonsets --timeout=180s
   ```

4. Nó perdido de verdade: remova do cluster somente depois de garantir que nenhum pod dele está servindo tráfego.

   ```bash
   kubectl get pods -A -o wide --field-selector spec.nodeName=ip-10-0-14-23.us-east-1.compute.internal
   kubectl delete node ip-10-0-14-23.us-east-1.compute.internal
   ```

## Escalonamento

- Acione o time de plantão de plataforma ao confirmar `NotReady` como causa (é o dono do cluster).
- Acione o time de plantão do serviço quando o eviction estiver derrubando réplicas e o serviço perder capacidade.
- Suba para o provedor de nuvem quando o nó não voltar e exigir substituição na camada de infraestrutura.

## Verificação

1. Todos os nós `Ready` e nenhum pod órfão apontando para o nó removido.

   ```bash
   kubectl get nodes
   kubectl get pods -A -o wide | grep -c ip-10-0-14-23.us-east-1.compute.internal
   ```

2. Réplicas de cada Deployment crítico voltaram ao desejado e passaram no readiness.

   ```bash
   kubectl -n prod get deploy -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas
   ```

3. Error budget do serviço estabilizou por 30 minutos antes de declarar resolvido.

## Prevenção

- Distribua workloads com `topologySpreadConstraints` para nenhum nó concentrar um serviço inteiro.
- Configure pelo menos 3 nós em zonas distintas (ou 3 AZs) para serviços de nível 1.
- Monitore `kubelet` como DaemonSet e alerte sobre ausência de heartbeat antes do `NotReady` (alertas de `up == 0` chegam antes).
- Automatize substituição de nó com `cluster-autoscaler` em vez de `kubectl delete node` manual.

## Referências

- [Kubernetes: node conditions](https://kubernetes.io/docs/concepts/architecture/nodes/)
- [Kubernetes: node-pressure eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/)
- [Kubernetes: safely drain a node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/)
- [Kubernetes: pod disruption budgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
