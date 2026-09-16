"""TLS certificate expiry, issuer and SAN coverage."""

from __future__ import annotations

import socket
import ssl
from datetime import datetime, timezone
from typing import List, Optional

from sretriage.checks.base import (
    FAIL,
    OK,
    SKIPPED,
    WARN,
    CheckResult,
    Context,
    has_tool,
    host_from_url,
    port_from_url,
    run_cmd,
)

WARN_DAYS = 30
FAIL_DAYS = 7


def _parse_not_after(value: str) -> Optional[datetime]:
    """Parse an OpenSSL ``notAfter`` string such as ``Aug 31 12:00:00 2026 GMT``."""

    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S %Y"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc)
    return None


def _format_name(name: object) -> str:
    """Flatten the RDN shape of ``getpeercert`` into ``key=value`` pairs.

    ``issuer`` arrives as ``((('organizationName', 'X'),), (('commonName', 'Y'),))``
    but some stacks return flat two-tuples, so both shapes are accepted.
    """

    parts: List[str] = []
    if not isinstance(name, (tuple, list)):
        return ""
    for rdn in name:
        candidates = rdn if isinstance(rdn, (tuple, list)) else (rdn,)
        if candidates and not isinstance(candidates[0], (tuple, list)):
            candidates = (candidates,)
        for attribute in candidates:
            if isinstance(attribute, (tuple, list)) and len(attribute) == 2 and attribute[0]:
                parts.append("%s=%s" % (attribute[0], attribute[1]))
    return ", ".join(parts)


def _peer_certificate(host: str, port: int, timeout: float):
    """Fetch the peer certificate dictionary, or ``(None, error)``."""

    context = ssl.create_default_context()
    try:
        with (
            socket.create_connection((host, port), timeout=timeout) as raw,
            context.wrap_socket(raw, server_hostname=host) as tls,
        ):
            return tls.getpeercert(), tls.version()
    except ssl.SSLCertVerificationError as exc:
        return None, "certificate verification failed: %s" % exc.verify_message
    except (ssl.SSLError, socket.error, OSError) as exc:
        return None, str(exc)


def _openssl_evidence(host: str, port: int, timeout: float) -> List[str]:
    """Use the real ``openssl s_client`` command when it is installed."""

    if not has_tool("openssl"):
        return ["openssl not available on PATH, used the standard-library TLS stack"]
    cmd = [
        "openssl",
        "s_client",
        "-connect",
        "%s:%d" % (host, port),
        "-servername",
        host,
        "-verify_return_error",
        "-brief",
    ]
    rc, out, err = run_cmd(cmd, timeout=timeout)
    combined = (out or "") + (err or "")
    evidence: List[str] = []
    for line in combined.splitlines():
        stripped = line.strip()
        if stripped.startswith(("subject=", "issuer=", "notBefore=", "notAfter=")):
            evidence.append("openssl s_client: %s" % stripped)
    if rc is None and not evidence:
        evidence.append("openssl s_client did not complete within %.1fs" % timeout)
    return evidence[:4]


def run(ctx: Context) -> List[CheckResult]:
    https_targets = ctx.https_targets()
    if not https_targets:
        return [
            CheckResult(
                name="tls",
                status=SKIPPED,
                summary="no https target supplied",
                runbook="network/tls-cert-expiry.md",
                targeted=True,
            )
        ]

    results: List[CheckResult] = []
    for url in https_targets:
        host = host_from_url(url)
        port = port_from_url(url, 443) or 443
        cert, extra = _peer_certificate(host, port, ctx.timeout)
        if cert is None:
            results.append(
                CheckResult(
                    name="tls",
                    status=SKIPPED,
                    summary="%s:%d TLS handshake not completed" % (host, port),
                    evidence=["error: %s" % extra],
                    runbook="network/tls-cert-expiry.md",
                    targeted=True,
                )
            )
            continue

        not_after_raw = cert.get("notAfter", "")
        not_after = _parse_not_after(not_after_raw)
        now = datetime.now(timezone.utc)
        days_left = None
        if not_after is not None:
            days_left = int((not_after - now).total_seconds() // 86400)

        issuer = _format_name(cert.get("issuer")) or "unknown"
        san = [value for kind, value in cert.get("subjectAltName", ()) if kind == "DNS"]

        evidence = [
            "peer %s:%d protocol=%s" % (host, port, extra),
            "notAfter=%s (%s days left)" % (not_after_raw or "?", days_left),
            "issuer=%s" % issuer,
            "SAN (%d entries): %s" % (len(san), ", ".join(san[:6]) or "none"),
        ]
        evidence.extend(_openssl_evidence(host, port, ctx.timeout))

        if days_left is None:
            status = WARN
        elif days_left <= FAIL_DAYS:
            status = FAIL
        elif days_left <= WARN_DAYS:
            status = WARN
        else:
            status = OK

        next_steps: List[str] = []
        if status in (WARN, FAIL):
            next_steps = [
                "Confirm the renewal job ran and check the ACME/CA order status.",
                "If renewal is stuck, ship the certificate manually via the ingress "
                "secret and open a follow-up to fix automation.",
            ]

        results.append(
            CheckResult(
                name="tls",
                status=status,
                summary="%s expires in %s days" % (host, days_left),
                evidence=evidence,
                runbook="network/tls-cert-expiry.md",
                next_steps=next_steps,
                targeted=True,
            )
        )
    return results
