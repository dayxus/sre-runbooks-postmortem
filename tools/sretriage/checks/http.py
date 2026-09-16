"""HTTP reachability: status code, latency, redirects and security headers."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Dict, List, Tuple

from sretriage.checks.base import (
    FAIL,
    OK,
    SKIPPED,
    WARN,
    CheckResult,
    Context,
)

# Headers a public service is expected to send. Their absence is a WARN, not a
# failure: internal-only endpoints legitimately drop some of them.
SECURITY_HEADERS = (
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "content-security-policy",
    "referrer-policy",
)

USER_AGENT = "sretriage/0.1 (+https://github.com/dayxus/sre-runbooks-postmortem)"

SLOW_TTFB_MS = 800
SLOW_TOTAL_MS = 3000


def fetch(url: str, timeout: float) -> Tuple[object, Dict[str, str], str, Dict[str, float]]:
    """Perform a GET, returning ``(response, headers, error, timings)``."""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    timings: Dict[str, float] = {}
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            timings["ttfb_ms"] = (time.monotonic() - started) * 1000
            body = response.read()
            timings["total_ms"] = (time.monotonic() - started) * 1000
            timings["bytes"] = float(len(body))
            headers = {k.lower(): v for k, v in response.headers.items()}
            return response, headers, "", timings
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a response
        body = exc.read() if exc.fp else b""
        timings["ttfb_ms"] = (time.monotonic() - started) * 1000
        timings["total_ms"] = timings["ttfb_ms"]
        timings["bytes"] = float(len(body))
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return exc, headers, "", timings
    except (urllib.error.URLError, OSError, ValueError) as exc:
        timings["total_ms"] = (time.monotonic() - started) * 1000
        return None, {}, str(exc), timings


def run(ctx: Context) -> List[CheckResult]:
    if not ctx.targets:
        return [
            CheckResult(
                name="http",
                status=SKIPPED,
                summary="no --target supplied",
                runbook="observability/missing-metrics.md",
                targeted=True,
            )
        ]

    results: List[CheckResult] = []
    for url in ctx.targets:
        response, headers, error, timings = fetch(url, ctx.timeout)
        if response is None:
            # External network problems must never fail a pipeline.
            results.append(
                CheckResult(
                    name="http",
                    status=SKIPPED,
                    summary="%s unreachable from this host" % url,
                    evidence=["error: %s" % error],
                    runbook="network/dns-failure.md",
                    duration_ms=int(timings.get("total_ms", 0)),
                    targeted=True,
                )
            )
            continue

        status_code = int(getattr(response, "status", 0) or getattr(response, "code", 0))
        final_url = getattr(response, "url", url) or url
        redirects = 0
        if final_url.rstrip("/") != url.rstrip("/"):
            redirects = 1
        ttfb = timings.get("ttfb_ms", 0.0)
        total = timings.get("total_ms", 0.0)

        evidence = [
            "GET %s -> %d" % (url, status_code),
            "ttfb=%.1f ms total=%.1f ms bytes=%d redirects=%d"
            % (ttfb, total, int(timings.get("bytes", 0)), redirects),
        ]
        missing = [h for h in SECURITY_HEADERS if h not in headers]
        if missing:
            evidence.append("missing security headers: %s" % ", ".join(missing))
        else:
            evidence.append("all %d security headers present" % len(SECURITY_HEADERS))

        if status_code >= 500:
            status = FAIL
        elif status_code >= 400 or missing or ttfb > SLOW_TTFB_MS or total > SLOW_TOTAL_MS:
            status = WARN
        else:
            status = OK

        summary = "%s -> %d in %.0f ms" % (url, status_code, total)
        next_steps: List[str] = []
        if status_code >= 500:
            next_steps = [
                "Read the served 5xx rate next to deploy timestamps before rolling back.",
                "If the error is isolated to one replica, drain it from the load balancer.",
            ]
        elif missing:
            next_steps = [
                "Add the missing security headers at the edge, then re-run this check.",
            ]

        results.append(
            CheckResult(
                name="http",
                status=status,
                summary=summary,
                evidence=evidence,
                runbook=(
                    "observability/silent-failure.md"
                    if status_code >= 400
                    else "observability/missing-metrics.md"
                ),
                duration_ms=int(total),
                next_steps=next_steps,
                targeted=True,
            )
        )
    return results
