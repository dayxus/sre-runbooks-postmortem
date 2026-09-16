"""Command line interface for sretriage.

Exit codes (contract, covered by tests/test_cli_exit_codes.py):

* ``run`` -> 0 without FAIL, 1 with at least one FAIL, 2 when no target could
  be evaluated at all.
* ``check-runbooks`` / ``index --check`` -> 1 when there is anything to fix.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from sretriage import __version__
from sretriage.checks import run_all
from sretriage.checks.base import CheckResult, Context, host_from_url
from sretriage.report import default_report_name, render, stderr_summary, summarize, verdict
from sretriage.runbook_lint import (
    check_internal_links,
    extract_index,
    lint_library,
    render_index,
    replace_index,
)

DEFAULT_TARGET = "https://example.org"
RUNBOOKS_DIR = "runbooks"
INDEX_FILE = "runbooks/README.md"


def _build_context(args: argparse.Namespace) -> Context:
    targets: List[str] = list(args.target or [])
    if not targets:
        targets = [DEFAULT_TARGET]
    host_list: List[str] = list(args.target_host or [])
    if not host_list:
        host_list = []
        for url in targets:
            host = host_from_url(url)
            if host and host not in host_list:
                host_list.append(host)
    return Context(targets=targets, target_hosts=host_list, timeout=args.timeout)


def exit_code_for(results: Sequence[CheckResult]) -> int:
    """Exit code contract for ``run`` (see the module docstring)."""

    targeted_ok = any(result.targeted and result.status != "SKIPPED" for result in results)
    if not targeted_ok:
        return 2
    if any(result.status == "FAIL" for result in results):
        return 1
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    ctx = _build_context(args)
    results = run_all(ctx)

    targeted_ok = any(result.targeted and result.status != "SKIPPED" for result in results)
    final = verdict(results, targeted_ok)
    counts = summarize(results)

    print("sretriage run — alvo(s): %s" % ", ".join(ctx.targets))
    print("")
    print("| Check | Status | Resumo |")
    print("| --- | --- | --- |")
    for result in results:
        print("| %s | %s | %s |" % (result.name, result.status, result.summary))
    print("")
    print(stderr_summary(results, final))

    out_dir = Path(args.out) if args.out else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / default_report_name()
        report_path.write_text(render(results, ctx, targeted_ok), encoding="utf-8")
        print("report: %s" % report_path.as_posix())

    if not targeted_ok:
        return 2
    if counts["FAIL"]:
        return 1
    return 0


def cmd_check_runbooks(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    runbooks_dir = root / RUNBOOKS_DIR
    runbooks, problems = lint_library(runbooks_dir)
    link_problems = check_internal_links(root)
    problems.extend(link_problems)

    print("sretriage check-runbooks — %d runbooks em %s/" % (len(runbooks), RUNBOOKS_DIR))
    for runbook in runbooks:
        print("  checked %s" % runbook.rel_path)
    print("links relativos internos: %d verificados" % _count_internal_links(root))
    if problems:
        print("")
        print("%d problema(s):" % len(problems))
        for problem in problems:
            print("  - %s" % problem.render())
        return 1
    print("")
    print("OK: front matter, seções, comandos e links internos verificados em %d runbooks" % len(runbooks))
    return 0


def _count_internal_links(root: Path) -> int:
    from sretriage.runbook_lint import _MD_LINK_RE  # local import keeps the public API small

    total = 0
    for pattern in ("*.md", "docs/*.md", "templates/*.md", "runbooks/*.md", "runbooks/*/*.md"):
        for path in sorted(root.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            total += len(
                [t for t in _MD_LINK_RE.findall(text) if not t.startswith(("http://", "https://", "mailto:"))]
            )
    return total


def cmd_index(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    index_path = root / INDEX_FILE
    runbooks, problems = lint_library(root / RUNBOOKS_DIR)
    fatal = [p for p in problems if "missing required sections" in p.message]
    if fatal:
        for problem in fatal:
            print("  - %s" % problem.render(), file=sys.stderr)
        print("sretriage index: corrija o lint dos runbooks antes de gerar o índice", file=sys.stderr)
        return 1

    generated = render_index(runbooks)
    current = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    existing_block = extract_index(current)

    if args.check:
        if existing_block == generated:
            print("sretriage index --check: %s está atualizado (%d runbooks)" % (INDEX_FILE, len(runbooks)))
            return 0
        print("sretriage index --check: %s está desatualizado" % INDEX_FILE, file=sys.stderr)
        print("rode: python3 -m sretriage index", file=sys.stderr)
        return 1

    updated = replace_index(current, generated)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(updated, encoding="utf-8")
    print("sretriage index: %s atualizado com %d runbooks" % (INDEX_FILE, len(runbooks)))
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    print("sretriage %s (python %s)" % (__version__, sys.version.split()[0]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sretriage",
        description="Triagem baseada em evidência para a biblioteca de runbooks operacionais.",
    )
    parser.add_argument("--version", action="version", version="sretriage %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="roda todos os checks e gera o relatório markdown")
    run_parser.add_argument("--target", action="append", default=[], help="URL a verificar (repetível)")
    run_parser.add_argument(
        "--target-host", action="append", default=[], help="host ou IP a verificar (repetível)"
    )
    run_parser.add_argument("--out", default=None, help="diretório do relatório (ex.: reports/)")
    run_parser.add_argument("--timeout", type=float, default=5.0, help="timeout por check, em segundos")
    run_parser.set_defaults(func=cmd_run)

    check_parser = sub.add_parser("check-runbooks", help="valida front matter, seções e links")
    check_parser.add_argument("--root", default=".", help="raiz do repositório")
    check_parser.set_defaults(func=cmd_check_runbooks)

    index_parser = sub.add_parser("index", help="regenera a tabela de runbooks/README.md")
    index_parser.add_argument("--root", default=".", help="raiz do repositório")
    index_parser.add_argument("--check", action="store_true", help="falha se o índice estiver desatualizado")
    index_parser.set_defaults(func=cmd_index)

    version_parser = sub.add_parser("version", help="mostra a versão")
    version_parser.set_defaults(func=cmd_version)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)
