# Gate Pass for ERPNext — Product Plan

**Target:** Frappe / ERPNext **v16** · Public app · Frappe Marketplace
**Author role:** Product Manager
**Status:** For approval. No code written.
**Basis:** Domain understanding drawn from two prior in-house implementations built for manufacturing clients. **This is a new app. Nothing is ported line-for-line.** That prior code served as a requirements source and as a defect register (§14); it is not referenced here by name or by content.

---

# Part I — Product

## 1. Problem statement

Every factory, warehouse, and distribution centre runs a physical control point that ERPNext does not model: **the gate**. Material physically arrives or leaves hours before — or after — the corresponding ERPNext document exists. Today that gap is filled by a paper register, an Excel sheet, or a WhatsApp photo.

The consequences are concrete and expensive:

- **Unrecorded arrivals.** Goods sit in the yard for days; nobody knows a PO is partially delivered until the storekeeper gets to it.
- **Unauthorised removals.** Material leaves the premises with no document trail. Job-work RM sent to a subcontractor is the classic loss point.
- **Receipt fraud and error.** A Purchase Receipt is entered for 100 units when 80 arrived, and there is no independent record to check it against.
- **No returnable tracking.** Tools, dies, moulds, and gas cylinders go out "for repair" and are never reconciled.
- **Audit failure.** Statutory and customer audits ask "show me what entered the premises on 14 March" and the answer is a photograph of a notebook.

ERPNext has no Gate Pass DocType in v15 or v16 (verified against the local `erpnext` checkout — zero matches for gate pass / gate entry). The marketplace has no widely-adopted, configurable one either. There is a real, unserved need in the exact segment ERPNext already sells to.

## 2. What this product is — and is not

**Gate Pass is a control document, not a stock document.**

It records a physical movement across a boundary and reconciles it against the commercial documents that ERPNext already owns. **It never posts a Stock Ledger Entry, never touches valuation, and never creates a GL Entry.** This is the single most important product principle, and it is what keeps the app safe to install on a live ERP.

| Gate Pass **is** | Gate Pass **is not** |
|---|---|
| A physical-movement record at a boundary | A stock transaction |
| An independent qty record to reconcile receipts against | A replacement for Purchase Receipt / Delivery Note |
| A control that can *block* a downstream document | A parallel inventory system |
| An audit trail of who/what/when/which vehicle | A WMS, TMS, or yard-management system |
| A launcher for the correct ERPNext document | A place to price, tax, or value goods |

**Explicit non-goals for v1:** dock scheduling, appointment booking, ANPR/camera integration, weighbridge hardware protocols, RFID, biometric turnstiles, driver payment/settlement, transporter freight billing.

## 3. Users

| Persona | Context | Needs |
|---|---|---|
| **Security Guard / Gate Operator** | Phone or shared tablet at the gate. Often low digital literacy. High volume, time-pressured, sometimes offline-ish network. | Scan or pick a reference, count items, photograph the vehicle, submit in under 90 seconds. Cannot be expected to navigate the ERPNext desk. |
| **Store Keeper / Receiving Clerk** | Desk. Converts arrivals into Purchase Receipts. | See what arrived, what's still in the yard, create the receipt pre-filled and capped at what actually came in. |
| **Purchase / Subcontracting Officer** | Desk. | Know a PO's real delivery status; know which job-work RM is still with which vendor. |
| **Plant / Warehouse Manager** | Desk + dashboard. | Yard visibility, overdue returnables, vehicle turnaround, exception report. |
| **Auditor / Compliance** | Read-only, periodic. | Immutable register, tamper evidence, "who changed the entry time and when". |
| **System Administrator / Implementer** | Setup once, per customer. | Configure the whole thing without writing code. This persona decides whether the app gets adopted. |

## 4. Product principles

1. **Configuration over code.** If a customer needs a different rule, that is a setting, not a fork. The prior implementations failed this badly — a supplier's legal name, a go-live date, and two role names are compiled into their business logic. Nothing customer-specific ships in this app, ever.
2. **Zero-config default.** A fresh install must produce a working, sensible Gate Pass for the most common flows with no setup at all. Time-to-first-gate-pass target: **under 10 minutes**, install included.
3. **Progressive enforcement, configured per rule.** Every business rule resolves to **Block / Warn / Ignore**, set globally, per rule, per source flow, and per role. Ship with the **Advisory** preset — everything warns, nothing blocks — and let customers tighten rule by rule with evidence from the Enforcement Impact Preview report. Nobody's production ERP breaks on install day. Full model and rule catalogue: `GATE_PASS_CONFIG_REFERENCE.md`.
4. **Never fail silently.** Every failure surfaces to the user with a cause and a log reference. No swallowed exceptions, no `ignore_validate`, no partial success reported as success. (§9, §14)
5. **The server is the authority.** Every rule is enforced server-side. Client scripts are convenience only. A rule that exists only as a hidden button is not a rule.
6. **Auditable by construction.** Every state transition and every post-submit mutation writes an immutable event row. (§9.2)
7. **Correct under concurrency.** Two gate operators working the same PO at the same instant must not both pass validation. (§8)
8. **Mobile-first at the gate, desk-first everywhere else.**

## 5. Positioning & differentiation

Against a paper register: obvious. Against a custom implementation: this is the pitch to the community.

| Differentiator | Why it matters |
|---|---|
| **Statutory compliance gating at the gate** | Blocks dispatch until the E-Invoice (IRN) and E-Way Bill actually exist. The gate is the last point where non-compliance is still preventable, and in India this is a legal requirement, not a nicety. Pluggable, so it is not India-only. |
| **Discrepancy capture — shortage, damage, rejection** | The gate is where damage is *discovered*. Recording it there, and carrying it into the receipt as rejected qty, is the difference between a control document and a formality. |
| **Bidirectional + returnable** in one document | Most attempts do inward only. Job-work and tools-out are where money actually leaks. |
| **Source-agnostic, configurable mapping** | Works with PO, SCO, SE, DN, SI, PR/SCR returns — and any future doctype — without code. |
| **Consumption ledger** | Partial gate passes chain correctly. This is the hard part and is what makes it usable beyond toy scenarios. |
| **Advisory → Mandatory** | Safe adoption path on a live ERP. |
| **Mobile gate console + QR** | The guard never opens the desk. This alone determines whether the app is actually used. |
| **Item-less passes** (visitor, vehicle, tools, documents) | Widens the market well past manufacturing. |
| **Real observability** | An implementer can answer "why didn't this create a receipt?" from the UI. |

## 6. Success metrics

| Metric | Target |
|---|---|
| Time from `bench install-app` to first submitted Gate Pass | < 10 min |
| Configuration achievable without code, for the 8 seeded flows | 100% |
| Gate operator: reference-scan → submit | < 90 s median |
| Test coverage of the validation catalogue (§7) | 100% of numbered rules |
| Marketplace rating | ≥ 4.0 |
| Support questions answerable from Gate Pass Event Log alone | ≥ 80% |

## 7. Scope

> **Tiering is specified in full in `GATE_PASS_CONFIG_REFERENCE.md` Part D.** Summarised here.

### v1.0 — the shipping product (≈13.5 weeks)
Core Gate Pass In/Out · items with source references · consumption ledger with row locking · `Gate Pass Source` configuration (8 seeded flows) · Settings with 4 enforcement presets and the 37-rule configuration table · field rules · document checklist · charges · weighbridge fields (manual) · returnable lifecycle with overdue detection · target creation for PR/SCR/SE/DN · reverse guards on ERPNext docs · event log + structured logging · notifications (email, and WhatsApp when that app is present) · mobile gate console with QR scan and offline draft queue · 6 reports · workspace · 3 print formats · 5 roles with row-level filtering · full test suite.

### v1.1 — "People & Process" (≈5 weeks)
Visitor & people gate passes (`Gate Pass Person`, ID capture, host, overstay and blacklist rules, visitor badge, visitor register) · approval workflow template · `Gate Pass Template` + bulk creation + Auto Repeat · direct label printing.

### v2.0 — "Integrations & Yard" (scoped after v1.1)
Device abstraction layer with weighbridge / ANPR / RFID adapters · dock & appointment scheduling · transporter portal · yard occupancy view · analytics module.

### Explicitly out of scope, permanently
Anything that writes a Stock Ledger Entry or GL Entry.

### Explicitly out of scope, permanently
Anything that writes a Stock Ledger Entry or GL Entry.

---

# Part II — Design

## 8. Domain model

### 8.1 Core concepts

**Direction.** Every gate pass is `In` or `Out`. Single doctype, not two — the field set overlaps ~85%, reporting must be unified, and In/Out pairs must reference each other for transit and returnable flows.

**Source.** Optionally, the ERPNext document that authorises the movement (a PO authorises an inward; a DN authorises an outward). A gate pass may have **no** source — a visitor, a tool going out for repair, an unplanned delivery. Source is configured, never hard-coded (§10.2).

**Target.** Optionally, the ERPNext document the gate pass produces or is consumed by (a PO-sourced inward gate pass produces a Purchase Receipt). One gate pass may produce **many** targets over time. This is a child table, never a scalar link — the prior implementation used a scalar `purchase_receipt` field and consequently could not represent partial receiving at all.

**The consumption ledger.** The central mechanism. Each `Gate Pass Item` row stores `source_row` — the **name of the source document's child row** (e.g. a specific `Purchase Order Item`). Consumed quantity for any source row is:

```
consumed(source_row) = Σ Gate Pass Item.qty
                       WHERE source_row = <row>
                         AND parent gate pass docstatus = 1
```

`pending(source_row) = ordered_qty − max(received_qty, consumed(source_row))`

