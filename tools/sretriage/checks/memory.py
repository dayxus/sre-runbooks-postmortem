"""Memory pressure, portable across macOS and Linux."""

from __future__ import annotations

import sys
from typing import List, Optional, Tuple

from sretriage.checks.base import FAIL, OK, SKIPPED, WARN, CheckResult, Context, run_cmd

WARN_PERCENT = 85
FAIL_PERCENT = 95


def _linux_memory() -> Tuple[Optional[float], List[str]]:
    evidence: List[str] = []
    total = available = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            fields = {}
            for line in handle:
                key, _, rest = line.partition(":")
                fields[key.strip()] = rest.strip()
    except OSError as exc:
        return None, ["cannot read /proc/meminfo: %s" % exc]

    for key in ("MemTotal", "MemAvailable"):
        raw = fields.get(key, "")
        if raw.endswith("kB"):
            value = int(raw.split()[0]) * 1024
            if key == "MemTotal":
                total = value
            else:
                available = value
    if not total:
        return None, ["MemTotal missing from /proc/meminfo"]
    used = total - available
    evidence.append("MemTotal=%.1f GiB MemAvailable=%.1f GiB" % (total / 1024**3, available / 1024**3))
    return (used / total) * 100.0, evidence


def _darwin_memory() -> Tuple[Optional[float], List[str]]:
    evidence: List[str] = []
    rc, out, err = run_cmd(["vm_stat"], timeout=5.0)
    if rc != 0:
        return None, ["vm_stat unavailable: %s" % (err.strip() or "no output")]

    page_size = 4096
    pages = {}
    for line in out.splitlines():
        if "page size of" in line:
            digits = "".join(ch for ch in line if ch.isdigit())
            if digits:
                page_size = int(digits)
            continue
        key, _, value = line.partition(":")
        value = value.strip().rstrip(".")
        if value.isdigit():
            pages[key.strip()] = int(value)

    rc, total_out, _ = run_cmd(["sysctl", "-n", "hw.memsize"], timeout=5.0)
    total_bytes = int(total_out.strip()) if rc == 0 and total_out.strip().isdigit() else 0
    if not total_bytes:
        return None, ["hw.memsize unavailable, cannot compute a ratio"]

    free_pages = sum(
        pages.get(key, 0) for key in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable")
    )
    free_bytes = free_pages * page_size
    used_percent = max(0.0, min(100.0, (1 - (free_bytes / total_bytes)) * 100.0))
    evidence.append(
        "vm_stat page_size=%d free+inactive+speculative=%.1f GiB hw.memsize=%.1f GiB"
        % (page_size, free_bytes / 1024**3, total_bytes / 1024**3)
    )
    return used_percent, evidence


def run(ctx: Context) -> List[CheckResult]:
    if sys.platform == "darwin":
        used_percent, evidence = _darwin_memory()
    elif sys.platform.startswith("linux"):
        used_percent, evidence = _linux_memory()
    else:  # pragma: no cover - other platforms are not supported targets
        used_percent, evidence = None, ["unsupported platform: %s" % sys.platform]

    if used_percent is None:
        return [
            CheckResult(
                name="memory",
                status=SKIPPED,
                summary="memory pressure could not be measured on this host",
                evidence=evidence,
                runbook="kubernetes/oomkilled.md",
            )
        ]

    if used_percent >= FAIL_PERCENT:
        status = FAIL
    elif used_percent >= WARN_PERCENT:
        status = WARN
    else:
        status = OK

    next_steps: List[str] = []
    if status in (WARN, FAIL):
        next_steps = [
            "Rank consumers before acting: `ps -Ao pcpu,pmem,comm -r | head`.",
            "Check page-cache reclaim and swap activity before restarting anything.",
        ]

    return [
        CheckResult(
            name="memory",
            status=status,
            summary="%.1f%% of RAM in use" % used_percent,
            evidence=evidence,
            runbook="kubernetes/oomkilled.md",
            next_steps=next_steps,
        )
    ]
