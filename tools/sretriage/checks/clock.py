"""Clock skew against the ``Date`` header of a reachable target."""

from __future__ import annotations

import email.utils
import time
from datetime import datetime, timezone
from typing import List

from sretriage.checks.base import FAIL, OK, SKIPPED, WARN, CheckResult, Context
from sretriage.checks.http import fetch

WARN_SECONDS = 5
FAIL_SECONDS = 30


def run(ctx: Context) -> List[CheckResult]:
    if not ctx.targets:
        return [
            CheckResult(
                name="clock",
                status=SKIPPED,
                summary="no --target supplied, cannot compare against a Date header",
                runbook="observability/silent-failure.md",
                targeted=True,
            )
        ]

    errors: List[str] = []
    for url in ctx.targets:
        response, headers, error, _ = fetch(url, ctx.timeout)
        if response is None:
            errors.append("%s: %s" % (url, error))
            continue

        raw_date = headers.get("date", "")
        if not raw_date:
            errors.append("%s: no Date header" % url)
            continue

        parsed = email.utils.parsedate_to_datetime(raw_date)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        remote = parsed.timestamp()
        local = time.time()
        skew = local - remote

        if abs(skew) >= FAIL_SECONDS:
            status = FAIL
        elif abs(skew) >= WARN_SECONDS:
            status = WARN
        else:
            status = OK

        evidence = [
            "remote Date: %s" % raw_date,
            "local UTC:   %s" % datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "skew: %+.1f s" % skew,
        ]
        next_steps: List[str] = []
        if status in (WARN, FAIL):
            next_steps = [
                "Confirm the host clock synced (chronyc tracking or timedatectl).",
                "Token validation and signed requests fail long before users notice skew.",
            ]
        return [
            CheckResult(
                name="clock",
                status=status,
                summary="skew %+.1f s against %s" % (skew, url),
                evidence=evidence,
                runbook="observability/silent-failure.md",
                next_steps=next_steps,
                targeted=True,
            )
        ]

    return [
        CheckResult(
            name="clock",
            status=SKIPPED,
            summary="no target returned a usable Date header",
            evidence=errors[:4],
            runbook="observability/silent-failure.md",
            targeted=True,
        )
    ]
