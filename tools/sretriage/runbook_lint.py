"""Structural lint for the runbook library.

The point of this repository is that a runbook is a *validated* artifact, not a
document nobody reads. Everything a runbook must contain is enforced here, and
the same code backs ``sretriage check-runbooks``, ``sretriage index`` and the
test suite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REQUIRED_KEYS: Tuple[str, ...] = (
    "id",
    "title",
    "severity",
    "services",
    "slo_impact",
    "last_reviewed",
    "owner",
)

REQUIRED_SECTIONS: Tuple[str, ...] = (
    "Sintomas",
    "Impacto no SLO",
    "Detecção",
    "Diagnóstico",
    "Mitigação",
    "Escalonamento",
    "Verificação",
    "Prevenção",
    "Referências",
)

ALLOWED_SEVERITY: Tuple[str, ...] = ("critical", "high", "medium", "low")

ALLOWED_SLO_IMPACT: Tuple[str, ...] = (
    "availability",
    "latency",
    "error-rate",
    "throughput",
    "freshness",
    "durability",
    "cost",
)

FORBIDDEN_TOKENS: Tuple[str, ...] = ("TODO", "TBD", "FIXME", "XXX", "lorem ipsum")

MIN_SECTION_CHARS = 40

FRONT_MATTER_DELIMITER = "---"
INDEX_BEGIN = "<!-- BEGIN GENERATED INDEX -->"
INDEX_END = "<!-- END GENERATED INDEX -->"

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_FENCE_RE = re.compile(r"^(\s*)```(.*)$")
_NUMBERED_RE = re.compile(r"^\s{0,3}\d+\.\s+\S", re.MULTILINE)
_ALERT_RE = re.compile(r"^\*\*Alerta:\*\*\s*`?([^`\n]+?)`?\s*$", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class Problem:
    """One lint violation, always tied to a file."""

    path: str
    message: str

    def render(self) -> str:
        return "%s: %s" % (self.path, self.message)


@dataclass
class Runbook:
    """A parsed runbook: front matter, sections and derived index fields."""

    path: Path
    rel_path: str
    area: str
    meta: Dict[str, str] = field(default_factory=dict)
    sections: Dict[str, str] = field(default_factory=dict)
    body: str = ""
    problems: List[Problem] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.meta.get("id", "")

    @property
    def title(self) -> str:
        return self.meta.get("title", "")

    @property
    def severity(self) -> str:
        return self.meta.get("severity", "")

    @property
    def slo_impact(self) -> str:
        return self.meta.get("slo_impact", "")

    @property
    def services(self) -> str:
        return self.meta.get("services", "")

    @property
    def alert(self) -> str:
        found = _ALERT_RE.search(self.sections.get("Detecção", ""))
        if found:
            return found.group(1).strip()
        return ""


def _parse_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_front_matter(text: str) -> Tuple[Dict[str, str], str, Optional[str]]:
    """Return ``(meta, body, error)`` for a YAML-ish front matter block.

    Only flat ``key: value`` pairs and inline lists are supported on purpose:
    the lint must stay dependency-free so it runs on a bare Python install.
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return {}, text, "missing front matter block (file must start with '---')"

    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONT_MATTER_DELIMITER:
            closing = index
            break
    if closing is None:
        return {}, text, "front matter block is not closed with '---'"

    meta: Dict[str, str] = {}
    for offset, line in enumerate(lines[1:closing], start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            return {}, text, "line %d is not a 'key: value' pair: %s" % (offset, stripped)
        meta[key.strip()] = _parse_value(value)

    body = "\n".join(lines[closing + 1 :])
    return meta, body, None


def split_sections(body: str) -> Tuple[List[str], Dict[str, str]]:
    """Return the ``##`` headings in order and their bodies."""

    headings: List[str] = []
    sections: Dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(body))
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        headings.append(heading)
        sections[heading] = body[match.end() : end].strip()
    return headings, sections


def fenced_blocks(text: str) -> List[Tuple[Optional[str], str]]:
    """Return ``(language, content)`` for every fenced code block.

    ``language`` is ``None`` when the fence has no info string, which the lint
    treats as an error: a command without a language is a command nobody can
    copy out of a renderer reliably.
    """

    blocks: List[Tuple[Optional[str], str]] = []
    language: Optional[str] = None
    buffer: List[str] = []
    inside = False
    for line in text.splitlines():
        match = _FENCE_RE.match(line)
        if match and not inside:
            inside = True
            language = match.group(2).strip() or None
            buffer = []
            continue
        if match and inside:
            blocks.append((language, "\n".join(buffer)))
            inside = False
            language = None
            buffer = []
            continue
        if inside:
            buffer.append(line)
    if inside:
        blocks.append((language, "\n".join(buffer)))
    return blocks


