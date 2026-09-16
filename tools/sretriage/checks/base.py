"""Shared primitives for every triage check.

A check never raises: it returns one :class:`CheckResult` per evaluated item.
Missing tooling or an unreachable external target degrades to ``SKIPPED`` so a
flaky network can never break a CI job.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
SKIPPED = "SKIPPED"

# Ordering used when a single check produces several results.
STATUS_SEVERITY = {FAIL: 0, WARN: 1, OK: 2, SKIPPED: 3}

STATUS_EMOJI = {OK: "OK", WARN: "WARN", FAIL: "FAIL", SKIPPED: "SKIPPED"}


@dataclass
class CheckResult:
    """Outcome of a single check against a single item."""

    name: str
    status: str
    summary: str
    evidence: List[str] = field(default_factory=list)
    runbook: str = ""
    next_steps: List[str] = field(default_factory=list)
    duration_ms: int = 0
    targeted: bool = False


@dataclass
class Context:
    """Everything a check may need, resolved once by the CLI."""

    targets: List[str] = field(default_factory=list)
    target_hosts: List[str] = field(default_factory=list)
    timeout: float = 5.0

    def https_targets(self) -> List[str]:
        return [t for t in self.targets if t.lower().startswith("https://")]


def has_tool(name: str) -> bool:
    """True when an executable is available on PATH."""

    return shutil.which(name) is not None


def run_cmd(cmd: Sequence[str], timeout: float = 10.0) -> Tuple[Optional[int], str, str]:
    """Run a command, returning ``(returncode, stdout, stderr)``.

    ``returncode`` is ``None`` when the tool is missing or the timeout hit;
    ``stderr`` carries the reason. Never raises.
    """

    if not cmd or shutil.which(cmd[0]) is None:
        return None, "", "command not found: %s" % (cmd[0] if cmd else "")
    try:
        proc = subprocess.run(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "", "timeout after %.1fs: %s" % (timeout, " ".join(cmd))
    except OSError as exc:  # pragma: no cover - defensive
        return None, "", "exec error: %s" % exc
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", "replace"),
        proc.stderr.decode("utf-8", "replace"),
    )


def host_from_url(url: str) -> str:
    """Extract the hostname from a URL without pulling in a dependency."""

    rest = url.split("://", 1)[-1]
    authority = rest.split("/", 1)[0].split("?", 1)[0]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    if authority.startswith("["):  # IPv6 literal
        return authority.split("]", 1)[0].strip("[")
    return authority.split(":", 1)[0]


def port_from_url(url: str, default: Optional[int] = None) -> Optional[int]:
    """Extract the explicit port from a URL, if any."""

    scheme = url.split("://", 1)[0].lower() if "://" in url else "http"
    rest = url.split("://", 1)[-1]
    authority = rest.split("/", 1)[0].split("?", 1)[0]
    if ":" in authority:
        port = authority.rsplit(":", 1)[1]
        if port.isdigit():
            return int(port)
    if default is not None:
        return default
    return 443 if scheme == "https" else 80


def is_ip_literal(value: str) -> bool:
    """True for IPv4/IPv6 literals."""

    parts = value.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return True
    return ":" in value


@dataclass
class Timer:
    """Tiny helper so every result reports how long it took."""

    started: float = field(default_factory=time.monotonic)

    def ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)
