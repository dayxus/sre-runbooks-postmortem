"""Top CPU and memory consumers on the local host."""

from __future__ import annotations

from typing import List, Tuple

from sretriage.checks.base import OK, SKIPPED, WARN, CheckResult, Context, run_cmd

HOT_CPU_PERCENT = 80.0
TOP_N = 5


def _parse_ps(output: str) -> List[Tuple[float, float, str]]:
    rows: List[Tuple[float, float, str]] = []
    for line in output.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            cpu = float(parts[0])
            mem = float(parts[1])
        except ValueError:
            continue
        rows.append((cpu, mem, parts[2].strip()))
    return rows


def run(ctx: Context) -> List[CheckResult]:
    rc, out, err = run_cmd(["ps", "-Ao", "pcpu,pmem,comm", "-r"], timeout=10.0)
    if rc != 0 or not out.strip():
        return [
            CheckResult(
                name="process",
                status=SKIPPED,
                summary="ps -Ao pcpu,pmem,comm -r produced no output",
                evidence=[(err or "").strip()[:200]],
                runbook="kubernetes/node-notready.md",
            )
        ]

    rows = _parse_ps(out)[:TOP_N]
    if not rows:
        return [
            CheckResult(
                name="process",
                status=SKIPPED,
                summary="no parseable rows in ps output",
                evidence=[out.strip().splitlines()[0][:200]],
                runbook="kubernetes/node-notready.md",
            )
        ]

    evidence = ["%5s %5s %s" % ("CPU%", "MEM%", "COMMAND")]
    for cpu, mem, command in rows:
        evidence.append("%5.1f %5.1f %s" % (cpu, mem, command))

    status = OK
    hottest = rows[0]
    if hottest[0] >= HOT_CPU_PERCENT or hottest[1] >= HOT_CPU_PERCENT:
        status = WARN

    next_steps: List[str] = []
    if status == WARN:
        next_steps = [
            "Sample the process before killing it: check its recent logs for restarts.",
            "Correlate the spike with a deploy or a batch window before acting.",
        ]

    return [
        CheckResult(
            name="process",
            status=status,
            summary="hottest process %s at %.1f%% CPU / %.1f%% MEM" % (hottest[2], hottest[0], hottest[1]),
            evidence=evidence,
            runbook="kubernetes/node-notready.md",
            next_steps=next_steps,
        )
    ]
