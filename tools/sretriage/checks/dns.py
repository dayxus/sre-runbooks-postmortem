"""DNS resolution and resolution latency."""

from __future__ import annotations

import socket
import time
from typing import List

from sretriage.checks.base import (
    FAIL,
    OK,
    WARN,
    CheckResult,
    Context,
    host_from_url,
    is_ip_literal,
    run_cmd,
)

SLOW_RESOLUTION_MS = 500


def _resolve(host: str, timeout: float):
    """Resolve a hostname, returning ``(addresses, elapsed_ms, error)``."""

    started = time.monotonic()
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        infos = socket.getaddrinfo(host, None)
        addresses = sorted({info[4][0] for info in infos})
        return addresses, int((time.monotonic() - started) * 1000), ""
    except socket.gaierror as exc:
        return [], int((time.monotonic() - started) * 1000), str(exc)
    finally:
        socket.setdefaulttimeout(previous)


def hosts_from_context(ctx: Context) -> List[str]:
    """Explicit ``--target-host`` values plus every host derived from a URL."""

    hosts: List[str] = []
    for host in list(ctx.target_hosts) + [host_from_url(t) for t in ctx.targets]:
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def run(ctx: Context) -> List[CheckResult]:
    hosts = hosts_from_context(ctx)
    if not hosts:
        return [
            CheckResult(
                name="dns",
                status="SKIPPED",
                summary="no host supplied (use --target or --target-host)",
                runbook="network/dns-failure.md",
                targeted=True,
            )
        ]

    results: List[CheckResult] = []
    for host in hosts:
        if is_ip_literal(host):
            evidence = ["%s is an IP literal, no resolution required" % host]
            rc, out, _ = run_cmd(["dig", "+short", "-x", host], timeout=ctx.timeout)
            if rc == 0 and out.strip():
                evidence.append("reverse lookup: %s" % out.strip().splitlines()[0])
            results.append(
                CheckResult(
                    name="dns",
                    status=OK,
                    summary="%s resolved as IP literal" % host,
                    evidence=evidence,
                    runbook="network/dns-failure.md",
                    targeted=True,
                )
            )
            continue

        addresses, elapsed_ms, error = _resolve(host, ctx.timeout)
        if error:
            results.append(
                CheckResult(
                    name="dns",
                    status=FAIL,
                    summary="%s did not resolve" % host,
                    evidence=["getaddrinfo(%s) -> %s" % (host, error)],
                    runbook="network/dns-failure.md",
                    duration_ms=elapsed_ms,
                    next_steps=[
                        "Confirm the authoritative zone still serves the record (dig +trace).",
                        "Check VPC resolver rules / search domains on the caller.",
                    ],
                    targeted=True,
                )
            )
            continue

        status = OK
        if elapsed_ms > SLOW_RESOLUTION_MS:
            status = WARN
        evidence = ["getaddrinfo(%s) -> %s" % (host, ", ".join(addresses[:6]))]
        rc, out, _ = run_cmd(["dig", "+noall", "+answer", host], timeout=ctx.timeout)
        if rc == 0 and out.strip():
            for line in out.strip().splitlines()[:4]:
                evidence.append("dig: %s" % line.strip())
        results.append(
            CheckResult(
                name="dns",
                status=status,
                summary="%s -> %s in %d ms" % (host, ", ".join(addresses[:3]), elapsed_ms),
                evidence=evidence,
                runbook="network/dns-failure.md",
                duration_ms=elapsed_ms,
                targeted=True,
            )
        )
    return results