def lint_text(rel_path: str, text: str, today: Optional[date] = None) -> Tuple[Runbook, List[Problem]]:
    """Lint one runbook and return it parsed together with its problems."""

    today = today or datetime.now().date()
    area = rel_path.split("/")[1] if "/" in rel_path else "root"
    problems: List[Problem] = []

    meta, body, error = parse_front_matter(text)
    if error:
        problems.append(Problem(rel_path, error))
    runbook = Runbook(path=Path(rel_path), rel_path=rel_path, area=area, meta=meta, body=body)

    for key in REQUIRED_KEYS:
        if not meta.get(key):
            problems.append(Problem(rel_path, "front matter is missing '%s'" % key))

    if meta.get("severity") and meta["severity"] not in ALLOWED_SEVERITY:
        problems.append(
            Problem(
                rel_path,
                "severity '%s' is not one of %s" % (meta["severity"], ", ".join(ALLOWED_SEVERITY)),
            )
        )

    if meta.get("slo_impact") and meta["slo_impact"] not in ALLOWED_SLO_IMPACT:
        problems.append(
            Problem(
                rel_path,
                "slo_impact '%s' is not one of %s" % (meta["slo_impact"], ", ".join(ALLOWED_SLO_IMPACT)),
            )
        )

    services = meta.get("services", "")
    if services and not (services.startswith("[") and services.endswith("]")):
        problems.append(Problem(rel_path, "services must be an inline list, e.g. [kubernetes]"))

    reviewed = meta.get("last_reviewed", "")
    if reviewed:
        try:
            parsed = datetime.strptime(reviewed, "%Y-%m-%d").date()
        except ValueError:
            problems.append(Problem(rel_path, "last_reviewed '%s' is not a valid YYYY-MM-DD date" % reviewed))
        else:
            if parsed > today:
                problems.append(Problem(rel_path, "last_reviewed %s is in the future" % reviewed))

    if meta.get("id") and not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", meta["id"]):
        problems.append(Problem(rel_path, "id '%s' must be lowercase kebab-case" % meta["id"]))

    headings, sections = split_sections(body)
    runbook.sections = sections

    if headings != list(REQUIRED_SECTIONS):
        missing = [name for name in REQUIRED_SECTIONS if name not in headings]
        extra = [name for name in headings if name not in REQUIRED_SECTIONS]
        if missing:
            problems.append(Problem(rel_path, "missing required sections: %s" % ", ".join(missing)))
        if extra:
            problems.append(Problem(rel_path, "unexpected sections: %s" % ", ".join(extra)))
        if not missing and not extra:
            problems.append(
                Problem(
                    rel_path,
                    "sections are out of order: expected %s" % " -> ".join(REQUIRED_SECTIONS),
                )
            )

    for name in REQUIRED_SECTIONS:
        content = sections.get(name)
        if content is not None and len(content) < MIN_SECTION_CHARS:
            problems.append(
                Problem(rel_path, "section '%s' is too thin (< %d chars)" % (name, MIN_SECTION_CHARS))
            )

    for token in FORBIDDEN_TOKENS:
        # case-sensitive on purpose: Portuguese "todo/todos" must not trip a TODO check
        if re.search(r"\b%s\b" % re.escape(token), body):
            problems.append(Problem(rel_path, "placeholder token '%s' found" % token))

    blocks = fenced_blocks(body)
    if not blocks:
        problems.append(Problem(rel_path, "no fenced code block: a runbook without commands is a myth"))
    for language, content in blocks:
        if not language:
            snippet = content.strip().splitlines()[0][:60] if content.strip() else "(empty)"
            problems.append(Problem(rel_path, "fenced code block without language: %s" % snippet))

    diagnostico_blocks = fenced_blocks(sections.get("Diagnóstico", ""))
    if not diagnostico_blocks:
        problems.append(Problem(rel_path, "section 'Diagnóstico' has no command block"))
    mitigacao_blocks = fenced_blocks(sections.get("Mitigação", ""))
    if not mitigacao_blocks:
        problems.append(Problem(rel_path, "section 'Mitigação' has no command block"))

    if not _NUMBERED_RE.search(sections.get("Diagnóstico", "")):
        problems.append(Problem(rel_path, "section 'Diagnóstico' needs at least one numbered step"))

    if not _ALERT_RE.search(sections.get("Detecção", "")):
        problems.append(Problem(rel_path, "section 'Detecção' needs a '**Alerta:** `name`' line"))

    escalonamento = sections.get("Escalonamento", "").lower()
    if escalonamento and "plantão" not in escalonamento and "on-call" not in escalonamento:
        problems.append(
            Problem(rel_path, "section 'Escalonamento' must say when to page the plantão/on-call")
        )

    mitigacao = sections.get("Mitigação", "").lower()
    if mitigacao and "risco" not in mitigacao:
        problems.append(Problem(rel_path, "section 'Mitigação' must declare the Risco involved"))

    runbook.problems = problems
    return runbook, problems


def discover(runbooks_dir: Path) -> List[Path]:
    """Every runbook markdown file, ``README.md`` excluded, sorted by path."""

    paths = [
        path for path in sorted(runbooks_dir.rglob("*.md")) if path.name != "README.md" and path.is_file()
    ]
    return paths


