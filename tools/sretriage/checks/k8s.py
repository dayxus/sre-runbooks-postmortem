"""Kubernetes cluster health. Degrades to SKIPPED when kubectl is absent."""

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


def _loads(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _node_conditions(node: Dict[str, Any]) -> Dict[str, str]:
    statuses: Dict[str, str] = {}
    for condition in node.get("status", {}).get("conditions", []) or []:
        if isinstance(condition, dict):
            statuses[str(condition.get("type", ""))] = str(condition.get("status", ""))
    return statuses


def run(ctx: Context) -> List[CheckResult]:
    if not has_tool("kubectl"):
        return [
            CheckResult(
                name="k8s",
                status=SKIPPED,
                summary="kubectl not available",
                evidence=["kubectl not found on PATH"],
                runbook="kubernetes/node-notready.md",
            )
        ]

    rc, out, err = run_cmd(["kubectl", "config", "current-context"], timeout=ctx.timeout)
    current_context = (out or "").strip()
    if rc != 0 or not current_context:
        return [
            CheckResult(
                name="k8s",
                status=SKIPPED,
                summary="no kubeconfig context selected",
                evidence=[(err or "kubectl config current-context returned nothing").strip()[:200]],
                runbook="kubernetes/node-notready.md",
            )
        ]

    rc, out, err = run_cmd(["kubectl", "get", "nodes", "-o", "json"], timeout=max(ctx.timeout, 10.0))
    if rc != 0:
        return [
            CheckResult(
                name="k8s",
                status=SKIPPED,
                summary="kubectl cannot reach the cluster in context %s" % current_context,
                evidence=[(err or "").strip()[:200]],
                runbook="kubernetes/node-notready.md",
            )
        ]

    nodes = _loads(out).get("items", [])
    not_ready: List[str] = []
    pressure: List[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        name = str(node.get("metadata", {}).get("name", "?"))
        conditions = _node_conditions(node)
        if conditions.get("Ready") != "True":
            not_ready.append(name)
        for kind in ("MemoryPressure", "DiskPressure", "PIDPressure"):
            if conditions.get(kind) == "True":
                pressure.append("%s/%s" % (name, kind))

    evidence = [
        "context=%s nodes=%d" % (current_context, len(nodes)),
        "not-ready: %s" % (", ".join(not_ready) if not_ready else "none"),
        "pressure conditions: %s" % (", ".join(pressure) if pressure else "none"),
    ]

    if not_ready:
        status = FAIL
    elif pressure:
        status = WARN
    else:
        status = OK

    next_steps: List[str] = []
    if status == FAIL:
        next_steps = [
            "Cordon the node, drain stateless workloads, then inspect kubelet logs.",
            "Confirm PodDisruptionBudgets still allow the remaining capacity to serve.",
        ]
    elif status == WARN:
        next_steps = [
            "Read the eviction thresholds and free space or memory before it escalates.",
        ]

    return [
        CheckResult(
            name="k8s",
            status=status,
            summary="%d nodes, %d not ready, %d under pressure" % (len(nodes), len(not_ready), len(pressure)),
            evidence=evidence,
            runbook="kubernetes/node-notready.md",
            next_steps=next_steps,
        )
    ]
