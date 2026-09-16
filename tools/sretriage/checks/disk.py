"""Root filesystem usage: bytes and inodes."""

from __future__ import annotations

import os
import shutil
from typing import List

from sretriage.checks.base import FAIL, OK, WARN, CheckResult, Context

WARN_PERCENT = 80
FAIL_PERCENT = 90


def _inode_usage(path: str):
    """Return ``(used_percent, total, free)`` for inodes, or ``(None, 0, 0)``."""

    try:
        stats = os.statvfs(path)
    except (OSError, AttributeError):
        return None, 0, 0
    total = stats.f_files
    free = stats.f_ffree
    if not total:
        return None, 0, 0
    return ((total - free) / total) * 100.0, total, free


def run(ctx: Context) -> List[CheckResult]:
    path = "/"
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return [
            CheckResult(
                name="disk",
                status="SKIPPED",
                summary="cannot stat %s" % path,
                evidence=["error: %s" % exc],
                runbook="kubernetes/node-notready.md",
            )
        ]

    used_percent = (usage.used / usage.total) * 100.0
    evidence = [
        "%s total=%.1f GiB used=%.1f GiB free=%.1f GiB (%.1f%%)"
        % (
            path,
            usage.total / 1024**3,
            usage.used / 1024**3,
            usage.free / 1024**3,
            used_percent,
        )
    ]

    inode_percent, inode_total, inode_free = _inode_usage(path)
    if inode_percent is not None:
        evidence.append("inodes total=%d free=%d (%.1f%% used)" % (inode_total, inode_free, inode_percent))

    worst = used_percent
    if inode_percent is not None:
        worst = max(worst, inode_percent)

    if worst >= FAIL_PERCENT:
        status = FAIL
    elif worst >= WARN_PERCENT:
        status = WARN
    else:
        status = OK

    next_steps: List[str] = []
    if status in (WARN, FAIL):
        next_steps = [
            "Find the growth: `du -x -d1 /var` then drill into the largest directory.",
            "Prune container images and rotated logs before adding capacity.",
        ]

    return [
        CheckResult(
            name="disk",
            status=status,
            summary="%s at %.1f%% (worst of space/inodes)" % (path, worst),
            evidence=evidence,
            runbook="kubernetes/node-notready.md",
            next_steps=next_steps,
        )
    ]
