<div align="center">

# Gate Pass Management

**Control every material movement at the gate.**

Gate passes for inward and outward movement, reconciled against the ERPNext documents you already use.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![Frappe v16](https://img.shields.io/badge/Frappe-v16-blue)
![ERPNext v16](https://img.shields.io/badge/ERPNext-v16-blue)

</div>

---

## The problem

Every factory, warehouse and distribution centre runs a control point that ERPNext does not model: **the gate**. Material physically arrives or leaves hours — sometimes days — before the corresponding ERPNext document exists. That gap is usually filled by a paper register, a spreadsheet, or a photo on WhatsApp.

The consequences are expensive and familiar:

- Goods sit in the yard for days and nobody knows a purchase order is part-delivered.
- Job-work material leaves for a subcontractor with no document trail, and never fully comes back.
- A Purchase Receipt is entered for 100 units when 80 arrived, with no independent record to check it against.
- Tools, dies and cylinders go out "for repair" and are never reconciled.
- An auditor asks what entered the premises on 14 March and the answer is a photograph of a notebook.
- A truck leaves without an E-Way Bill and is detained, along with the goods.

## What this app is

**Gate Pass is a control document, not a stock document.**

It records a physical movement across a boundary and reconciles it against the commercial documents ERPNext already owns. **It never writes a Stock Ledger Entry, never touches valuation, and never creates a GL Entry.** That constraint is what makes it safe to install on a live ERP.

| Gate Pass **is** | Gate Pass **is not** |
|---|---|
| A record of physical movement at a boundary | A stock transaction |
| An independent count to reconcile receipts against | A replacement for Purchase Receipt or Delivery Note |
| A control that can block a downstream document | A parallel inventory system |
| An audit trail of who, what, when and which vehicle | A WMS, TMS or yard-management system |
| A launcher for the correct ERPNext document | A place to price, tax or value goods |

---

## Highlights

**Inward and outward in one document.** Purchase orders, subcontracting, stock transfers, delivery notes, sales invoices, returns — and returnable movements for tools and equipment that must come back.

**A consumption ledger that actually works.** Every gate pass row remembers the exact source line it draws on, so partial gate passes chain correctly across many passes and many receipts. Reads are taken under a row lock, so two operators working the same purchase order at the same moment cannot both slip through.

**Statutory compliance at the gate.** The gate is the last point where a non-compliant dispatch is still preventable. Ships with an India provider that blocks dispatch until the E-Invoice (IRN) and E-Way Bill exist, reading thresholds from GST Settings rather than hard-coding them. The framework is jurisdiction-neutral; other countries plug in through a hook.

**Discrepancy where it is discovered.** Shortage, damage and rejection are captured at the gate, by reason and by liable party. Accepted quantity — not the paperwork quantity — is what flows into the receipt, and damage maps to rejected quantity automatically.

**Configurable rather than forkable.** 60 business rules, each set to **Block**, **Warn** or **Ignore** — globally, per flow, and per role. Twelve source flows ship as data you can duplicate and edit. No customer-specific logic is compiled into this app.

**Safe to adopt.** Ships in **Advisory** mode: everything warns, nothing blocks. Tighten rule by rule using the Enforcement Impact Preview report, which replays your own history against a candidate configuration and tells you exactly what would have been stopped.

**Auditable by construction.** Every state change, every post-submit correction, every warning and every override writes an immutable event. The audit log has no write or delete permission for any role, including System Manager.

---

## Installation

```bash
bench get-app https://github.com/aurigait/gatepass_management
```

```bash
bench --site your-site.local install-app gatepass_management
```

Requires **Frappe v16** and **ERPNext v16**.

Installation seeds twelve working source flows, the rule catalogue, four roles and a set of discrepancy reasons. **A fresh install produces a usable gate pass with no configuration at all.**

---

## Five minutes to your first gate pass

1. Open **Gate Pass Settings**. Confirm the preset is **Advisory** — nothing will block while you learn the app.
2. Create a **Gate Pass Location** for your site, and a **Gate** within it.
3. Assign the **Gate Pass Operator** role to your security staff.
4. Open a submitted Purchase Order, then **Create → Gate Pass**.
5. Add vehicle and driver, confirm what actually arrived, and submit.
6. From the gate pass, press **Create Purchase Receipt**.

Full walkthrough: [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md).

---

## Configuring it for your site

Three layers, each owning a different kind of decision.

**Gate Pass Settings** — global policy. Which fields are mandatory, which features are on, naming, dating limits, permissions, notifications, and the rule table where every rule's action is set.

**Gate Pass Source** — one record per flow, e.g. "Purchase Order — Inward". Defines the child table, quantity fields, pending formula, allowed statuses, permitted roles, quantity-edit policy, required documents, compliance checks, what target document it produces, and whether a draft is created automatically when the source is submitted.

**Rule overrides** — any flow can override a rule for itself. Block on over-quantity for purchase receipts while only warning on delivery notes, without touching anything else.

### Enforcement in four layers

```
Global preset  →  Per-rule setting  →  Per-source override  →  Bypass role
```

Most specific wins. A bypass role can only ever *loosen* a rule — there is deliberately no way to make a rule stricter for one role, because that would make behaviour depend on who is looking.

| Preset | Behaviour |
|---|---|
| **Advisory** | Everything warns, nothing blocks. **The shipped default.** |
| **Balanced** | Data quality and references block; quantity warns. |
| **Strict** | Everything blocks. |
| **Custom** | Set automatically the moment you edit any rule by hand. |

Statutory compliance rules stay at **Block** under every preset. Advisory is a statement about your own process maturity; it is not permission to dispatch without an E-Way Bill. You can still relax one deliberately, per flow, on the record.

---

## Roles

| Role | What it can do |
|---|---|
| **Gate Pass Operator** | Security staff. Create and submit gate passes. |
| **Gate Pass User** | Stores and purchase staff. Also create target documents. |
| **Gate Pass Manager** | Cancel, amend, correct timestamps, override where configured. |
| **Gate Pass Auditor** | Read-only, including the full event log. |

Row-level visibility can additionally be restricted by source flow, location, gate and company — each switchable independently, and enforced in both the permission query and `has_permission` so list views, reports and direct URLs are all covered.

---

## Reports

| Report | What it answers |
|---|---|
| **Pending Gate Passes** | What is in the yard waiting to be received, and for how long. The store manager's morning worklist. |
| **Gate Pass Register** | The statutory register: everything that crossed the gate, by date, party, vehicle and item. |
| **Gate Pass vs Document Reconciliation** | What was gate-passed against what was actually received or dispatched. |
| **Discrepancy Register** | Shortage, damage and rejection by supplier, item, reason and liable party. Feeds supplier scorecards and transporter claims. |
| **Pending Returnable Gate Passes** | What went out and has not come back, overdue first. |
| **Vehicle Movement & Turnaround** | Dwell time per vehicle and transporter. |
| **Gate Pass Exceptions** | Every rule that fired as a warning, with the reason given and by whom. |
| **Compliance Exceptions** | Dispatches released without a statutory document, by whom and why. |
| **Enforcement Impact Preview** | What *would* have been blocked under a different configuration. Use this before tightening anything. |

---

## Troubleshooting

Every user-facing error carries a **trace ID**. The same ID appears in three places, so you can move between them from a string the user reads off their screen:

1. The **Gate Pass Event Log** row for that gate pass.
2. The **Error Log**, linked back to the document.
3. The structured log — `logs/gatepass.log` in your bench, one JSON object per line.

Set **Log Level** to `Verbose` in Gate Pass Settings while diagnosing.

Common questions:

**"Why didn't my gate pass create a receipt?"** Open the gate pass → **View → Audit Trail**. A `Target Creation Failed` event carries the reason and the trace ID.

**"A rule is blocking something it shouldn't."** Gate Pass Settings → **Rules**, find it by code, set it to Warn or Ignore. If it should stay strict for most people, add a bypass role instead.

**"The app is causing problems and I need it to stop now."** Gate Pass Settings → uncheck **Enabled**. Every hook goes inert immediately; ERPNext behaves exactly as it did before installation.

---

## Contributing

Issues and pull requests are welcome.

```bash
bench --site your-site.local run-tests --app gatepass_management
```

Before opening a PR:

- Every user-facing string wrapped in `_()`.
- No raw SQL string interpolation — use `frappe.qb` or fully parameterised queries.
- No customer names, hard-coded dates, or hard-coded role names. CI fails the build on these.
- New business rules go in `rules/catalogue.py` with a stable code, and route through `RuleContext.check()`.
- No `frappe.db.commit()` inside a request handler; no `ignore_validate` or `ignore_mandatory`.

---

## License

GPL-3.0. See [`license.txt`](license.txt).

Built by [Auriga IT](https://aurigait.com).
