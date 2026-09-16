"""AWS account and RDS sanity checks. Degrades to SKIPPED without the CLI."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from sretriage.checks.base import (
    FAIL,
    OK,
    SKIPPED,
    WARN,
    CheckResult,
    Context,
    has_tool,
    run_cmd,
)

# Sustained DatabaseConnections above this ratio is the early signal of pool
# exhaustion upstream.
CONNECTION_WARN_RATIO = 0.8


def _loads(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def run(ctx: Context) -> List[CheckResult]:
    if not has_tool("aws"):
        return [
            CheckResult(
                name="aws",
                status=SKIPPED,
                summary="aws cli not available",
                evidence=["aws not found on PATH"],
                runbook="cloud/rds-connection-exhaustion.md",
            )
        ]

    rc, out, err = run_cmd(
        ["aws", "sts", "get-caller-identity", "--output", "json"],
        timeout=max(ctx.timeout, 10.0),
    )
    if rc != 0:
        return [
            CheckResult(
                name="aws",
                status=SKIPPED,
                summary="no usable AWS credentials or no network path",
                evidence=[(err or "").strip().splitlines()[0][:200] if err.strip() else "no output"],
                runbook="cloud/rds-connection-exhaustion.md",
            )
        ]

    identity = _loads(out)
    account = str(identity.get("Account", "unknown"))
    evidence = ["sts get-caller-identity -> account=%s arn=%s" % (account, identity.get("Arn", "unknown"))]

    rc, out, err = run_cmd(
        ["aws", "rds", "describe-db-instances", "--output", "json"],
        timeout=max(ctx.timeout, 20.0),
    )
    if rc != 0:
        evidence.append("rds describe-db-instances unavailable: %s" % (err or "").strip()[:160])
        return [
            CheckResult(
                name="aws",
                status=OK,
                summary="credentials valid, RDS inventory not readable with this role",
                evidence=evidence,
                runbook="cloud/rds-connection-exhaustion.md",
            )
        ]

    instances = _loads(out).get("DBInstances", [])
    risky: List[str] = []
    detail: List[str] = []
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        identifier = str(instance.get("DBInstanceIdentifier", "?"))
        status = str(instance.get("DBInstanceStatus", "?"))
        max_connections = instance.get("MaxAllocatedStorage") or 0
        detail.append("%s status=%s max_allocated_storage=%s" % (identifier, status, max_connections))
        if status not in ("available", "backing-up", "modifying"):
            risky.append("%s status=%s" % (identifier, status))

    evidence.append("db instances: %d" % len(instances))
    evidence.extend(detail[:6])

    status = OK
    if risky:
        status = FAIL
    elif len(instances) == 0:
        status = WARN

    next_steps: List[str] = []
    if status == FAIL:
        next_steps = [
            "Read the latest RDS events and confirm a failover or storage-auto-scaling action.",
            "Compare active connections against the parameter group max_connections.",
        ]

    return [
        CheckResult(
            name="aws",
            status=status,
            summary="account %s, %d RDS instances, %d needing attention"
            % (account, len(instances), len(risky)),
            evidence=evidence,
            runbook="cloud/rds-connection-exhaustion.md",
            next_steps=next_steps,
        )
    ]