This makes partial gate passes chain correctly, is the unit both validation and UI operate on, and is computed under a row lock (§11.1) so it is correct when two operators work concurrently.

**Line-level everything.** Every quantity rule operates per source row, never on document totals. The prior implementation checked only the header total against the gate pass total, which permits receiving 100 of item A and 0 of item B against a 50/50 gate pass. That class of bug is designed out here.

### 8.2 DocType inventory

| DocType | Kind | Purpose |
|---|---|---|
| `Gate Pass` | Submittable | The transaction |
| `Gate Pass Item` | Child | Goods rows |
| `Gate Pass Person` | Child | People rows (visitor/driver/helper) — v1.1 |
| `Gate Pass Document` | Child | Attachment checklist instance |
| `Gate Pass Compliance Check` | Child | Statutory check results (E-Invoice, E-Way Bill, …) |
| `Gate Pass Charge` | Child | Freight / handling / other |
| `Gate Pass Reference` | Child | Target documents produced |
| **`Gate Pass Source`** | **Master (standalone)** | Per-source-document behaviour. **Standalone, not a child of Settings** — it must be a `Link` target from `Gate Pass.source_type`, it must be fixture-exportable, and it owns its own child tables. |
| `Gate Pass Source Field Map` | Child of Source | Field-to-field mapping |
| `Gate Pass Source Checklist` | Child of Source | Required documents per source |
| `Gate Pass Compliance Rule` | Child of Source | Which statutory checks apply, threshold, action |
| `Gate Pass Settings` | Single | Global configuration |
| `Gate Pass Field Rule` | Child of Settings | Per-field mandatory/hidden/read-only |
| `Gate Pass Charge Type` | Child of Settings | Charge rows to seed |
| **`Gate Pass Event Log`** | Standalone, non-submittable, insert-only | Immutable audit trail |
| `Gate` | Master | Physical gate |
| `Gate Pass Location` | Master (tree) | Site / plant / branch |
| `Gate Pass Purpose` | Master | Purpose taxonomy |

---

## 9. Data model — full field specification

Legend: **R** reqd · **RO** read-only · **H** hidden · `→` Link target · `⇐` fetch_from

### 9.1 `Gate Pass` (submittable, `track_changes`, `track_seen`)

**Naming:** `Document Naming Rule`-compatible. Default series `GP-.YYYY.-`; optional per-direction series `GP-IN-.YYYY.-` / `GP-OUT-.YYYY.-`; optional per-location prefix. Configured in Settings, applied via Property Setter, never hard-coded.

#### Section — Basic
| Fieldname | Type | Options / → | Default | Flags | Notes |
|---|---|---|---|---|---|
| `naming_series` | Select | from Settings | `GP-.YYYY.-` | R | |
| `company` | Link | → Company | user default | R | |
| `direction` | Select | `In`\n`Out` | — | R | **Auto-derived from `source_type.direction` and read-only whenever a source is chosen.** User-selectable only on source-less passes (visitor, tools, unplanned). Immutable after first save (V-2). The guard picks *what document they are holding*, not a direction — direction is a consequence. |
| `gate_pass_type` | Select | `Material`\n`Returnable Material`\n`Non-Stock`\n`Visitor`\n`Vehicle Only` | `Material` | R | Drives which sections apply |
| `purpose` | Link | → Gate Pass Purpose | — | | |
| `posting_date` | Date | — | Today | R | |
| `posting_time` | Time | — | now | R | |
| `status` | Select | see §12 | `Draft` | RO | Derived, never typed |
| `amended_from` | Link | → Gate Pass | — | RO H | |

#### Section — Gate & Location
| Fieldname | Type | Options / → | Flags |
|---|---|---|---|
| `location` | Link | → Gate Pass Location | R if `Settings.require_location` |
| `gate` | Link | → Gate (filtered by `location`) | R if `Settings.require_gate` |
| `cost_center` | Link | → Cost Center | shown if `Settings.enable_cost_center` |
| `entry_datetime` | Datetime | — | RO — stamped on submit when `direction = In` |
| `exit_datetime` | Datetime | — | RO — stamped on submit when `direction = Out` |
| `turnaround_minutes` | Int | — | RO — computed when both stamps exist |
| `security_officer` | Link | → Employee | **Auto-filled from the session user's Employee record on load**, editable by a manager. This is the accountability field — who was on the gate — and must never be blank on a submitted pass. |
| `security_officer_name` | Data | — | RO, fetched |

#### Section — Party
| Fieldname | Type | Options / → | Flags | Notes |
|---|---|---|---|---|
| `party_type` | Link | → DocType, filtered to `Settings.allowed_party_types` | R | Supplier · Customer · Employee · Contact · Company |
| `party` | Dynamic Link | `party_type` | R | |
| `party_name` | Data | — | RO | Resolved server-side; never a client fetch |
| `party_display_name` | Data | — | | Free text when `party_type` is Contact/blank |
| `address` | Link | → Address | `mandatory_depends_on` from Settings | |
| `address_display` | Small Text | — | RO | |
| `contact_person` | Link | → Contact | | |
| `contact_mobile` | Phone | — | | |

#### Section — Source Document
| Fieldname | Type | Options / → | Flags | Notes |
|---|---|---|---|---|
| `source_type` | Link | → **Gate Pass Source** | RO | Set by the "Get Items From" action |
| `source_doctype` | Link | → DocType | RO | ⇐ `source_type.source_doctype` |
| `source_sub_type` | Data | — | RO | ⇐ `source_type.sub_type` |
| `source_document` | Dynamic Link | `source_doctype` | RO | Populated only when all rows share one source |
| `source_document_date` | Date | — | RO | |
| `is_multi_source` | Check | — | RO | Set when rows span >1 source document |
| `reference_no` | Data | — | R if `Settings.require_reference_no` | Supplier invoice / challan / DC / LR |
| `reference_date` | Date | — | | Cannot be future (V-3) |
| `tracking_id` | Data | — | RO | Rendered once from a Jinja template (§10.3); unique if configured |

#### Section — Vehicle & Transport
| Fieldname | Type | Options / → | Flags |
|---|---|---|---|
| `vehicle_number` | Data | — | R if `Settings.require_vehicle`; normalised uppercase, whitespace-stripped |
| `vehicle_type` | Select | `Truck`\n`Trailer`\n`Container`\n`Tempo`\n`Car`\n`Two Wheeler`\n`Hand Cart`\n`Courier`\n`Other` | |
| `transporter` | Link | → Supplier (`is_transporter = 1`) | |
| `lr_number` / `lr_date` | Data / Date | — | |
| `driver_name` | Data | — | R if `Settings.require_driver` |
| `driver_contact` | Phone | — | |
| `driver_license` | Data | — | |
| `eway_bill_no` | Data | — | shown if `Settings.enable_eway_bill` |
| `gross_weight` / `tare_weight` | Float | — | shown if `Settings.enable_weighbridge` |
| `net_weight` | Float | — | RO — `gross − tare` |
| `weight_uom` | Link | → UOM | default `Kg` |

#### Section — Items
`items` — Table → `Gate Pass Item`. Mandatory unless `gate_pass_type in ("Visitor","Vehicle Only")` or `Settings.allow_gate_pass_without_items`.
`total_qty` — Float, RO · `total_amount` — Currency, RO (shown if `Settings.enable_valuation`) · `total_packages` — Int.

#### Section — People *(v1.1)*
`persons` — Table → `Gate Pass Person` (`person_name`, `person_type`, `id_type`, `id_number`, `mobile`, `photo`, `in_time`, `out_time`, `remarks`). Mandatory when `gate_pass_type = "Visitor"`.

#### Section — Returnable
| Fieldname | Type | Flags | Depends |
|---|---|---|---|
| `is_returnable` | Check | | `direction = Out` and `Settings.enable_returnable`; auto-1 when `gate_pass_type = "Returnable Material"` |
| `expected_return_date` | Date | mandatory when `is_returnable` | |
| `actual_return_date` | Date | RO | |
| `returned_qty` | Float | RO | |
| `return_status` | Select | `Not Applicable`\n`Pending`\n`Partially Returned`\n`Returned`\n`Overdue` | RO |
| `return_gate_passes` | Table → `Gate Pass Reference` | RO | The IN passes that closed this OUT pass |

#### Section — Statutory Compliance *(shown when any compliance rule applies to this source)*

| Fieldname | Type | Flags | Notes |
|---|---|---|---|
| `compliance_checks` | Table → `Gate Pass Compliance Check` | RO | One row per applicable check, evaluated live |
| `compliance_status` | Select | RO | `Not Applicable` · `Pending` · `Passed` · `Failed` — the roll-up |
| `compliance_html` | HTML | RO | Colour-coded status board with a **Refresh** button, so the guard re-checks after the sales team generates the missing document instead of reloading the form |
| `compliance_checked_on` | Datetime | RO | Staleness indicator |
| `compliance_override_by` / `compliance_override_reason` | Link → User / Small Text | RO | Populated only when a rule set to Warn was overridden; always audited |

#### Section — Discrepancy

The gate is where shortage and damage are **discovered**. Recording it here — and carrying it into the receipt — is what makes the gate pass a control document rather than a formality.

| Fieldname | Type | Flags | Notes |
|---|---|---|---|
| `has_discrepancy` | Check | | Auto-set when any row has shortage, damage, or rejection |
| `total_accepted_qty` | Float | RO | Σ `items.accepted_qty` |
| `total_shortage_qty` | Float | RO | Material that did not arrive |
| `total_damaged_qty` | Float | RO | Arrived damaged |
| `total_rejected_qty` | Float | RO | Refused at the gate |
| `discrepancy_notes` | Text | mandatory when `has_discrepancy` | |
| `discrepancy_photo` | Attach Image | | |
| `discrepancy_reported_by` / `discrepancy_reported_on` | Link → User / Datetime | RO | |

