---
name: lark-rich-response
description: Generates and validates low-noise Lark schema 2.0 card JSON for structured replies, including code analysis, plans, reviews, diagnosis, comparisons, and delivery reports. Applies to L2/L3 results with evidence, risks, or complex flows; excludes short confirmations. Runs offline with Python standard library only. Returns portable JSON artifacts; sending through an authorized Lark integration is optional.
metadata:
  runtime: Requires Python 3 only; generation and validation use the standard library and run offline.
---

# Lark Rich Response

Create compact, self-contained schema 2.0 cards whose visual structure matches the information relationship. This skill standardizes card authoring and self-checking. Its output is a portable JSON artifact; it does not implement messaging transport.

## Distribution and runtime

This standalone edition is distributed through AgentBuddy's default public space with the
original owner's authorization. It contains only the Skill instructions, generator, examples,
evaluations and regression tests; no workspace configuration or credentials are included.

Resolve this Skill's installation directory from the loaded `SKILL.md`. In the commands below,
`<skill-dir>` means that directory, not the user's project working directory. Use Python 3;
the generator uses only the standard library and works without a network connection, login,
CLI messaging tools, or an active chat session. Return the generated JSON file by default.
Sending is an optional, separate operation through a Lark integration already available and
authorized in the calling environment. Do not install or require a messaging framework.
Diagrams require a separate visualization tool only when the applicable card-level rules call
for one; return a local diagram artifact when no image-upload integration is available.

## Required context

1. Read the active repository's Lark response style file completely when its `AGENTS.md` points to one.
2. When delivery is requested, follow the calling environment's routing, recipient, mention, identity, and authorization rules. A generated file alone does not authorize sending.
3. Preserve the repository's safety, region, evidence, and disclosure rules. Card design never overrides task boundaries.

## Classify before drafting

- `L0`: no more than 3 lines; confirmation, low-information progress, or a one-line answer. Use plain text.
- `L1`: one core conclusion, short content, no branching/topology/sequence. Markdown card is sufficient.
- `L2`: structured analysis, plan, CR, diagnosis, launch assessment, final delivery, or a response combining sections, a table, boundaries, and evidence. Use this skill and a schema 2.0 card.
- `L3`: 7 or more nodes, 2 or more branches, or topology/sequence/state/dependency relationships. Use this skill and add a flow diagram or equivalent visualization.

When uncertain between two levels, choose the higher one. A Markdown message automatically wrapped by a messaging client is not an L2/L3 custom card.

## Compose the information

Design the card in this order:

1. Put the outcome, impact, and important boundary in a 2–4 line summary at the top.
2. Use a short directional flow for a simple 3–7 node chain.
3. Use a 2–4 column table for exact mappings or repeated comparisons.
4. Put risks and uncertainty after the main result, not before it.
5. Put code paths, symbols, log fields, configuration keys, and unverified coverage in a collapsed evidence panel with an explicit arrow.
6. Delete repeated prose. Each section should add a distinct relationship or decision.

### Default information design for assessments and delivery

For multi-section assessments, reviews, diagnoses and delivery updates, start with
[`assets/spec-template.json`](assets/spec-template.json). It demonstrates a complete,
compact card; its example facts and statuses must be replaced with the current evidence.
Use `assets/chain-example.json` for chains and mappings. Choose by the information relationship,
not by the workspace where the session started.

Use the builder's named information layouts for these recurring replies:

- `preset: "assessment"`: supply `findings` and optional `boundaries`.
- `preset: "delivery"`: supply `deliverables` and optional `checks`.
- Each group is an array of `{label, verdict, detail?, tone?}`. The verdict is factual;
  optional tone is `blue|orange|green|red`. Two or more items become a native two-column
  comparison with verdicts first; one item becomes a compact titled paragraph.
- Optional `next_action` is shown only when supplied; `evidence` becomes the bottom collapsed
  panel. Keep `title`, `summary`, and factual header metadata in the existing specification.
  Omit empty groups. Do not fabricate status or follow-up work to fill the layout.
- Do not combine a preset with `sections`: the builder rejects that ambiguous input, so a
  recurring reply cannot silently discard its comparison layout and become a prose stack.
  Custom `sections` remain appropriate for chains, images or other information relationships.

See [the delivery preset example](assets/delivery-preset.json). Preserve the chosen relationship
through revisions; change the layout only when the actual information relationship changes.

- Keep a meaningful header icon, specific topic, factual status tag and short scope subtitle when
  they convey distinct information. Do not remove them merely to shorten the card while leaving
  explanatory paragraphs intact. A status tag describes the actual state or verification boundary;
  generating a draft does not make it approved or complete.
