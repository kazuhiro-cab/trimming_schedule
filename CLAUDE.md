# CLAUDE.md
@仕様書_トリミングサロン_スケジュール調整ツール_反映版v279.md

## Project memory
このプロジェクトは、**Windows 専用のトリミングサロン向けスケジュール管理ツール**を実装するためのものである。
実装の仕様正本は、次の 1 ファイルに固定する。

- `仕様書_トリミングサロン_スケジュール調整ツール_反映版v279.md`

Claude Code は、この仕様書を「何を作るか」の正本として扱い、この `CLAUDE.md` を「どう作業するか」の正本として扱うこと。

---

## Non-negotiable constraints
- Target OS is **Windows only**.
- Stack is **Streamlit + SQLite only**.
- All operational input must be completed in the UI.
- Output must be **HTML** and printable to PDF from the browser.
- Time values are handled as **integer minutes**.
- Do not invent features, screens, states, tables, columns, or business concepts that are not defined in the spec.
- If code conflicts with the spec, the **spec wins**.
- If a schema change is required, use a **startup-time auto recreation approach**. Do not introduce partial migration logic unless explicitly requested.

---

## Role separation
### Spec file
The spec defines:
- business rules
- screens
- operations
- state transitions
- tables and columns
- UI targets
- output requirements
- acceptance-level behavior

### This file
This file defines:
- implementation discipline
- coding guardrails
- file operation rules
- testing expectations
- reporting style

This file must not be used to override the business meaning of the spec.

---

## Priority order
Use this priority order.

1. `CLAUDE.md`
2. `仕様書_トリミングサロン_スケジュール調整ツール_反映版v279.md`
3. existing code

Interpretation rule:
- `CLAUDE.md` controls **work behavior**.
- The spec controls **product behavior**.

If there is tension, preserve the spec’s product behavior and apply this file only as a work rule.

---

## Before making changes
Before coding, always do the following.

1. Read the relevant sections of spec `v279`.
2. Identify the related:
   - chapter
   - OP block
   - UI target
   - table / column
   - recalculation / side effect / output impact
3. Check whether the change touches a wider scope.
4. Prefer updating existing files over adding new files.

If the change affects a UI target, review at least:
- input conditions
- UI entry target
- UI reflection
- list / index references
- dictionary / naming consistency

---

## Prohibited behavior
Do not:
- add new features not defined in the spec
- add new screens not defined in the spec
- change business semantics for convenience
- introduce Linux-only deliverables
- build the workflow around bash scripts
- rename core UI targets independently from the spec
- create alternative spec documents
- bury mismatches behind temporary flags or ambiguous fallbacks
- perform broad refactors unrelated to the requested work

---

## Implementation style
### Python / Streamlit
- Keep the implementation Windows-stable.
- Keep the UI fully operable from Streamlit.
- Use names that can be traced back to the spec vocabulary.
- Keep state handling explicit.
- Match displayed labels and state names to the spec.

### SQLite
- Use SQLite as the only persistence layer.
- Respect the spec for table and column meaning.
- Implement side effects, recalculation, invalidation, and audit-log behavior when the spec requires them.
- Do not stop at a raw save if the operation requires dependent updates.

### Windows operations
- If setup or helper scripts are needed, prefer `.bat` or PowerShell.
- Think in Windows paths, Windows encoding issues, and Windows runtime behavior.
- Development may happen elsewhere, but deliverables must target Windows execution.

---

## UI discipline
The project is sensitive to naming and cross-screen consistency.

Always align UI implementation with:
- Chapter 34
- Chapter 35
- Chapter 36
- Chapter 38

Important UI targets include:
- `ガント / タイムライン`
- `予約済み一覧`
- `予約検索結果`
- `予約情報タブ`
- `当日対応タブ`
- `施術履歴一覧`
- output summary blocks

When changing one of these, do not change only one surface. Check all linked places.

---

## Output discipline
The output is not cosmetic. It is part of the product contract.
Implement output so that HTML can clearly show:
- one-day timeline
- total handled pets for the day
- before / after adjustment comparison
- rationale such as menu duration, buffer, break, and business hours
- short submission summary
- detailed reference view

The output must remain printable to PDF from the browser.

---

## Change discipline
- Fix the requested scope precisely.
- If one issue implies a same-scope consistency check, perform that consistency check.
- Avoid unrelated cleanup.
- Keep changes small enough to review.
- Preserve the current architecture unless the spec-compliant fix requires local restructuring.

---

## Testing expectations
After changes, verify at minimum:
1. the app starts
2. database initialization or recreation works
3. the changed operation behaves according to the spec
4. HTML output can be produced
5. major state transitions do not error
6. unrelated nearby behavior was not broken

Do not report completion without testing.

---

## File rules
- Do not rename the spec file.
- Do not create many derivative spec files.
- Do not add explanatory files unless they are genuinely needed.
- Keep file additions minimal.
- Prefer one canonical place for each rule.

---

## Reporting style
When reporting work, keep it short and concrete.
Always state:
1. what changed
2. which spec sections justified it
3. which files changed
4. what was checked
5. what remains uncertain, if anything

Avoid long theory unless explicitly requested.

---

## Project values to preserve
Preserve these priorities throughout the project.

- strict spec compliance
- Windows-ready operation
- UI / persistence consistency
- reproducible output rationale
- no speculative expansion
- no regression to older assumptions
