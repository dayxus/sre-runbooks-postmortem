# Auditoria de links externos

- Executado em: 2026-09-21 12:57:07 (UTC)
- Arquivos varridos: 26
- URLs únicas verificadas: 55
- URLs mortas: 0
- User-Agent: `sretriage-link-audit/0.1 (+https://github.com/dayxus/sre-runbooks-postmortem)`

| URL | Status | Método/Erro | Arquivos |
| --- | --- | --- | --- |
| https://cli.github.com/manual/gh_run | 200 | HEAD | runbooks/cicd/pipeline-flaky.md |
| https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html | 200 | HEAD | runbooks/cloud/rds-connection-exhaustion.md |
| https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.html | 200 | HEAD | runbooks/database/replication-lag.md |
| https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html | 200 | HEAD | runbooks/cloud/s3-throttling.md |
| https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html | 200 | HEAD | runbooks/cloud/s3-throttling.md |
| https://docs.aws.amazon.com/AmazonS3/latest/userguide/request-rate-perf-considerations.html | 200 | HEAD | runbooks/cloud/s3-throttling.md |
| https://docs.aws.amazon.com/cli/latest/reference/rds/ | 200 | HEAD | runbooks/cloud/rds-connection-exhaustion.md, runbooks/database/replication-lag.md |
| https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html | 200 | HEAD | runbooks/cloud/s3-throttling.md |
| https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax | 200 | HEAD | runbooks/cicd/pipeline-flaky.md |
| https://docs.openssl.org/3.0/man1/openssl-s_client/ | 200 | HEAD | runbooks/network/tls-cert-expiry.md |
| https://github.com/dayxus | 200 | HEAD | README.md, README.pt-BR.md |
| https://github.com/dayxus/sre-runbooks-postmortem/actions/workflows/ci.yml/badge.svg | 200 | HEAD | README.md, README.pt-BR.md |
| https://img.shields.io/badge/license-MIT-blue.svg | 200 | HEAD | README.md, README.pt-BR.md |
| https://img.shields.io/badge/python-3.9%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg | 200 | HEAD | README.md, README.pt-BR.md |
| https://kubernetes.io/docs/concepts/architecture/nodes/ | 200 | HEAD | runbooks/cloud/eks-node-degraded.md, runbooks/kubernetes/node-notready.md, runbooks/kubernetes/pending-pods.md |
| https://kubernetes.io/docs/concepts/cluster-administration/cluster-autoscaling/ | 200 | HEAD | runbooks/cloud/eks-node-degraded.md |
| https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/ | 200 | HEAD | runbooks/kubernetes/crashloopbackoff.md, runbooks/kubernetes/oomkilled.md |
| https://kubernetes.io/docs/concepts/policy/resource-quotas/ | 200 | HEAD | runbooks/kubernetes/pending-pods.md |
| https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/ | 200 | HEAD | runbooks/kubernetes/pending-pods.md |
| https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/ | 200 | HEAD | runbooks/kubernetes/node-notready.md, runbooks/kubernetes/oomkilled.md |
| https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/ | 200 | HEAD | runbooks/network/dns-failure.md |
| https://kubernetes.io/docs/concepts/services-networking/ingress/ | 200 | HEAD | runbooks/network/tls-cert-expiry.md |
| https://kubernetes.io/docs/concepts/workloads/controllers/daemonset/ | 200 | HEAD | runbooks/cloud/eks-node-degraded.md |
| https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ | 200 | HEAD | runbooks/cicd/deploy-rollback.md |
| https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/ | 200 | HEAD | runbooks/network/dns-failure.md |
| https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/ | 200 | HEAD | runbooks/cloud/eks-node-degraded.md, runbooks/kubernetes/node-notready.md |
| https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/ | 200 | HEAD | runbooks/kubernetes/oomkilled.md |
| https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/ | 200 | HEAD | runbooks/kubernetes/crashloopbackoff.md |
| https://kubernetes.io/docs/tasks/debug/debug-application/determine-reason-pod-failure/ | 200 | HEAD | runbooks/kubernetes/crashloopbackoff.md |
| https://kubernetes.io/docs/tasks/run-application/configure-pdb/ | 200 | HEAD | runbooks/kubernetes/node-notready.md, runbooks/kubernetes/pending-pods.md |
| https://kubernetes.io/docs/tutorials/kubernetes-basics/update/update-intro/ | 200 | HEAD | runbooks/cicd/deploy-rollback.md |
| https://man7.org/linux/man-pages/man5/resolv.conf.5.html | 200 | HEAD | runbooks/network/dns-failure.md |
| https://martinfowler.com/articles/continuousIntegration.html | 200 | HEAD | runbooks/cicd/pipeline-flaky.md |
| https://prometheus.io/docs/practices/alerting/ | 200 | HEAD | runbooks/observability/alert-fatigue.md, runbooks/observability/missing-metrics.md |
| https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/ | 200 | HEAD | runbooks/observability/alert-fatigue.md |
| https://prometheus.io/docs/prometheus/latest/configuration/configuration/ | 200 | HEAD | runbooks/observability/missing-metrics.md |
| https://prometheus.io/docs/prometheus/latest/querying/basics/ | 200 | HEAD | runbooks/observability/missing-metrics.md, runbooks/observability/silent-failure.md |
| https://prometheus.io/docs/prometheus/latest/querying/functions/ | 200 | HEAD | runbooks/kubernetes/oomkilled.md |
| https://sre.google/sre-book/being-on-call/ | 200 | HEAD | runbooks/observability/alert-fatigue.md |
| https://sre.google/sre-book/example-postmortem/ | 200 | HEAD | docs/postmortem-guide.md, templates/postmortem.md |
| https://sre.google/sre-book/monitoring-distributed-systems/ | 200 | HEAD | runbooks/kubernetes/crashloopbackoff.md, runbooks/observability/silent-failure.md |
| https://sre.google/sre-book/postmortem-culture/ | 200 | HEAD | docs/postmortem-guide.md, runbooks/cicd/deploy-rollback.md, runbooks/observability/silent-failure.md, templates/postmortem.md |
| https://sre.google/sre-book/testing-reliability/ | 200 | HEAD | runbooks/cicd/pipeline-flaky.md |
| https://sre.google/workbook/alerting-on-slos/ | 200 | HEAD | runbooks/database/connection-pool-saturation.md, runbooks/observability/alert-fatigue.md, runbooks/observability/missing-metrics.md, runbooks/observability/silent-failure.md |
| https://sre.google/workbook/canarying-releases/ | 200 | HEAD | runbooks/cicd/deploy-rollback.md |
| https://sre.google/workbook/postmortem-culture/ | 200 | HEAD | docs/postmortem-guide.md, templates/postmortem.md |
| https://www.iana.org/domains/root/servers | 200 | HEAD | runbooks/network/dns-failure.md |
| https://www.postgresql.org/docs/current/libpq-connect.html | 200 | HEAD | runbooks/database/connection-pool-saturation.md |
| https://www.postgresql.org/docs/current/monitoring-stats.html | 200 | HEAD | runbooks/cloud/rds-connection-exhaustion.md, runbooks/database/replication-lag.md |
| https://www.postgresql.org/docs/current/runtime-config-connection.html | 200 | HEAD | runbooks/cloud/rds-connection-exhaustion.md, runbooks/database/connection-pool-saturation.md |
| https://www.postgresql.org/docs/current/runtime-config-resource.html | 200 | HEAD | runbooks/database/connection-pool-saturation.md |
| https://www.postgresql.org/docs/current/warm-standby.html | 200 | HEAD | runbooks/database/replication-lag.md |
| https://www.rfc-editor.org/rfc/rfc1035 | 200 | HEAD | runbooks/network/dns-failure.md |
| https://www.rfc-editor.org/rfc/rfc6797 | 200 | HEAD | runbooks/network/tls-cert-expiry.md |
| https://www.rfc-editor.org/rfc/rfc8446 | 200 | HEAD | runbooks/network/tls-cert-expiry.md |

