"""Relative links between runbooks, index, docs and templates must resolve."""

from __future__ import annotations

from pathlib import Path

import pytest
from sretriage.runbook_lint import check_internal_links, extract_index, load_runbooks, render_index

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_all_relative_links_in_the_repository_resolve() -> None:
    problems = check_internal_links(REPO_ROOT)
    assert problems == [], "\n".join(problem.render() for problem in problems)


def test_relative_link_to_missing_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("Veja [sumido](../runbooks/nao-existe.md).\n", encoding="utf-8")
    problems = check_internal_links(tmp_path)
    assert len(problems) == 1
    assert "does not resolve" in problems[0].message


def test_link_escaping_the_repository_is_reported(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("Veja [fora](../../../etc/hosts).\n", encoding="utf-8")
    problems = check_internal_links(tmp_path)
    assert any("escapes the repository" in problem.message for problem in problems)


def test_broken_anchor_is_reported(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# Título\n\n[ir](a.md#nao-existe)\n", encoding="utf-8")
    problems = check_internal_links(tmp_path)
    assert any("anchor not found" in problem.message for problem in problems)


def test_valid_anchor_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# Título\n\n[ir](a.md#título)\n", encoding="utf-8")
    assert check_internal_links(tmp_path) == []


def test_external_links_are_left_to_the_audit() -> None:
    text = "Veja [Kubernetes](https://kubernetes.io/docs/).\n"
    problems_root = Path(__file__).resolve().parent
    (problems_root / "_tmp_link_probe.md").write_text(text, encoding="utf-8")
    try:
        assert check_internal_links(REPO_ROOT) == []
    finally:
        (problems_root / "_tmp_link_probe.md").unlink()


def test_generated_index_links_point_to_existing_runbooks() -> None:
    index_text = (REPO_ROOT / "runbooks" / "README.md").read_text(encoding="utf-8")
    block = extract_index(index_text)
    assert block, "runbooks/README.md is missing the generated index block"
    runbooks = load_runbooks(REPO_ROOT / "runbooks")
    assert block.strip() == render_index(runbooks).strip()


@pytest.mark.parametrize("runbook", load_runbooks(REPO_ROOT / "runbooks"), ids=lambda item: item.id)
def test_index_lists_every_runbook(runbook) -> None:
    index_text = (REPO_ROOT / "runbooks" / "README.md").read_text(encoding="utf-8")
    assert runbook.rel_path.replace("runbooks/", "", 1) in index_text
