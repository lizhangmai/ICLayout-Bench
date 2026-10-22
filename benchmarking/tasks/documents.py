"""The six-section structure shared by task authors and presentation consumers."""

from markdown_it import MarkdownIt

TASK_SECTIONS = (
    "Objective",
    "Inputs and Interface",
    "Operating Conditions",
    "Physical Requirements",
    "Electrical Requirements and Scoring",
    "Tools and Submission",
)

_TITLES = {
    "en": TASK_SECTIONS,
    "zh": ("目标", "输入与接口", "工作条件", "物理要求", "电学要求与评分", "工具与提交"),
}


def parse_task_description(text: str, *, language: str = "en") -> dict[str, str]:
    """Validate six ordered, nonempty sections and return their original Markdown.

    Section keys always use TASK_SECTIONS. Authors select their document language;
    consumers do not infer sections from prose, synonyms or translated titles.
    """
    if language not in _TITLES:
        raise ValueError("Unsupported task description language: " + language)
    lines = text.splitlines(keepends=True)
    tokens = MarkdownIt("commonmark").parse(text)
    headings = [(token.map, tokens[index + 1].content)
                for index, token in enumerate(tokens)
                if token.type == "heading_open" and token.tag == "h2" and token.level == 0]
    expected = _TITLES[language]
    actual = tuple(title for _, title in headings)
    if actual != expected:
        raise ValueError("Task description requires six level-two headings in order: "
                         + "; ".join(expected) + ". Found: " + "; ".join(actual))
    sections = {}
    for number, (span, _) in enumerate(headings):
        stop = headings[number + 1][0][0] if number + 1 < len(headings) else len(lines)
        content = "".join(lines[span[1]:stop]).strip("\r\n")
        if not content.strip():
            raise ValueError("Empty task description section: " + expected[number])
        sections[TASK_SECTIONS[number]] = content
    return sections
