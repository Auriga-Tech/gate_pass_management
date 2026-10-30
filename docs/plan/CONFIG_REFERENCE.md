# Gate Pass — Configuration & Enforcement Reference

**Companion to** `GATE_PASS_PRODUCT_PLAN.md`. This document specifies (a) the enforcement configuration model, (b) every rule and whether it can be configured, (c) the complete inventory of configurable knobs, and (d) the corrected v1.0 / v1.1 / v2.0 tiering with v1.1 and v2.0 actually specified.

---

# Part A — Enforcement configuration model

## A.1 The three actions

Every configurable rule resolves to one of three actions:

| Action | Behaviour | Audit |
|---|---|---|
| **Block** | `frappe.throw`. The save or submit fails. | `Validation Failed` event row |
| **Warn** | `frappe.msgprint` with a warning indicator. The operation proceeds. Optionally requires an override reason (§A.4). | `Rule Warned` event row, with the reason if captured |
| **Ignore** | The rule is not evaluated at all. No message, no cost. | Nothing |

`Ignore` is deliberately distinct from `Warn`: some customers want a rule genuinely switched off (and want the query it would have run skipped, for speed), not merely quietened.

## A.2 Where the action comes from — layering

Four layers, most specific wins:

```
1. Global preset          Gate Pass Settings.enforcement_preset
                          ↓ sets a baseline for every configurable rule
2. Per-rule setting       Gate Pass Rule (child of Settings), one row per rule code
                          ↓ overrides the preset for that rule
3. Per-source override    Gate Pass Source → Rule Overrides child table
                          ↓ overrides the rule for that flow only
4. Bypass role            Gate Pass Rule.bypass_roles
                          ↓ downgrades Block → Warn for users holding the role
                            (never upgrades; a bypass role can never make a rule stricter)
```

**Worked example — over-quantity (rule `QTY-LEDGER`):**

| Layer | Setting | Effective action |
|---|---|---|
| Global preset | `Balanced` | Warn |
| Per-rule | `QTY-LEDGER` = Block | **Block** |
| Per-source override | "Delivery Note - Outward" = Warn | Block for all flows; **Warn** for DN outward |
| Bypass role | `Gate Pass Manager` | Block for everyone; **Warn** for a Gate Pass Manager |

Net effect: a guard creating a PO inward pass is blocked at over-quantity; the plant manager is warned and can proceed with a recorded reason; and outward delivery passes never block anyone.

That combination is impossible to express with a single Advisory/Mandatory switch, and it is exactly what a real customer asks for in week three.

## A.3 Global presets

`Gate Pass Settings.enforcement_preset` — a one-click baseline, not a separate mechanism. Selecting a preset **rewrites the `Gate Pass Rule` rows**; the customer can then tune individual rows, at which point the preset switches itself to `Custom`.

| Preset | Behaviour | Use |
|---|---|---|
| **Advisory** | Every configurable rule → Warn. Nothing blocks except hard-integrity rules. | Week 1. Run alongside existing process, collect data, break nothing. **Ship default.** |
| **Balanced** | Data-quality and reference rules → Block. Quantity and downstream-enforcement rules → Warn. | The usual steady state. |
| **Strict** | Every configurable rule → Block. | Regulated sites, high-value goods, audit-driven customers. |
| **Custom** | Set automatically the moment any row is edited by hand. | Everyone, eventually. |

**Adoption tooling:** a report, **Enforcement Impact Preview**, replays the last N days of gate passes and target documents against a candidate preset and lists what *would* have been blocked, by rule and by user. A customer moves Advisory → Balanced with evidence rather than hope. This is what makes progressive enforcement real rather than a marketing word.

## A.4 Override with reason

Per rule: `require_override_reason` (Check). When a `Warn` rule fires and this is on, the user must type a reason before the document saves. The reason is mandatory, free text, minimum length configurable, and written to `Gate Pass Event Log` alongside the rule code, the computed values, and the user.

This turns the warn tier from "a message nobody reads" into a genuine exception log — and the **Gate Pass Exceptions** report is built directly on it. For most customers this is more valuable than blocking, because it tells them *where their process actually breaks* instead of just stopping work.

