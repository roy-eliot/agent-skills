#!/usr/bin/env python3
"""Build and locally validate display-only Lark schema 2.0 cards."""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import string
import sys
import unicodedata
from pathlib import Path
from typing import Any


THEMES = {
    "blue",
    "wathet",
    "turquoise",
    "green",
    "yellow",
    "orange",
    "red",
    "carmine",
    "violet",
    "purple",
    "indigo",
    "grey",
    "default",
}
ROOT_TAGS = {"markdown", "hr", "table", "collapsible_panel", "img", "chart"}
NESTED_TAGS = {"markdown", "hr", "img", "chart", "collapsible_panel"}
# Document/HTML formatting is not card Markdown. Keep this deliberately scoped
# to known foreign formatting tags; this is not a full Lark Markdown parser.
FOREIGN_TAGS = set("b strong i em u del s span p div h1 h2 h3 h4 h5 h6 table thead tbody tr th td pre code blockquote ul ol li img source whiteboard callout title".split())


class CardError(ValueError):
    pass


def require(value: Any, message: str) -> Any:
    if value is None or value == "" or value == []:
        raise CardError(message)
    return value


def prose_only(text: str) -> str:
    """Mask fenced and inline code without changing the actual card content."""
    lines, fence = [], None
    for line in re.sub(r"<br\s*/?>", "\n", text, flags=re.I).splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", line):
                fence = None
            lines.append("\n")
        elif marker:
            fence = marker.group(1)
            lines.append("\n")
        else:
            lines.append(line)
    text = "".join(lines)
    return re.sub(r"(?<!`)(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)", " ", text)


def validate_text(text: Any, path: str) -> None:
    for match in re.finditer(r"(?<!\\)</?([a-zA-Z][\w-]*)(?:\s[^<>]*|\s*/?)>", prose_only(str(text))):
        if match.group(1).lower() in FOREIGN_TAGS:
            raise CardError(f"{path}: foreign document/HTML tag {match.group(0)!r}; use card Markdown (e.g. **bold**), or put literal markup in code")


def normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Named information layouts, rendered from facts rather than copied prose."""
    preset = spec.get("preset")
    if preset is None:
        return spec
    if preset not in {"assessment", "delivery"}:
        raise CardError("preset must be assessment or delivery")
    if "sections" in spec:
        raise CardError("a preset derives sections from facts; do not also supply sections")
    result = copy.deepcopy(spec)
    sections = []
    groups = (("findings", "🧭 核心判断", "判断对象"), ("boundaries", "📌 边界与处理", "边界")) if preset == "assessment" else (("deliverables", "📝 交付内容", "交付项"), ("checks", "🔎 验证结果", "检查项"))
    for field, title, column_label in groups:
        items = spec.get(field, [])
        if not isinstance(items, list):
            raise CardError(f"{field} must be an array")
        rows = []
        for item in items:
            if not isinstance(item, dict):
                raise CardError(f"{field} entries must be objects")
            label = str(require(item.get("label"), f"{field} requires label"))
            verdict = str(require(item.get("verdict"), f"{field} requires factual verdict"))
            tone = item.get("tone")
            if tone not in {None, "blue", "orange", "green", "red"}:
                raise CardError("verdict tone must be blue, orange, green, red or omitted")
            rendered = f"**{verdict}**"
            if tone:
                rendered = f'<font color="{tone}">{rendered}</font>'
            if item.get("detail"):
                rendered += "；" + str(item["detail"])
            rows.append({"item": label, "result": rendered})
        if len(rows) == 1:
            sections.append({"type": "markdown", "title": title, "content": rows[0]["item"] + "：" + rows[0]["result"]})
        elif rows:
            sections.append({"type": "table", "title": title, "columns": [{"name": "item", "display_name": column_label, "data_type": "lark_md"}, {"name": "result", "display_name": "结论与依据", "data_type": "lark_md"}], "rows": rows})
    if not sections:
        raise CardError(f"{preset} needs at least one factual item")
    if spec.get("next_action"):
        sections.append({"type": "markdown", "title": "📌 后续", "content": str(spec["next_action"])})
    if spec.get("evidence"):
        sections.append({"type": "collapsible", "title": "📂 证据与边界（点击展开）", "content": str(spec["evidence"])})
    result["sections"] = sections
    return result


def markdown(content: str, *, text_size: str = "normal") -> dict[str, Any]:
    return {"tag": "markdown", "content": content, "text_size": text_size}


def section_markdown(section: dict[str, Any]) -> dict[str, Any]:
    content = str(require(section.get("content"), "markdown section requires content"))
    title = section.get("title")
    if title:
        content = f"**{title}**<br>{content}"
    return markdown(content)


def section_table(section: dict[str, Any]) -> list[dict[str, Any]]:
    columns = require(section.get("columns"), "table section requires columns")
    rows = require(section.get("rows"), "table section requires rows")
    if not isinstance(columns, list) or not 2 <= len(columns) <= 4:
        raise CardError("table sections must contain 2 to 4 columns for mobile readability")
    names = set()
    for column in columns:
        if not isinstance(column, dict):
            raise CardError("each table column must be an object")
        name = str(require(column.get("name"), "table column requires name"))
        require(column.get("display_name"), f"table column {name} requires display_name")
        require(column.get("data_type"), f"table column {name} requires data_type")
        if name in names:
            raise CardError(f"duplicate table column name: {name}")
        names.add(name)
    if not isinstance(rows, list):
        raise CardError("table rows must be an array")
    for row in rows:
        if not isinstance(row, dict) or not set(row).issubset(names):
            raise CardError("table row keys must match declared column names")

    result: list[dict[str, Any]] = []
    if section.get("title"):
        result.append(markdown(f"**{section['title']}**"))
    result.append(
        {
            "tag": "table",
            "columns": columns,
            "rows": rows,
            "page_size": min(max(int(section.get("page_size", 5)), 1), 10),
            "row_height": section.get("row_height", "auto"),
            "header_style": {
                "background_style": "grey",
                "bold": True,
                "text_align": "left",
            },
        }
    )
    return result


def section_collapsible(section: dict[str, Any]) -> dict[str, Any]:
    title = str(require(section.get("title"), "collapsible section requires title"))
    content = str(require(section.get("content"), "collapsible section requires content"))
    if "展开" not in title:
        title = f"{title}（点击展开）"
    return {
        "tag": "collapsible_panel",
        "expanded": bool(section.get("expanded", False)),
        "border": {"color": "grey", "corner_radius": "8px"},
        "padding": "8px",
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "width": "fill",
            "icon": {
                "tag": "standard_icon",
                "token": "down-small-ccm_outlined",
                "color": "grey",
                "size": "16px",
            },
            "icon_position": "right",
            "icon_expanded_angle": 180,
        },
        "elements": [markdown(content)],
    }


def section_image(section: dict[str, Any]) -> list[dict[str, Any]]:
    img_key = str(require(section.get("img_key"), "image section requires img_key"))
    result: list[dict[str, Any]] = []
    if section.get("title"):
        result.append(markdown(f"**{section['title']}**"))
    result.append(
        {
            "tag": "img",
            "img_key": img_key,
            "alt": {
                "tag": "plain_text",
                "content": str(section.get("alt", section.get("title", "流程图"))),
            },
            "scale_type": "fit_horizontal",
            "preview": True,
        }
    )
    return result


def section_chart(section: dict[str, Any]) -> list[dict[str, Any]]:
    chart_spec = require(section.get("chart_spec"), "chart section requires chart_spec")
    if not isinstance(chart_spec, dict):
        raise CardError("chart_spec must be an object")
    result: list[dict[str, Any]] = []
    if section.get("title"):
        result.append(markdown(f"**{section['title']}**"))
    result.append(
        {
            "tag": "chart",
            "chart_spec": chart_spec,
            "aspect_ratio": section.get("aspect_ratio", "16:9"),
            "color_theme": section.get("color_theme", "brand"),
            "preview": True,
        }
    )
    return result


def build_card(spec: dict[str, Any]) -> dict[str, Any]:
    spec = normalize_spec(spec)
    level = spec.get("level")
    if level not in {"L2", "L3"}:
        raise CardError("level must be L2 or L3")
    theme = spec.get("theme", "blue")
    if theme not in THEMES:
        raise CardError(f"unsupported header theme: {theme}")

    title = str(require(spec.get("title"), "title is required"))
    summary = str(require(spec.get("summary"), "summary is required"))
    sections = spec.get("sections", [])
    if not isinstance(sections, list) or not sections:
        raise CardError("at least one section is required")

    header: dict[str, Any] = {
        "title": {"tag": "plain_text", "content": title},
        "template": theme,
    }
    if spec.get("subtitle"):
        header["subtitle"] = {"tag": "plain_text", "content": str(spec["subtitle"])}
    if spec.get("status_tag"):
        tag_color = theme if theme not in {"default", "grey"} else "neutral"
        header["text_tag_list"] = [
            {
                "tag": "text_tag",
                "text": {"tag": "plain_text", "content": str(spec["status_tag"])},
                "color": tag_color,
            }
        ]

    elements: list[dict[str, Any]] = [markdown(f"**结论**<br>{summary}"), {"tag": "hr"}]
    has_visual = False
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise CardError("each section must be an object")
        kind = section.get("type", "markdown")
        if kind == "markdown":
            elements.append(section_markdown(section))
        elif kind == "table":
            elements.extend(section_table(section))
        elif kind == "collapsible":
            elements.append(section_collapsible(section))
        elif kind == "image":
            elements.extend(section_image(section))
            has_visual = True
        elif kind == "chart":
            elements.extend(section_chart(section))
            has_visual = True
        else:
            raise CardError(f"unsupported section type: {kind}")
        # Keep first-level information groups visually distinct in Lark's compact
        # mobile layout. Authors can opt out for intentionally continuous groups.
        if index != len(sections) - 1 and section.get("separator_after", True):
            elements.append({"tag": "hr"})

    if level == "L3" and not has_visual and not spec.get("external_visual", False):
        raise CardError("L3 requires an image/chart section or external_visual=true")

    if spec.get("footer"):
        elements.extend([{"tag": "hr"}, markdown(str(spec["footer"]), text_size="notation")])

    card = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "default",
            "summary": {"content": title},
            "style": {
                "text_size": {
                    "normal": {"default": "normal", "pc": "normal", "mobile": "normal"},
                    "notation": {"default": "notation", "pc": "notation", "mobile": "notation"},
                }
            },
        },
        "header": header,
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 20px 12px",
            "vertical_spacing": "8px",
            "elements": elements,
        },
    }
    validate_card(card)
    return card


def visible_text(value: Any) -> str:
    """Approximate visible text for advisory checks, not rendered dimensions."""
    text = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", str(value))
    text = re.sub(r"</?(?:font|br|at|text_tag)\b[^>]*>", " ", text, flags=re.I)
    return re.sub(r"[\s`*_#]+", " ", html.unescape(text)).strip()


def has_unsafe_strong_boundary(text: str) -> bool:
    """Spot a common CJK strong-emphasis mistake; not a full Markdown parser."""
    prose = prose_only(text)

    def punctuation(char: str) -> bool:
        return char in string.punctuation or unicodedata.category(char).startswith("P")

    for match in re.finditer(r"(?<![\\*])\*\*(?!\*)([^\n*]+?)(?<!\\)\*\*(?!\*)", prose):
        following = prose[match.end():match.end() + 1]
        if (following and punctuation(match.group(1)[-1])
                and not following.isspace() and not punctuation(following)):
            return True
    return False


def presentation_warnings(spec: dict[str, Any]) -> list[dict[str, str]]:
    """Flag observed readability risks without inventing content or blocking send."""
    spec = normalize_spec(spec)
    warnings: list[dict[str, str]] = []

    def warn(code: str, path: str, message: str) -> None:
        warnings.append({"code": code, "path": path, "message": message})

    sections = spec.get("sections", [])
    main_sections = [s for s in sections if s.get("type", "markdown") != "collapsible"]
    if len(main_sections) >= 3:
        if not spec.get("subtitle"):
            warn("HEADER_SCOPE", "subtitle", "多节卡片未写副标题；有明确范围时用短语交代，避免首屏依赖长段背景。")
        if not spec.get("status_tag"):
            warn("HEADER_STATUS", "status_tag", "多节卡片未写状态；有真实状态或核验边界时保留标签，不为补样式虚构状态。")

    for index, section in enumerate(sections):
        path = f"sections[{index}]"
        kind = section.get("type", "markdown")
        if kind == "collapsible":
            continue
        title = visible_text(section.get("title", ""))
        if len(main_sections) >= 3 and not title:
            warn("SECTION_ANCHOR", path, "主要信息块没有短标题；使用便于扫读的语义标题，收尾补充可放 footer。")
        elif len(title) > 28:
            warn("LONG_HEADING", path + ".title", "标题较长，可能已在解释原因；将标题缩成主题，把必要说明放正文。")

        if kind == "markdown" and len(visible_text(section.get("content", ""))) > 180:
            warn("LONG_TEXT", path + ".content", "单个正文块较长；检查是否能删重复解释、按判断拆分或将次要证据折叠。")
        if kind == "table" and section.get("rows"):
            columns, rows = section["columns"], section["rows"]
            averages = [
                sum(len(visible_text(row.get(column["name"], ""))) for row in rows) / len(rows)
                for column in columns
            ]
            shortest, longest = min(averages), max(averages)
            if shortest <= 12 and longest >= 40 and longest >= 4 * max(shortest, 1):
                warn("TABLE_BALANCE", path, "表格一列多为短标签、另一列多为长段；改为具体判断对照，或使用短标题加正文。")
            if any(len(visible_text(value)) > 140 for row in rows for value in row.values()):
                warn("LONG_CELL", path, "表格单元格承载长段解释；每行先给短判断，详细依据移到分项或折叠区。")

    text_values = [("summary", str(spec.get("summary", ""))), ("footer", str(spec.get("footer", "")))]
    for index, section in enumerate(sections):
        text_values.append((f"sections[{index}]", str(section.get("content", ""))))
        for row in section.get("rows", []):
            text_values.extend((f"sections[{index}].rows", str(value)) for value in row.values())
    for path, text in text_values:
        if has_unsafe_strong_boundary(text):
            warn("EMPHASIS_BOUNDARY", path, "加粗以标点结尾且紧接正文，可能原样显示星号；将句末标点移到加粗之外，或在闭合标记后加空格/换行。代码示例不改写。")
        if any(len(visible_text(match)) > 32 for match in re.findall(r"<font\b[^>]*>(.*?)</font>", text, re.I | re.S)):
            warn("LONG_ACCENT", path, "整句或长段使用颜色会稀释重点；优先只强调判断、阈值或风险短语。")
    return warnings


def validate_card(card: dict[str, Any]) -> None:
    if card.get("schema") != "2.0":
        raise CardError("card schema must be 2.0")
    header = card.get("header")
    if not isinstance(header, dict):
        raise CardError("card header is required")
    title = header.get("title")
    if not isinstance(title, dict) or not title.get("content"):
        raise CardError("card header title is required")
    if header.get("template", "default") not in THEMES:
        raise CardError("card header template is invalid")
    body = card.get("body")
    if not isinstance(body, dict) or not isinstance(body.get("elements"), list):
        raise CardError("card body.elements is required")

    count = 0

    def walk(elements: list[Any], *, root: bool) -> None:
        nonlocal count
        allowed = ROOT_TAGS if root else NESTED_TAGS
        for element in elements:
            count += 1
            if count > 200:
                raise CardError("card exceeds the 200 element limit")
            if not isinstance(element, dict):
                raise CardError("card element must be an object")
            tag = element.get("tag")
            if tag not in allowed:
                raise CardError(f"unsupported display-only element: {tag}")
            if tag == "table" and not root:
                raise CardError("table must be a root body element")
            if tag == "markdown":
                validate_text(element.get("content", ""), "markdown.content")
            if tag == "table":
                for row_index, row in enumerate(element.get("rows", [])):
                    for column in element.get("columns", []):
                        if column.get("data_type") in {"lark_md", "text"}:
                            validate_text(row.get(column["name"], ""), f"table.rows[{row_index}].{column['name']}")
            if tag == "collapsible_panel":
                panel_header = element.get("header", {})
                icon = panel_header.get("icon", {}) if isinstance(panel_header, dict) else {}
                if icon.get("token") != "down-small-ccm_outlined" or panel_header.get("icon_position") != "right":
                    raise CardError("collapsible panel requires the explicit right-side expand arrow")
                nested = element.get("elements", [])
                if not isinstance(nested, list):
                    raise CardError("collapsible panel elements must be an array")
                walk(nested, root=False)

    walk(body["elements"], root=True)
    if not body["elements"] or body["elements"][0].get("tag") != "markdown":
        raise CardError("first body element must contain the conclusion")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise CardError("JSON root must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--spec", type=Path, help="content specification JSON")
    mode.add_argument("--validate-card", type=Path, help="validate an existing card JSON")
    parser.add_argument("--output", type=Path, help="output card JSON; stdout when omitted")
    parser.add_argument("--design-report", type=Path, help="write advisory presentation checks for --spec")
    args = parser.parse_args()

    try:
        if args.validate_card:
            if args.design_report:
                raise CardError("--design-report requires --spec")
            validate_card(load_json(args.validate_card))
            print(f"valid schema 2.0 display card: {args.validate_card}")
            return 0

        spec = load_json(args.spec)
        card = build_card(spec)
        warnings = presentation_warnings(spec)
        for warning in warnings:
            print(f"presentation hint [{warning['code']}] {warning['path']}: {warning['message']}", file=sys.stderr)
        if not warnings:
            print("presentation heuristics: no hints; rendered visual review still required", file=sys.stderr)
        if args.design_report:
            report = {
                "structural_validation": "passed",
                "presentation_warnings": warnings,
                "visual_review": "not_performed",
            }
            args.design_report.parent.mkdir(parents=True, exist_ok=True)
            args.design_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rendered = json.dumps(card, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"generated and structurally validated: {args.output}")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, json.JSONDecodeError, CardError) as exc:
        print(f"card build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
