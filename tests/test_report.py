"""The rendered report must carry the verdict, the evidence and the runbook links."""

from __future__ import annotations

from datetime import datetime, timezone

from sretriage.checks.base import CheckResult, Context
from sretriage.report import default_report_name, render, summarize, verdict


def _results() -> list:
    return [
        CheckResult(
            name="http",
            status="FAIL",
            summary="https://api.probe/ -> 500 in 812 ms",
            evidence=["GET https://api.probe/ -> 500", "ttfb=800.0 ms total=812.0 ms bytes=21 redirects=0"],
            runbook="observability/silent-failure.md",
            next_steps=["Read the served 5xx rate next to deploy timestamps."],
            duration_ms=812,
            targeted=True,
        ),
        CheckResult(
            name="disk",
            status="OK",
            summary="/ at 41.0% (worst of space/inodes)",
            evidence=["/ total=460.4 GiB used=188.8 GiB free=271.6 GiB (41.0%)"],
            runbook="kubernetes/node-notready.md",
            duration_ms=3,
        ),
    ]


def test_report_contains_verdict_and_evidence() -> None:
    ctx = Context(targets=["https://api.probe/"], target_hosts=["api.probe"], timeout=5.0)
    text = render(_results(), ctx, targeted_ok=True)
    assert "**VEREDITO: DEGRADADO**" in text
    assert "| http | FAIL |" in text
    assert "| disk | OK |" in text
    assert "ttfb=800.0 ms total=812.0 ms bytes=21 redirects=0" in text
    assert "## Evidências" in text
    assert "## Próximos passos sugeridos" in text
    assert "../runbooks/observability/silent-failure.md" in text
    assert "OK=1 WARN=0 FAIL=1 SKIPPED=0" in text


def test_report_without_target_marks_no_data() -> None:
    ctx = Context(targets=["https://api.probe/"], timeout=1.0)
    results = [
        CheckResult(name="http", status="SKIPPED", summary="unreachable", targeted=True),
    ]
    text = render(results, ctx, targeted_ok=False)
    assert "SEM ALVO AVALIÁVEL" in text
    assert "Nada a fazer" not in text  # a skipped target still needs a next step


def test_verdict_helper() -> None:
    assert verdict([], targeted_ok=False) == "SEM ALVO AVALIÁVEL"
    assert verdict(_results(), targeted_ok=True) == "DEGRADADO"
    assert verdict([CheckResult(name="disk", status="WARN", summary="x")], targeted_ok=True) == "ATENÇÃO"
    assert verdict([CheckResult(name="disk", status="OK", summary="x")], targeted_ok=True) == "SAUDÁVEL"


def test_summarize_counts_every_status() -> None:
    counts = summarize(_results())
    assert counts == {"OK": 1, "WARN": 0, "FAIL": 1, "SKIPPED": 0}


def test_report_name_matches_spec_pattern() -> None:
    name = default_report_name(datetime(2026, 9, 15, 13, 45, 12, tzinfo=timezone.utc))
    assert name == "triage-20260915-134512.md"
