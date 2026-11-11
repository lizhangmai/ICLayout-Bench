"""Repository Markdown links resolve, and user guides stay inside docs/."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DOCUMENTS = sorted({ROOT / "README.md", ROOT / "README_CN.md", ROOT / "CONTRIBUTING.md",
                    ROOT / "AGENTS.md", ROOT / "tests" / "AGENTS.md", *DOCS.glob("*.md")})
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"\]\(([^)\s]+)\)|href=\"([^\"]+)\"")
EXPLICIT_ID = re.compile(r"<a id=\"([^\"]+)\"")


def prose(text):
    """Return lines outside fenced code blocks."""
    lines, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            lines.append(line)
    return lines


def anchors(path):
    """GitHub heading slugs, numbered on repetition, plus explicit HTML ids."""
    found = set(EXPLICIT_ID.findall(path.read_text()))
    counts = {}
    for line in prose(path.read_text()):
        heading = re.match(r"#{1,6} (.+)", line)
        if not heading:
            continue
        title = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading.group(1)).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
        found.add(slug if slug not in counts else f"{slug}-{counts[slug]}")
        counts[slug] = counts.get(slug, 0) + 1
    return found


def links(path):
    for line in prose(path.read_text()):
        for match in LINK.finditer(INLINE_CODE.sub("", line)):
            target = match.group(1) or match.group(2)
            if not target.startswith(("http://", "https://", "mailto:")):
                yield target


def test_anchor_slugs_follow_github_headings(tmp_path):
    page = tmp_path / "page.md"
    page.write_text('# AC response (`parameters.response`)\n## Usage\n## Usage\n'
                    '```\n# not a heading\n```\n<a id="kept"></a>\n### 快速开始\n')
    assert anchors(page) == {"ac-response-parametersresponse", "usage", "usage-1", "kept", "快速开始"}


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: str(path.relative_to(ROOT)))
def test_relative_links_and_anchors_resolve(document):
    broken = []
    for target in links(document):
        name, _, anchor = target.partition("#")
        resolved = (document.parent / name) if name else document
        if not resolved.exists():
            broken.append(f"{target}: missing file")
        elif anchor and resolved.suffix == ".md" and anchor not in anchors(resolved):
            broken.append(f"{target}: missing anchor")
    assert not broken, broken


@pytest.mark.parametrize("document", sorted(DOCS.glob("*.md")), ids=lambda path: path.name)
def test_user_guides_link_only_within_docs(document):
    outside = [target for target in links(document)
               if target.partition("#")[0]
               and not (document.parent / target.partition("#")[0]).resolve().is_relative_to(DOCS)]
    assert not outside, outside
