# Gate Pass Management — Feature List

*Marketing and sales reference. Every feature listed here is implemented in the app.*

---

## The one-line pitch

**ERPNext knows what you ordered. Gate Pass knows what actually arrived.**

---

## The elevator version

Every factory and warehouse has a gate. ERPNext has no idea it exists.

Material arrives hours before anyone raises a receipt. Job-work material leaves and never fully comes back. A receipt says 100 when 80 arrived, and nothing independent contradicts it. A truck leaves without an E-Way Bill and is detained on the highway with your goods on it.

Gate Pass Management closes that gap. It records every movement at the boundary, reconciles it against the ERPNext documents you already use, and blocks what should not leave — without ever touching your stock ledger.

---

## Positioning

| | |
|---|---|
| **Category** | Gate control and material movement for ERPNext |
| **Built for** | Manufacturing, warehousing, distribution, contract manufacturing, job work |
| **Users** | Security guards, store keepers, purchase and subcontracting officers, plant managers, auditors |
| **Platform** | Frappe / ERPNext v16 |
| **Licence** | GPL-3.0 — free and open source |
| **Install time** | Under 10 minutes, including a working gate pass |

---

## What makes it different

### 1. It is a control document, not a parallel stock system

Gate Pass **never** writes a Stock Ledger Entry, touches valuation, or creates a GL Entry. It records physical movement and reconciles against ERPNext's own documents.

**Why this matters:** you can install it on a live production ERP without risk to your stock or your books. Most alternatives try to become a second inventory system, which is why they never get past pilot.

### 2. Progressive enforcement — safe from day one

Ships in **Advisory** mode. Every rule records and warns; nothing blocks. When you are ready, tighten one rule at a time.

The **Enforcement Impact Preview** report replays your own history against a candidate configuration and shows exactly what would have been stopped, by rule and by user. You tighten with evidence, not hope.

**Why this matters:** nobody's production ERP breaks on install day. This is the single biggest reason gate-control projects fail, and it is designed out.

### 3. Sixty rules, 44 of them yours to configure

Each configurable rule is **Block**, **Warn**, or **Ignore**, resolved through four layers (a further 16 integrity checks are fixed, because bypassing them would corrupt the ledger):

```
Global preset  →  Per-rule setting  →  Per-flow override  →  Bypass role
```

Block on over-quantity for purchase receipts while warning on delivery notes. Block everyone except the plant manager, who gets a warning and must state a reason. No code, no fork.

**Why this matters:** the same install serves two plants with different disciplines. Your consultants configure; they do not develop.

### 4. Statutory compliance enforced at the gate

The gate is the last point where a non-compliant dispatch is still preventable.

Ships with an **India provider** (it needs the India Compliance app, and switches off cleanly when that app is absent): blocks dispatch until the E-Invoice (IRN) and E-Way Bill actually exist on the invoice. Thresholds are read live from GST Settings and the state-wise E-Way Bill master — never hard-coded, because the limits change and vary by state.

The operator sees plain language — *"Ask Priya, who created SI-00123, to generate the E-Way Bill"* — with a **Re-check** button to press once it is done, while the vehicle waits.

Compliance rules stay at Block even under the Advisory preset. Advisory describes your own process maturity; it is not permission to break the law.

**Why this matters:** one detained truck costs more than the entire implementation. The framework is jurisdiction-neutral — any country pack can register checks through a hook.

### 5. A consumption ledger that survives reality

Every gate pass row remembers the exact source line it draws on. Partial deliveries chain correctly across many gate passes and many receipts, and over-receipt on one order line can never be masked by under-receipt on another line of the same item.

Reads happen under a database row lock, so two operators processing the same purchase order at the same instant cannot both slip through.

**Why this matters:** partial deliveries are the normal case, not the exception. Systems that get this wrong quietly over-receive, and nobody notices until the year-end count.

### 6. Discrepancy captured where it is discovered