- Give major sections short semantic titles with useful icons, such as findings, risks and next
  action. A heading names the topic; it should not contain the entire explanation. Keep extra
  separators for actual changes of subject, not after every paragraph.
- Put the concrete verdict first. In repeated comparisons, each result starts with a short judgment
  and then its evidence. Color the judgment or threshold, not the whole explanation. Inline code
  distinguishes real paths and symbols; do not add code styling to ordinary prose for decoration.
- A table should compare real questions or objects. If one column is a four-character label and
  another is a paragraph, rewrite the rows or use titled prose instead of allocating half the width
  to empty space. After the table, do not repeat its conclusions in another long paragraph.
- L0/L1 stay lightweight. Single-point L2 cards may intentionally omit metadata or remain neutral;
  do not invent a status, risk, next action or icon to fill the example.

### Add semantic accents deliberately

After the information structure is stable, make one explicit semantic-accent pass. This is not a decoration quota and is not a hard validation gate: a neutral card is valid when the content has no useful state distinctions. The important point is to make the choice intentionally instead of inheriting a visually neutral default.

- Use a small, stable icon vocabulary at the levels where it speeds scanning: one icon in a section heading, circled numerals plus arrows for an ordered flow, and a business-specific emoji for table rows when categories are otherwise easy to confuse.
- In `markdown` content and `lark_md` table cells, use `<font color='blue'>` for structure or chain labels, `<font color='orange'>` for constraints, filtering, warnings, and uncertainty, `<font color='green'>` for selected, successful, or verified outcomes, and `<font color='red'>` only for genuine blockers or high risk.
- Color short labels, thresholds, and outcomes rather than entire paragraphs. Keep the body self-contained without relying on color or icons alone.
- Use `data_type: "lark_md"` for table columns that need inline code, semantic color, or emoji-rich content; plain `text` cells cannot express the same hierarchy reliably.
- A useful default density is one icon per section and one per business category row, not one per sentence. The goal is faster recognition, not visual noise.

For L3, use an applicable visualization skill such as Draw.io, Excalidraw, Mermaid, or another available diagram generator. If the resulting image has a Lark `img_key`, add it as an `image` section in the card specification. If only a local image path is available, return it alongside the self-contained card JSON. An authorized delivery integration may upload it and provide the resulting Lark image key, or deliver it separately. Do not put local paths into image-key fields or invent resource keys.

## Build the card

1. Copy the applicable example above to the repository's allowed temporary directory and replace its content.
2. Keep `level` as `L2` or `L3`; select the semantic `theme`:
   - `blue`: code analysis, chains, general technical explanation
   - `orange`: diagnosis, warning, uncertainty
   - `green`: verified completion or delivery
   - `red`: genuine high risk or blocker
   - `violet` or `purple`: technical proposal
3. Use the section types supported by the builder: `markdown`, `table`, `collapsible`, `image`, and `chart`.
4. Review the spec for semantic accents before generation: where the content contains an ordered path, a constraint/risk, a winning result, or distinct business categories, decide whether numbered markers, arrows, icons, or a short colored phrase would make that relationship faster to read. Leaving them out is acceptable when the card is intentionally neutral.
5. Generate and validate the card:

```bash
python3 "<skill-dir>/scripts/build_card.py" \
  --spec <spec.json> \
  --output <card.json> \
  --design-report <design-report.json>
```

The builder reports structural validation separately from advisory presentation checks. Read the
presentation hints and address applicable ones before sending; an intentional exception is an
authoring judgment, not a reason to ask the user for permission. Hints identify missing header
context in multi-section cards, absent/long headings, long prose or cells, unbalanced tables and
overlong colored phrases. They are heuristics, not a quality score: no hints does not prove that
the card reads well, and neutral short cards do not need extra decoration.

First-level sections are separated by a divider by default, except after the final section. Set
`separator_after: false` only when two adjacent sections intentionally form one continuous group.
The conclusion keeps its own separating rule.

6. If a card was edited after generation, validate it again without sending:

```bash
python3 "<skill-dir>/scripts/build_card.py" \
  --validate-card <card.json>
```

7. Return the card JSON file and, when requested, the design report and diagram artifacts. Include
   a short status such as "Generated and structurally validated; not sent." If the user also
   requests sending and an authorized integration is available, follow the optional delivery
   contract below.

The builder rejects unsupported or callback-style components so the generated card remains display-only. This is a local authoring check; a downstream sender must also enforce its own transport restrictions.

### Keep text syntax specific to the channel

