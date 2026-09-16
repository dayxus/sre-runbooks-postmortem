---
id: net-dns-failure
title: Falha de resolução DNS com impacto em cascata
severity: critical
services: [network, kubernetes]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# Falha de resolução DNS com impacto em cascata

`no such host` aparece em vários serviços ao mesmo tempo e o sintoma parece
"aplicação quebrada". Na prática, todo serviço que depende de nome falha junto —
a investigação começa no resolvedor, não no código.

## Sintomas

- Logs de múltiplos serviços com `no such host`, `SERVFAIL` ou `Temporary failure in name resolution`.
- Latência de requisições entre serviços sobe muito e depois vira erro.
- Pods novos não inicializam porque não resolvem dependências de bootstrap.
- Cache de DNS expirado é a fronteira do incidente: falhas começam depois do TTL.

## Impacto no SLO

`availability` cai rápido e de forma ampla: serviços saudáveis passam a falhar
por não conseguir falar com dependências. A duração costuma ser limitada pelo
TTL do cache, o que faz o incidente parecer intermitente enquanto os caches se misturam.

## Detecção

**Alerta:** `DNSResolutionFailureRate`

```promql
sum(rate(dns_queries_total{rcode="SERVFAIL"}[5m])) / sum(rate(dns_queries_total[5m])) > 0.05
```

**Alerta:** `DNSServfailSpike`

```promql
increase(coredns_panics_total[10m]) > 0
```

## Diagnóstico

1. Reproduza a falha de dentro de um pod, não da sua máquina: o caminho é diferente.

   ```bash
   kubectl -n prod run dns-probe --rm -it --restart=Never --image=busybox:1.36 -- nslookup checkout-api.prod.svc.cluster.local
   ```

   Tempo: ~30 s.

2. Verifique o `resolv.conf` do pod (search domains e `ndots` mudam o resultado).

   ```bash
   kubectl -n prod exec deploy/checkout-api -- cat /etc/resolv.conf
   ```

   Tempo: ~10 s.

3. Teste o resolvedor do cluster diretamente e compare com um resolvedor público.

   ```bash
   dig @192.0.2.53 checkout-api.prod.svc.cluster.local +short
   dig @1.1.1.1 example.org +short
   ```

   Sucesso no público com falha no interno isola o problema no resolvedor do cluster. Tempo: ~15 s.

4. Suba a cadeia até a autoridade com `+trace` quando o nome for externo.

   ```bash
   dig +trace api.lab.internal | tail -20
   ```

   Tempo: ~30 s.

5. Cheque a saúde dos pods do resolvedor e a taxa de erro deles.

   ```bash
   kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide
   kubectl -n kube-system logs -l k8s-app=kube-dns --tail=100 | grep -Ei 'error|timeout|SERVFAIL|refused' | tail -20
   ```

   Tempo: ~30 s.

6. Verifique limites de conntrack e de configuração de DNS no kubelet (causa clássica em clusters grandes).

   ```bash
   kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}{"\n"}'
   sysctl net.netfilter.nf_conntrack_count net.netfilter.nf_conntrack_max
   ```

   Tempo: ~20 s.

## Mitigação

**Risco:** reiniciar o resolvedor do cluster derruba a resolução por segundos;
escamar mais réplicas de DNS ajuda sem risco, mas não resolve problemas de
conntrack ou de Corefile mal configurado.

1. Escame o resolvedor do cluster para absorver o pico (ação de baixo risco).

   ```bash
   kubectl -n kube-system scale deploy coredns --replicas=5
   kubectl -n kube-system rollout status deploy/coredns --timeout=120s
   ```

2. Reduza a pressão no resolvedor aplicando cache local nos clientes que mais consultam.

   ```bash
   kubectl -n prod patch deploy checkout-api --type=strategic -p '{"spec":{"template":{"spec":{"dnsConfig":{"options":[{"name":"ndots","value":"2"}]}}}}}'
   ```

3. Reinicie pods presos com `ndots` errado para forçar novo `resolv.conf`.

   ```bash
   kubectl -n prod rollout restart deploy/checkout-api
   ```

4. Aumente conntrack quando o gargalo for tabela cheia (e volte com mudança permanente depois).

   ```bash
   sysctl -w net.netfilter.nf_conntrack_max=262144
   ```

5. Verifique o registro e o TTL na zona autoritativa antes de concluir que é o resolvedor.

   ```bash
   dig api.lab.internal @ns1.lab.internal +norecurse
   ```

## Escalonamento

- Acione o time de plantão de plataforma imediatamente: DNS do cluster é infraestrutura compartilhada.
- Acione o time de plantão do serviço se a falha for de um nome específico do serviço (registro, label de Service ou selector errado).
- Suba para o time de redes quando envolver zona autoritativa, VPC resolver ou transit gateway.

## Verificação

1. A resolução funciona de dentro de um pod para todos os nomes críticos.

   ```bash
   kubectl -n prod run dns-probe --rm -it --restart=Never --image=busybox:1.36 -- sh -c 'for h in checkout-api payments-worker lab-orders-db; do nslookup $h.prod.svc.cluster.local; done'
   ```

2. Taxa de `SERVFAIL` volta a zero por 15 minutos.

   ```promql
   sum(rate(dns_queries_total{rcode="SERVFAIL"}[5m]))
   ```

3. Serviços que falharam por resolução voltaram a responder no caminho crítico.

## Prevenção

- Monitore o resolvedor do cluster como SLO próprio, com alerta em `SERVFAIL` e latência p99.
- Prefira nomes de Service com `ndots` explícito no workload e evite nomes externos sem FQDN com ponto final.
- Evite reiniciar tudo ao mesmo tempo: rajada de DNS após restart em massa derruba o resolvedor.
- Dimensione réplicas de DNS por QPS observado e mantenha cache de sucesso curto e previsível.

## Referências

- [RFC 1035: domain names, implementation and specification](https://www.rfc-editor.org/rfc/rfc1035)
- [Kubernetes: DNS for services and pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
- [Kubernetes: debugging DNS resolution](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/)
- [IANA: DNS root servers](https://www.iana.org/domains/root/servers)
- [resolv.conf(5): resolver configuration file](https://man7.org/linux/man-pages/man5/resolv.conf.5.html)
