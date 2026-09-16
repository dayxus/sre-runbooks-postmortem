"""Isolated, skippable checks used by ``sretriage run``.

Every module in this package exposes ``run(ctx) -> list[CheckResult]`` and is
guaranteed not to raise: a missing tool or an unreachable target becomes a
``SKIPPED`` verdict instead of a crash.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from sretriage.checks import (
    aws,
    clock,
    disk,
    dns,
    http,
    k8s,
    memory,
    process,
    tls,
)
from sretriage.checks.base import CheckResult, Context

# Order matters: it is the order the report presents, cheapest and most
# target-specific first.
CHECK_MODULES: Dict[str, Callable[[Context], List[CheckResult]]] = {
    "dns": dns.run,
    "http": http.run,
    "tls": tls.run,
    "clock": clock.run,
    "disk": disk.run,
    "memory": memory.run,
    "process": process.run,
    "k8s": k8s.run,
    "aws": aws.run,
}


def run_all(ctx: Context) -> List[CheckResult]:
    """Run every check, never letting one module break the others."""

    results: List[CheckResult] = []
    for name, runner in CHECK_MODULES.items():
        try:
            results.extend(runner(ctx))
        except Exception as exc:  # pragma: no cover - last-resort guardrail
            results.append(
                CheckResult(
                    name=name,
                    status="SKIPPED",
                    summary="check crashed, isolated by the runner",
                    evidence=["%s: %s" % (type(exc).__name__, exc)],
                )
            )
    return results


__all__ = ["CHECK_MODULES", "CheckResult", "Context", "run_all"]
