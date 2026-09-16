"""The exit-code contract of the CLI is part of the public interface."""

from __future__ import annotations

from pathlib import Path

from sretriage.checks.base import CheckResult
from sretriage.cli import exit_code_for, main

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_exit_zero_without_failures() -> None:
    results = [
        CheckResult(name="disk", status="OK", summary="ok", targeted=True),
        CheckResult(name="aws", status="SKIPPED", summary="aws cli not available"),
    ]
    assert exit_code_for(results) == 0


def test_exit_one_on_fail() -> None:
    results = [
        CheckResult(name="http", status="FAIL", summary="500", targeted=True),
        CheckResult(name="disk", status="OK", summary="ok"),
    ]
    assert exit_code_for(results) == 1


def test_exit_two_when_no_target_was_evaluated() -> None:
    results = [
        CheckResult(name="http", status="SKIPPED", summary="unreachable", targeted=True),
        CheckResult(name="dns", status="SKIPPED", summary="unresolvable", targeted=True),
        CheckResult(name="disk", status="OK", summary="ok"),
    ]
    assert exit_code_for(results) == 2


def test_skipped_tooling_never_pushes_the_code_to_two() -> None:
    results = [
        CheckResult(name="k8s", status="SKIPPED", summary="kubectl not available"),
        CheckResult(name="aws", status="SKIPPED", summary="aws cli not available"),
        CheckResult(name="disk", status="WARN", summary="87% full", targeted=True),
    ]
    assert exit_code_for(results) == 0


def test_check_runbooks_on_the_real_library_passes(capsys) -> None:
    code = main(["check-runbooks", "--root", str(REPO_ROOT)])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK: front matter, seções, comandos e links internos verificados" in out


def test_check_runbooks_fails_on_a_broken_runbook(tmp_path: Path, capsys) -> None:
    target = tmp_path / "runbooks" / "kubernetes"
    target.mkdir(parents=True)
    (target / "broken.md").write_text(
        "---\nid: k8s-broken\ntitle: Quebrado\nseverity: high\n---\n\n# Quebrado\n\n## Sintomas\n\n- nada\n",
        encoding="utf-8",
    )
    code = main(["check-runbooks", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "problema(s)" in out
    assert "front matter is missing" in out


def test_index_check_passes_on_the_generated_file(capsys) -> None:
    code = main(["index", "--check", "--root", str(REPO_ROOT)])
    out = capsys.readouterr()
    assert code == 0
    assert "está atualizado" in out.out


def test_index_check_fails_when_the_table_is_stale(tmp_path: Path, capsys) -> None:
    runbook_dir = tmp_path / "runbooks" / "kubernetes"
    runbook_dir.mkdir(parents=True)
    source = (REPO_ROOT / "runbooks" / "kubernetes" / "oomkilled.md").read_text(encoding="utf-8")
    (runbook_dir / "oomkilled.md").write_text(source, encoding="utf-8")
    (tmp_path / "runbooks" / "README.md").write_text("# Índice\n", encoding="utf-8")

    assert main(["index", "--root", str(tmp_path)]) == 0
    assert main(["index", "--check", "--root", str(tmp_path)]) == 0

    (tmp_path / "runbooks" / "README.md").write_text("# Índice\n\nnada aqui\n", encoding="utf-8")
    code = main(["index", "--check", "--root", str(tmp_path)])
    capsys.readouterr()
    assert code == 1


def test_version_command(capsys) -> None:
    assert main(["version"]) == 0
    assert "sretriage" in capsys.readouterr().out


def test_no_command_prints_help(capsys) -> None:
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()