**Post-submit discrepancy.** Damage is often found during unloading, after the pass is submitted. Rather than force a cancel-and-amend, discrepancy fields are editable after submit **only** through the audited `record_discrepancy` API: role-gated, reason mandatory, every change written to `Gate Pass Event Log` with old and new values, and refused once any target document is submitted (V-58). This is the same pattern as timestamp amendment (§13.3) — the operational need is real, so it is granted explicitly and audited, not left as a hole.

#### Section — Inspection & Documents
`packaging_condition` (Select: `Good` / `Damaged` / `Partially Damaged`) · `documentation_status` (Select: `Complete` / `Incomplete`) · `inspection_remarks` (Small Text) · `documents` (Table → `Gate Pass Document`) · `vehicle_photo`, `goods_photo`, `document_photo` (Attach Image) · `remarks` (Text).

#### Section — Charges
`charges` (Table → `Gate Pass Charge`) · `total_charges` (Currency, RO). Shown if `Settings.enable_charges`.

#### Section — Processing
| Fieldname | Type | Flags | Notes |
|---|---|---|---|
| `references` | Table → `Gate Pass Reference` | RO | Target documents produced |
| `processed_qty` | Float | RO | Σ qty consumed by submitted targets |
| `per_processed` | Percent | RO | `processed_qty / total_qty × 100` |
| `enforcement_mode` | Select | RO | `Advisory` / `Mandatory` — **snapshotted at submit** so historical docs are judged by the rules that were live when they were created |

### 9.2 `Gate Pass Item`

| Fieldname | Type | Options / → | Flags | Notes |
|---|---|---|---|---|
| `item_code` | Link | → Item | R unless `is_non_stock` | |
| `item_name` | Data | ⇐ `item_code.item_name` | | Editable when `is_non_stock` |
| `is_non_stock` | Check | — | | Free-text item: tools, documents, scrap, samples |
| `description` | Small Text | ⇐ item | | |
| `uom` | Link | → UOM, ⇐ `item_code.stock_uom` | R | |
| `conversion_factor` | Float | default 1 | | |
| `stock_uom` | Link | → UOM | RO | |
| `source_qty` | Float | — | RO | Ordered / required qty on the source row |
| `already_passed_qty` | Float | — | RO | Ledger value at fetch time (display only — never trusted at validate; recomputed under lock) |
| `pending_qty` | Float | — | RO | `source_qty − max(received, already_passed)` |
| `qty` | Float | — | R | The gate-pass quantity — what the paperwork says |
| `stock_qty` | Float | — | RO | `qty × conversion_factor` |
| `accepted_qty` | Float | — | R | **What is actually taken in / released.** Defaults to `qty`; this is the number that flows to the target document |
| `shortage_qty` | Float | — | | Short-delivered against the paperwork |
| `damaged_qty` | Float | — | | Arrived damaged — maps to `Purchase Receipt Item.rejected_qty` |
| `rejected_qty` | Float | — | | Refused outright at the gate |
| `rejected_warehouse` | Link | → Warehouse | | For damaged/rejected qty on the target receipt |
| `discrepancy_reason` | Link | → Gate Pass Discrepancy Reason | mandatory when any of the three above is non-zero | Master, so discrepancies are reportable by cause rather than by free text |
| `rate` / `amount` | Currency | — | amount RO | Shown if `Settings.enable_valuation` |
| `warehouse` | Link | → Warehouse | RO | Carried from the source row; keeps same-item-different-warehouse rows distinct |
| `bom` | Link | → BOM | | Subcontracting; pushed to the SCR |
| `batch_no` / `serial_no` | Link → Batch / Small Text | | Shown if `Settings.enable_batch_serial` |
| `packages` | Int | — | | Cartons / bundles / bags |
| `source_doctype` | Link | → DocType | RO H | |
| `source_document` | Dynamic Link | `source_doctype` | RO H | |
| **`source_row`** | Data | — | RO H | **The ledger key** — name of the source document's child row. Indexed. |
| `processed_qty` | Float | — | RO | Consumed by submitted targets |
| `returned_qty` | Float | — | RO | For returnable OUT rows |
| `remarks` | Small Text | — | | |

**Indexes:** `source_row`, `(source_doctype, source_document)`, `item_code`.

### 9.3 `Gate Pass Reference` (child)

`reference_doctype` (Link → DocType) · `reference_name` (Dynamic Link) · `reference_row` (Data) · `qty` (Float) · `direction` (Select: `Target` / `Return Leg`) · `created_on` (Datetime, RO) · `created_by` (Link → User, RO) · `docstatus_snapshot` (Int, RO).
**Unique constraint** on `(parent, reference_doctype, reference_name, reference_row)` — the idempotency guard for target creation (§11.2).

### 9.4 `Gate Pass Document` (child)

`document_name` (Data, RO — from the checklist) · `is_mandatory` (Check, RO) · `attachment` (Attach) · `document_no` (Data) · `document_date` (Date) · `verified` (Check) · `remarks` (Small Text).

### 9.5 `Gate Pass Charge` (child)

`charge_type` (Data, RO) · `is_mandatory` (Check, RO) · `amount` (Currency) · `paid_by` (Select: `Company` / `Party` / `Transporter`) · `remarks`.

### 9.6 `Gate Pass Event Log` (standalone, insert-only)

The audit spine. Written by the app, never by users; no write/delete permission for anyone including System Manager (§13.3).

| Fieldname | Type | Notes |
|---|---|---|
| `gate_pass` | Link → Gate Pass | Indexed |
| `event` | Select | `Created` · `Submitted` · `Entered` · `Exited` · `Target Created` · `Target Cancelled` · `Timestamp Amended` · `Return Recorded` · `Closed` · `Cancelled` · `Amended` · `Validation Failed` · `Target Creation Failed` |
| `event_datetime` | Datetime | RO, server clock |
| `user` | Link → User | RO |
| `reference_doctype` / `reference_name` | Link / Dynamic Link | The other document involved |
| `field_changed` | Data | For post-submit mutations |
| `old_value` / `new_value` | Data | |
| `qty_delta` | Float | |
| `message` | Small Text | Human-readable |
| `error_log` | Link → Error Log | Set on failure events |
| `trace_id` | Data | Correlates the event with the structured log line and the Error Log (§14.1) |

---

## 10. Configuration model

Three layers, each owning a different kind of decision.

### 10.1 `Gate Pass Settings` (Single) — global policy

**Tab: General**
`enabled` (Check, default 1 — master kill switch; every hook no-ops when off) · `enforcement_preset` (Select `Advisory` / `Balanced` / `Strict` / `Custom`, default **Advisory** — a one-click baseline that rewrites the `Gate Pass Rule` rows; switches itself to `Custom` on any manual edit) · `enforce_from_date` (Date — rules apply only to gate passes and target documents dated on/after this; replaces the compiled-in date literal in the prior implementation) · `naming_series` (Small Text) · `separate_series_by_direction` (Check) · `allowed_party_types` (Table MultiSelect → DocType) · `allow_gate_pass_without_items` (Check) · `allow_backdated_gate_pass` (Check) + `backdate_limit_days` (Int) · `allow_future_dated_gate_pass` (Check).

**Tab: Required Fields** — `require_location`, `require_gate`, `require_vehicle`, `require_driver`, `require_reference_no`, `require_packaging_check`, `require_documentation_check`, `require_vehicle_photo` (all Check).

**Tab: Feature Toggles** — `enable_returnable`, `enable_charges`, `enable_valuation`, `enable_weighbridge`, `enable_batch_serial`, `enable_cost_center`, `enable_security_officer`, `enable_eway_bill`, `enable_qr_code`, `enable_mobile_console`, `enable_people_tracking` (all Check).

**Tab: Tracking ID** — `enable_tracking_id` (Check) · `tracking_id_template` (Code, Jinja; default `{{ party_code }}/{{ reference_no }}`) · `tracking_id_unique` (Check) · `tracking_id_inherit_field` (Data — fieldname on the source doc to inherit from instead of rendering).
The template is rendered **once, in `before_insert`, inside a sandboxed Jinja environment**, and is thereafter immutable. Rendering failure raises a validation error naming the template — it does not silently produce an empty string.

**Tab: Rules** — child table `Gate Pass Rule`, one row per configurable rule: `rule_code` · `rule_name` · `category` · `description` · `default_action` · **`action` (Block/Warn/Ignore)** · `can_ignore` · `applies_to_direction` · `applies_to_gate_pass_type` · `bypass_roles` · `require_override_reason` · `custom_message` · `threshold`. Rows are seeded and reconciled by `after_migrate` — new rules in future versions appear at their defaults, and a customer's edits are never overwritten. Specified in `GATE_PASS_CONFIG_REFERENCE.md` §A.5.

**Tab: Field Rules** — child table `Gate Pass Field Rule`:
`document` (Select: Gate Pass / Gate Pass Item) · `fieldname` (Data, validated to exist) · `applies_to_direction` (Both/In/Out) · `applies_to_gate_pass_type` (Select) · `applies_to_source_type` (Link → Gate Pass Source) · `is_mandatory` / `is_hidden` / `is_read_only` (Check) · `custom_label` (Data) · `default_value` (Data) · `depends_on` (Data).
Unconditional rules are materialised as **Property Setters** on `Settings.on_update`. Conditional rules are applied in the form script **and independently re-checked in `validate`** (V-9). A rule is never enforced by the client alone.

**Tab: Charges** — child table `Gate Pass Charge Type`: `charge_type` (Data) · `default_amount` (Currency) · `is_mandatory` (Check) · `applies_to_direction`.