def load_runbooks(runbooks_dir: Path, today: Optional[date] = None) -> List[Runbook]:
    """Parse and lint every runbook in the library."""

    runbooks: List[Runbook] = []
    for path in discover(runbooks_dir):
        rel_path = path.relative_to(runbooks_dir.parent).as_posix()
        runbook, _ = lint_text(rel_path, path.read_text(encoding="utf-8"), today=today)
        runbook.path = path
        runbooks.append(runbook)
    return runbooks


def lint_library(runbooks_dir: Path, today: Optional[date] = None) -> Tuple[List[Runbook], List[Problem]]:
    """Lint the whole library, including cross-file rules (unique ids)."""

    if not runbooks_dir.is_dir():
        return [], [Problem(str(runbooks_dir), "runbooks directory not found")]

    runbooks = load_runbooks(runbooks_dir, today=today)
    problems: List[Problem] = []
    seen: Dict[str, str] = {}
    for runbook in runbooks:
        problems.extend(runbook.problems)
        if runbook.id:
            if runbook.id in seen:
                problems.append(
                    Problem(
                        runbook.rel_path, "duplicate id '%s' (also in %s)" % (runbook.id, seen[runbook.id])
                    )
                )
            else:
                seen[runbook.id] = runbook.rel_path
    return runbooks, problems


def slugify(heading: str) -> str:
    """Approximate GitHub's anchor slug so anchors can be validated."""

    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\s\-À-ÿ]", "", slug)
    slug = slug.replace(" ", "-")
    return slug


def check_internal_links(root: Path, extra_files: Sequence[Path] = ()) -> List[Problem]:
    """Validate every relative markdown link (and anchor) resolves on disk."""

    problems: List[Problem] = []
    candidates: List[Path] = []
    for pattern in ("*.md", "docs/*.md", "templates/*.md", "runbooks/*.md", "runbooks/*/*.md"):
        candidates.extend(sorted(root.glob(pattern)))
    candidates.extend(extra_files)

    seen_files = set()
    for path in candidates:
        if not path.is_file() or path in seen_files:
            continue
        seen_files.add(path)
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root).as_posix()
        for raw_target in _MD_LINK_RE.findall(text):
            target = raw_target.strip()
            if not target:
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue  # absolute URL, audited by the weekly link audit instead
            if target.startswith("#"):
                if not _anchor_exists(path, slugify(target[1:])):
                    problems.append(Problem(rel, "anchor not found in this file: %s" % target))
                continue
            file_part, _, anchor = target.partition("#")
            resolved = (path.parent / file_part).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                problems.append(Problem(rel, "link escapes the repository: %s" % target))
                continue
            if not resolved.exists():
                problems.append(Problem(rel, "relative link does not resolve: %s" % target))
                continue
            if anchor and resolved.suffix == ".md" and not _anchor_exists(resolved, slugify(anchor)):
                problems.append(Problem(rel, "anchor not found in %s: %s" % (file_part, anchor)))
    return problems


def _anchor_exists(path: Path, slug: str) -> bool:
    return any(slugify(heading) == slug for heading in _HEADING_RE.findall(path.read_text(encoding="utf-8")))


def render_index(runbooks: Sequence[Runbook]) -> str:
    """Markdown table: area, symptom, runbook, firing alert, SLO impact."""

    ordered = sorted(runbooks, key=lambda item: (item.area, item.id))
    lines = [
        "| Área | Sintoma | Runbook | Alerta que dispara | SLO impactado |",
        "| --- | --- | --- | --- | --- |",
    ]
    for runbook in ordered:
        rel = runbook.rel_path.replace("runbooks/", "", 1)
        link = "`%s` → [%s](%s)" % (runbook.id, rel, rel)
        lines.append(
            "| %s | %s | %s | `%s` | %s |"
            % (
                runbook.area,
                runbook.title,
                link,
                runbook.alert or "n/a",
                runbook.slo_impact,
            )
        )
    lines.append("")
    lines.append("_%d runbooks, all of them lint-clean._" % len(ordered))
    return "\n".join(lines)


def replace_index(text: str, generated: str) -> str:
    """Swap the generated block, adding the markers if they are missing."""

    begin = text.find(INDEX_BEGIN)
    end = text.find(INDEX_END)
    if begin == -1 or end == -1 or end < begin:
        return text.rstrip() + "\n\n" + INDEX_BEGIN + "\n" + generated + "\n" + INDEX_END + "\n"
    block = INDEX_BEGIN + "\n" + generated + "\n" + INDEX_END
    return text[:begin] + block + text[end + len(INDEX_END) :]


def extract_index(text: str) -> Optional[str]:
    """Return the current generated block, or ``None`` when absent."""

    begin = text.find(INDEX_BEGIN)
    end = text.find(INDEX_END)
    if begin == -1 or end == -1 or end < begin:
        return None
    return text[begin + len(INDEX_BEGIN) : end].strip()
