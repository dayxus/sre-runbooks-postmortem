---
id: k8s-oomkilled
title: Contêiner morto por OOMKilled em produção
severity: high
services: [kubernetes]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# Contêiner morto por OOMKilled em produção

O kernel mata o processo porque o cgroup estourou o limite. A resposta errada é
dobrar o limite sem olhar o padrão de consumo: sem entender se o crescimento é
por vazamento, por cache ou por carga, o problema volta maior.

## Sintomas

- `restartCount` cresce em pods específicos, sempre no mesmo pico de tráfego.
- `Last State: Terminated`, `Reason: OOMKilled`, com exit code 137.
- latência em p95 sobe antes do restart (pressão de memória, swap e GC agressivo).
- O nó pode registrar `MemoryPressure = True` se vários pods estouram ao mesmo tempo.

## Impacto no SLO

Cada OOMKilled remove uma réplica do balanceamento e provoca uma rajada de erros
durante o restart. Em serviços com poucas réplicas, o `error-rate` sobe junto com o
restart; em serviços com cache local, o efeito se estende além do restart porque
o cache precisa ser reconstruído.

## Detecção

**Alerta:** `ContainerOOMKilled`

```promql
increase(kube_pod_container_status_restarts_total{namespace="prod"}[30m]) > 0
and on(namespace, pod, container)
max_over_time(kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}[30m]) == 1
```

Gráfico de apoio para ver o crescimento antes do limite:

```promql
max by (pod) (container_memory_working_set_bytes{namespace="prod", container!=""})
```

## Diagnóstico

1. Confirme o OOM e o horário, não apenas o restart.

   ```bash
   kubectl -n prod get pod checkout-api-7d9c8f6b5-x4ltq -o jsonpath='{.status.containerStatuses[*].restartCount}{" "}{.status.containerStatuses[*].lastState.terminated.finishedAt}{"\n"}'
   ```

   Tempo: ~10 s.

2. Compare working set com o limite declarado.

   ```bash
   kubectl -n prod get pod checkout-api-7d9c8f6b5-x4ltq -o jsonpath='{.spec.containers[*].resources}{"\n"}'
   kubectl -n prod top pod -l app=checkout-api --containers --sort-by=memory
   ```

   Se o working set no pico está a menos de 10% do limite, o limite é o gargalo. Tempo: ~20 s.

3. Descubra se o consumo é proporcional à carga (cresce com RPS) ou monotônico (vazamento).

   ```bash
   kubectl -n prod top pod -l app=checkout-api --containers
   sleep 300
   kubectl -n prod top pod -l app=checkout-api --containers
   ```

   Crescimento com RPS estável indica vazamento ou cache sem limite. Tempo: ~6 min.

4. Levante os parâmetros de memória da runtime no manifesto.

   ```bash
   kubectl -n prod get deploy checkout-api -o jsonpath='{.spec.template.spec.containers[0].env}' | tr ',' '\n' | grep -Ei 'MEMORY|JAVA_OPTS|GOMEMLIMIT|NODE_OPTIONS'
   ```

   Runtime com heap fixo maior que o limite do cgroup garante OOM. Tempo: ~10 s.

5. Verifique se o vazamento vem de um endpoint ou job específico nos logs.

   ```bash
   kubectl -n prod logs deploy/checkout-api --tail=500 | grep -Ei 'cache|grow|allocat|leak|retry' | tail -20
   ```

   Tempo: ~20 s.

6. Cheque se o kubelet está sob pressão de memória (afeta todos os pods do nó).

   ```bash
   kubectl describe node $(kubectl -n prod get pod checkout-api-7d9c8f6b5-x4ltq -o jsonpath='{.spec.nodeName}') | sed -n '/Conditions:/,/Events:/p'
   ```

   Tempo: ~15 s.

## Mitigação

**Risco:** aumentar o limite dá folga imediata mas também depende da capacidade do
nó; se o node estiver com `MemoryPressure`, o pod pode voltar a ser morto mesmo
abaixo do próprio limite.

1. Reduza o heap da aplicação para caber no limite atual quando o parâmetro estiver errado.

   ```bash
   kubectl -n prod set env deploy/checkout-api JAVA_OPTS="-Xmx768m -XX:MaxRAMPercentage=75"
   ```

2. Aumente o limite para o valor medido no pico mais 30% de folga (não para um valor redondo arbitrário).

   ```bash
   kubectl -n prod patch deploy/checkout-api --type=strategic -p '{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"limits":{"memory":"1500Mi"},"requests":{"memory":"1Gi"}}}]}}}}'
   ```

3. Se o pico é sazonal e passa logo, reduza a pressão tirando o pod do balanceamento antes que o kernel decida por você.

   ```bash
   kubectl -n prod scale deploy/checkout-api --replicas=10
   ```

4. Vazamento confirmado: reinicie de forma escalonada como contenção e abra trabalho de correção.

   ```bash
   kubectl -n prod rollout restart deploy/checkout-api
   kubectl -n prod rollout status deploy/checkout-api --timeout=180s
   ```

## Escalonamento

- Acione o time de plantão do serviço quando o OOM for específico de um serviço e recorrente.
- Acione o time de plantão de plataforma quando o nó inteiro estiver sob `MemoryPressure` ou o limite de nó for o gargalo.
- Acione o time de desenvolvimento do serviço quando houver vazamento confirmado (o fix não é operacional).

## Verificação

1. `restartCount` estável por pelo menos 30 minutos após a mudança.

   ```bash
   kubectl -n prod get pods -l app=checkout-api -o custom-columns=NAME:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,AGE:.metadata.creationTimestamp
   ```

2. Working set permanece abaixo do limite com margem durante um pico real.

   ```bash
   kubectl -n prod top pod -l app=checkout-api --containers --sort-by=memory
   ```

3. O gráfico de `container_memory_working_set_bytes` mostra platô, não rampa, depois da mitigação.

## Prevenção

- Ajuste `requests` pela mediana e `limits` pelo pico medido; meça o pico em produção, não em teste de carga sintético pequeno.
- Limite caches internos (`maxsize`, TTL) — cache sem teto é vazamento com nome bonito.
- Configure `MaxRAMPercentage`/`GOMEMLIMIT` alinhado ao limite do cgroup.
- Alerte sobre `working set / limit > 0.85` por 15 minutos antes que o kernel precise agir.

## Referências

- [Kubernetes: managing resources for containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Kubernetes: node-pressure eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/)
- [Kubernetes: assigning memory resources](https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/)
- [Prometheus: query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