**Tab: Permissions** — `restrict_by_source_role` (Check) · `restrict_by_location` (Check) · `restrict_by_gate` (Check) · `timestamp_edit_roles` (MultiSelect → Role) · `cancellation_policy` (Select: `Block if Linked Documents Exist` / `Cascade Cancel Targets` / `Allow and Unlink`, default **Block**) · `lock_attachments_on_submit` (Check, default 1) · `attachment_unlock_roles` (MultiSelect → Role).

**Tab: Notifications** — `notify_on_submit` · `notify_roles` · `notify_overdue_returns` · `overdue_reminder_days_before` (Int) · `overdue_escalation_roles` · `email_template` (Link → Email Template) · `enable_whatsapp` (Check — active only when `frappe_whatsapp` is installed; degrades silently to off, with a note in the field description).

**Tab: Advanced** — `ledger_lock_timeout_seconds` (Int, default 30) · `log_level` (Select: `Errors Only` / `Standard` / `Verbose`) · `event_log_retention_days` (Int, 0 = forever) · `enable_api_rate_limit` (Check).

### 10.2 `Gate Pass Source` (Master) — per-source-document behaviour

**This is the heart of the product.** One record per (source document, direction, sub-type). Ships with 8 pre-seeded records covering the common flows; an implementer adds more without code.

| Fieldname | Type | Purpose |
|---|---|---|
| `source_name` | Data (name) | e.g. "Purchase Order — Inward" |
| `enabled` | Check | |
| `direction` | Select `In`/`Out` | Which direction this source appears under |
| `source_doctype` | Link → DocType | |
| `sub_type` | Data | Stamped on the gate pass (Return of Goods, Finished Goods, RM Return, …) |
| `button_label` | Data | Label under "Get Items From" |
| `sequence` | Int | Button order |
| **Item mapping** | | |
| `child_table` | Data | `items`, `supplied_items` |
| `item_field` | Data | `item_code`, `rm_item_code` |
| `qty_field` | Data | `qty`, `required_qty` |
| `consumed_field` | Data | `received_qty` — participates in the pending formula |
| `uom_field` / `rate_field` / `warehouse_field` / `bom_field` | Data | |
| `field_map` | Table → `Gate Pass Source Field Map` | Arbitrary extra source→gate-pass field copies, header and row |
| `pending_formula` | Select | `qty − consumed` · `qty − max(received, consumed)` · `abs(qty) − consumed` · `full qty (no netting)` |
| **Selection** | | |
| `source_filters` | Code (JSON) | Merged into the picker's filters, e.g. `{"docstatus":1,"is_return":1}` |
| `allowed_statuses` | Small Text | Comma-separated status allow-list |
| `party_type` | Select | `Supplier`/`Customer`/`Company`/`From Field` |
| `party_field` | Data | Supports one level of indirection: `subcontracting_order.supplier` |
| `party_filters` | Code (JSON) | Replaces hard-coded supplier-group filters |
| `dialog_fields` | Code (JSON) | Extra pre-filter fields shown before the picker |
| `allow_row_selection` | Check | Child-row picker |
| `row_columns` | Data | Columns shown in the picker |
| `allowed_roles` | MultiSelect → Role | Replaces the compiled-in `…User V1`/`V2` role names |
| **Quantity policy** | | |
| `qty_policy` | Select | **`Editable`** · **`Locked to Source`** · **`Editable within Tolerance`** · `Prefilled, Editable`. Outbound dispatch against a Sales Invoice or Delivery Note must be **Locked to Source** — the guard verifies what leaves, they do not get to restate the invoice. Inbound against a PO is **Editable**, because what arrives is genuinely unknown until it is counted. |
| `allow_over_qty` | Check | |
| `over_qty_allowance_pct` | Percent | Falls back to `Stock Settings.over_delivery_receipt_allowance` |
| `allow_zero_qty_rows` | Check | |
| `allow_discrepancy` | Check | Whether shortage / damage / rejection may be recorded on this flow |
| **Automation** | | |
| `auto_create_draft` | Check | **When the source document is submitted, create a draft Gate Pass automatically.** The dispatch team submits the Stock Entry; a draft pass appears in the guard's worklist needing only vehicle, driver, and confirmation. This inverts the workflow from "guard creates from scratch" to "guard completes and confirms" — materially lower friction and materially better data. |
| `auto_create_assign_to_role` | Link → Role | Who the draft is assigned and notified to |
| `auto_create_condition` | Code (Jinja/Python-safe eval) | e.g. only for `Send to Subcontractor` |
| **Target policy** | | |
| `target_doctype` | Link → DocType | |
| `target_creation_mode` | Select | `None` · `Auto on Submit` · `Manual Button` · `From Target Form` |
| `target_mapper` | Data | Dotted path override; blank ⇒ built-in generic mapper |
| `copy_attachments_to_target` | Check | |
| `block_native_target_button` | Check | Removes the source form's own Create button — **enforced server-side too** (V-39) |
| `enforce_on_target` | Select | `Not Required` · `Required` · `Forbidden` |
| `checklist` | Table → `Gate Pass Source Checklist` | Documents required for this source specifically |
| `compliance_rules` | Table → `Gate Pass Compliance Rule` | Statutory checks for this flow (§10.4) |

**Seeded records (v1.0) — 12 flows:**

| # | Source | Direction | Qty policy | Notes |
|---|---|---|---|---|
| 1 | Purchase Order | In | Editable | The core inbound flow |
| 2 | Subcontracting Order (Finished Goods) | In | Editable | |
| 3 | Subcontracting Order (RM Return) | Out | Editable | |
| 4 | Stock Entry — Send to Subcontractor | Out | Locked to Source | `auto_create_draft` on |
| 5 | Stock Entry — Material Transfer (transit out) | Out | Locked to Source | `auto_create_draft` on |
| 6 | Stock Entry — return (transit in) | In | Prefilled, Editable | Direction auto-derived |
| 7 | **Stock Entry — outbound reference, manual return** | In | Editable | **Material comes back before any return Stock Entry exists.** The guard references the *original outbound* Stock Entry and enters quantities by hand. Common and, until now, missing from the plan. |
| 8 | Purchase Receipt (Return of Goods) | Out | Editable | E-Way Bill check applies |
| 9 | Subcontracting Receipt (FG Return) | Out | Editable | |
| 10 | **Sales Invoice** | Out | **Locked to Source** | **E-Invoice + E-Way Bill checks apply** |
| 11 | Delivery Note | Out | **Locked to Source** | E-Way Bill check applies |
| 12 | Gate Pass (transit In leg) | In | Prefilled, Editable | Gate-to-gate, for sites with no interim document |

### 10.3 `Gate Pass Source Field Map` (child of Source)

`level` (Select: `Header` / `Row`) · `source_field` (Data) · `target_field` (Data) · `is_mandatory` (Check) · `default_value` (Data).
All fieldnames are validated against the actual DocType meta on save, so a typo is caught at configuration time rather than at 2 a.m. at the gate.

### 10.4 Statutory compliance framework

**The gate is the last point at which non-compliant dispatch is still preventable.** Once the truck leaves without an E-Way Bill, the exposure is a penalty and a detained vehicle. Putting the check at the gate — rather than at invoice creation, where it is routinely deferred — is the single highest-value control this app can offer in the Indian market, which is also the largest ERPNext market.

**It must not be India-only.** The framework is a provider interface; India is the first provider, shipped in the box.

#### `Gate Pass Compliance Rule` (child of `Gate Pass Source`)

| Fieldname | Type | Notes |
|---|---|---|
| `check_code` | Select | Populated from registered providers: `IN_E_INVOICE` · `IN_E_WAY_BILL` · `CUSTOM` |
| `label` | Data | Shown to the guard, translated |
| `provider` | Data | Dotted path to a callable returning a `ComplianceResult` |
| `required_when` | Select | `Always` · `Above Threshold` · `From Provider` · `Never` |
| `threshold_amount` | Currency | Used when `required_when = Above Threshold` |
| `threshold_source` | Select | `Fixed Amount` · `From Provider` — India reads the state-wise E-Way Bill threshold from `GST Settings`, so we never hard-code ₹50,000 |
| `action` | Select | **Block** · Warn · Ignore |
| `bypass_roles` | MultiSelect → Role | |
| `require_override_reason` | Check | Default 1 |
| `recheck_on_submit` | Check | Default 1 — re-evaluate immediately before submit, not just on load |

#### Provider contract

A provider is a callable receiving the gate pass and the source document, returning:

```
ComplianceResult(
    status,          # Not Applicable | Not Required | Pending | Generated | Failed | Provider Unavailable
    document_no,     # IRN / EWB number, for display and print
    document_date,
    message,         # plain-language, shown to the guard
    remediation,     # "Ask the sales team to generate the E-Way Bill on SI-00123"
    detail_url,      # deep link to the source doc's compliance section
)
```

#### Shipped provider — India (`india_compliance`)

Active **only when the `india_compliance` app is installed**; otherwise every India rule reports `Not Applicable` and the section stays hidden. No hard dependency, no import error, no half-configured state.

| Check | Reads | Required when |
|---|---|---|
| `IN_E_INVOICE` | `Sales Invoice.irn`, `.einvoice_status` | `GST Settings.enable_e_invoice` is on and the company/turnover conditions in `E Invoice Applicable Company` are met |
| `IN_E_WAY_BILL` | `Sales Invoice.ewaybill`, `Delivery Note.ewaybill`, `Purchase Invoice.ewaybill`, `Purchase Receipt.ewaybill` | `GST Settings.enable_e_waybill` is on and invoice value exceeds the applicable `State Wise E Waybill Threshold` |

Field names verified against the installed `india_compliance` source. The provider is version-guarded and reports `Provider Unavailable` — never a traceback — if the upstream schema changes.