Shortage, damage and rejection are recorded at the gate — per item, with a reason and a **liable party** (supplier, transporter, internal).

**Accepted quantity**, not the paperwork quantity, is what flows into the Purchase Receipt. Damaged goods and goods rejected at the gate map to rejected quantity with a rejected warehouse, automatically. Whether a counted shortage is also booked as rejected stock is a setting you choose: by default short goods are simply not received, so the order line stays open.

Damage found while unloading, after the pass is submitted, can still be recorded — role-gated, reason required, fully audited, and refused once a receipt exists.

**Why this matters:** the gate's physical count becomes the receipt's count. And the Discrepancy Register turns recorded damage into supplier scorecards and transporter claims — the report that pays for the app.

### 7. Auto-created draft gate passes

When a configured source document is submitted, a draft gate pass appears in the gate's worklist, already carrying the items and assigned to the right role. The guard adds vehicle and driver, confirms what arrived, and submits.

**Why this matters:** it inverts the workflow from *create from scratch under time pressure* to *complete and confirm*. Lower friction and materially better data.

### 8. Quantity policy per flow

Outward dispatch against an invoice is **locked to source** — the gate verifies what leaves, it does not get to restate the invoice. Inward against a purchase order is **editable**, because what arrived is genuinely unknown until it is counted.

**Why this matters:** it puts the right control in the right place, instead of one blanket rule that is wrong half the time.

### 9. Audit trail that cannot be edited

Every state change, correction, warning and override writes an immutable event. The log has **no write or delete permission for any role — including System Manager**.

Post-submit changes to entry and exit times — the fields most worth tampering with — are role-gated, require a reason, and record the previous value. The form displays a visible warning when timestamps have been amended.

**Why this matters:** an audit trail that can be edited is not an audit trail.

### 10. Real observability

Every error carries a **trace ID** that appears in the event log, the Error Log and the structured JSON log. "Why didn't this create a receipt?" is answerable from the UI in under a minute.

No swallowed exceptions. No partial batch reported as success. When a batch partially fails, the app shows both columns: created, and failed with reasons.

**Why this matters:** this is the difference between a two-minute answer and a two-hour database session.

---

## Feature inventory

### Gate pass document
- Inward and outward in one document, direction derived from the source
- Five types: Material, Returnable Material, Non-Stock, Visitor, Vehicle Only
- Eleven-state lifecycle: Draft → At Gate → Inside → Partially Processed → Completed, plus the returnable path through Pending Return, Partially Returned, Returned and Overdue Return
- Vehicle, driver, transporter, LR/consignment, e-way bill number
- Weighbridge gross / tare / net
- Photo capture for vehicle, goods and documents
- Configurable document checklist per flow, blocking submission when required
- Charges, with mandatory rows where configured
- Free-text items for tools, scrap, samples and documents with no Item master
- Batch and serial capture
- Several documents from one party on a single pass, with a list of them and a one-click remove while a draft; a different party or a repeated document is refused
- A picker that offers only what still has something left to pass
- Fifteen ready-made purposes, offered only for the direction they fit, each pre-filling its usual pass type
- Party address and contact limited to the chosen party, with the contact's mobile filled in
- Allowed party types, and a separate numbering series for inward and outward passes
- Tracking ID from a placeholder template (`{{ party_code }}/{{ reference_no }}`), rendered once at creation and then frozen

### Source flows — twelve shipped, unlimited configurable
Purchase Order · Subcontracting Order (finished goods) · Subcontracting Order (raw material out) · Stock Entry (send to subcontractor) · Stock Entry (transit out) · Stock Entry (transit in) · **Stock Entry (manual return, before any return entry exists)** · Purchase Receipt return · Subcontracting Receipt return · **Sales Invoice** · Delivery Note · **Gate Pass return leg**