Nenhum link morto encontrado.

## URLs repetidas em vários arquivos

- `https://docs.aws.amazon.com/cli/latest/reference/rds/` (2 arquivos)
- `https://github.com/dayxus` (2 arquivos)
- `https://github.com/dayxus/sre-runbooks-postmortem/actions/workflows/ci.yml/badge.svg` (2 arquivos)
- `https://img.shields.io/badge/license-MIT-blue.svg` (2 arquivos)
- `https://img.shields.io/badge/python-3.9%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg` (2 arquivos)
- `https://kubernetes.io/docs/concepts/architecture/nodes/` (3 arquivos)
- `https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/` (2 arquivos)
- `https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/` (2 arquivos)
- `https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/` (2 arquivos)
- `https://kubernetes.io/docs/tasks/run-application/configure-pdb/` (2 arquivos)
- `https://prometheus.io/docs/practices/alerting/` (2 arquivos)
- `https://prometheus.io/docs/prometheus/latest/querying/basics/` (2 arquivos)
- `https://sre.google/sre-book/example-postmortem/` (2 arquivos)
- `https://sre.google/sre-book/monitoring-distributed-systems/` (2 arquivos)
- `https://sre.google/sre-book/postmortem-culture/` (4 arquivos)
- `https://sre.google/workbook/alerting-on-slos/` (4 arquivos)
- `https://sre.google/workbook/postmortem-culture/` (2 arquivos)
- `https://www.postgresql.org/docs/current/monitoring-stats.html` (2 arquivos)
- `https://www.postgresql.org/docs/current/runtime-config-connection.html` (2 arquivos)
