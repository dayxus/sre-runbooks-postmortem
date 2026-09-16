---
id: cloud-eks-node-degraded
title: Nó gerenciado degradado em cluster Kubernetes gerenciado
severity: high
services: [kubernetes, cloud]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# Nó gerenciado degradado em cluster Kubernetes gerenciado

Um nó de node group gerenciado entra em estado degradado e o autoscaler não
substitui sozinho. A diferença para o runbook de `NotReady` é que aqui existe
uma camada de controle do provedor entre o kubelet e a instância.

## Sintomas

- Node group mostra instância em estado de degradação no painel do provedor.
- `kubectl get nodes` mantém o nó `NotReady` por mais de 10 minutos.
- Eventos do node group repetem falha de `bootstrap` ou de `health check`.
- Novos nós criados pelo autoscaler não conseguem entrar no cluster (`NotReady` imediato).

## Impacto no SLO

O nó degradado deixa de receber pods novos e pode perder os que já roda. Em node
groups pequenos, a capacidade efetiva cai antes de o autoscaler reagir, e o
serviço perde `availability` durante a janela de substituição.

## Detecção

**Alerta:** `ManagedNodeDegraded`

```promql
kube_node_status_condition{condition="Ready", status="true"} == 0
and on(node) time() - kube_node_created > 600
```

Correlação no provedor (usando a AWS CLI como referência; troque `eks` pelo serviço equivalente):

```bash
aws eks describe-nodegroup --cluster-name lab-cluster --nodegroup-name lab-workers --query 'nodegroup.health.issues'
```

## Diagnóstico

1. Identifique o nó e o node group dele.

   ```bash
   kubectl get node ip-10-0-14-23.us-east-1.compute.internal -o jsonpath='{.metadata.labels.eks\.amazonaws\.com/nodegroup}{"\n"}'
   ```

   Tempo: ~10 s.

2. Leia a saúde do node group no provedor.

   ```bash
   aws eks describe-nodegroup --cluster-name lab-cluster --nodegroup-name lab-workers \
     --query 'nodegroup.{status:status,health:health,capacity:scalingConfig}' --output json
   ```

   `health.issues` diz se é problema de daemonset obrigatório, IAM ou capacidade. Tempo: ~15 s.

3. Confirme se é a instância ou o kubelet.

   ```bash
   kubectl describe node ip-10-0-14-23.us-east-1.compute.internal | sed -n '/Conditions:/,/Events:/p'
   ```

   Tempo: ~15 s.

4. Verifique se os daemonsets obrigatórios estão rodando em todos os nós — é a causa mais comum de node group "degraded".

   ```bash
   kubectl -n kube-system get daemonset -o custom-columns=NAME:.metadata.name,DESIRED:.status.desiredNumberScheduled,READY:.status.numberReady
   ```

   Tempo: ~15 s.

5. Veja se o autoscaler está tentando escalar e sendo bloqueado.

   ```bash
   kubectl -n kube-system logs deploy/cluster-autoscaler --tail=150 | grep -Ei 'node group|scale|max size|blocked'
   ```

   Tempo: ~30 s.

6. Cheque se a instância foi trocada pelo provedor mas o cluster ainda guarda o nó antigo.

   ```bash
   kubectl get nodes -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp,PROVIDER:.spec.providerID
   ```

   Nó com `providerID` que não existe mais precisa ser removido do cluster. Tempo: ~10 s.

## Mitigação

**Risco:** forçar remoção do node group (`force`) recria os nós e derruba os pods
deles; a substituição de instância preserva o node group mas depende de o
autoscaler ter capacidade na conta.

1. Aumente o node group em uma unidade e remova o nó degradado depois que o novo estiver `Ready`.

   ```bash
   aws eks update-nodegroup-config --cluster-name lab-cluster --nodegroup-name lab-workers \
     --scaling-config minSize=3,maxSize=8,desiredSize=5
   kubectl get nodes -w
   ```

2. Drene o nó degradado antes de removê-lo do cluster.

   ```bash
   kubectl cordon ip-10-0-14-23.us-east-1.compute.internal
   kubectl drain ip-10-0-14-23.us-east-1.compute.internal --ignore-daemonsets --delete-emptydir-data --timeout=180s
   ```

3. Nó fantasma (instância já substituída): remova apenas o objeto do cluster.

   ```bash
   kubectl delete node ip-10-0-14-23.us-east-1.compute.internal
   ```

4. Daemonset obrigatório com poucas réplicas saudáveis é bloqueio do próprio provedor; recrie para destravar o health check.

   ```bash
   kubectl -n kube-system rollout restart daemonset/aws-node
   kubectl -n kube-system rollout status daemonset/aws-node --timeout=180s
   ```

## Escalonamento

- Acione o time de plantão de plataforma sempre: a causa está na camada de node group do cluster.
- Acione o time de plantão do serviço se o drain estiver derrubando réplicas com PDB apertado.
- Abra caso no provedor de nuvem quando a instância não passar do bootstrap e a mensagem indicar falha da camada de controle.

## Verificação

1. O node group não tem mais issues e todos os nós estão `Ready`.

   ```bash
   aws eks describe-nodegroup --cluster-name lab-cluster --nodegroup-name lab-workers --query 'nodegroup.health'
   kubectl get nodes
   ```

2. Daemonsets obrigatórios com `DESIRED == READY` em todos os nós.

   ```bash
   kubectl -n kube-system get daemonset -o custom-columns=NAME:.metadata.name,DESIRED:.status.desiredNumberScheduled,READY:.status.numberReady
   ```

3. Capacidade do cluster voltou ao patamar anterior e nenhum pod ficou `Unknown`.

## Prevenção

- Rode daemonsets obrigatórios com `updateStrategy: RollingUpdate` e monitore `numberUnavailable`.
- Use múltiplas AZs no node group e `topologySpreadConstraints` nos workloads.
- Alerte sobre `node_group_health_issues > 0`, não apenas sobre nós `NotReady`: o provedor avisa antes.
- Mantenha `minSize` do node group acima do mínimo necessário para sobreviver à perda de uma AZ.

## Referências

- [Kubernetes: nodes](https://kubernetes.io/docs/concepts/architecture/nodes/)
- [Kubernetes: safely drain a node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/)
- [Kubernetes: DaemonSet](https://kubernetes.io/docs/concepts/workloads/controllers/daemonset/)
- [Kubernetes: cluster autoscaling](https://kubernetes.io/docs/concepts/cluster-administration/cluster-autoscaling/)
