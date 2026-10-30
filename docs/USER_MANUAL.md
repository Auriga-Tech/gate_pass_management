# Gate Pass Management — User Manual

**Version 1.0.0 · Frappe / ERPNext v16**

---

## Who should read what

| You are | Read |
|---|---|
| Security guard at the gate | [Part 1](#part-1--for-the-security-guard) |
| Store keeper or purchase officer | [Part 2](#part-2--for-stores-and-purchase) |
| Plant or warehouse manager | [Part 3](#part-3--for-managers) |
| Implementing or configuring the app | [Part 4](#part-4--configuration) |
| Troubleshooting | [Part 5](#part-5--when-something-goes-wrong) |

Part 4 explains every master in plain language, including a dedicated section on
**Gate Pass Source** — the one piece of configuration worth reading properly
before you change anything.

---

# Part 1 — For the security guard

## What you are doing

Every time material comes in or goes out, you create a **Gate Pass**. It records what physically crossed the gate, which vehicle brought it, who was driving, and anything wrong with it.

Your record is independent of what the office says should have arrived. That is the point. If the paperwork says 100 bags and you count 80, the gate pass says 80 — and the store's receipt will say 80 too.

## Before you start

You need the **Gate Pass Operator** role. Ask your system administrator.

## Creating a gate pass for material arriving

### If a draft is already waiting for you

Often the office submits the paperwork before the vehicle arrives, and the system creates a draft gate pass for you automatically.

1. Open **Gate Pass** from the menu, or check your notifications.
2. Look for a gate pass with status **Draft**.
3. Open it. The items are already filled in.
4. Skip to [step 4 below](#4-record-the-vehicle-and-driver).

This is the easy path. You are confirming, not typing.

### If you are starting from scratch

#### 1. Create the gate pass

Click **+ Add Gate Pass**.

#### 2. Choose where the material is coming from

Click **Get Items From** and pick what matches the paperwork the driver handed you:

| The driver has… | Choose |
|---|---|
| A supplier's invoice or challan against your purchase order | **Purchase Order** |
| Finished goods from a job worker | **Subcontracting Order (Finished Goods)** |
| Material coming back from another of your plants | **Stock Entry (Incoming Transfer)** |
| Material coming back with no paperwork raised yet | **Return Against an Outbound Transfer** |

> **You do not choose "In" or "Out".** The system works that out from the document you picked. If you picked a purchase order, it knows material is coming in.

#### 3. Pick the document

Search by supplier or document number. Tick it, then press **Get Items**.

The list shows only orders that still have something left to pass. An order that
has already been fully gate-passed is left out (your administrator can switch this
off in Settings, and picking one then explains which gate pass used it up).

**One truck, several orders.** Tick more than one document to put them all on the
same gate pass, for example two purchase orders from the same supplier on one
vehicle. The rules:

- All the documents must be for the **same party**. A document from a different
  supplier is refused with *One Gate Pass covers one party*.
- A document that is already on the pass is refused, so quantities are never
  counted twice.
- You can pull another document into a draft later; it is added to the rows
  already there.

The pass then shows **Spans Multiple Documents**, and creating the receipts makes
one for each purchase order.

A **Documents on this Gate Pass** list shows every document on the pass. While the
pass is still a draft, press the **x** beside a document to take it off again, for
example when the driver did not bring that order. Its rows are removed, the table
is renumbered and the totals update. Nothing is changed in the database until you
save.

The rows appear on the form but are not saved until you press **Save**. The form
shows **Not Saved** until you do.

#### The party, its address and its contact

Material that comes from a document has its party filled in for you. If you start
without one, choose **Party Type** and **Party**. Only the party types your
administrator has allowed are offered.

- **Party Address** and **Party Contact** offer only the addresses and contacts
  that are linked to that party, and nothing until a party is chosen. If the one
  you need is missing, ask the office to add the party under *Links* on that
  Address or Contact.
- Choosing a different party clears both, because they belonged to the old party.
- **Contact Mobile** is filled in from the contact when you save, if you left it blank.
- Saving with an address or contact that is not linked to the party is refused.

#### The purpose (optional)

**Purpose** says why the material is moving. The list offers only purposes that fit
the direction of the pass, so an inward pass will not offer *Sales Dispatch*, and
choosing one fills in the pass type it usually means (*Visitor or Vendor Visit*
sets the type to Visitor). You can still change the type. If you change the
direction after choosing, a purpose that no longer fits is cleared.

The system fills in the items, showing for each one:

- **Source Qty** — what was ordered
- **Already Gate Passed** — what came in on earlier trips
- **Pending** — what is still expected
- **Qty** — starts at the pending amount; change it to what actually arrived

#### 4. Record the vehicle and driver

| Field | Notes |
|---|---|
| **Vehicle Number** | Required. As shown on the plate. |
| **Driver Name** | Required. |
| **Driver Contact** | Useful if something is wrong and the driver has already left. |
| **Transporter** | If your company tracks transporters. |
| **LR / Consignment No** | From the transporter's copy. |

Your name fills in automatically as **Security Officer**. If it is blank, tell your administrator — your user account is not linked to your employee record.

#### 5. Count and enter what actually arrived

Go through the items. For each one, put the **real counted quantity** in **Qty**.

> On some outward gate passes the Qty column is greyed out. That is deliberate — the invoice is fixed and you may not change it. Record any difference in the discrepancy columns instead (next step).

#### 6. Record anything wrong

If everything is fine, skip this.

If not, fill in the columns beside the quantity:

| Column | Use it when |
|---|---|
| **Short** | Fewer arrived than the paperwork says |
| **Damaged** | Arrived broken, wet, crushed, leaking |
| **Rejected** | You refused it at the gate |

Pick a **Reason** for each. **Accepted** is calculated for you — you never do the arithmetic.

Then open the **Discrepancy** section and write what happened in plain words. Attach a photo. This is what the office and the supplier will look at.

> **Example.** Paperwork says 100 bags. You count 100, but 6 are torn and leaking.
> Qty **100**, Damaged **6**, Reason **Damaged in Transit**. Accepted becomes **94** automatically.
> The store's receipt will show 94 good and 6 rejected. Nobody has to re-enter anything.

#### 7. Attach the documents

The **Required Documents** section lists what your company needs. Photograph or upload each one. Items marked required will stop you submitting without them.

Take a **vehicle photo** if your company asks for it.

#### 8. Submit

Click **Submit**.

If something is missing you will get one message listing everything wrong — fix it all at once, rather than one problem at a time.

Some messages are **warnings** in orange. Those record the issue and let you carry on.

---

## Creating a gate pass for material leaving

Same process, with one important addition.

Use **Get Items From** and choose **Sales Invoice**, **Delivery Note**, **Stock Entry (Send to Subcontractor)**, or one of the return options.

### The compliance check — read this carefully

For dispatches, you will see a **Statutory Compliance** section with coloured rows:

| Colour | Meaning | What to do |
|---|---|---|
| 🟢 **Generated** | The document exists | Carry on |
| 🔵 **Not Required** | Below the legal threshold | Carry on |
| ⚪ **Not Applicable** | Does not apply here | Carry on |
| 🟠 **Pending** | **Missing. Required by law.** | See below |
| 🔴 **Failed / Unavailable** | Problem with the document | See below |

**If a row is orange or red, do not let the vehicle leave.** The system will not let you submit.

The message tells you who to contact, by name. For example:

> **E-Way Bill — Pending**
> E-Way Bill has not been generated for SI-2026-00123.
> *Ask Priya Sharma (who created SI-2026-00123) to generate the E-Way Bill.*

What to do:

1. Call or message that person.
2. Wait for them to generate it.
3. Press **Re-check** on the gate pass. You will not lose anything you typed.
4. When it turns green, submit.

Once the check passes, the **E-Way Bill No** field on the gate pass fills in
by itself with the number from the invoice. If you had already typed a number,
the app leaves yours alone — so if the paper in the driver's hand disagrees with
the system, the difference stays visible rather than being quietly replaced.

> **Why this matters.** A vehicle stopped without an E-Way Bill can be detained along with the goods, and the penalty falls on your company. This check is the last chance to catch it — once the vehicle is on the road, it is too late.

If it is genuinely urgent, a manager can override the check. They must give a reason, and it is recorded permanently against their name.

---

## Returnable material

For tools, dies, moulds, cylinders, testing equipment — anything that leaves and must come back.

1. Create an outward gate pass as usual.
2. Tick **Material Will Return**.
3. Set the **Expected Return** date.
4. Submit.

The system tracks it. If it does not come back by the expected date, it is flagged **Overdue Return** and managers are notified.

### When it comes back

1. Create a new gate pass.
2. **Get Items From → Returning Gate Pass (Out)**.
3. Pick the original outward pass.
4. Confirm what actually came back — record shortage or damage if some did not.
5. Submit.

The original pass closes automatically once everything is back.

---

## Correcting a mistake after submitting

### Wrong entry or exit time

Open the gate pass → **Correct → Amend Entry / Exit Time**. Enter the right time and a reason.

The change is recorded permanently with your name, the old value and the new one, and the gate pass shows a visible warning that its times were amended.

### Damage found while unloading

Common — you cannot see everything at the gate.

Open the gate pass → **Correct → Record Discrepancy**. Enter what you found and describe it.

The pass's totals and its **Discrepancy Recorded** flag update to match what you entered.

> This only works until the store creates the receipt. After that, the store must cancel the receipt first.

### Something more serious

Ask a Gate Pass Manager to cancel the gate pass so you can create a fresh one.

---

## Quick reference

| Situation | What to do |
|---|---|
| Vehicle arrives with an invoice | Get Items From → Purchase Order |
| Fewer goods than the paperwork | Enter the real count, put the difference in **Short** |
| Goods are damaged | Full count in Qty, damaged amount in **Damaged**, pick a reason, add a photo |
| Compliance row is orange | Do not release the vehicle. Contact the person named. Press **Re-check**. |
| Qty column is greyed out | Deliberate. Use the discrepancy columns. |
| Vehicle leaving with tools that come back | Tick **Material Will Return** and set a date |
| Made a mistake after submitting | **Correct** menu, or ask a manager |

---

# Part 2 — For stores and purchase

## Your morning worklist

Open the **Pending Gate Passes** report. It shows every submitted gate pass with no receipt against it yet, with an ageing column.

Anything above two days needs a reason. That report is the whole point of the app for your role.

## Creating a receipt from a gate pass

### From the gate pass

Open it and click **Create Purchase Receipt** (or Subcontracting Receipt, depending on the flow).

The receipt is created with:

- **Accepted quantity** from the gate — what actually arrived, not what was ordered
- **Damaged** and **Rejected at Gate** quantities as rejected qty, in the rejected warehouse
- **Shortage**, only if your site chose to — see *Shortage and the receipt* below
- Taxes, currency and terms from the original order, because the app uses ERPNext's own mapper
- The **Cost Center**, if one was chosen on the gate pass. Left blank, the receipt keeps the order's own cost center; chosen, it replaces it on every line
- A link back to the gate pass

Check it, then submit as normal.

### From the receipt

Some flows are configured the other way round: create the Purchase Receipt first, then **Get Items From → Gate Pass**. Only gate passes with quantity still available are offered.

### Partial receiving

One gate pass can produce several receipts over time — receive part today, the rest tomorrow. Each receipt draws down what is left, and the gate pass shows **% Processed**.

You cannot receive more than the gate pass accepted. If you try, you will be told which line is over and by how much.

### Shortage and the receipt

If 100 were ordered and 94 arrived, 6 are **short**. What the receipt does with
them is a choice your site makes once, in **Gate Pass Settings → Shortage on the
Receipt**:

| Choice | The receipt | The order | Stock |
|---|---|---|---|
| **Not Received** *(default)* | Books the 94 that arrived | Stays open for the missing 6 | Matches the shelf |
| **Book as Rejected** | Books 94 accepted and 6 rejected | Closes as fully received | Shows 6 in the rejected warehouse that were never there |

Neither is wrong. *Not Received* keeps the stock honest and keeps the shortfall
visible on the order until it is chased. *Book as Rejected* suits a site that
wants every unit on the order accounted for on the receipt itself.

Damaged goods and goods rejected at the gate are booked as rejected under both
choices, and either way you need
a **Rejected Warehouse**, on the gate pass row or as the default in Settings.

## When quantities disagree

If the gate says 94 accepted and 6 damaged, the receipt says exactly that. **The gate's physical count is authoritative.**

If you believe the gate is wrong, do not edit the receipt — the gate pass and the receipt would then disagree, and the audit trail would show it. Instead, ask the gate to record a corrected discrepancy (they can, until the receipt is submitted), or ask a manager to cancel and amend.

## Cancelling

By default, a gate pass cannot be cancelled while a submitted receipt is linked to it — you will get a list of what to cancel first. Cancelling the receipt releases the quantity, and the gate pass becomes available again.

---

# Part 3 — For managers

## What to watch daily

| Report | What it tells you |
|---|---|
| **Pending Gate Passes** | Material sitting in the yard unreceived. Anything over 2 days is a problem. |
| **Pending Returnable Gate Passes** | Tools and equipment out with subcontractors, overdue first. |
| **Gate Pass Exceptions** | Every warning that fired, with the reason given. **This is where you find out how your process actually breaks.** |
| **Compliance Exceptions** | Dispatches released without a statutory document, by whom and why. |
| **Discrepancy Register** | Shortage and damage by supplier, transporter and reason. Feeds scorecards and claims. |

## Tightening enforcement

The app ships in **Advisory** mode — everything warns, nothing blocks. That is deliberate, so installing it breaks nothing.

When you are ready to tighten:

1. Run **Enforcement Impact Preview** and choose a candidate preset.
2. It replays your last N days and lists exactly what *would* have been blocked, by rule and by user.
3. If the list is small and reasonable, apply the preset.
4. If it is large, fix the process first — or set just those rules to Block and leave the rest.

Move **Advisory → Balanced** first. Reach **Strict** only if you have a reason.

> Statutory compliance rules block under every preset, including Advisory. You can relax one deliberately, per flow, and it will be recorded — but it never happens as a side effect of choosing a preset.

## Overriding a compliance check

If you hold the right role, a blocked compliance check offers an override. You must give a reason. It is recorded permanently against your name and appears in the Compliance Exceptions report.

Use it when you have independently confirmed the document exists but the system cannot see it. Do not use it to release a genuinely non-compliant dispatch.

## Reading the audit trail

Every gate pass has **View → Audit Trail**: creation, submission, entry and exit stamps, every target created or cancelled, every timestamp correction with old and new values, every warning that fired, every override.

Nobody can edit or delete it. Not managers, not System Manager.

---

# Part 4 — Configuration

## Three layers

| Layer | Where | Decides |
|---|---|---|
| **Global policy** | Gate Pass Settings | Mandatory fields, features, naming, dating, permissions, notifications |
| **Per flow** | Gate Pass Source | Field mapping, quantity policy, roles, documents, compliance, target document |
| **Per rule** | Settings → Rules, and per-flow overrides | Whether each rule blocks, warns, or is ignored |

## First-hour setup

1. **Gate Pass Settings** → confirm **Enabled** and preset **Advisory**.
2. Set **Enforce From Date** to your go-live date. Documents before it are untouched.
3. Create **Gate Pass Location** records for your sites, and **Gate** records within them.
4. Assign roles: Operator to security, User to stores and purchase, Manager to supervisors.
5. Review the twelve shipped **Gate Pass Source** records. Disable any flow you do not use.
6. If guards should only see their own site, add **User Permissions** — see below.

## What a guard can see, and how to narrow it

A guard has to pull items off a Purchase Order. They must *not* have the Buying
role, because that role would also let them change prices and approve orders.

So the app grants one narrow exception: **anyone who can create a Gate Pass can
read a source document for the purpose of building a gate pass from it.** That
is all it grants. It does not give access to the Purchase Order list, to reports,
or to editing anything.

It is deliberately an exception for the whole doctype. A guard with the Gate Pass
Operator role can therefore pull from *any* submitted Purchase Order on the site
unless you narrow it, and the way you narrow it is **User Permissions**:

| To restrict a guard to… | Add a User Permission on |
|---|---|
| One company | **Company** |
| One supplier or customer | **Supplier** / **Customer** |

Set them under **User** → the guard → *User Permissions*, or from the User
Permission list. Once set, the picker stops offering documents outside the
permitted values, and pulling one directly is refused as well.

The restriction works on whatever the source document itself is linked to. If
your sites are separate **Companies**, a Company permission is all you need. If
they are not — one company, several plants — restrict on the field the documents
actually carry, usually **Warehouse** or a branch field of your own, and give
each guard the values for their site.

**Do this on every multi-site install.** Without a User Permission there is
nothing restricting which site's documents a guard can pull from.

Two further controls, if you want the restriction expressed per flow instead:

- **Gate Pass Source → Allowed Roles** — which roles may use a flow at all. A
  flow with no roles listed is open to everyone.
- **Gate Pass Settings → Restrict by Location / Gate / Company** — the same User
  Permissions applied to the *gate pass list* as well, so a guard sees only their
  own site's passes.

> **Prices.** Gate Pass rows carry rate and amount, copied from the source
> document. If guards should not see values, set the permission level on the
> **Rate** and **Amount** fields of *Gate Pass Item* to 1 and give level-1 access
> to supervisors only.

---

# Understanding the masters

Six things you set up before or during use. Five are simple lists. The sixth —
Gate Pass Source — is the one that does the real work, and it gets its own
section after this table.

| Master | What it is | Do you have to set it up? |
|---|---|---|
| **Gate Pass Location** | Your sites, plants or branches | Yes, at least one |
| **Gate** | The physical gates at a location | Only if you have more than one |
| **Gate Pass Purpose** | A label for *why* material is moving | Optional |
| **Gate Pass Discrepancy Reason** | The list of reasons for shortage or damage | Eight ship ready to use |
| **Gate Pass Source** | A recipe telling the app how to read one kind of document | Twelve ship ready to use |
| **Gate Pass Settings** | Every global switch and rule | Works out of the box |

## Gate Pass Location

Your physical sites. A factory, a warehouse, a branch depot.

You need at least one. If you have a single site, create it, and you will
rarely think about it again.

Locations form a tree, so a large plant can have zones beneath it (`Pune Plant`
→ `North Yard`, `South Yard`). Reports can then be filtered by site, and if you
switch on **Restrict by Location** in Settings, staff at one site stop seeing
another site's gate passes.

**To create one:** Gate Pass Location → New → name it, pick the company, save.

## Gate

The actual gates in the fence. Only worth setting up if a location has more
than one and you care which was used.

Each gate belongs to a location. You can restrict a gate to one direction —
useful when goods-in and goods-out use separate entrances — set its operating
hours, and name a default security officer.

**To create one:** Gate → New → name it, pick its Location, save.

## Gate Pass Purpose

A short label for why something is moving.

Fifteen are created for you: Purchase Delivery, Sales Dispatch, Job Work - Send
to Subcontractor, Job Work - Receive Back, Stock Transfer, Customer Return,
Supplier Return, Sample Dispatch, Repair and Maintenance, Returned After Repair,
Tools, Dies and Cylinders on Loan, Scrap Disposal, Asset Movement, Visitor or
Vendor Visit, Vehicle Entry Only. Add your own, or mark any you do not use as
inactive. Each one records the **direction** it applies to (In, Out or Both) and a
default **pass type**, and the gate pass uses both:

- The Purpose dropdown offers only active purposes that fit the pass's direction.
  *Both* fits either.
- Choosing a purpose pre-fills the pass type. The guard can still change it.
- Saving a pass with a purpose for the other direction, or a retired purpose, is
  refused. A pass saved earlier keeps its purpose even if the purpose is retired
  later.

Purpose is optional, and it is a label rather than a rule: nothing else depends on
it. It is what you filter and group on later, such as "show me everything that went
out for repair last quarter".

## Gate Pass Discrepancy Reason

The dropdown the guard picks from when something is short or damaged.

Eight are created for you: Short Delivered, Lost in Transit, Damaged in
Transit, Damaged Packaging, Wrong Item Supplied, Quality Rejected at Gate,
Documents Missing, Counting Difference.

Each reason carries two things that matter:

- **Category** — Shortage, Damage, Rejection or Documentation.
- **Liable Party** — Supplier, Transporter, Internal or Unknown.

Liable Party is the important one. It is what lets the **Discrepancy Register**
answer "how much did this transporter cost us last quarter" rather than just
listing incidents. Set it thoughtfully; it turns a log into a claim.

**To add your own:** Gate Pass Discrepancy Reason → New → name it, pick a
category and who is usually at fault, save.

---

# Gate Pass Source — the one to understand

This is the master people find confusing, so here it is slowly.

## The problem it solves

A guard at the gate is holding a piece of paper. It might be a supplier's
invoice against a purchase order, a delivery challan for a customer, or a
transfer note for material going to another plant.

Each of those means the app has to look somewhere different in ERPNext. A
purchase order keeps its lines in a table called `items` and calls the quantity
`qty`. A subcontracting order keeps raw materials in `supplied_items` and calls
the quantity `required_qty`. Stock entries call the rate `basic_rate`, while
purchase orders call it `rate`.

Without something to describe these differences, every new kind of document
would need a programmer.

## What it actually is

**A Gate Pass Source is a recipe.** One recipe per kind of document you accept
at the gate. It tells the app:

> *"When the guard says they are holding a Purchase Order — look in the `items`
> table, the item is in `item_code`, the quantity is in `qty`, this is material
> coming **In**, the counterparty is the `supplier`, the guard may correct the
> quantity, and afterwards this should produce a Purchase Receipt."*

Write that down once and the app can handle purchase orders for ever. Write a
second recipe and it handles delivery notes too. No code.

## What the guard sees

Recipes are why the **Get Items From** button has a list under it. Each recipe
you have enabled puts one entry there:

```
Get Items From ▸  Purchase Order
                  Subcontracting Order (Finished Goods)
                  Stock Entry (Send to Subcontractor)
                  Sales Invoice
                  Delivery Note
                  ...
```

The guard picks the one matching their paperwork. Everything after that —
whether it is In or Out, which fields are filled, whether quantities can be
edited, what documents are required, what compliance is checked — comes from
that recipe. **The guard makes one choice; the recipe makes the rest.**

## The twelve you already have

You do not need to create any of these. They are installed and working:

| The guard is holding | Direction |
|---|---|
| Purchase Order | In |
| Subcontracting Order (finished goods coming back) | In |
| Subcontracting Order (raw material going out) | Out |
| Stock Entry — send to subcontractor | Out |
| Stock Entry — transfer to another plant | Out |
| Stock Entry — transfer arriving from another plant | In |
| Stock Entry — return with no return document raised yet | In |
| Purchase Receipt return (goods back to supplier) | Out |
| Subcontracting Receipt return | Out |
| Sales Invoice | Out |
| Delivery Note | Out |
| A returnable gate pass coming back | In |

Open **Gate Pass Source** to see them. Disable any you do not use — that
shortens the guard's menu, which is a real kindness at a busy gate.

## The settings inside a recipe, in plain terms

You only meet these if you are creating or adjusting one.

**What it is called**

| Setting | In plain words |
|---|---|
| Name | How the flow is described on screen, e.g. "Purchase Order - Inward" |
| Flow Code | Its permanent identity, e.g. `PO-IN` |
| Button Label | The wording under *Get Items From* on the gate pass |

The **Name** is just a label. Reword it whenever you like — nothing breaks.

The **Flow Code** is different: it is the flow's real identity, and every gate
pass created from it stores this code. That is why the form will not let you
change a code once the record is saved. Keep codes short and uppercase.

If you create your own flow, you choose its code. Anything unused works; the
shipped ones follow a document-then-direction pattern (`PO-IN`, `DN-OUT`,
`SCO-RM-OUT`) which is worth copying so a list of codes stays readable.

**Where to read the data**

| Setting | In plain words |
|---|---|
| Source DocType | Which ERPNext document this recipe is about |
| Child Table | Which table on it holds the item lines |
| Item / Quantity / UOM / Rate / Warehouse Field | What each column is called in that table |
| Pending Formula | How to work out what is still expected |

*Leave a field blank if the document has no such column.* Blank means "does not
apply" and is always safe. The app checks these names against the real document
when you save, so a typo fails in front of you rather than at 2 a.m. at the gate.

**How it behaves**

| Setting | In plain words |
|---|---|
| Direction | Is this material coming in or going out? |
| Quantity Policy | May the guard change the quantity? |
| Allow Discrepancy | May the guard record shortage or damage? |
| Allowed Roles | Who may use this recipe. Blank means everyone. |
| Auto-Create Draft | Should a gate pass appear by itself when this document is submitted? |

**Quantity Policy** deserves a moment, because it is where most of the judgement
sits:

- **Editable** — the guard counts and types what arrived. Correct for a
  purchase order: nobody knows what is on the truck until it is counted.
- **Locked to Source** — the quantity is fixed and greyed out. Correct for a
  sales invoice: the guard verifies what leaves, they do not get to restate the
  invoice. Differences go in the discrepancy columns instead.
- **Editable within Tolerance** — small differences allowed, large ones flagged.
- **Prefilled, Editable** — starts filled in, guard can adjust.

**What happens afterwards**

| Setting | In plain words |
|---|---|
| Target DocType | What ERPNext document this can produce |
| Creation Mode | Automatically on submit, by a button, or not at all |
| Gate Pass on Target Document | Not required / required / forbidden |
| Target Only Via Gate Pass | Stop anyone creating that document without a gate pass |

**Extra requirements**

| Setting | In plain words |
|---|---|
| Checklist | Documents the guard must attach for this kind of movement |
| Compliance Checks | Statutory documents to verify, e.g. E-Way Bill |
| Rule Overrides | Bend a global rule for this recipe only |

## Making a new one

Almost always: **find the closest existing recipe, duplicate it, change what
differs.** Starting from a blank form means filling in field names you would
have to look up.

1. Gate Pass Source → open the closest match → menu → **Duplicate**.
2. Rename it, and give it a Button Label the guard will recognise.
3. Change the Source DocType and the field names to match.
4. Set the direction and quantity policy.
5. Save. If a field name is wrong, the app tells you which one.
6. Test it: open a gate pass, press Get Items From, and confirm your new entry
   appears and pulls the right lines.

> A recipe you have edited is yours. The app refreshes the twelve shipped
> recipes on upgrade but never touches one you have created or taken over, so
> your changes survive updates.

---

# Gate Pass Settings — the global switchboard

One page, eighteen sections. It works out of the box; you visit it to change policy, not
to make the app run.

| Tab | What lives there |
|---|---|
| **General** | The master **Enabled** switch, the enforcement preset, and the date from which rules apply |
| **Naming** | The numbering series for gate passes. With *Separate Series by Direction* on, an inward pass is always numbered from the Inward series and an outward pass from the Outward series; the Series field on the form follows the direction and cannot be changed by hand |
| **Dating** | How far back or forward a gate pass may be dated |
| **Party & Items** | **Allowed Party Types**: the only party types the Party Type field offers, and any other is refused on save (leave it empty to allow all; the Default Party Type must be one of them); whether free-text items are permitted; *Hide Fully Gate-Passed Documents in the Picker* (on by default) leaves orders out of the Get Items From list once every line has been passed |
| **Required Fields** | Which fields are compulsory — vehicle, driver, location, photo, and so on |
| **Features** | Switches for returnable tracking, discrepancy, compliance, charges, weighbridge, batch/serial |
| **Tracking ID** | An optional reference built from a template of `{{ party_code }}`, `{{ party }}`, `{{ reference_no }}`, `{{ vehicle_number }}`, `{{ posting_date }}` and `{{ direction }}` placeholders. Anything else is refused |
| **Returnable** | Default return window, reminders, who gets escalations |
| **Discrepancy** | Whether damage may be recorded after submission, and who may |
| **Compliance** | Whether to block when a provider is unreachable, who may override |
| **Automation** | Auto-created drafts, and when unclaimed ones expire |
| **Lifecycle** | Cancellation policy, attachment locking, who may amend timestamps |
| **Access Restrictions** | Restrict visibility by flow, location, gate or company |
| **Notifications** | Who is told what, and by which channel. An optional Email Template can word the message: it may use `{{ intro }}`, the document's fields such as `{{ party }}`, or `{{ doc.party }}` |
| **Rules** | The 44 configurable rules, see below. A further 16 integrity checks are fixed and cannot be switched off |
| **Field Rules** | Make any field mandatory, hidden or read-only |
| **Charge Types** | The charges to seed on a new gate pass |
| **Advanced** | Lock timeout, log level, audit retention |

**The two you will touch first:**

- **Enabled** — the master switch. Turn it off and the app goes completely
  inert; ERPNext behaves exactly as it did before installation. Nothing is
  deleted. This is your emergency brake.
- **Enforcement Preset** — Advisory, Balanced, Strict or Custom. Ships on
  **Advisory**, where everything warns and nothing blocks.

## Configuring rules

**Gate Pass Settings → Rules.** Each row is one rule, with a permanent code.

| Column | Purpose |
|---|---|
| **Action** | Block, Warn, or Ignore |
| **Threshold** | Tolerance percentage or day limit, where the rule uses one |
| **Bypass Roles** | These roles get a warning instead of a block |
| **Require Override Reason** | Make the user state why before saving |
| **Custom Message** | Replace the shipped wording |

Resolution: **global preset → per-rule → per-flow override → bypass role**. Most specific wins. A bypass role can only loosen, never tighten.

### Worked example

You want over-quantity blocked for inward receipts, warned for outward deliveries, and bypassed by the plant manager:

1. Settings → Rules → `QTY-LEDGER` → Action **Block**, Bypass Roles **Gate Pass Manager**.
2. Gate Pass Source "Delivery Note - Dispatch" → Rule Overrides → `QTY-LEDGER` → **Warn**.

A guard on a purchase order is blocked. The plant manager is warned and must give a reason. Delivery notes never block.

## Field rules

**Settings → Field Rules** makes any field mandatory, hidden or read-only — optionally only for one direction, gate pass type or flow. Enforced on the server as well as in the browser.

## Compliance setup (India)

Requires the `india_compliance` app. Without it, the checks report Not Applicable and the section stays hidden.

1. Confirm GST Settings has e-invoicing and e-way bill enabled, with thresholds set.
2. Open the relevant Gate Pass Source (Sales Invoice, Delivery Note).
3. Under **Statutory Compliance**, confirm the checks are present and set to **Block**.
4. Leave **Threshold Source** as *From Provider* so limits come from GST Settings and follow the law when it changes.

---

# Part 5 — When something goes wrong

## Every error has a trace ID

The same ID appears in three places:

1. The **Gate Pass Event Log** for that gate pass (View → Audit Trail)
2. The **Error Log**, linked to the document
3. `logs/gatepass.log` in your bench — one JSON object per line

Give the ID to whoever supports your system and they can find the whole story.

## Common situations

**"Why didn't my gate pass create a receipt?"**
View → Audit Trail. A `Target Creation Failed` event carries the reason and the trace ID.

**"It says everything has already been gate passed."**
Someone already created a pass for it. The message lists them — open one and check.

**"Two people created gate passes and now the quantity is over."**
It should not be possible; the app locks the source document during validation. If it happened, capture the trace IDs of both passes and report it.

**"A rule is blocking something it shouldn't."**
Settings → Rules, find the code from the error message, set it to Warn or Ignore. If it should stay strict for most people, add a bypass role instead.

**"Compliance says Provider Unavailable."**
The check tried to verify the document and failed (for example GST Settings is incomplete, or the India Compliance data is not there yet). By default the app **fails closed** on purpose, so the vehicle is held. Settings → Compliance has a switch for this. Check that India Compliance is installed and GST Settings is configured, then press **Re-check**. A manager can override with a reason if you have confirmed the document exists another way. If India Compliance is not installed at all, these checks report *Not Applicable* and never block.

**"It says 'Different party' when I add a second order."**
One gate pass covers one party. Put each supplier's orders on their own gate pass.

**"It says the order is 'already on this Gate Pass'."**
The same document cannot be added twice, so its quantities are never counted twice. To drop it, press the **x** beside it in *Documents on this Gate Pass*.

**"The Party Address (or Party Contact) list is empty."**
It offers only what is linked to the party on the pass. Open the Address or Contact, add the party under *Links*, and try again. Choose the party first: until one is chosen both lists are empty.

**"A purpose I expect is not in the list."**
The list shows only active purposes that fit the pass's direction. Check the direction, and the purpose's own Direction and Active settings.

**"The app is causing problems and I need it to stop."**
Gate Pass Settings → uncheck **Enabled**. Every check goes inert immediately and ERPNext behaves exactly as before installation. Nothing is deleted.

## Getting help

Include: the gate pass number, the exact error text, the trace ID, what you were doing, and your role. That is usually enough to diagnose without access to your system.

---

## Glossary

| Term | Meaning |
|---|---|
| **Accepted Qty** | What was physically taken in or released. Flows to the receipt. |
| **Advisory mode** | Preset where rules warn but do not block. The shipped default. |
| **Consumption ledger** | How the app tracks what has already been gate passed against each order line. |
| **Direction** | In or Out. Derived from the source flow. |
| **Gate Pass Source** | A configured flow, e.g. "Purchase Order - Inward". |
| **Pending Qty** | Still expected: ordered minus already received or gate passed. |
| **Source Row** | The exact order line a gate pass row draws on. |
| **Target document** | What a gate pass produces — a receipt, transfer or delivery note. |
| **Trace ID** | Code on every error, linking the message to the logs. |
