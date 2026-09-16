"""Internal and external link audit for the runbook library.

``links``  — checks every external http(s) link with HEAD and falls back to GET,
             writes ``reports/link-audit.md`` and exits 1 when a link is dead.
``stale``  — lists runbooks whose ``last_reviewed`` is older than the allowed
             window, writes ``reports/stale-runbooks.md`` and exits 1 when any
             is overdue.

Used by ``.github/workflows/maintenance.yml`` on a weekly schedule.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from sretriage.runbook_lint import discover, parse_front_matter  # noqa: E402

USER_AGENT = "sretriage-link-audit/0.1 (+https://github.com/dayxus/sre-runbooks-postmortem)"
TIMEOUT = 10.0
MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
SCAN_PATTERNS = (
    "README.md",
    "README.pt-BR.md",
    "docs/*.md",
    "templates/*.md",
    "runbooks/*.md",
    "runbooks/*/*.md",
)


def md_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for pattern in SCAN_PATTERNS:
        files.extend(sorted(root.glob(pattern)))
    return [path for path in files if path.is_file()]


def collect_links(root: Path) -> Dict[str, List[str]]:
    """Map URL -> list of files that reference it, skipping fenced code."""

    links: Dict[str, List[str]] = {}
    for path in md_files(root):
        rel = path.relative_to(root).as_posix()
        inside = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("```"):
                inside = not inside
                continue
            if inside:
                continue
            for url in MD_LINK_RE.findall(line):
                links.setdefault(url.rstrip(".,;"), []).append(rel)
    return links


def probe(url: str) -> Tuple[Optional[int], str]:
    """Return ``(status_code, method)`` for a URL, HEAD first then GET."""

    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return int(response.status), method
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 405, 429) and method == "HEAD":
                continue  # many servers refuse HEAD; retry with GET
            return int(exc.code), method
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = getattr(exc, "reason", exc)
            if method == "HEAD":
                continue
            return None, "error: %s" % last
    return None, "unreachable"


def audit_links(root: Path, out_path: Path) -> int:
    links = collect_links(root)
    stale_dupes = []
    rows: List[Tuple[str, int, str, str]] = []
    dead: List[Tuple[str, str, List[str]]] = []

    for url in sorted(links):
        status, method = probe(url)
        files = sorted(set(links[url]))
        if status is None or status >= 400:
            dead.append((url, str(status), files))
            rows.append((url, status or 0, str(status), ", ".join(files)))
        else:
            rows.append((url, status, method, ", ".join(files)))
        if len(files) > 1:
            stale_dupes.append((url, files))

    lines = [
        "# Auditoria de links externos",
        "",
        "- Executado em: %s (UTC)" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- Arquivos varridos: %d" % len(md_files(root)),
        "- URLs únicas verificadas: %d" % len(rows),
        "- URLs mortas: %d" % len(dead),
        "- User-Agent: `%s`" % USER_AGENT,
        "",
        "| URL | Status | Método/Erro | Arquivos |",
        "| --- | --- | --- | --- |",
    ]
    for url, status, method, files in rows:
        lines.append("| %s | %s | %s | %s |" % (url, status, method, files))
    lines.append("")

    if dead:
        lines.append("## Links mortos")
        lines.append("")
        for url, status, files in dead:
            lines.append("- `%s` → %s (referenciado em %s)" % (url, status, ", ".join(files)))
        lines.append("")
    else:
        lines.append("Nenhum link morto encontrado.")
        lines.append("")

    if stale_dupes:
        lines.append("## URLs repetidas em vários arquivos")
        lines.append("")
        for url, files in stale_dupes:
            lines.append("- `%s` (%d arquivos)" % (url, len(files)))
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("link audit: %d URLs, %d mortas -> %s" % (len(rows), len(dead), out_path.as_posix()))
    for url, status, files in dead:
        print("  DEAD %s (%s) in %s" % (url, status, ", ".join(files)))
    return 1 if dead else 0


def stale_runbooks(root: Path, out_path: Path, max_age_days: int) -> int:
    runbooks_dir = root / "runbooks"
    today = date.today()
    stale: List[Tuple[str, str, int]] = []
    fresh = 0

    for path in discover(runbooks_dir):
        rel = path.relative_to(root).as_posix()
        meta, _, _ = parse_front_matter(path.read_text(encoding="utf-8"))
        raw = meta.get("last_reviewed", "")
        try:
            reviewed = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            stale.append((rel, raw or "ausente", -1))
            continue
        age = (today - reviewed).days
        if age > max_age_days:
            stale.append((rel, raw, age))
        else:
            fresh += 1

    lines = [
        "# Runbooks pendentes de revisão",
        "",
        "- Executado em: %s (UTC)" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- Janela de revisão: %d dias" % max_age_days,
        "- Runbooks dentro da janela: %d" % fresh,
        "- Runbooks vencidos: %d" % len(stale),
        "",
    ]
    if stale:
        lines.extend(["| Runbook | last_reviewed | Dias desde a revisão |", "| --- | --- | --- |"])
        for rel, reviewed, age in sorted(stale, key=lambda item: item[2], reverse=True):
            lines.append("| %s | %s | %s |" % (rel, reviewed, age if age >= 0 else "data inválida"))
        lines.append("")
        lines.append(
            "Ação: revisar comandos, alertas e links; atualizar `last_reviewed` para a data da revisão efetiva."
        )
    else:
        lines.append("Nenhum runbook vencido nesta janela.")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("stale audit: %d vencidos, %d em dia -> %s" % (len(stale), fresh, out_path.as_posix()))
    for rel, reviewed, age in stale:
        print("  STALE %s (last_reviewed=%s, %s dias)" % (rel, reviewed, age))
    return 1 if stale else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="link and staleness audit")
    parser.add_argument("command", choices=("links", "stale"))
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--out", default=None)
    parser.add_argument("--max-age-days", type=int, default=180)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.command == "links":
        out = Path(args.out) if args.out else root / "reports" / "link-audit.md"
        return audit_links(root, out)
    out = Path(args.out) if args.out else root / "reports" / "stale-runbooks.md"
    return stale_runbooks(root, out, args.max_age_days)


if __name__ == "__main__":
    raise SystemExit(main())