Card body text uses Lark Markdown: `**bold**`, inline code, links and supported semantic
`<font>`/`<br>` syntax. Do not paste document XML or HTML formatting such as `<b>`, `<span>`,
`<p>` or `<table>` into card text. Tables are native components generated by the builder.
Both generation and `--validate-card` reject known foreign formatting tags in summaries,
body, table cells, evidence and footers. Literal markup belongs in inline/fenced code or
escaped text; the validator preserves it, and does not silently rewrite content.
This is a targeted cross-channel check, not a complete Lark Markdown parser or visual validator.

Keep header title, subtitle and status labels as plain text. In Markdown body text, put sentence-ending
punctuation outside bold spans when the next sentence follows immediately: use `**结论**。后续内容`,
not `**结论。**后续内容`. A space or line break after the closing marker also separates the boundary.
The latter unseparated form can leave literal asterisks under CommonMark emphasis rules. The builder
reports `EMPHASIS_BOUNDARY` as an authoring hint; fix the prose before sending. It does not rewrite
content or code examples, and passing structural validation does not establish correct rendering.

## Optional delivery contract

Generation is complete when the JSON artifact and its validation result are available. Delivery
is not a prerequisite. The output is a direct Lark schema 2.0 card object, not an HTTP envelope.

If sending is explicitly requested:

1. Discover the calling environment's available Lark connector, API client, webhook wrapper,
   or CLI. Use its documented card-message interface and the user's authorized destination.
   Keep credentials in that integration; do not include them in the card or Skill package.
2. Pass the generated card object using the integration's required argument or envelope.
   Preserve the schema and content; only serialize or wrap as required by its documented API.
   Verify that the integration accepts schema 2.0 and the card's components.
3. Report a sent status only after a successful transport response, retaining its message ID
   when available. Do not send again after success. A timeout or ambiguous result requires
   checking delivery status before retrying.
4. If no suitable integration is available, return the JSON artifact and state that it has
   not been sent. Do not install a transport, request unrelated credentials, or block generation.

## Handle blocking user decisions separately

Keep generated cards display-only. If execution requires the user's choice, present the
self-contained result and use the host environment's supported question or approval mechanism.
If no structured question tool exists, ask a concise plain-text question in the current
conversation. Wait for an explicit answer; a timeout is not consent. Do not embed callback
buttons, selects or forms, invent clickable options, or depend on a particular host framework.

## Visual review before delivery

Check all of the following:

- The first screen contains the conclusion.
- A heading and the body immediately following it share one Markdown component and use `<br>` for a single controlled line break; do not use `\n\n`, which creates an extra paragraph margin in Lark.
- Header color matches the message semantics.
- Compare the card against the chosen example for information hierarchy, not identical wording or
  color: the header communicates state/scope, section anchors are easy to scan, and verdicts precede
  evidence. When the user provides a reference screenshot, inspect it and preserve its useful
  information design rather than assuming a successful build reproduces it.
- Body accents are intentional: ordered flows, constraints, selected outcomes, and business categories use a small number of semantic colors/icons when that improves scanning. If the body has no colored text or line/row icons, confirm that neutral presentation is a conscious choice rather than an untouched default.
- Semantic colors are sparse and consistent: blue for structure, orange for constraints or uncertainty, green for success/selection, and red only for real blockers/high risk.
- Icons add category or hierarchy meaning; they are not repeated on every sentence.
- A table or flow replaces repetitive prose where it improves comprehension.
- The mobile layout does not rely on a wide table or a very long single line.
- L3 has a diagram or equivalent visualization.
- Evidence is collapsed and the title explicitly says it can be expanded.
- Code facts, online facts, and inference are visibly distinguished.
- The card is self-contained and does not rely on prior progress messages.

## Failure handling

If generation or structural validation fails, fix the specification and rerun validation before
claiming success. If optional delivery definitively rejects the card, retain the validated JSON
and report the integration's error. An authorized text-capable integration may deliver an
equivalent Markdown fallback, clearly identified as a downgrade. If delivery status is ambiguous,
check it first to avoid duplicate messages. Never equate file generation with successful delivery.

## Bundled resources

- `assets/spec-template.json`: default assessment example with a full header, short semantic sections, verdict-first comparisons and collapsed evidence.
- `assets/chain-example.json`: chain/mapping example with semantic colors and numbered flow markers.
- `scripts/build_card.py`: generator, structural validator and advisory presentation checks; it does not verify visual quality.
- [`assets/evals.json`](assets/evals.json): representative prompts and expected card-level behavior.

## Regression checks

Run the bundled [regression checks](scripts/test_build_card.py) after changing the generator,
examples or package layout. These checks use only the Python standard library.

```bash
python3 -B "<skill-dir>/scripts/test_build_card.py"
```

Example specifications contain illustrative facts and statuses. Replace them with current
evidence before sending. A successful build or regression run does not send a card and does
not establish visual quality in the Lark client.
