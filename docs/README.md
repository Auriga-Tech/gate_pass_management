# Documentation

| File | Audience | What it is |
|---|---|---|
| [`USER_MANUAL.md`](USER_MANUAL.md) | Everyone using the app | Guards, stores, managers, implementers, troubleshooting. Explains every master in plain language. |
| [`../FEATURES.md`](../FEATURES.md) | Sales and evaluation | What the product does and why it is different |
| [`../README.md`](../README.md) | Anyone arriving at the repo | Problem statement, install, five-minute setup |
| [`plan/PRODUCT_PLAN.md`](plan/PRODUCT_PLAN.md) | Contributors and implementers | The full product design: data model, 60 rules, correctness requirements, defect register, release plan |
| [`plan/CONFIG_REFERENCE.md`](plan/CONFIG_REFERENCE.md) | Implementers | Every rule and every configurable setting, with defaults and enforcement layering |
| [`word/`](word/) | External distribution | Feature List and User Manual as formatted Word documents |

## Reading order

**Evaluating the app** — `../README.md`, then `../FEATURES.md`.

**Rolling it out** — `USER_MANUAL.md` Part 4 for configuration, then
`plan/CONFIG_REFERENCE.md` when you need the exact behaviour of a specific rule.

**Contributing** — `plan/PRODUCT_PLAN.md` first. Section 13 (correctness and
observability) and section 14 (the defect register) explain why the code is
shaped the way it is; a change that ignores them will look reasonable and
reintroduce a bug the design exists to prevent.

## Regenerating the Word documents

`word/` is generated from the Markdown, so edit the Markdown and regenerate —
never edit the `.docx` by hand. Both follow the Auriga IT document standard
(cover page, running header, address footer, brand palette).