Each flow configures: child table, item/qty/UOM/rate/warehouse/BOM fields, pending formula, allowed statuses, party resolution with one level of indirection, selection filters, permitted roles, quantity policy, over-quantity allowance, target document and creation mode, required documents, compliance checks, and rule overrides.

### Target documents
- Purchase Receipt, Subcontracting Receipt, Stock Entry, Delivery Note
- Auto on submit, manual button, or pulled from the target's own form
- Uses ERPNext's own mappers, so taxes, currency, terms and company defaults come along
- Idempotent — a double click produces one receipt and a clear message
- Savepoint per target: one failure rolls back only that target, and is reported
- Never `ignore_validate`, never `ignore_mandatory` — if ERPNext refuses, you see why

### Reverse controls on ERPNext documents
- Require, or forbid, a gate pass on a receipt, transfer or dispatch
- Per-source-line quantity caps, not just document totals
- Row coverage check that **fails closed** — unreferenced rows are reported, not skipped
- Optionally remove the source form's native Create button, enforced server-side so API and bulk imports cannot bypass it
- Internal supplier and customer transfers skipped automatically

### Compliance
- Provider framework, registered through a hook
- India: E-Invoice (IRN) and E-Way Bill, thresholds from GST Settings
- Six statuses, colour-coded, with plain-language remediation
- Re-check button, and automatic re-verification inside the submitting transaction
- **Fails closed** when a provider is unreachable
- Overrides recorded with user and reason
- Passing numbers printed on the gate slip the driver carries

### Configuration
- 76 global settings in 18 sections
- 44 configurable rules with per-rule action, threshold, bypass roles and custom message, plus 16 fixed integrity checks
- Field rules: make any field mandatory, hidden or read-only, scoped by direction, type or flow
- Document checklist and charge types
- Four one-click enforcement presets

### Access control
- Four purpose-built roles
- Row-level restriction by source flow, location, gate and company
- Enforced in both the permission query and `has_permission`

### Reporting
Pending Gate Passes (with ageing) · Gate Pass Register · Gate Pass vs Document Reconciliation · Discrepancy Register · Pending Returnable Gate Passes · Vehicle Movement & Turnaround · Gate Pass Exceptions · Compliance Exceptions · Enforcement Impact Preview

### Operations
- Daily overdue-return detection with reminders and escalation
- Configurable audit-log retention
- Structured JSON logging with three verbosity levels
- Idempotent install and migrate; rules and flows reconcile without overwriting your configuration
- Clean uninstall that removes app-owned fields and leaves your records alone

---

## Objection handling

**"Will this break our live ERP?"**
No. It ships in Advisory mode where nothing blocks, and Gate Pass Settings has a master switch that makes every hook inert instantly. It also never writes to the stock ledger or the general ledger.

**"We have a unique process."**
Twelve flows ship as configuration you can duplicate and edit. Each defines its own field mapping, quantity policy, roles, documents and rules. Most "unique" processes are a new Gate Pass Source record, not a development project.

**"Our guards can't use ERPNext."**
Direction is derived from the document, quantities are pre-filled, drafts can be created automatically so the guard only confirms, and accepted quantity is calculated from what they report as short or damaged. They enter vehicle, driver, and what went wrong.

**"What about GST compliance?"**
Enforced at the gate, reading live from `india_compliance` and GST Settings when that app is installed. Thresholds come from the state-wise master, never hard-coded. Overrides are possible but always recorded.

**"How do we know it's working?"**
Nine reports, an immutable audit trail, and a trace ID on every error that ties the user's message to the log and the Error Log.

**"Why not build it ourselves?"**
You can. Budget for the consumption ledger with row locking, idempotent target creation, a fail-closed compliance framework, an unforgeable audit trail, 60 configurable rules, and nine reports. Then budget for maintaining it across ERPNext upgrades.

---

## Requirements

Frappe v16 · ERPNext v16 · `india_compliance` optional, only for Indian statutory checks (the app self-disables those cleanly when it is absent)