#### Behaviour at the gate

1. On load and on source selection, all applicable checks evaluate and render in the compliance board.
2. A failing check shows the guard **what is missing and who to contact**, from `remediation`. Not an error code.
3. **Refresh** re-evaluates without losing entered data — the guard clicks it after the sales team generates the document, while the truck waits.
4. On submit, checks with `recheck_on_submit` re-run inside the submitting transaction, so a check that passed ten minutes ago cannot let a since-cancelled IRN through.
5. `Block` refuses the submit. `Warn` requires an override reason, and stamps `compliance_override_by` / `compliance_override_reason` and an event log row — so "who let the truck out without an E-Way Bill" is always answerable.
6. Passing check numbers (IRN, EWB) print on the gate slip, which is what the driver actually carries.

#### Extensibility

`hooks.py` exposes `gate_pass_compliance_providers`, so any app — a country pack, a customer overlay — can register a check without touching this app. Candidates: EU customs, Brazil NF-e, hazmat/dangerous-goods declarations, food-safety certificates, weighbridge certification.

---

## 11. Business rules & validation catalogue

Every rule is numbered, server-enforced, independently unit-tested, and carries a stable `rule_code`.

**Enforcement is configured per rule, not globally.** Each rule resolves to **Block / Warn / Ignore** through four layers — global preset → per-rule setting → per-source override → bypass role. Rules marked 🔒 are **HARD**: they always block and cannot be configured, because bypassing them would corrupt the ledger or produce documents that cannot be reasoned about. Rules marked ⚠ are configurable; the action shown below is the shipped **default**, which the `Advisory` preset downgrades to Warn.

**The complete catalogue — 48 rules, 11 HARD, 37 configurable, 24 source-overridable, with rule codes, defaults, thresholds and override semantics — is in `GATE_PASS_CONFIG_REFERENCE.md` Part B.** The tables below give the rule logic and messages.

### On validate — header

| # | Mode | Rule | Message |
|---|---|---|---|
| V-1 | 🔒 | App disabled and document is new | *Gate Pass is disabled in Gate Pass Settings.* |
| V-2 | 🔒 | `direction` / `gate_pass_type` changed after first save | *{Field} cannot be changed after the Gate Pass is saved. Create a new Gate Pass instead.* |
| V-3 | 🔒 | `reference_date > today` | *Reference Date cannot be in the future.* |
| V-4 | 🔒 | `posting_date` outside the allowed backdate/future window | *Gate Pass date {d} is outside the permitted range ({from} to {to}). Adjust the limit in Gate Pass Settings.* |
| V-5 | 🔒 | `is_returnable` with `direction = In` | *Only outward gate passes can be returnable.* |
| V-6 | 🔒 | `is_returnable` and `expected_return_date < posting_date` | *Expected Return Date cannot be before the Gate Pass date.* |
| V-7 | ⚠ | Address required for this `party_type` and missing | *Address is mandatory for party type {t}.* |
| V-8 | 🔒 | Source document's `company ≠ company` | *Gate Pass company {a} does not match {b} on {doctype} {name}.* |
| V-9 | ⚠ | A matching `Gate Pass Field Rule` is mandatory and the value is empty | *{Label} is mandatory for {direction} gate passes of type {t}.* |
| V-10 | 🔒 | No item rows and the type/setting requires them | *At least one item row is required for a {type} gate pass.* |
| V-11 | 🔒 | Rows reference more than one `source_doctype` | *All item rows must come from the same document type. Found: {list}.* |
| V-12 | ⚠ | Rows span multiple source documents with differing party | *All rows must belong to documents of the same {party_type}. Found: {list}.* |
| V-13 | ⚠ | Header `party` ≠ source document's party | *Gate Pass party {a} does not match {b} on {doctype} {name}.* |
| V-14 | 🔒 | Source status ∉ `allowed_statuses` | *{doctype} {name} has status "{s}" and is not open for a gate pass. Allowed: {list}.* |
| V-15 | 🔒 | Source `docstatus ≠ 1` | *{doctype} {name} must be submitted before a Gate Pass can be created against it.* |
| V-16 | 🔒 | `posting_date < enforce_from_date` on a new document | *Gate Pass is effective from {date}. Set an earlier date in Gate Pass Settings if this is intentional.* |
| V-17 | 🔒 | Duplicate `tracking_id` on a submitted pass | *Tracking ID {id} is already used on Gate Pass {name}.* |
| V-18 | 🔒 | `net_weight ≤ 0` when weighbridge enabled and weights entered | *Net Weight must be greater than zero. Gross {g}, Tare {t}.* |
| V-19 | ⚠ | `gate` does not belong to `location` | *Gate {g} does not belong to Location {l}.* |

### On validate — item rows

| # | Mode | Rule | Message |
|---|---|---|---|
| V-20 | 🔒 | `qty ≤ 0` and zero rows not allowed | *Row {i}: Qty must be greater than zero.* |
| V-21 | 🔒 | Item missing and not `is_non_stock` | *Row {i}: Item Code is required. Tick "Is Non Stock" for free-text items.* |
| V-22 | 🔒 | `conversion_factor ≤ 0` | *Row {i}: Conversion Factor must be greater than zero.* |
| V-23 | 🔒 | `is_non_stock` and `item_name` blank | *Row {i}: Item Name is required for non-stock items.* |
| V-24 | ⚠ | Batch/serial required by the Item and missing | *Row {i}: {Batch No / Serial No} is required for Item {code}.* |
| V-25 | 🔒 | Duplicate `source_row` across two rows in the same gate pass | *Row {i} and Row {j} reference the same source line {row}. Merge them into one row.* |
| V-26 | ⚠ | **Per-row over-qty** — `qty > pending_qty × (1 + allowance)` | *Row {i}, Item {code}: qty {q} exceeds the pending qty {p} on {doctype} {name} (maximum {m} with {a}% allowance).* |
| V-27 | ⚠ | **Ledger over-qty** — Σ consumed across submitted passes for this `source_row` + this row's qty > `source_qty × (1 + allowance)` — computed **under row lock** (§11.1) | *Item {code}: total gate-passed qty {t} against line {row} exceeds {o} plus {a}% allowance (maximum {m}). Already passed on: {gate pass links}.* |
| V-28 | 🔒 | `is_non_stock` row on a source-backed gate pass without an explicit allowance | *Row {i}: non-stock items cannot be added to a Gate Pass created from {doctype}.* |

### On submit

| # | Mode | Rule |
|---|---|---|
| V-29 | 🔒 | Every mandatory `Gate Pass Document` row has an attachment — *Attach the required document: {name}.* |
| V-30 | ⚠ | Every mandatory charge has a non-zero amount |
| V-31 | ⚠ | `packaging_condition` / `documentation_status` set when required |
| V-32 | 🔒 | Re-run V-27 under lock immediately before commit — the definitive ledger check |
| V-33 | — | Stamp `entry_datetime` / `exit_datetime`; snapshot `enforcement_mode`; write `Submitted` + `Entered`/`Exited` event rows |
| V-34 | 🔒 | If `target_creation_mode = "Auto on Submit"`, create the target **within the same transaction**. Failure aborts the submit with the underlying error surfaced verbatim plus a log reference. (Contrast with the prior implementation, which logged and continued.) |

### On cancel / amend

| # | Rule |
|---|---|
| V-35 | Policy `Block if Linked Documents Exist`: refuse while any submitted target exists, listing them as clickable links |
| V-36 | Policy `Cascade Cancel Targets`: cancel each submitted target first, in reverse creation order, inside one transaction; re-entrancy guarded by an explicit context manager rather than a global flag or a `form_dict` string sniff |
| V-37 | Policy `Allow and Unlink`: unlink targets and write an event row per unlink |
| V-38 | Cancelling always releases the ledger (submitted → cancelled rows stop counting), recomputes `pending` on affected source rows, and writes a `Cancelled` event |
| V-39 | Amending copies rows but **clears** `references`, `processed_qty`, `returned_qty`, `entry_datetime`, `exit_datetime`, and `tracking_id` — an amended gate pass is a new physical event, not a continuation |
| V-40 | Attachments on a submitted gate pass cannot be deleted unless the user holds a role in `attachment_unlock_roles`; every deletion writes an event row |

### Quantity policy, discrepancy, and compliance

| # | Mode | Rule | Message |
|---|---|---|---|
| V-49 | 🔒 | `qty_policy = "Locked to Source"` and `qty` differs from the source row | *Row {i}: Qty is locked to {doctype} {name} and cannot be changed. Record any difference as shortage or rejection instead.* |
| V-50 | ⚠ | `qty_policy = "Editable within Tolerance"` and the variance exceeds the tolerance | *Row {i}: Qty {q} differs from {s} on the source by more than the permitted {t}%.* |
| V-51 | 🔒 | `accepted + shortage + damaged + rejected ≠ qty` | *Row {i}: Accepted {a} + Shortage {s} + Damaged {d} + Rejected {r} must equal Qty {q}.* |
| V-52 | 🔒 | Any of shortage / damaged / rejected is negative | *Row {i}: Discrepancy quantities cannot be negative.* |
| V-53 | 🔒 | Discrepancy recorded on a source whose `allow_discrepancy` is off | *Discrepancies cannot be recorded on Gate Passes created from {doctype}.* |
| V-54 | ⚠ | `has_discrepancy` and `discrepancy_notes` empty | *Describe the discrepancy before submitting.* |
| V-55 | ⚠ | Row has damage or rejection but no `discrepancy_reason` | *Row {i}: select a Discrepancy Reason.* |
| V-56 | ⚠ | `damaged_qty > 0` and no `rejected_warehouse` on a flow that will create a receipt | *Row {i}: set a Rejected Warehouse so damaged qty can be received separately.* |
| V-57 | 🔒 | A compliance check with `action = Block` did not return `Generated` / `Not Required` / `Not Applicable` | *{Label} has not been generated for {doctype} {name}. {remediation} This Gate Pass cannot be submitted until it is.* |
| V-58 | 🔒 | Post-submit discrepancy edit attempted after any target document is submitted | *Discrepancy cannot be changed after {doctype} {name} has been submitted. Cancel it first.* |
| V-59 | ⚠ | Compliance status is stale (evaluated more than N minutes ago) at submit | Re-evaluated automatically; the message appears only if the re-check now fails |
| V-60 | 🔒 | Compliance provider raised or is unreachable, and the rule is `Block` | *{Label} could not be verified ({reason}). Retry, or ask a Gate Pass Manager to override.* — **fails closed**, never open |