## A.5 New DocType — `Gate Pass Rule` (child of Gate Pass Settings)

| Fieldname | Type | Notes |
|---|---|---|
| `rule_code` | Data | RO — stable identifier, e.g. `QTY-LEDGER`. Never changes across versions. |
| `rule_name` | Data | RO — translated display name |
| `category` | Select | RO — `Document` · `Party & Source` · `Quantity` · `Attachments & Checks` · `Lifecycle` · `Downstream Enforcement` |
| `description` | Small Text | RO — what the rule checks, in plain language |
| `default_action` | Select | RO — the product default |
| `action` | Select | **`Block` / `Warn` / `Ignore`** — the setting |
| `can_ignore` | Check | RO — some rules may be downgraded to Warn but not switched off entirely |
| `applies_to_direction` | Select | `Both` / `In` / `Out` |
| `applies_to_gate_pass_type` | Select | Blank = all |
| `bypass_roles` | Table MultiSelect → Role | Downgrades Block → Warn for these roles |
| `require_override_reason` | Check | |
| `custom_message` | Small Text | Overrides the shipped message; supports `{placeholders}` |
| `threshold` | Float | For rules that carry a number (tolerance %, day limits) |

Rows are **seeded and reconciled by `after_migrate`**: new rules added in a future version appear automatically at their default action, and rules removed from the product are dropped. A customer's edits are never overwritten.

## A.6 Per-source overrides — `Gate Pass Source Rule Override` (child of Gate Pass Source)

`rule_code` (Link → the rule) · `action` (Block/Warn/Ignore) · `threshold` (Float) · `require_override_reason` (Check).

Only rules flagged `source_overridable` may appear here. Quantity, checklist, and downstream-enforcement rules are overridable; document-integrity rules are not.

---

# Part B — Complete rule catalogue

**Legend:** **HARD** = always blocks, not configurable (data integrity — allowing these to be bypassed would corrupt the ledger or produce documents that cannot be reasoned about). **CONFIG** = Block / Warn / Ignore. **SRC** = also overridable per `Gate Pass Source`.

## B.1 Document integrity — mostly HARD

