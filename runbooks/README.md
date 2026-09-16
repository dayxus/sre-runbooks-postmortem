# Índice de runbooks

Tabela gerada por `python3 -m sretriage index` a partir do front matter e da
seção `Detecção` de cada runbook. Não edite a tabela à mão: `sretriage index
--check` falha no CI quando ela diverge dos runbooks.

<!-- BEGIN GENERATED INDEX -->
| Área | Sintoma | Runbook | Alerta que dispara | SLO impactado |
| --- | --- | --- | --- | --- |
| cicd | Deploy com degradação e decisão de rollback | `cicd-deploy-rollback` → [cicd/deploy-rollback.md](cicd/deploy-rollback.md) | `DeployRegression` | availability |
| cicd | Pipeline de CI instável com falhas intermitentes | `cicd-pipeline-flaky` → [cicd/pipeline-flaky.md](cicd/pipeline-flaky.md) | `PipelineFlakeRate` | throughput |
| cloud | Nó gerenciado degradado em cluster Kubernetes gerenciado | `cloud-eks-node-degraded` → [cloud/eks-node-degraded.md](cloud/eks-node-degraded.md) | `ManagedNodeDegraded` | availability |
| cloud | Esgotamento de conexões em banco relacional gerenciado | `cloud-rds-connection-exhaustion` → [cloud/rds-connection-exhaustion.md](cloud/rds-connection-exhaustion.md) | `DatabaseConnectionSaturation` | error-rate |
| cloud | Throttling de object storage em picos de acesso | `cloud-s3-throttling` → [cloud/s3-throttling.md](cloud/s3-throttling.md) | `ObjectStorageSlowDown` | latency |
| database | Saturação do pool de conexões da aplicação | `db-connection-pool-saturation` → [database/connection-pool-saturation.md](database/connection-pool-saturation.md) | `PoolSaturation` | latency |
| database | Replication lag crescente entre primário e réplicas | `db-replication-lag` → [database/replication-lag.md](database/replication-lag.md) | `ReplicationLagHigh` | freshness |
| kubernetes | CrashLoopBackOff em workload de produção | `k8s-crashloopbackoff` → [kubernetes/crashloopbackoff.md](kubernetes/crashloopbackoff.md) | `KubePodCrashLooping` | availability |
| kubernetes | Node NotReady com workloads em risco | `k8s-node-notready` → [kubernetes/node-notready.md](kubernetes/node-notready.md) | `KubeNodeNotReady` | availability |
| kubernetes | Contêiner morto por OOMKilled em produção | `k8s-oomkilled` → [kubernetes/oomkilled.md](kubernetes/oomkilled.md) | `ContainerOOMKilled` | availability |
| kubernetes | Pods em Pending por tempo indefinido | `k8s-pending-pods` → [kubernetes/pending-pods.md](kubernetes/pending-pods.md) | `KubePodPendingTooLong` | availability |
| network | Falha de resolução DNS com impacto em cascata | `net-dns-failure` → [network/dns-failure.md](network/dns-failure.md) | `DNSResolutionFailureRate` | availability |
| network | Certificado TLS próximo do vencimento ou expirado | `net-tls-cert-expiry` → [network/tls-cert-expiry.md](network/tls-cert-expiry.md) | `TLSCertificateExpiringSoon` | availability |
| observability | Fadiga de alertas com ruído acima do sinal | `obs-alert-fatigue` → [observability/alert-fatigue.md](observability/alert-fatigue.md) | `AlertNoiseRatio` | cost |
| observability | Métricas ausentes para um serviço ativo | `obs-missing-metrics` → [observability/missing-metrics.md](observability/missing-metrics.md) | `ScrapeTargetDown` | freshness |
| observability | Falha silenciosa sem alerta nem erro visível | `obs-silent-failure` → [observability/silent-failure.md](observability/silent-failure.md) | `BusinessKpiStalled` | error-rate |

_16 runbooks, all of them lint-clean._
<!-- END GENERATED INDEX -->

## Como usar

1. Encontre o sintoma mais próximo do que você está vendo (a coluna _Sintoma_ é o
   `id` do runbook, e o link leva ao runbook completo).
2. Rode `python3 -m sretriage run --target <url do serviço> --out reports/` para
   produzir evidência antes de mudar qualquer coisa.
3. Siga o `## Diagnóstico` na ordem: cada passo tem comando copiável e tempo esperado.
4. Declare o `Risco` da mitigação para quem está no canal de incidente.
5. Depois de resolver, use `templates/postmortem.md` e registre action items com dono e prazo.

## Áreas

- `kubernetes/` — pods, nodes e agendamento.
- `cloud/` — recursos gerenciados pelo provedor (nodes, object storage, banco gerenciado).
- `observability/` — métricas ausentes, ruído de alerta e falha silenciosa.
- `database/` — replicação e pools de conexão.
- `cicd/` — pipeline instável e decisão de rollback.
- `network/` — DNS e certificados TLS.

## Escrevendo um runbook novo

Use `templates/runbook-template.md`, coloque o arquivo no diretório da área e
rode:

```bash
python3 -m sretriage check-runbooks
python3 -m sretriage index
```

O lint rejeita seção ausente, seção fora de ordem, bloco de código sem
linguagem, `Diagnóstico` sem passo numerado, `Mitigação` sem risco declarado,
`Escalonamento` sem plantão, data inválida e link relativo quebrado.