### Reverse guards on ERPNext documents

All gated on `Settings.enabled`, `enforce_from_date`, and the target document's own posting date.

| # | Target | Trigger | Rule |
|---|---|---|---|
| V-41 | PR / SCR / SE / DN / SI | `validate` | `enforce_on_target = Required` and no gate pass → ⚠ *A Gate Pass is required for this {doctype}.* |
| V-42 | same | `validate` | `enforce_on_target = Forbidden` and a gate pass is set → 🔒 *A Gate Pass should not be linked to this {doctype}.* |
| V-43 | same | `validate` | **Fail-closed** row check: every target row that *can* carry a source reference must appear in the gate pass. Rows with no source reference are reported explicitly rather than silently passing — the prior implementation's `if row.ref and row.ref not in mapped` pattern let unreferenced rows through unchecked. → *These rows are not covered by Gate Pass {g}: {list}.* |
| V-44 | same | `before_submit` | **Per source row** (not per document total): Σ target qty for a source row across all submitted targets sharing the gate pass + current > gate pass qty for that row → 🔒 *Item {code}, line {row}: total {t} against Gate Pass {g} exceeds the gate-passed qty {q}.* |
| V-45 | same | `before_submit` | Header-total check retained as a cheap backstop |
| V-46 | same | `on_cancel` / `on_trash` | Decrement `processed_qty`, remove the `Gate Pass Reference` row, write an event, add `Gate Pass` to `ignore_linked_doctypes` |
| V-47 | any | `validate` | Skip V-41..V-45 entirely when the party is an internal supplier/customer (`is_internal_supplier` / `is_internal_customer`) — the generic replacement for a hard-coded company name |
| V-48 | PO / SCO / DN | `validate` (server) | When `block_native_target_button` is on, refuse a target document created without a gate pass — **server-side**, because the prior implementation enforced this only by removing a button in a Client Script, which every API and bulk import bypassed |

---

## 12. Lifecycle & state machine

```
                     ┌─────────┐
                     │  Draft  │
                     └────┬────┘
                          │ submit
              ┌───────────┴────────────┐
     direction=In                 direction=Out
          │                             │
    ┌─────▼─────┐                 ┌─────▼─────┐
    │  At Gate  │                 │  At Gate  │
    └─────┬─────┘                 └─────┬─────┘
          │ entry stamped               │ exit stamped
    ┌─────▼─────┐            ┌──────────┴──────────┐
    │  Inside   │      not returnable         returnable
    └─────┬─────┘            │                     │
          │ targets    ┌─────▼─────┐        ┌──────▼───────┐
          │ created    │ Completed │        │Pending Return│
    ┌─────▼─────┐      └───────────┘        └──────┬───────┘
    │ Partially │                    ┌─────────────┼─────────────┐
    │ Processed │              partial          full        past due
    └─────┬─────┘                    │             │             │
          │              ┌───────────▼──┐   ┌──────▼───┐  ┌──────▼──────┐
    ┌─────▼─────┐        │  Partially   │   │ Returned │  │   Overdue   │
    │ Completed │        │   Returned   │   │          │  │   Return    │
    └───────────┘        └──────────────┘   └──────────┘  └─────────────┘

  any state ──cancel──▶ Cancelled
```

`status` is **derived on every save, on every target/return event, and by a nightly scheduler** (the Overdue transition is the only time-driven one). It is never user-editable. The derivation function is pure and unit-tested against a table of inputs.

---

## 13. Correctness, safety, and observability

This section exists because it is where both prior implementations were weakest. These are requirements, not implementation notes.

### 13.1 Concurrency

**Requirement:** two gate operators creating passes against the same source line simultaneously must not both succeed beyond the available quantity.

- The ledger read in V-27/V-32 acquires a **row-level lock on the source document row** (`SELECT … FOR UPDATE`) inside the submitting transaction, so the second transaction blocks until the first commits and then re-reads the true consumed quantity.
- Target creation acquires a lock on the `Gate Pass` row for the same reason.
- Lock wait is bounded by `Settings.ledger_lock_timeout_seconds`; on timeout the user gets *Another user is currently creating a Gate Pass against {doctype} {name}. Please retry in a moment.* — never a raw deadlock traceback.
- The `already_passed_qty` shown on the form is explicitly a **display-time snapshot** and is documented as such in the field description. It is never the value validated against.

### 13.2 Transactions & idempotency

- **One logical operation, one transaction.** No `frappe.db.commit()` inside any whitelisted method or document hook. (The prior implementation committed mid-request in three places, which makes a later failure leave half the work permanently applied.)
- **Batch operations use savepoints.** When one gate pass produces several targets, each target is wrapped in a savepoint. A failure rolls back only that target, and the operation returns a structured result — `{"created": [...], "failed": [{"source": …, "error": …, "trace_id": …}]}` — which the UI renders as a two-column success/failure dialog. **A partial batch is never reported as a success.**
- **Never `ignore_validate` or `ignore_mandatory`.** If ERPNext refuses to create the target, that refusal is the answer and it is shown to the user. The prior implementation suppressed both flags, which is how invalid Subcontracting Receipts get created.
- **Idempotent target creation.** Guarded by the unique constraint on `Gate Pass Reference` plus a locked pre-read. Double-clicking "Create Purchase Receipt" produces one receipt and a clear message, not two.

### 13.3 Audit trail

Every one of these writes a `Gate Pass Event Log` row, insert-only, with no write or delete permission for any role:

Creation · submission · entry/exit stamping · **any post-submit field mutation** (with old and new value) · target created/cancelled/deleted · return recorded · status transition · attachment added/removed · cancellation · amendment · every ⚠ rule that fired in Advisory mode · every failure.

The prior implementation allowed a `Gate Pass Manager` to silently rewrite the entry and exit timestamps of a submitted document — precisely the field an auditor cares most about — with no record of who changed it or what it was before. That capability is retained (it is operationally necessary) but is now fully audited, role-gated through Settings, and surfaced with a "Timestamps amended" indicator on the form.

### 13.4 Logging

- A dedicated logger, `frappe.logger("gatepass")`, writing structured single-line JSON: `{trace_id, gate_pass, event, source, target, user, duration_ms, outcome, error}`.
- Verbosity from `Settings.log_level` — Errors Only / Standard / Verbose.
- Every user-facing error message carries a **trace ID** that appears in the log line, the `Error Log` record, and the `Gate Pass Event Log` row. An implementer can move between all three from a single string the user read off their screen.
- `frappe.log_error` is used only with `reference_doctype` and `reference_name` populated, so Error Log entries are navigable from the gate pass.

### 13.5 Security

