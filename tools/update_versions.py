"""Refresh the upstream component versions recorded in docs/versions.md.

The generated block is the part between the two markers; everything outside it
is prose maintained by hand. Exits 1 when an upstream lookup fails, so the weekly
maintenance workflow can report the failure instead of silently writing stale data.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "docs" / "versions.md"
USER_AGENT = "sretriage-version-check/0.1 (+https://github.com/dayxus/sre-runbooks-postmortem)"
TIMEOUT = 15.0

BEGIN = "<!-- BEGIN GENERATED VERSIONS -->"
END = "<!-- END GENERATED VERSIONS -->"

KUBERNETES_SOURCE = "https://dl.k8s.io/release/stable.txt"
AWS_CLI_SOURCE = "https://api.github.com/repos/aws/aws-cli/tags?per_page=100"

SOURCES: List[Tuple[str, str]] = [
    ("Kubernetes", KUBERNETES_SOURCE),
    ("kubectl", KUBERNETES_SOURCE),
    ("AWS CLI v2", AWS_CLI_SOURCE),
]


def _fetch(url: str) -> Optional[str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    # The weekly workflow runs with a token available; use it to avoid the
    # unauthenticated GitHub API rate limit.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = "Bearer %s" % token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print("fetch failed for %s: %s" % (url, exc), file=sys.stderr)
        return None


def _highest_semver(names: List[str], major: int) -> Optional[str]:
    versions = []
    for name in names:
        match = re.match(r"^(%d)\.(\d+)\.(\d+)$" % major, name)
        if match:
            versions.append((tuple(int(part) for part in match.groups()), name))
    if not versions:
        return None
    return max(versions)[1]


def _aws_cli_v2_version() -> Optional[str]:
    """Highest ``2.x.y`` tag of aws/aws-cli.

    The releases endpoint only publishes a ``2.0.0dev0`` placeholder for this
    repository, so the tags list is the reliable source.
    """

    raw = _fetch(AWS_CLI_SOURCE)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, list):
        return None
    names = [str(item.get("name", "")) for item in payload if isinstance(item, dict)]
    return _highest_semver(names, major=2)


def collect() -> Dict[str, str]:
    values: Dict[str, str] = {}
    kubernetes = _fetch(SOURCES[0][1])
    if kubernetes:
        values["Kubernetes"] = kubernetes.strip().lstrip("v")
        values["kubectl"] = values["Kubernetes"]
    aws_version = _aws_cli_v2_version()
    if aws_version:
        values["AWS CLI v2"] = aws_version
    return values


def render(values: Dict[str, str], previous: Dict[str, str], checked_at: str) -> str:
    lines = [
        "| Componente | Versão estável | Verificado em (UTC) | Fonte |",
        "| --- | --- | --- | --- |",
    ]
    sources = {
        "Kubernetes": "https://dl.k8s.io/release/stable.txt",
        "kubectl": "https://dl.k8s.io/release/stable.txt",
        "AWS CLI v2": "https://github.com/aws/aws-cli/releases",
    }
    for name, _ in SOURCES:
        value = values.get(name) or previous.get(name, "desconhecida")
        lines.append("| %s | `%s` | %s | %s |" % (name, value, checked_at, sources[name]))
    return "\n".join(lines)


def parse_previous(text: str) -> Dict[str, str]:
    previous: Dict[str, str] = {}
    for line in text.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 4 and parts[1] in ("Kubernetes", "kubectl", "AWS CLI v2"):
            previous[parts[1]] = parts[2].strip("` ")
    return previous


def main() -> int:
    if not TARGET.exists():
        print("%s not found" % TARGET, file=sys.stderr)
        return 1

    text = TARGET.read_text(encoding="utf-8")
    previous = parse_previous(text)
    values = collect()
    if not values:
        print("no upstream version could be fetched, leaving docs/versions.md untouched", file=sys.stderr)
        return 1

    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = BEGIN + "\n" + render(values, previous, checked_at) + "\n" + END

    begin_index = text.find(BEGIN)
    end_index = text.find(END)
    if begin_index == -1 or end_index == -1:
        print("markers %s / %s missing in docs/versions.md" % (BEGIN, END), file=sys.stderr)
        return 1

    updated = text[:begin_index] + block + text[end_index + len(END) :]
    if updated == text:
        print("versions unchanged: %s" % ", ".join("%s=%s" % kv for kv in sorted(values.items())))
        return 0
    TARGET.write_text(updated, encoding="utf-8")
    print("versions updated: %s" % ", ".join("%s=%s" % kv for kv in sorted(values.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
