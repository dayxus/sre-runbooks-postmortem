"""Markdown report rendering for ``sretriage run``."""

from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from sretriage.checks.base import CheckResult, Context

REPO_URL = "https://github.com/dayxus/sre-runbooks-postmortem"

VERDICT_BY_STATUS = {
    "FAIL": "DEGRADADO",
    "WARN": "ATENÇÃO",
    "OK": "SAUDÁVEL",
    "SKIPPED": "SEM DADOS",
}


def summarize(results: Sequence[CheckResult]) -> Dict[str, int]:
    """Count results per status, guaranteeing every status key exists."""

    counts = {"OK": 0, "WARN": 0, "FAIL": 0, "SKIPPED": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def verdict(results: Sequence[CheckResult], targeted_ok: bool) -> str:
    """Overall verdict string used in the header and in the exit code."""

    counts = summarize(results)
    if not targeted_ok:
        return "SEM ALVO AVALIÁVEL"
    if counts["FAIL"]:
        return "DEGRADADO"
    if counts["WARN"]:
        return "ATENÇÃO"
    return "SAUDÁVEL"


def _table(results: Sequence[CheckResult]) -> List[str]:
    lines = [
        "| Check | Status | Resumo | Duração | Runbook |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in results:
        runbook = (
            "[runbooks/%s](../runbooks/%s)" % (result.runbook, result.runbook) if result.runbook else "—"
        )
        lines.append(
            "| %s | %s | %s | %d ms | %s |"
            % (result.name, result.status, result.summary.replace("|", "\\|"), result.duration_ms, runbook)
        )
    return lines


def _evidence(results: Sequence[CheckResult]) -> List[str]:
    lines = ["## Evidências", ""]
    for result in results:
        lines.append("### %s — %s (%s)" % (result.name, result.status, result.summary))
        lines.append("")
        if result.evidence:
            lines.append("```text")
            for item in result.evidence:
                lines.append(str(item))
            lines.append("```")
        else:
            lines.append("_sem evidência coletada_")
        lines.append("")
    return lines


def _next_steps(results: Sequence[CheckResult], targeted_ok: bool) -> List[str]:
    lines = [
        "## Próximos passos sugeridos",
        "",
        "Cada linha aponta o runbook que trata o sintoma detectado.",
        "",
    ]
    if not targeted_ok:
        lines.append(
            "Nenhum alvo pôde ser avaliado (rede indisponível ou alvo inválido). "
            "Confirme o alvo com `--target https://example.org --target-host 1.1.1.1` "
            "e então siga [`runbooks/network/dns-failure.md`](../runbooks/network/dns-failure.md)."
        )
        lines.append("")
        return lines
    actionable = [r for r in results if r.status in ("FAIL", "WARN") or r.next_steps]
    if not actionable:
        lines.append("Nada a fazer: todos os checks ficaram OK ou SKIPPED.")
        lines.append("")
        return lines
    for result in actionable:
        runbook = result.runbook or ""
        label = "runbooks/%s" % runbook if runbook else "runbooks/"
        href = "../runbooks/%s" % runbook if runbook else "../runbooks/"
        lines.append("- **%s (%s)** → [`%s`](%s)" % (result.name, result.status, label, href))
        for step in result.next_steps:
            lines.append("  - %s" % step)
    lines.append("")
    return lines


def render(
    results: Sequence[CheckResult],
    ctx: Context,
    targeted_ok: bool,
    now: Optional[datetime] = None,
) -> str:
    """Render the full triage report as markdown."""

    now = now or datetime.now(timezone.utc)
    counts = summarize(results)
    lines = [
        "# Relatório de triagem sretriage",
        "",
        "**VEREDITO: %s**" % verdict(results, targeted_ok),
        "",
        "- Gerado em: %s (UTC)" % now.strftime("%Y-%m-%d %H:%M:%S"),
        "- Alvos: %s" % (", ".join(ctx.targets) if ctx.targets else "nenhum"),
        "- Hosts verificados: %s" % (", ".join(ctx.target_hosts) if ctx.target_hosts else "—"),
        "- Timeout por check: %.1f s" % ctx.timeout,
        "- Runner: %s %s / Python %s" % (platform.system(), platform.release(), platform.python_version()),
        "- Totais: OK=%d WARN=%d FAIL=%d SKIPPED=%d"
        % (counts["OK"], counts["WARN"], counts["FAIL"], counts["SKIPPED"]),
        "- Biblioteca: %s" % REPO_URL,
        "",
        "## Veredito por check",
        "",
    ]
    lines.extend(_table(results))
    lines.append("")
    lines.extend(_evidence(results))
    lines.extend(_next_steps(results, targeted_ok))
    lines.append("---")
    lines.append("")
    lines.append("Relatório gerado por `sretriage` a partir de execução real, sem valores simulados.")
    return "\n".join(lines) + "\n"


def default_report_name(now: Optional[datetime] = None) -> str:
    """``triage-YYYYMMDD-HHMMSS.md`` as required by the spec."""

    now = now or datetime.now()
    return "triage-%s.md" % now.strftime("%Y%m%d-%H%M%S")


def stderr_summary(results: Sequence[CheckResult], last_verdict: str) -> str:
    """Short human summary printed to stdout after a run."""

    counts = summarize(results)
    return "sretriage: %d checks, OK=%d WARN=%d FAIL=%d SKIPPED=%d, veredito=%s" % (
        len(results),
        counts["OK"],
        counts["WARN"],
        counts["FAIL"],
        counts["SKIPPED"],
        last_verdict,
    )


def python_supported() -> bool:
    return sys.version_info >= (3, 9)
