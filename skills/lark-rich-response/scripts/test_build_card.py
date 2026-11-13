#!/usr/bin/env python3
"""Regression checks for compact Lark card heading spacing."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).parent / "build_card.py"
SPEC = importlib.util.spec_from_file_location("build_card", SCRIPT)
assert SPEC and SPEC.loader
build_card_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_card_module)


def test_heading_and_body_use_one_controlled_break() -> None:
    card = build_card_module.build_card(
        {
            "level": "L2",
            "theme": "green",
            "title": "排版回归测试",
            "summary": "标题下方不应出现空白段落。",
            "sections": [
                {
                    "type": "markdown",
                    "title": "修复内容",
                    "content": "使用一次受控换行连接标题和正文。",
                }
            ],
        }
    )

    conclusion = card["body"]["elements"][0]["content"]
    section = card["body"]["elements"][2]["content"]

    assert conclusion == "**结论**<br>标题下方不应出现空白段落。"
    assert section == "**修复内容**<br>使用一次受控换行连接标题和正文。"
    assert "\n\n" not in conclusion
    assert "\n\n" not in section


def test_callback_controls_are_rejected() -> None:
    card = build_card_module.build_card(
        {
            "level": "L2",
            "theme": "blue",
            "title": "展示卡片边界测试",
            "summary": "交互选择应交给宿主环境的提问机制。",
            "sections": [{"type": "markdown", "content": "只展示信息。"}],
        }
    )
    card["body"]["elements"].append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "继续"},
            "value": {"choice": "continue"},
        }
    )

    try:
        build_card_module.validate_card(card)
    except build_card_module.CardError as error:
        assert "unsupported display-only element: button" in str(error)
    else:
        raise AssertionError("callback-style button must be rejected")


def test_semantic_accents_and_icons_are_preserved_without_being_required() -> None:
    card = build_card_module.build_card(
        {
            "level": "L2",
            "theme": "blue",
            "title": "🔗 语义强调回归测试",
            "summary": "<font color='blue'>结论：</font>正文颜色应原样保留。",
            "sections": [
                {
                    "type": "markdown",
                    "title": "🎯 主链路",
                    "content": (
                        "<font color='blue'>① 召回</font><br>↓<br>"
                        "<font color='orange'>② 过滤</font><br>↓<br>"
                        "<font color='green'>③ 选中</font>"
                    ),
                }
            ],
        }
    )

    conclusion = card["body"]["elements"][0]["content"]
    section = card["body"]["elements"][2]["content"]

    assert "<font color='blue'>结论：</font>" in conclusion
    assert "🎯" in section
    assert "①" in section and "↓" in section
    assert "<font color='orange'>② 过滤</font>" in section
    assert "<font color='green'>③ 选中</font>" in section

    neutral_card = build_card_module.build_card(
        {
            "level": "L2",
            "theme": "blue",
            "title": "中性卡片仍然合法",
            "summary": "没有状态差异时可以有意保持中性。",
            "sections": [{"type": "markdown", "content": "普通说明。"}],
        }
    )
    build_card_module.validate_card(neutral_card)


def assessment_spec() -> dict:
    return json.loads((SCRIPT.parents[1] / "assets" / "spec-template.json").read_text())


def test_assessment_preserves_header_verdicts_and_evidence() -> None:
    spec = assessment_spec()
    card = build_card_module.build_card(spec)
    assert card["header"]["subtitle"]["content"] == spec["subtitle"]
    assert card["header"]["text_tag_list"][0]["text"]["content"] == spec["status_tag"]
    table = next(e for e in card["body"]["elements"] if e["tag"] == "table")
    assert table["rows"] == spec["sections"][0]["rows"]
    assert all(c["data_type"] == "lark_md" for c in table["columns"])
    panel = next(e for e in card["body"]["elements"] if e["tag"] == "collapsible_panel")
    assert panel["expanded"] is False
    assert panel["header"]["icon_position"] == "right"
    assert panel["elements"][0]["content"] == spec["sections"][-1]["content"]


def test_first_level_sections_are_divided_by_default_and_can_opt_out() -> None:
    spec = assessment_spec()
    spec["sections"] = [
        {"type": "markdown", "title": "🧭 判断", "content": "有已确认的结论。"},
        {"type": "markdown", "title": "📌 风险", "content": "有未核验的边界。"},
        {"type": "markdown", "title": "✅ 后续", "content": "先核对边界。"},
    ]
    card = build_card_module.build_card(spec)
    assert sum(e["tag"] == "hr" for e in card["body"]["elements"]) == 3
    assert card["body"]["elements"][-1]["tag"] != "hr"
    spec["sections"][0]["separator_after"] = False
    card = build_card_module.build_card(spec)
    assert sum(e["tag"] == "hr" for e in card["body"]["elements"]) == 2


def test_degraded_assessment_produces_actionable_hints() -> None:
    spec = assessment_spec()
    spec.pop("subtitle")
    spec.pop("status_tag")
    spec["sections"][0].pop("title")
    spec["sections"][0]["rows"] = [
        {"question": "卡片", "result": "本来应当先给出判断，但实际却把整个分析经过和检查记录全部写在了这个单元格里面，导致右侧多次折行、左侧空白很大。"}
    ]
    # Input remains a legal card; these are authoring hints, not new safety gates.
    build_card_module.build_card(spec)
    codes = {w["code"] for w in build_card_module.presentation_warnings(spec)}
    assert {"HEADER_SCOPE", "HEADER_STATUS", "SECTION_ANCHOR", "TABLE_BALANCE"} <= codes


def test_bundled_examples_have_no_presentation_hints() -> None:
    for name in ["spec-template.json", "chain-example.json"]:
        spec = json.loads((SCRIPT.parents[1] / "assets" / name).read_text())
        build_card_module.build_card(spec)
        assert build_card_module.presentation_warnings(spec) == [], name


def test_skill_local_references_resolve() -> None:
    root = SCRIPT.parents[1]
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", (root / "SKILL.md").read_text())
    for link in links:
        if not link.startswith(("http:", "https:", "#")):
            assert (root / link.split("#", 1)[0]).is_file(), link


def test_short_neutral_card_does_not_require_decoration() -> None:
    spec = {
        "level": "L2", "title": "核验结果", "summary": "接口签名一致。",
        "sections": [{"type": "markdown", "content": "已对照两个版本的公开定义。"}],
    }
    original = json.dumps(spec)
    card = build_card_module.build_card(spec)
    assert build_card_module.presentation_warnings(spec) == []
    assert "text_tag_list" not in card["header"]
    assert json.dumps(spec) == original


def test_visible_text_ignores_markup_and_link_target_length() -> None:
    text = '<font color="green">已核验</font> [`symbol`](https://example.com/' + 'a' * 250 + ')'
    assert build_card_module.visible_text(text) == "已核验 symbol"


def test_long_prose_and_highlights_are_hints_not_rewrites() -> None:
    spec = assessment_spec()
    spec["summary"] = '<font color="orange">' + "较长的风险说明" * 8 + '</font>'
    spec["sections"][2]["content"] = "同一个段落不断重复解释过程。" * 20
    spec["sections"][0]["rows"][0]["result"] = "过长的表格解释。" * 25
    original = json.dumps(spec)
    codes = {w["code"] for w in build_card_module.presentation_warnings(spec)}
    assert {"LONG_ACCENT", "LONG_TEXT", "LONG_CELL"} <= codes
    assert json.dumps(spec) == original


def test_cli_report_does_not_claim_visual_validation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source, output, report = root / "spec.json", root / "card.json", root / "report.json"
        source.write_text(json.dumps(assessment_spec()))
        process = subprocess.run(
            [sys.executable, str(SCRIPT), "--spec", str(source), "--output", str(output), "--design-report", str(report)],
            capture_output=True, text=True,
        )
        assert process.returncode == 0, process.stderr
        result = json.loads(report.read_text())
        assert result["structural_validation"] == "passed"
        assert result["visual_review"] == "not_performed"
        build_card_module.validate_card(json.loads(output.read_text()))


def test_foreign_document_tags_are_rejected_at_all_content_entries() -> None:
    for tag in ['b', 'strong', 'span', 'p', 'table', 'pre', 'whiteboard']:
        for position in ['summary', 'footer', 'markdown', 'table', 'evidence']:
            spec = assessment_spec()
            bad = f'<{tag}>unexpected</{tag}>'
            if position in ['summary', 'footer']:
                spec[position] = bad
            elif position == 'markdown':
                spec['sections'][2]['content'] = bad
            elif position == 'table':
                spec['sections'][0]['rows'][0]['result'] = bad
            else:
                spec['sections'][-1]['content'] = bad
            try:
                build_card_module.build_card(spec)
            except build_card_module.CardError as e:
                assert 'foreign document/HTML tag' in str(e)
            else:
                raise AssertionError((tag, position))


def test_direct_card_validation_cannot_bypass_text_validation() -> None:
    card = build_card_module.build_card(assessment_spec())
    card['body']['elements'][0]['content'] = '<b>wrong format</b>'
    try:
        build_card_module.validate_card(card)
    except build_card_module.CardError:
        pass
    else:
        raise AssertionError('edited card bypassed validation')


def test_code_examples_escaped_literals_and_native_tags_are_not_rewritten() -> None:
    examples = [
        '`<b>literal</b>`', '``code `<b>` ``', '```html\n<b>sample</b>\n```',
        '~~~xml\n<whiteboard/>\n~~~', '&lt;b&gt;literal&lt;/b&gt;', r'\<b>literal\</b>',
        '<font color="green">**verified**</font><br><at id="ou_example"></at>',
        'Use `List<T>` when a < b and b > c.',
    ]
    for text in examples:
        spec = assessment_spec()
        spec['summary'] = text
        card = build_card_module.build_card(spec)
        assert card['body']['elements'][0]['content'].endswith(text)
    # A closed code sample must not hide later foreign markup.
    try:
        build_card_module.validate_text('```xml\n<b>literal</b>\n```\n<b>wrong</b>', 'test')
    except build_card_module.CardError:
        pass
    else:
        raise AssertionError('code fence swallowed later prose')


def test_preset_produces_comparisons_and_collapsed_evidence_from_facts() -> None:
    for preset, key in [('assessment', 'findings'), ('delivery', 'deliverables')]:
        spec = {'level': 'L2', 'preset': preset, 'title': '📝 修复结果', 'subtitle': '文档与卡片',
                'status_tag': '待评审', 'theme': 'blue', 'summary': '已修复规则；图示仍有阻碍。',
                key: [{'label': '模板保护', 'verdict': '通过', 'tone': 'green', 'detail': '默认控件保持原样'},
                      {'label': 'MindAI', 'verdict': '未完成', 'tone': 'orange', 'detail': '网关不可达'}],
                'evidence': '核对范围：当前文档。'}
        original = json.dumps(spec)
        card = build_card_module.build_card(spec)
        table = next(e for e in card['body']['elements'] if e['tag'] == 'table')
        assert len(table['columns']) == 2 and len(table['rows']) == 2
        assert table['rows'][1]['result'].startswith('<font color="orange">**未完成**')
        assert card['body']['elements'][-1]['tag'] == 'collapsible_panel'
        assert not card['body']['elements'][-1]['expanded']
        assert json.dumps(spec) == original


def test_preset_omits_empty_sections_and_does_not_invent_status() -> None:
    spec = {'level': 'L2', 'preset': 'delivery', 'title': '接口结果', 'summary': '接口一致。',
            'deliverables': [{'label': '接口签名', 'verdict': '一致'}]}
    card = build_card_module.build_card(spec)
    assert all(e['tag'] != 'table' for e in card['body']['elements'])
    assert 'text_tag_list' not in card['header']
    assert len(card['body']['elements']) == 3
    spec['sections'] = [{'type': 'markdown', 'content': 'discard preset'}]
    try:
        build_card_module.build_card(spec)
    except build_card_module.CardError:
        pass
    else:
        raise AssertionError('preset can silently degrade into arbitrary prose')


def test_foreign_markup_is_not_hidden_by_presentation_measurement() -> None:
    assert '<b>' in build_card_module.visible_text('<b>incorrect</b>')


def test_recent_summary_emphasis_boundaries_are_reported_without_rewriting() -> None:
    for text in [
        '**有这个风险，而且方案中的倾向会传递到后续实现。**我之前概括得太宽。',
        '**保留现有流程，补强两项调研。**结论进入已有技术方案。',
        '我的判断是：**现状调研停在“代码怎么写”。**这可能导致遗漏。',
    ]:
        spec = assessment_spec()
        spec['summary'] = text
        original = json.dumps(spec)
        warnings = build_card_module.presentation_warnings(spec)
        assert any(w['code'] == 'EMPHASIS_BOUNDARY' and w['path'] == 'summary' for w in warnings)
        card = build_card_module.build_card(spec)
        assert card['body']['elements'][0]['content'].endswith(text)
        assert json.dumps(spec) == original


def test_emphasis_hint_covers_body_tables_footer_and_collapsed_details() -> None:
    for position in ['markdown', 'table', 'footer', 'evidence']:
        spec = assessment_spec()
        text = '**结论。**后续内容'
        if position == 'markdown':
            spec['sections'][2]['content'] = text
        elif position == 'table':
            spec['sections'][0]['rows'][0]['result'] = text
        elif position == 'footer':
            spec['footer'] = text
        else:
            spec['sections'][-1]['content'] = text
        assert any(w['code'] == 'EMPHASIS_BOUNDARY' for w in build_card_module.presentation_warnings(spec)), position


def test_safe_emphasis_and_literal_code_do_not_raise_boundary_hints() -> None:
    for text in [
        '**结论**。后续内容', '**结论。** 后续内容', '**结论。**<br>后续内容',
        '**结论。**\n后续内容', '**结论。**', '前文：**结论**后续',
        '`**结论。**后续内容`', '``**结论。**后续内容``',
        '```markdown\n**结论。**后续内容\n```', '~~~md\n**结论。**后续内容\n~~~',
        r'\*\*结论。\*\*后续内容', '<font color="blue">**结论。**</font>后续内容',
    ]:
        assert not build_card_module.has_unsafe_strong_boundary(text), text
    assert build_card_module.has_unsafe_strong_boundary('```md\n**示例。**文字\n```\n**结论。**后续内容')


if __name__ == "__main__":
    tests = [function for name, function in sorted(globals().items()) if name.startswith("test_") and callable(function)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} rich response regression tests passed")
