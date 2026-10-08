"""Task descriptions keep one section contract across authoring and browsing."""

import pytest

from benchmarking.task_documents import parse_task_description

pytestmark = pytest.mark.unit

ENGLISH = """# Circuit layout

## Objective
Implement the circuit.

```markdown
## Example heading inside a code block
```

### Additional detail
Keep the original Markdown.

## Inputs and Interface
Use [the circuit](materials/circuit.spice).

## Operating Conditions
Use 1 V at 27 C.

## Physical Requirements
Pass DRC and LVS.

## Electrical Requirements and Scoring
Preserve function; score quality.

## Tools and Submission
Submit output/final.gds.
"""


def test_description_preserves_markdown_and_ignores_example_headings():
    sections = parse_task_description(ENGLISH)
    assert sections["Objective"] == (
        "Implement the circuit.\n\n```markdown\n## Example heading inside a code block\n```"
        "\n\n### Additional detail\nKeep the original Markdown.")
    assert sections["Inputs and Interface"] == "Use [the circuit](materials/circuit.spice)."
    assert sections["Operating Conditions"] == "Use 1 V at 27 C."
    assert sections["Tools and Submission"] == "Submit output/final.gds."


def test_markdown_heading_whitespace_does_not_hide_an_extra_section():
    text = ENGLISH.replace("## Physical Requirements", "   ##\tPhysical Requirements ###")
    assert parse_task_description(text)["Physical Requirements"] == "Pass DRC and LVS."
    with pytest.raises(ValueError, match="six level-two headings"):
        parse_task_description(ENGLISH + "\n  ##\tUnexpected section\nExtra content.\n")


def test_author_language_returns_the_same_section_keys():
    text = """# 版图任务
## 目标
实现电路。
## 输入与接口
按网表端口连接。
## 工作条件
电源为 1 V。
## 物理要求
通过 DRC 与 LVS。
## 电学要求与评分
按声明指标评分。
## 工具与提交
提交最终 GDS。
"""
    sections = parse_task_description(text, language="zh")
    assert sections["Objective"] == "实现电路。"
    assert sections["Physical Requirements"] == "通过 DRC 与 LVS。"
    with pytest.raises(ValueError, match="six level-two headings"):
        parse_task_description(text)


@pytest.mark.parametrize("changed", [
    ENGLISH.replace("## Objective\n", "## Objective and solve budget\n"),
    ENGLISH.replace("## Operating Conditions\n", ""),
    ENGLISH.replace("## Physical Requirements\n", "## Objective\n"),
    ENGLISH.replace("## Tools and Submission\n", "## Additional Section\n"),
])
def test_unrecognized_missing_or_duplicate_sections_fail_explicitly(changed):
    with pytest.raises(ValueError, match="six level-two headings"):
        parse_task_description(changed)


def test_empty_section_is_an_author_error():
    text = ENGLISH.replace("Pass DRC and LVS.", "")
    with pytest.raises(ValueError, match="Empty task description section: Physical Requirements"):
        parse_task_description(text)


def test_commented_headings_cannot_complete_the_document():
    text = ENGLISH.replace("## Physical Requirements", "<!--\n## Physical Requirements\n-->")
    with pytest.raises(ValueError, match="six level-two headings"):
        parse_task_description(text)
    with pytest.raises(ValueError, match="six level-two headings"):
        parse_task_description("<!--\n" + ENGLISH + "\n-->\n")


def test_setext_headings_follow_the_same_section_contract():
    text = ENGLISH.replace("## Physical Requirements", "Physical Requirements\n---------------------")
    assert parse_task_description(text)["Physical Requirements"] == "Pass DRC and LVS."
    with pytest.raises(ValueError, match="six level-two headings"):
        parse_task_description(ENGLISH + "\nUnexpected section\n------------------\nExtra content.\n")


def test_section_content_preserves_indented_code():
    content = "    ## Literal heading in a code example\n    Preserve this indentation."
    text = ENGLISH.replace("Implement the circuit.", content)
    assert parse_task_description(text)["Objective"].startswith(content + "\n")