| Code | Rule (V#) | Type | Default | Notes |
|---|---|---|---|---|
| `SYS-DISABLED` | App disabled (V-1) | HARD | Block | Not a rule; the master switch |
| `DOC-DIRECTION-LOCK` | Direction / type immutable after save (V-2) | HARD | Block | Changing direction invalidates every downstream reference |
| `DOC-RETURNABLE-DIR` | Returnable only on outward (V-5) | HARD | Block | Nonsensical state |
| `DOC-COMPANY-MATCH` | Source company = gate pass company (V-8) | HARD | Block | Cross-company leakage |
| `SRC-SUBMITTED` | Source document must be submitted (V-15) | HARD | Block | Draft child rows can be deleted, orphaning the ledger key |
| `ITEM-REQUIRED` | Item Code required unless non-stock (V-21) | HARD | Block | |
| `ITEM-NAME-REQUIRED` | Item Name required for non-stock (V-23) | HARD | Block | |
| `ITEM-CONVERSION` | Conversion factor > 0 (V-22) | HARD | Block | Division by zero downstream |
| `ITEM-QTY-NEGATIVE` | Qty may not be negative (V-20a) | HARD | Block | Negative qty corrupts the ledger sum |
| `TGT-CREATE-FAIL` | Auto-created target failed (V-34) | HARD | Block | Cannot half-create; the submit aborts |
| `LIFE-AMEND-RESET` | Amend clears references and stamps (V-39) | HARD | — | Behaviour, not a check |

## B.2 Document rules — CONFIG

| Code | Rule (V#) | Default | Ignore? | SRC | Threshold |
|---|---|---|---|---|---|
| `DOC-REF-DATE-FUTURE` | Reference date not in the future (V-3) | Block | ✓ | | |
| `DOC-BACKDATE` | Posting date within the backdate window (V-4) | Warn | ✓ | | days |
| `DOC-FUTUREDATE` | Posting date not in the future (V-4) | Block | ✓ | | days |
| `DOC-RETURN-DATE` | Expected return ≥ posting date (V-6) | Block | ✓ | | |
| `DOC-RETURN-WINDOW` | Expected return within N days of posting | Warn | ✓ | ✓ | days |
| `DOC-ITEMS-REQUIRED` | At least one item row (V-10) | Block | ✓ | ✓ | |
| `DOC-TRACKING-UNIQUE` | Tracking ID not already used (V-17) | Block | ✓ | | |
| `DOC-GATE-LOCATION` | Gate belongs to the location (V-19) | Warn | ✓ | | |
| `DOC-EFFECTIVE-DATE` | On/after `enforce_from_date` (V-16) | Block | ✓ | | |
| `FIELD-RULE-*` | Per-field mandatory rules (V-9) | per row | ✓ | ✓ | — each `Gate Pass Field Rule` row carries its own action |

## B.3 Party & source rules — CONFIG

| Code | Rule (V#) | Default | Ignore? | SRC |
|---|---|---|---|---|
| `PARTY-ADDRESS` | Address required for this party type (V-7) | Warn | ✓ | ✓ |
| `PARTY-SOURCE-MATCH` | Gate pass party = source document party (V-13) | Block | ✓ | ✓ |
| `SRC-MIXED-DOCTYPE` | All rows from one source doctype (V-11) | Block | ✓ | ✓ |
| `SRC-MIXED-PARTY` | Multi-source rows share one party (V-12) | Block | ✓ | ✓ |
| `SRC-MIXED-GROUP` | Multi-source rows share configured grouping fields (V-12) | Warn | ✓ | ✓ |
| `SRC-STATUS` | Source status in the allowed list (V-14) | Block | ✓ | ✓ |
| `SRC-NONSTOCK-MIX` | Non-stock rows on a source-backed pass (V-28) | Warn | ✓ | ✓ |

## B.4 Quantity rules — CONFIG *(the ones customers tune most)*

| Code | Rule (V#) | Default | Ignore? | SRC | Threshold |
|---|---|---|---|---|---|
| `QTY-ZERO` | Zero-qty rows not allowed (V-20b) | Block | ✓ | ✓ | |
| `QTY-ROW-PENDING` | Row qty ≤ pending qty on the source line (V-26) | **Warn** | ✓ | ✓ | tolerance % |
| `QTY-LEDGER` | Total gate-passed across all passes ≤ source qty + tolerance (V-27, V-32) | **Warn** | ✓ | ✓ | tolerance % |
| `QTY-DUPLICATE-ROW` | Two rows referencing the same source line (V-25) | Warn | ✓ | ✓ | |
| `QTY-TARGET-ROW` | Per-source-row target qty ≤ gate-passed qty (V-44) | **Block** | ✓ | ✓ | tolerance % |
| `QTY-TARGET-TOTAL` | Header-total target qty ≤ gate pass total (V-45) | Block | ✓ | ✓ | tolerance % |
| `QTY-WEIGHT` | Net weight > 0 when weights entered (V-18) | Warn | ✓ | | |
| `QTY-WEIGHT-VARIANCE` | Net weight within N% of expected item weight | Ignore | ✓ | ✓ | variance % |

> Tolerance defaults to `Stock Settings.over_delivery_receipt_allowance` when the rule's own `threshold` is blank, so ERPNext's existing configuration is honoured rather than duplicated.

## B.4a Quantity policy & discrepancy — CONFIG

| Code | Rule (V#) | Default | Ignore? | SRC | Threshold |
|---|---|---|---|---|---|
| `QTY-POLICY-LOCKED` | Qty locked to source (V-49) | HARD when the policy is set | — | ✓ | — the *policy* is the setting; once `Locked to Source`, the check is absolute |
| `QTY-POLICY-TOLERANCE` | Qty within tolerance of source (V-50) | Warn | ✓ | ✓ | variance % |
| `DISC-BALANCE` | Accepted + shortage + damaged + rejected = qty (V-51) | HARD | — | | |
| `DISC-NEGATIVE` | No negative discrepancy quantities (V-52) | HARD | — | | |
| `DISC-ALLOWED` | Discrepancy permitted on this flow (V-53) | HARD | — | ✓ | — governed by `allow_discrepancy` |
| `DISC-NOTES` | Notes required when a discrepancy exists (V-54) | Warn | ✓ | ✓ | |
| `DISC-REASON` | Reason required per discrepancy row (V-55) | Warn | ✓ | ✓ | |
| `DISC-REJ-WAREHOUSE` | Rejected warehouse set when damage exists (V-56) | Warn | ✓ | ✓ | |
| `DISC-POST-SUBMIT` | No discrepancy edit after a target is submitted (V-58) | HARD | — | | |
| `DISC-THRESHOLD` | Discrepancy exceeds N% of consignment → escalate | Warn | ✓ | ✓ | % of total qty |

## B.4b Statutory compliance — CONFIG, per source

Configured on `Gate Pass Source → Compliance Rules`, one row per check. The action lives on the rule row itself, so an install can block on E-Way Bill while merely warning on E-Invoice.

| Code | Rule (V#) | Default | Ignore? | SRC | Notes |
|---|---|---|---|---|---|
| `CMP-IN-EINVOICE` | E-Invoice (IRN) generated (V-57) | **Block** | ✓ | ✓ | Sales Invoice only. Auto-`Not Applicable` without `india_compliance` |
| `CMP-IN-EWAYBILL` | E-Way Bill generated (V-57) | **Block** | ✓ | ✓ | SI, DN, PI, PR. Threshold read from `GST Settings` / `State Wise E Waybill Threshold` — never hard-coded |
| `CMP-STALE` | Re-check compliance at submit (V-59) | Block | ✓ | ✓ | Prevents a since-cancelled IRN passing |
| `CMP-PROVIDER-DOWN` | Provider unreachable (V-60) | **Block — fails closed** | ✓ | ✓ | Downgrade to Warn only as a deliberate, audited decision |
| `CMP-CUSTOM-*` | Any registered third-party check | per rule | ✓ | ✓ | Via the `gate_pass_compliance_providers` hook |

**Per-rule knobs:** `required_when` (Always / Above Threshold / From Provider / Never) · `threshold_amount` · `threshold_source` · `action` · `bypass_roles` · `require_override_reason` (default on) · `recheck_on_submit` (default on).

## B.5 Attachments & checks — CONFIG

| Code | Rule (V#) | Default | Ignore? | SRC |
|---|---|---|---|---|
| `CHK-DOC-MANDATORY` | Mandatory checklist documents attached (V-29) | Block | ✓ | ✓ — **and per checklist row**, each of which carries its own action |
| `CHK-CHARGE-MANDATORY` | Mandatory charges entered (V-30) | Warn | ✓ | ✓ — and per charge row |
| `CHK-PACKAGING` | Packaging condition recorded (V-31) | Warn | ✓ | ✓ |
| `CHK-DOCUMENTATION` | Documentation status recorded (V-31) | Warn | ✓ | ✓ |
| `CHK-VEHICLE-PHOTO` | Vehicle photo attached | Warn | ✓ | ✓ |
| `CHK-BATCH-SERIAL` | Batch/serial supplied where the Item requires it (V-24) | Warn | ✓ | ✓ |

## B.6 Lifecycle — CONFIG

| Code | Rule (V#) | Default | Ignore? |
|---|---|---|---|
| `LIFE-CANCEL-POLICY` | Cancellation with linked targets (V-35/36/37) | `Block if Linked` | — 3-way Select, not Block/Warn/Ignore |
| `LIFE-ATTACH-LOCK` | Attachments immutable after submit (V-40) | Block | ✓ — with `attachment_unlock_roles` |
| `LIFE-TIMESTAMP-EDIT` | Post-submit timestamp amendment | Role-gated | — reason always mandatory, always audited |
| `LIFE-STALE-DRAFT` | Draft older than N days | Ignore | ✓ — threshold in days |

## B.7 Downstream enforcement — CONFIG, and the most important group

These decide whether the ERP itself bends to the gate. Each is settable globally **and** per `Gate Pass Source`, which is how one customer requires a gate pass for purchase receipts but not for delivery notes.

| Code | Rule (V#) | Default | Ignore? | SRC |
|---|---|---|---|---|
| `TGT-REQUIRED` | Target document must carry a gate pass (V-41) | **Warn** | ✓ | ✓ |
| `TGT-FORBIDDEN` | Target document must not carry a gate pass (V-42) | Block | ✓ | ✓ |
| `TGT-ROW-COVERAGE` | Every target row is covered by the gate pass (V-43) | Warn | ✓ | ✓ |
| `TGT-BLOCK-NATIVE` | Suppress the source form's native Create button (V-48) | Ignore | ✓ | ✓ |
| `TGT-INTERNAL-SKIP` | Skip all target rules for internal party (V-47) | On | — toggle |
| `TGT-IDEMPOTENT` | One target per gate pass per reference | HARD | — | |

## B.8 Summary

**60 rules · 16 HARD · 44 configurable · 33 also overridable per source.**

Every configurable rule accepts a bypass-role list and an override-reason requirement. Thirteen carry a numeric threshold.

Two design notes worth stating explicitly:

- **Compliance rules default to Block even under the Advisory preset.** Advisory means "do not obstruct our internal process while we learn the tool" — it does not mean "let trucks leave without an E-Way Bill". A statutory rule is not a house policy, and the preset does not get to relax it. An install can still set it to Warn deliberately, per source, with an audited override; that is a decision someone makes on the record, not a side effect of choosing a preset.
- **Provider failure fails closed.** If the compliance provider cannot be reached, the default is to block. An app that quietly lets dispatches through whenever an API is down provides no control at all.

---

# Part C — Complete configurable-knob inventory

Grouped by where the setting lives. This is the implementer's map.

## C.1 `Gate Pass Settings` — Single (~70 fields)

| Group | Knobs |
|---|---|
| **Master** | `enabled` · `enforcement_preset` · `enforce_from_date` |
| **Naming** | `naming_series` · `separate_series_by_direction` · `prefix_by_location` · `naming_rule` |
| **Dating** | `allow_backdated` + `backdate_limit_days` · `allow_future_dated` + `futuredate_limit_days` |
| **Party** | `allowed_party_types` · `default_party_type` · `allow_gate_pass_without_party` |
| **Items** | `allow_gate_pass_without_items` · `allow_non_stock_items` · `default_uom_source` |
| **Discrepancy** | `enable_discrepancy` · `discrepancy_reasons_mandatory` · `allow_post_submit_discrepancy` · `post_submit_discrepancy_roles` · `discrepancy_escalation_pct` · `discrepancy_escalation_roles` · `default_rejected_warehouse` · `shortage_handling` (**Not Received** default / Book as Rejected — whether a counted shortage is booked as rejected qty on the target) |
| **Compliance** | `enable_compliance_checks` · `compliance_staleness_minutes` · `compliance_override_roles` · `block_on_provider_failure` (default on) · `show_compliance_on_print` |
| **Automation** | `enable_auto_draft_creation` · `auto_draft_notify` · `auto_draft_expiry_days` (auto-cancel unclaimed drafts) |
| **Required fields** | `require_location` · `require_gate` · `require_vehicle` · `require_driver` · `require_reference_no` · `require_packaging_check` · `require_documentation_check` · `require_vehicle_photo` |
| **Features** | `enable_returnable` · `enable_charges` · `enable_valuation` · `enable_weighbridge` · `enable_batch_serial` · `enable_cost_center` · `enable_security_officer` · `enable_eway_bill` · `enable_qr_code` · `enable_mobile_console` · `enable_packages` |
| **Tracking ID** | `enable_tracking_id` · `tracking_id_template` · `tracking_id_unique` · `tracking_id_inherit_field` |
| **Returnable** | `default_return_days` · `max_return_days` · `overdue_reminder_days_before` · `auto_close_on_full_return` |
| **Lifecycle** | `cancellation_policy` · `lock_attachments_on_submit` · `attachment_unlock_roles` · `timestamp_edit_roles` · `allow_amend` |
| **Permissions** | `restrict_by_source_role` · `restrict_by_location` · `restrict_by_gate` · `restrict_by_company` |
| **Notifications** | `notify_on_submit` · `notify_roles` · `notify_overdue_returns` · `overdue_escalation_roles` · `email_template` · `enable_whatsapp` · `notify_on_block` |
| **Advanced** | `ledger_lock_timeout_seconds` · `log_level` · `event_log_retention_days` · `enable_api_rate_limit` · `override_reason_min_length` |

## C.2 Child tables of Settings

| Table | Per-row knobs |
|---|---|
| `Gate Pass Rule` | rule action · bypass roles · override reason · threshold · custom message · direction · gate pass type |
| `Gate Pass Field Rule` | document · fieldname · direction · gate pass type · source type · mandatory / hidden / read-only · **action** · label · default · depends_on |
| `Gate Pass Charge Type` | charge type · default amount · mandatory · **action** · direction · paid by |

## C.3 `Gate Pass Source` — Master, one per flow (~35 fields)

Everything in §10.2 of the product plan, **plus** the `Gate Pass Source Rule Override` child table (§A.6) and the `Gate Pass Source Checklist` child table, whose rows each carry their own `action`.

The practical consequence: a customer can require a signed challan and block on over-quantity for **Purchase Order inward**, while the same install merely warns on both for **Delivery Note outward** — with no code, and without touching the global preset.

## C.4 Masters

`Gate` — location, active, allowed directions, allowed gate pass types, operating hours, default security officer.
`Gate Pass Location` — tree, company, address, active.
`Gate Pass Purpose` — direction, default gate pass type, default source, active.
`Gate Pass Discrepancy Reason` — reason, category (Shortage / Damage / Rejection / Documentation), liable party (Supplier / Transporter / Internal / Unknown), requires photo, active. Makes discrepancies reportable by cause and by who is liable, which is what turns the Discrepancy Register into a supplier scorecard and a transporter claim.

## C.6 Compliance provider registration

`hooks.py` key `gate_pass_compliance_providers` — a list of dotted paths. Each provider declares its `check_code`, the doctypes it applies to, and a callable returning a `ComplianceResult`. The India provider ships in the box and self-disables when `india_compliance` is absent. Any country pack or customer overlay can add checks without forking this app.

## C.5 What is deliberately *not* configurable

Making this explicit is as important as the list above; unbounded configurability is how a product becomes unmaintainable.

- The 11 HARD rules in §B.1
- That Gate Pass never posts a Stock Ledger or GL Entry
- The ledger key (`source_row`) and how consumption is computed
- Event Log immutability
- Locking and idempotency behaviour
- The status state machine's transitions (though the labels are translatable)

---

# Part D — Corrected version tiering

## D.1 Correction

The product plan's §7 listed weighbridge fields, notifications, and the mobile offline draft queue under v1.1, while §9, §10, §15 and §16 fully specify all three as v1.0. **Those three move to v1.0**, where they were already designed — they are cheap and the design is done. Everything genuinely deferred is specified below rather than merely named.

## D.2 v1.0 — the shipping product

Everything specified in the product plan, plus this document's enforcement model. Concretely:

Core Gate Pass In/Out · items with source references · consumption ledger with row locking · `Gate Pass Source` configuration (**12 seeded flows**) · Settings with 4 presets and the 44-rule configuration table · field rules · document checklist · charges · weighbridge fields (manual) · **discrepancy capture (shortage / damage / rejection), with damage flowing into target documents as rejected qty and shortage doing so only where the site chooses (`shortage_handling`)** · **statutory compliance framework with the India E-Invoice + E-Way Bill provider** · **quantity-edit policy per flow** · **auto-created draft gate passes from source submission** · returnable lifecycle with overdue detection · target creation for PR/SCR/SE/DN (auto and manual) · reverse guards on ERPNext documents · event log and structured logging · notifications (email, plus WhatsApp when the app is present) · QR on the printed slip, with `scan` and `yard_status` API endpoints ready for the console · **9 reports** including Pending Gate Passes, Discrepancy Register, Compliance Exceptions and Enforcement Impact Preview · workspace · 3 print formats · 5 roles with row-level filtering · full test suite.

## D.3 v1.1 — "People & Process" *(≈ 5 weeks after v1.0)*

Now specified, not just named.

**Mobile gate console** — moved here from v1.0 on 2026-10-30. The product plan's §16.2 describes it (scan, confirm, capture, submit; yard view; overdue returns; offline draft queue). The `scan` and `yard_status` endpoints it calls already ship in v1.0; the route and UI do not. Re-estimate when scoped.

**1. Visitor & people gate passes**
New child `Gate Pass Person`: `person_name` · `person_type` (Visitor / Driver / Helper / Contractor / Employee) · `id_type` (Aadhaar / PAN / Driving Licence / Passport / Employee ID / Other) · `id_number` · `mobile` · `photo` (Attach Image, camera capture) · `company_represented` · `whom_to_meet` (Link → Employee) · `in_time` · `out_time` · `pass_number` · `remarks`.
New `gate_pass_type` values already reserved (`Visitor`, `Vehicle Only`). New rules: `PERSON-ID-REQUIRED` · `PERSON-HOST-REQUIRED` · `PERSON-OVERSTAY` (threshold in hours) · `PERSON-BLACKLIST`. New master `Gate Pass Blacklist` (party or ID number, reason, expiry). New print format: **Visitor Badge** (label-printer size, photo + QR). New report: **Visitor Register**. Mobile console gains a person-capture flow.
*Why deferred:* it is a self-contained addition that does not touch the ledger, and it opens a market (offices, hospitals, campuses) that has no use for the material flows. Better shipped once the core is proven than bundled into an already-large v1.0.

**2. Approval workflow template**
A shipped, optional Frappe Workflow: `Draft → Pending Approval → Approved → Submitted`, with `approval_required_above_value` and `approval_required_for_types` thresholds in Settings, and an `Approval Required` rule with its own action. Not built into the document — installed as a template so customers who do not want it are unaffected.

**3. Bulk & template gate passes**
`Gate Pass Template` master (pre-filled party, items, purpose) for repeating movements such as daily scrap removal or canteen supply. A bulk-create tool producing many gate passes from a list of source documents, and `Auto Repeat` support for scheduled recurring passes.

**4. Label printing**
Direct-to-label-printer formats (Zebra/TSC) for gate slips and visitor badges.

## D.4 v2.0 — "Integrations & Yard" *(a separate initiative, scoped after v1.1 ships)*

**1. Device integrations** — an abstraction layer (`Gate Pass Device` master: type, protocol, endpoint, credentials from the site config) with adapters for weighbridge serial/TCP readouts, ANPR camera webhooks that create a draft pass from a plate read, and RFID/barcode gate readers. Deliberately an adapter pattern: hardware varies wildly by site, and no single implementation will serve everyone.

**2. Dock & appointment scheduling** — `Dock` master, `Gate Pass Appointment` doctype, slot capacity per dock per hour, a calendar view, and supplier-facing self-booking through the portal.

**3. Transporter portal** — a Website User role letting a transporter see their expected deliveries, upload documents in advance, and track gate status. Turns the app into a supplier-collaboration tool.

**4. Yard occupancy** — a live view of what is inside by location, dwell-time alerts, and a visual yard map.

**5. Analytics module** — turnaround trends, supplier on-time delivery computed from actual gate times rather than document dates, gate throughput heat-maps, and exception trending.

## D.5 Timeline impact

| | Weeks | Cumulative |
|---|---|---|
| v1.0 (product plan §20) | 16.0 | 16.0 |
| v1.1 | 5.0 | 21.0 |
| v2.0 | scoped later | — |

v1.0 grew from 13.5 to 16 weeks with the compliance framework (+1.5), the discrepancy model (+0.5), and the extra reports and seeded flows (+0.5). All three are load-bearing: compliance is the strongest single reason an Indian customer adopts this rather than building it themselves, discrepancy is what makes the gate a control rather than a formality, and Pending Gate Passes is the report the store manager opens every morning.

If the timeline needs compressing, the honest cut is **v1.1's visitor module**, not any part of this. Compliance and discrepancy are core; visitor passes are a separate market.
