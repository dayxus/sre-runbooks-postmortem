"""The runbook lint is the product: a runbook that fails it must fail loudly."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sretriage.runbook_lint import (
    REQUIRED_SECTIONS,
    discover,
    lint_library,
    lint_text,
    parse_front_matter,
    split_sections,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID = """---
id: k8s-crashloopbackoff
title: CrashLoopBackOff em workload de produção
severity: high
services: [kubernetes]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# CrashLoopBackOff em workload de produção

Resposta rápida para pods que reiniciam em laço em um ambiente de laboratório.

## Sintomas

- Pod em `CrashLoopBackOff` com contador de restarts crescendo a cada minuto.
- Erro visível no load balancer apenas nos endpoints dos pods em laço.

## Impacto no SLO

`availability` cai na proporção dos pods que não sobem, queimando error budget.

## Detecção

**Alerta:** `KubePodCrashLooping`

```promql
max_over_time(kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"}[10m]) > 0
```

## Diagnóstico

1. Leia o estado anterior do contêiner para saber por que ele morreu.

   ```bash
   kubectl -n prod describe pod checkout-api-abc123 | sed -n '/Last State/,/Events/p'
   ```

   Esperado: `Reason: OOMKilled`. Tempo: ~20 s.

2. Leia os logs do contêiner anterior, não do atual.

   ```bash
   kubectl -n prod logs checkout-api-abc123 --previous --tail=80
   ```

   Tempo: ~15 s.

## Mitigação

**Risco:** o rollback devolve o código anterior e deixa a migração aplicada.

```bash
kubectl -n prod rollout undo deploy/checkout-api
```

## Escalonamento

- Acione o time de plantão do serviço quando houver usuário afetado.

## Verificação

1. Nenhum pod em laço por dez minutos seguidos.

   ```bash
   kubectl -n prod get pods -l app=checkout-api
   ```

## Prevenção

- Rode a versão nova em canário antes do rollout completo do serviço.

## Referências

- [Kubernetes: determine the reason for pod failure](https://kubernetes.io/docs/tasks/debug/debug-application/determine-reason-pod-failure/)
"""


def _lint(text: str):
    runbook, problems = lint_text("runbooks/kubernetes/probe.md", text)
    return runbook, [problem.message for problem in problems]


def test_valid_runbook_passes() -> None:
    runbook, problems = _lint(VALID)
    assert problems == []
    assert runbook.id == "k8s-crashloopbackoff"
    assert runbook.alert == "KubePodCrashLooping"
    assert runbook.area == "kubernetes"


def test_missing_section_fails() -> None:
    text = VALID.replace("## Prevenção", "## Observações")
    _, problems = _lint(text)
    assert any("missing required sections" in message for message in problems)
    assert any("unexpected sections" in message for message in problems)


def test_sections_out_of_order_fails() -> None:
    text = VALID.replace(
        "## Escalonamento\n\n- Acione o time de plantão do serviço quando houver usuário afetado.\n\n",
        "",
    )
    text = text.replace(
        "## Prevenção",
        "## Escalonamento\n\n- Acione o time de plantão do serviço quando houver usuário afetado.\n\n## Prevenção",
    )
    _, problems = _lint(text)
    assert any("out of order" in message for message in problems)


def test_fenced_block_without_language_fails() -> None:
    text = VALID.replace(
        "```bash\nkubectl -n prod rollout undo deploy/checkout-api\n```",
        "```\nkubectl -n prod rollout undo deploy/checkout-api\n```",
    )
    _, problems = _lint(text)
    assert any("without language" in message for message in problems)


def test_diagnostico_without_numbered_step_fails() -> None:
    text = VALID.replace("1. Leia o estado anterior", "Leia o estado anterior")
    text = text.replace(
        "2. Leia os logs do contêiner anterior, não do atual.",
        "Leia os logs do contêiner anterior, não do atual.",
    )
    _, problems = _lint(text)
    assert any("numbered step" in message for message in problems)


def test_missing_front_matter_fails() -> None:
    _, problems = _lint("# Runbook sem front matter\n\n## Sintomas\n\n- nada\n")
    assert any("missing front matter" in message for message in problems)
    assert any("missing required sections" in message for message in problems)


def test_invalid_date_and_severity_fail() -> None:
    text = VALID.replace("last_reviewed: 2026-09-15", "last_reviewed: 2026/09/15")
    text = text.replace("severity: high", "severity: urgent")
    _, problems = _lint(text)
    assert any("valid YYYY-MM-DD" in message for message in problems)
    assert any("severity" in message for message in problems)


def test_future_reviewed_date_fails() -> None:
    text = VALID.replace("last_reviewed: 2026-09-15", "last_reviewed: 2099-01-01")
    _, problems = _lint(text)
    assert any("in the future" in message for message in problems)


def test_placeholder_token_fails() -> None:
    text = VALID.replace(
        "## Verificação", "## Verificação\n\nTODO: completar esta seção depois do incidente.\n"
    )
    _, problems = _lint(text)
    assert any("placeholder token" in message for message in problems)


def test_mitigacao_without_declared_risk_fails() -> None:
    text = VALID.replace(
        "**Risco:** o rollback devolve o código anterior e deixa a migração aplicada.",
        "Apenas execute o rollback do serviço em produção.",
    )
    _, problems = _lint(text)
    assert any("Risco" in message for message in problems)


def test_escalonamento_without_oncall_fails() -> None:
    text = VALID.replace(
        "- Acione o time de plantão do serviço quando houver usuário afetado.",
        "- Abra um ticket e aguarde a resposta do time responsável pela aplicação.",
    )
    _, problems = _lint(text)
    assert any("plantão" in message for message in problems)


def test_front_matter_parser_reads_inline_lists() -> None:
    meta, body, error = parse_front_matter(VALID)
    assert error is None
    assert meta["services"] == "[kubernetes]"
    assert body.lstrip().startswith("# CrashLoopBackOff")


def test_split_sections_keeps_order() -> None:
    headings, sections = split_sections(VALID)
    assert headings == list(REQUIRED_SECTIONS)
    assert "KubePodCrashLooping" in sections["Detecção"]


def test_library_has_at_least_sixteen_clean_runbooks() -> None:
    runbooks, problems = lint_library(REPO_ROOT / "runbooks", today=date(2026, 9, 15))
    assert problems == []
    assert len(runbooks) >= 16
    assert len({runbook.id for runbook in runbooks}) == len(runbooks)


def test_every_area_from_the_spec_is_present() -> None:
    areas = {path.parent.name for path in discover(REPO_ROOT / "runbooks")}
    assert areas >= {
        "kubernetes",
        "cloud",
        "observability",
        "database",
        "cicd",
        "network",
    }


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    runbook_dir = tmp_path / "runbooks" / "kubernetes"
    runbook_dir.mkdir(parents=True)
    (runbook_dir / "a.md").write_text(VALID, encoding="utf-8")
    (runbook_dir / "b.md").write_text(VALID, encoding="utf-8")
    _, problems = lint_library(tmp_path / "runbooks")
    assert any("duplicate id" in problem.message for problem in problems)
