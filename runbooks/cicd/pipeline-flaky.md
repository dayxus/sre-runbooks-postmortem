---
id: cicd-pipeline-flaky
title: Pipeline de CI instável com falhas intermitentes
severity: medium
services: [cicd]
slo_impact: throughput
last_reviewed: 2026-09-15
owner: developer-experience
---

# Pipeline de CI instável com falhas intermitentes

O pipeline falha em execuções idênticas. O custo real não é o tempo de reexecução:
é a perda de confiança que leva o time a ignorar a vermelha e mergear mesmo assim.

## Sintomas

- Mesmo commit falha e passa sem alteração de código.
- Falha concentrada em poucos jobs (teste de integração, snapshot, e2e).
- Reexecução manual "resolve" e ninguém investiga.
- Tempo médio de fila do pipeline cresce por causa das reexecuções.

## Impacto no SLO

`throughput` de entrega cai: cada falha instável bloqueia merge e atrasa o
caminho de correção de incidente (é comum precisar de um hotfix durante o
incidente e ficar preso na pipeline). Também empurra o time para bypass manual,
que reduz a cobertura de verificação.

## Detecção

**Alerta:** `PipelineFlakeRate`

```promql
sum(rate(ci_pipeline_failures_total{retried="true"}[24h]))
  / sum(rate(ci_pipeline_runs_total[24h])) > 0.05
```

**Alerta:** `JobIntermittentFailures`

```promql
topk(5, sum by (job_name) (increase(ci_job_failures_total{retried="true"}[7d])))
```

## Diagnóstico

1. Identifique quais jobs concentram as falhas intermitentes.

   ```bash
   gh run list --repo dayxus/sre-runbooks-postmortem --limit 50 --json name,conclusion,createdAt,url \
     --jq '.[] | select(.conclusion=="failure") | .name' | sort | uniq -c | sort -rn
   ```

   Tempo: ~30 s.

2. Compare duas execuções do mesmo commit e veja o que difere.

   ```bash
   gh run view <run-id-verde> --log-failed | tail -40
   gh run view <run-id-vermelho> --log-failed | tail -40
   ```

   Tempo: ~2 min.

3. Verifique dependências externas não determinísticas no job (rede, registry, serviço de terceiros).

   ```bash
   grep -RniE 'curl|wget|docker pull|npm install|pip install' .github/workflows | head -20
   ```

   Download sem versão fixa é a causa mais comum. Tempo: ~5 s.

4. Cheque tempo limite e concorrência: job que estoura o timeout às vezes é flake aparente.

   ```bash
   grep -RniE 'timeout-minutes|concurrency|strategy|fail-fast' .github/workflows | head -30
   ```

   Tempo: ~5 s.

5. Procure estado compartilhado entre execuções paralelas (porta fixa, banco comum, diretório temporário).

   ```bash
   grep -RniE 'localhost:[0-9]{2,5}|/tmp/[a-z]' tests .github/workflows 2>/dev/null | head -20
   ```

   Tempo: ~10 s.

6. Meça a taxa de flake por job com dado, não com impressão.

   ```bash
   gh api -X GET 'repos/dayxus/sre-runbooks-postmortem/actions/runs?per_page=100' \
     --jq '[.workflow_runs[] | {name: .name, conclusion: .conclusion, attempt: .run_attempt}] | group_by(.name) | map({name: .[0].name, retries: (map(select(.attempt > 1)) | length), total: length})'
   ```

   Tempo: ~30 s.

## Mitigação

**Risco:** quarentenar teste reduz sinal de verificação; exige prazo e
responsável, senão vira teste desligado para sempre.

1. Fixe as versões de toda dependência externa baixada no pipeline.

   ```bash
   grep -Rn "uses:" .github/workflows | grep -v "@v[0-9]" || echo "all actions are pinned"
   ```

2. Isole o serviço de teste em porta efêmera para eliminar colisão entre execuções paralelas.

   ```bash
   sed -i.bak 's/port=8080/port=0/' tests/conftest.py && grep -n 'port=0' tests/conftest.py
   ```

3. Aumente o timeout do job que estoura por contenção do runner, mantendo o teto.

   ```bash
   grep -n "timeout-minutes" .github/workflows/*.yml
   ```

4. Quarentene o teste instável com prazo explícito, registrando o chamado.

   ```bash
   pytest -q -m "not quarantine"
   ```

5. Repita o job instável com retry controlado apenas durante a investigação (não como solução permanente).

   ```bash
   gh run rerun <run-id> --failed
   ```

## Escalonamento

- Acione o time de plantão de developer experience quando a instabilidade for do runner ou da infraestrutura de CI.
- Acione o time de plantão do serviço quando o teste instável for do próprio código.
- Suba para o dono da trilha de entrega se a pipeline estiver bloqueando correção de incidente.

## Verificação

1. A taxa de flake medida cai e se mantém abaixo de 2% em 10 execuções consecutivas do mesmo commit.

   ```bash
   gh run list --repo dayxus/sre-runbooks-postmortem --limit 10 --json conclusion --jq 'map(.conclusion) | group_by(.) | map({k: .[0], n: length})'
   ```

2. O job corrigido não depende mais de recurso externo sem versão fixa.

   ```bash
   grep -RnE 'curl -[^ ]* https://[^ ]+ \| *(bash|sh)' .github/workflows || echo "no unversioned remote scripts executed"
   ```

3. Um merge real passou pela pipeline sem reexecução depois da correção.

## Prevenção

- Fixe imagens por digest e actions por tag imutável.
- Trate flake como bug com dono e métrica; meça retry rate por job semanalmente.
- Proíba `retry` automático sem registro — retry que esconde a causa é dívida técnica.
- Mantenha a suíte determinística: relógio injetado, porta efêmera, ordem independente.

## Referências

- [GitHub Actions: workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub CLI: run commands](https://cli.github.com/manual/gh_run)
- [Martin Fowler: continuous integration](https://martinfowler.com/articles/continuousIntegration.html)
- [Google SRE Book: testing for reliability](https://sre.google/sre-book/testing-reliability/)