- **No SQL string interpolation of user input, ever.** All queries use the Query Builder (`frappe.qb`) or fully parameterised SQL. Identifiers such as `searchfield` are validated against DocType meta before use, never interpolated. (The prior implementation both interpolated `searchfield` and embedded a company's legal name as a literal inside a WHERE clause.)
- Every `@frappe.whitelist()` method performs an explicit `frappe.has_permission` check on the documents it touches.
- Link queries are decorated with `@frappe.validate_and_sanitize_search_inputs` **in addition to** parameterisation, not instead of it.
- All user-facing messages are built with `frappe.bold` / `get_link_to_form` and translated via `_()`; no hand-concatenated HTML containing document names.
- File attachments respect Frappe's private/public model. Copying an attachment to a target document **copies the file**, it does not share the `file_url` — so deleting one document's attachment cannot destroy another's. Private attachments are copied as private, not skipped.
- Rate limiting available on the public scan/lookup endpoints.

### 13.6 Performance

- The ledger is a single indexed aggregate query per source document, not per row.
- Dashboard connection counts and button visibility use one batched call per form, not one call per check.
- List views and reports are paginated; no report loads unbounded rows.
- Event log retention is configurable, with a nightly cleanup job.
- Target load: 50 000 gate passes with 10 rows each; register report under 3 s for a one-month window.

---

## 14. Defect register — what we are engineering away

Drawn from reading the two prior implementations. Each is a real defect, and each has a named fix in this plan. This list is the justification for building fresh rather than porting.

| # | Defect observed | Consequence | Fixed by |
|---|---|---|---|
| D-1 | Batch target creation wraps each item in `except Exception: log_error; continue` | Partial failure reported as success; users believe receipts exist that do not | §13.2 savepoints + structured success/failure result |
| D-2 | `flags.ignore_validate = True`, `ignore_mandatory = True` on created Subcontracting Receipts and Stock Entries | Invalid documents enter the ERP, bypassing ERPNext's own rules | §13.2 — never used; ERPNext's refusal is surfaced |
| D-3 | `frappe.db.commit()` inside whitelisted request methods (3 sites) | A later failure leaves half the operation permanently applied | §13.2 — one operation, one transaction |
| D-4 | A supplier's legal name embedded as a literal inside a SQL WHERE clause | Unsellable; wrong results for everyone else | §10.2 `party_filters` + §13.5 |
| D-5 | `searchfield` interpolated into SQL via `.format()` | Injection surface | §13.5 — meta-validated identifiers, Query Builder |
| D-6 | A go-live date compiled into two controllers | Every customer needs a code change; backdated documents silently skip all enforcement | `Settings.enforce_from_date` + V-4/V-16 |
| D-7 | Role names compiled into JS and the permission query | Cannot be renamed or reused | `Gate Pass Source.allowed_roles` |
| D-8 | Post-submit timestamp edit with no audit record | The most audit-sensitive field is silently mutable | §13.3 event log + role gating |
| D-9 | Scalar `purchase_receipt` link on the gate pass | Partial receiving structurally impossible; re-creation overwrites history | `Gate Pass Reference` child table |
| D-10 | Target qty guard checks the **document total** only | 100 of item A against a 50/50 gate pass passes validation | V-44 per-source-row check |
| D-11 | Over-receipt aggregated by `item_code` rather than by order line | Over-receipt on one line masked by under-receipt on another | Ledger keyed on `source_row` (§8.1) |
| D-12 | No locking anywhere on the consumed-qty read | Concurrent operators both pass validation and over-consume | §13.1 row locks |
| D-13 | Row checks written as `if row.ref and row.ref not in mapped` | Rows with no source reference pass unchecked — fail-open | V-43 fail-closed |
| D-14 | Attachment copy shares `file_url` and skips private files | Deleting one document's attachment destroys another's; challan scans not copied | §13.5 |
| D-15 | Cancel re-entrancy detected by string-matching `frappe.form_dict["cmd"]` | Breaks in background jobs, API calls, and tests, where `form_dict` is empty | V-36 explicit context manager |
| D-16 | Global `frappe.flags` used as cancel guards | Leak across jobs sharing a worker process | V-36 |
| D-17 | Enforcement implemented by removing a button in a Client Script fixture | Every API call, data import, and bulk operation bypasses it entirely | V-48 server-side enforcement |
| D-18 | Business toggle parked on `Buying Settings` | Configuration scattered across unrelated singles; invisible to implementers | Single `Gate Pass Settings` |
| D-19 | `db_set(..., update_modified=False)` mutating a submitted document | Silent change, invisible to version history | Immutable after submit; changes go through audited APIs |
| D-20 | Tests are a `bench execute` script printing PASS/FAIL, with hard-coded document names | Not runnable in CI; rots immediately | §15 real test suite |
| D-21 | Nothing logged except two error blocks | "Why didn't this create a receipt?" is unanswerable | §13.4 structured logging + event log |
| D-22 | `File.on_trash` hook throws for *all* deletions on submitted gate passes, with no override | No legitimate way to fix a wrong attachment; users cancel-and-amend instead | V-40 role-gated unlock, audited |
| D-23 | Customer-specific fields (fabric width/length, dyed dimensions) in the core item table | Irrelevant columns for 99% of installs | Not in core; a customer overlay app, or an Item Attribute |

---

## 15. Integration surface

### 15.1 Custom fields installed on ERPNext DocTypes

Namespaced `gate_pass_*`, not `custom_*` — an app-owned field should carry the app's identity, and this avoids collision with the customers' existing `custom_gate_pass` / `custom_gate_entry` fields during migration.

| DocType | Fieldname | Type | Notes |
|---|---|---|---|
| Purchase Receipt | `gate_pass` | Link → Gate Pass | Read-only when created from a gate pass |
| Purchase Receipt | `gate_pass_reference_no`, `gate_pass_tracking_id` | Data (fetch) | RO |
| Purchase Receipt | `gate_pass_vehicle_photo` | Attach Image (fetch) | RO |
| Purchase Receipt Item | `gate_pass_item` | Data | RO, hidden — links back to the exact gate pass row |
| Purchase Invoice | `gate_pass`, `gate_pass_tracking_id` | Link, Data | Fetched through the PR |
| Subcontracting Receipt | `gate_pass` | Link → Gate Pass | |
| Subcontracting Receipt Item | `gate_pass_item` | Data | RO H |
| Stock Entry | `gate_pass` | Link → Gate Pass | |
| Stock Entry Detail | `gate_pass_item` | Data | RO H |
| Delivery Note / Sales Invoice | `gate_pass` | Link → Gate Pass | |
| Delivery Note Item | `gate_pass_item` | Data | RO H |
| Purchase Order / Subcontracting Order | `gate_pass_status` | Select | RO — `Not Started` / `Partial` / `Complete` |
| Supplier / Customer | `gate_pass_party_code` | Data | Feeds the tracking-ID template; created only if no equivalent field exists |
| Item | `exclude_from_gate_pass` | Check | Services and non-physical items |

**Nothing is added to `Buying Settings` or `Stock Settings`.** All configuration lives in `Gate Pass Settings`.

### 15.2 Hooks

`doc_events` on Purchase Receipt, Subcontracting Receipt, Stock Entry, Delivery Note, Sales Invoice (validate / before_submit / on_cancel / on_trash) and on File (on_trash).
`override_doctype_dashboards` adding the Gate Pass connection to PO, SCO, PR, SCR, SE, DN, SI, Supplier, Customer — with the `non_standard_fieldnames` entries required wherever the base dashboard assumes a different link fieldname (a documented trap on Purchase Receipt).
`permission_query_conditions` on Gate Pass for source-role, location, and gate restrictions.
`scheduler_events`: daily — overdue-return detection, status refresh, event-log retention; hourly — stale-draft reminder (optional).
`on_app_install` / `after_migrate` — idempotent seeding of Settings, the 8 `Gate Pass Source` records, roles, and masters.

### 15.3 Public API

| Method | Purpose |
|---|---|
| `gatepass.api.source.list_available(direction, doctype)` | Drives the "Get Items From" button group |
| `gatepass.api.source.build(source_type, source_name, filters)` | The single generic mapper — replaces per-source functions entirely |
| `gatepass.api.ledger.get_pending(source_doctype, source_name)` | `{source_row: pending}` |
| `gatepass.api.target.create(gate_pass, target_doctype)` | Idempotent, savepointed, structured result |
| `gatepass.api.gate_pass.query(...)` | Link query — direction, party, and remaining-qty aware |
| `gatepass.api.gate_pass.scan(code)` | QR / barcode lookup for the mobile console |
| `gatepass.api.gate_pass.stamp(name, event)` | Audited entry/exit stamping |
| `gatepass.api.gate_pass.amend_timestamp(name, field, value, reason)` | Role-gated, reason mandatory, audited |
| `gatepass.api.report.yard_status(location)` | Currently-inside summary |

Every method: permission-checked, rate-limitable, structured return, trace ID on every error.

---

## 16. User experience

### 16.1 Desk (clerk / manager)
Standard Frappe form with sections in the order of §9.1. A single **"Get Items From"** button group built dynamically from `Gate Pass Source`. A live pending-qty indicator per row. A connections panel showing targets. An "Amended timestamps" warning indicator where applicable.

### 16.2 Mobile Gate Console — the differentiator
A dedicated route (`/gate`) built with Frappe UI, designed for a phone held one-handed by someone wearing gloves:

1. **Scan or search** — QR on a printed gate pass, or type a PO/DN number, or pick a supplier.
2. **Confirm items** — big touch targets, quantity steppers, "same as ordered" one-tap.
3. **Capture** — camera straight to `vehicle_photo` / `goods_photo` / `document_photo`.
4. **Submit** — one button, clear success or a plain-language error.

Also: a **Yard view** (what is currently inside, by location), and an **Overdue returns** list. Optimised for a 3G connection; failed submits queue as drafts rather than losing the operator's work.

### 16.3 Print & QR
`Gate Pass Slip` (A5, gate copy, large QR of the document name) · `Gate Pass Detail` (A4, items + charges + signatures) · `Returnable Gate Pass` (with a return-acknowledgement block).
QR encodes the document name only — never a token, never a URL with credentials.

### 16.4 Workspace
Shortcuts to Gate Pass (In / Out / Overdue Returns), Gate Pass Settings, Gate Pass Source, the masters, the reports, and the number cards.

---

## 17. Reports & analytics

| Report | Type | Purpose |
|---|---|---|
| **Pending Gate Passes** | Query | **The store manager's daily worklist.** Submitted gate passes with no target document yet, with an ageing column in days and buckets (0–1 / 2–3 / 4–7 / 7+). The single most-used report in the app — it is what turns "material is in the yard" into "someone receives it today". |
| **Gate Pass Register** | Query | The statutory register: date range, direction, location, gate, party, vehicle, item, status, created by |
| **Discrepancy Register** | Query | Shortage, damage, and rejection by supplier, item, reason, and transporter. Feeds supplier scorecards and transporter claims — the report that pays for the app. |
| **Compliance Exceptions** | Query | Dispatches where a compliance check was overridden, by whom, with the reason. Audit-facing. |
| **Gate Pass vs Document Reconciliation** | Query | Source → gate-passed qty → target document(s) → target qty → pending. Works for every configured source, not just PO |
| **Pending Returnable Gate Passes** | Query | Ageing buckets, overdue first |
| **Vehicle Movement & Turnaround** | Query | In/out times, dwell time per vehicle and transporter |
| **Gate Pass Exceptions** | Query | Every rule that fired as a Warn, with the override reason, the user, and the computed values. Over-qty passes, gate passes with no target after N days, timestamp amendments |
| **Enforcement Impact Preview** | Query | Replays the last N days against a candidate preset and lists what *would* have been blocked, by rule and by user. The tool that makes Advisory → Balanced a decision with evidence behind it. |

**Number cards:** Inside Now · Today In · Today Out · Overdue Returns · Unprocessed Gate Passes · Avg Turnaround.
**Dashboard chart:** gate pass volume by direction over time.

---

## 18. Permissions

| Role | Read | Write | Create | Submit | Cancel | Amend | Notes |
|---|---|---|---|---|---|---|---|
| Gate Pass Operator | ✓ | ✓ | ✓ | ✓ | — | — | The guard. Mobile console access. |
| Gate Pass User | ✓ | ✓ | ✓ | ✓ | — | — | Store/purchase staff |
| Gate Pass Manager | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Timestamp amendment, attachment unlock |
| Gate Pass Auditor | ✓ | — | — | — | — | — | Includes read on Gate Pass Event Log |
| System Manager | full | | | | | | No write/delete on Event Log |

Row-level: by **source type** (derived from `Gate Pass Source.allowed_roles`), by **location**, and by **gate** — each independently switchable in Settings. All three are implemented in `permission_query_conditions` **and** `has_permission`, so list, report, and direct-URL access are all covered.

### Reading the source document

A guard must be able to pull items off a Purchase Order without holding Buying
read, since that role also carries price and approval rights. So **Gate Pass
create permission substitutes for read permission on the source doctype**, and
only for the pull: `get_pending`, `build_gate_pass`, and the picker query
`source_query`.

**User Permissions continue to apply.** Once the role requirement is relaxed they
are the only restriction left, so a guard limited to a Company, Gate Pass
Location, Supplier or Warehouse by User Permission cannot pull another site's
documents — the picker does not list them and a direct call is refused. Sites
restrict guards by location this way; it is a deployment step, documented in the
user manual, not a code change.

The picker needs its own query because the ordinary list query raises
`PermissionError` on the source doctype, which would have left the relaxation
unreachable from the UI. `source_query` grants nothing wider than the pull
endpoints: the flow's `allowed_roles`, the flow's configured `source_filters`
applied server-side rather than trusted from the client, submitted documents
only, and the same User Permission filtering.

---

## 19. Testing strategy

- **Unit tests** — one test per numbered rule V-1 … V-48, asserting both the block and the Advisory-mode downgrade. The status-derivation function tested against an input/expectation table.
- **Integration tests** — the six end-to-end flows: PO→GP→PR (full and partial) · SCO RM out → SCR in · branch transit out→in · DN out · returnable out→return in · PR return out.
- **Concurrency tests** — two simultaneous transactions against the same source row; assert exactly one succeeds.
- **Idempotency tests** — double-submit of target creation produces one target.
- **Configuration tests** — every `Gate Pass Source` field exercised; an invalid `field_map` is rejected at configuration time.
- **Migration tests** — seeded fixtures survive `bench migrate` twice (idempotency of `after_migrate`).
- **Permission tests** — each role against each action; row-level filters verified via list, report, and direct GET.
- **CI** — GitHub Actions on every PR: `bench --site test run-tests --app gatepass`, plus ruff/eslint, plus a `grep` gate failing the build on any customer name, hard-coded date, or hard-coded role string in the codebase.

Target: **≥ 85% line coverage, 100% of the numbered rules.**

---

## 20. Release plan

| Phase | Deliverable | Weeks |
|---|---|---|
| **0 — Foundation** | App scaffold, CI, test harness, logging + event-log infrastructure, Settings skeleton, masters, roles | 1.0 |
| **1 — Core document** | Gate Pass + Item + Document + Charge, **rule configuration engine (`Gate Pass Rule`, resolver, presets, seeding/reconciliation)**, field rules, status engine, V-1..V-25 + V-29..V-33, desk form, list view | 2.5 |
| **2 — Sources & ledger** | `Gate Pass Source` master + 8 seeded records, generic mapper, consumption ledger with locking, V-26..V-28, "Get Items From" UX, source-form Create buttons, dashboards | 2.5 |
| **3 — Targets & guards** | Generic target creation (PR/SCR/SE/DN), `Gate Pass Reference`, idempotency + savepoints, V-34..V-48, cancel/amend semantics, attachment handling, **discrepancy model + V-49..V-56 + accepted-qty flow into targets** | 3.0 |
| **3b — Compliance** | Provider framework, `Gate Pass Compliance Rule`, India provider (E-Invoice + E-Way Bill), compliance board + refresh, V-57..V-60, override + audit, Compliance Exceptions report | 1.5 |
| **4 — Returnable & transit** | Returnable lifecycle, return-leg pass, overdue scheduler + notifications, branch-transit flow, **auto-create-draft automation** | 1.5 |
| **5 — Mobile & print** | Gate console, QR, scan API, yard view, 3 print formats | 1.5 |
| **6 — Reporting** | 9 reports incl. Pending Gate Passes, Discrepancy Register, Compliance Exceptions, Enforcement Impact Preview, workspace, number cards, chart | 1.5 |
| **7 — Hardening & launch** | Full test pass, performance run, docs site, screenshots, demo data, marketplace listing | 1.5 |

**≈ 16 weeks, one developer.** Phases 0–3b are the shippable core (10.5 weeks); a private beta with your own customers can start there.

**Beta gate:** Phases 0–3 complete, 100% of the numbered rules tested at all three actions, Advisory preset default, and one internal site running for two weeks with zero data-integrity incidents.

**v1.1** adds ≈5 weeks after v1.0 (`GATE_PASS_CONFIG_REFERENCE.md` §D.3). **v2.0** is a separate initiative, scoped once v1.1 ships.

---

## 21. Marketplace & community readiness

- `pyproject.toml` with `required_apps = ["frappe/erpnext"]`, semantic versioning, classifiers
- README with a 60-second demo GIF, screenshots, and a "what this is not" section
- Documentation site: install, 10-minute quick start, configuration reference (every Settings field), source-configuration cookbook, API reference, troubleshooting via trace IDs
- Idempotent `after_install` / `after_migrate` seeding; clean `before_uninstall` removing app-owned custom fields and property setters
- Full translation extraction; every user-facing string in `_()`
- `LICENSE` (recommend **GPL-3.0** — marketplace convention and keeps community forks open)
- Public issue tracker, `CONTRIBUTING.md`, `CHANGELOG.md`, security-disclosure policy
- Demo data command: `bench --site x execute gatepass.demo.setup` producing a working sandbox

---

## 22. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **v16 ERPNext API drift** — the mapper functions we call (`make_purchase_receipt`, `make_subcontracting_receipt`, `make_stock_in_entry`) may have moved or changed signature. The checkout here is v15.107; v16 is unverified. | High | A thin `gatepass.erpnext_compat` module isolates every ERPNext import. **First task of Phase 0: verify all of these against the v16 branch.** |
| Configuration surface is large enough to intimidate | Medium | Zero-config default; the 8 seeded sources; a guided setup wizard on first open of Settings |
| Mandatory mode breaks a live ERP | High | Advisory default; a "what would have been blocked" preview report before switching |
| Scope creep into WMS/yard management | Medium | §2 non-goals are contractual |
| Marketplace name collision | Low | Check availability before Phase 0; alternatives listed in §23 |
| Performance at high gate volume | Medium | Indexed ledger, batched dashboard calls, explicit performance targets in §13.6 |

---

## 23. Decisions I need from you

1. **App and DocType names.** Recommendation: app `gatepass`, module `Gate Pass`, DocType `Gate Pass`. Needs a marketplace availability check. Fallbacks: `gate_control`, `gatekeeper`, `erpnext_gatepass`.
2. **Licence.** Recommendation **GPL-3.0** (marketplace convention). MIT if you want commercial forks to stay closed.
3. **Visitor / people passes in v1.0 or v1.1?** Specified in `GATE_PASS_CONFIG_REFERENCE.md` §D.3 and scoped to v1.1 to protect the core timeline, but they materially widen the market — offices, hospitals, and schools have no manufacturing use for the rest of the app. Say the word and I move them into v1.0 (+1.5 weeks).
4. **Default cancellation policy.** Recommendation **Block if linked documents exist**. Cascade silently reverses stock ledger entries, which is a dangerous default for a community app.
5. **Default enforcement preset.** Recommendation **Advisory** (everything warns, nothing blocks). Confirm — this is the single biggest adoption decision in the plan. Also confirm the shipped per-rule defaults in `GATE_PASS_CONFIG_REFERENCE.md` Part B, particularly that `QTY-ROW-PENDING` and `QTY-LEDGER` default to **Warn** while `QTY-TARGET-ROW` defaults to **Block** — i.e. we let goods through the gate and record the discrepancy, but we do not let a wrong Purchase Receipt into the ledger.
6. **Weighbridge.** v1 fields only (manual gross/tare/net), device integration deferred to v2. Confirm.
7. **Your three existing customers.** Do we (a) build the public app first and migrate them afterwards, (b) build migration scripts alongside, or (c) leave them on their current apps indefinitely? This changes the plan by roughly 2 weeks and affects whether backward-compatible field names matter at all.
8. **Textile fields** (fabric width/length, dyed dimensions). Recommendation: keep them out of the public app entirely — a small private overlay app for that customer, or Item Attributes.
9. **Compliance scope for v1.0.** Recommendation: ship the framework plus the India provider only (E-Invoice, E-Way Bill). Other jurisdictions arrive through the hook, contributed or commissioned. Confirm you want India in v1.0 rather than v1.1 — it is +1.5 weeks and, in my judgement, the strongest single reason an Indian customer chooses this app over building their own.
10. **Discrepancy → receipt mapping.** Recommendation: `damaged_qty` maps to `Purchase Receipt Item.rejected_qty` with a rejected warehouse, and `accepted_qty` (not `qty`) is what flows to the target. This is ERPNext-native and means the gate's count is the receipt's count. Confirm, because it makes the gate pass genuinely authoritative over the receipt — which is the point, but it is a real shift in who owns the number.
