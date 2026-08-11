# Workspace naming — do not rename this to "Gate Pass"

The workspace is deliberately called **Gate Pass Management**, not "Gate Pass",
even though the module and the main DocType are both called "Gate Pass".

## Why

Frappe's router resolves a public workspace **before** a DocType route, and it
matches on the first path segment only — discarding the rest.

From `frappe/public/js/frappe/router.js`:

```js
if (frappe.workspaces[route[0]]) {
    // public workspace
    route = ["Workspaces", frappe.workspaces[route[0]].name];
} else if (this.routes[route[0]]) {
    route = await this.set_doctype_route(route);
}
```

A workspace named "Gate Pass" claims the slug `gate-pass`. That is the same slug
the "Gate Pass" DocType needs. The workspace wins, and because only `route[0]`
is consulted, the document name in `route[1]` is thrown away:

```
/app/gate-pass/GP-2026-00002  ->  ["Workspaces", "Gate Pass"]
```

The user asks for a document and gets the dashboard. Every Gate Pass form
becomes unreachable by URL — no error, no clue, just the wrong page.

ERPNext never runs into this because its workspaces are named after areas
(Stock, Buying, Selling) while its DocTypes are named after documents (Stock
Entry, Purchase Order). The slugs never overlap.

## The rule

**A public workspace must never share a slug with a DocType.**

Before adding or renaming a workspace in this app, check that
`frappe.scrub(workspace_name).replace("_", "-")` does not match any DocType
route. Current DocTypes to avoid: `gate-pass`, `gate`, `gate-pass-source`,
`gate-pass-settings`, `gate-pass-location`, `gate-pass-purpose`,
`gate-pass-event-log`, `gate-pass-discrepancy-reason`.

There is a regression test for this in `tests/test_routing.py`.

---

# Two more traps in this file

## 1. Content blocks match child rows by LABEL, not by name

`frappe/public/js/frappe/views/workspace/blocks/block.js`:

```js
let block_data = this.config.page_data[block + "s"].items.find((obj) => {
    return frappe.utils.unescape_html(obj.label) == frappe.utils.unescape_html(__(block_name));
});
if (!block_data) return false;   // <- widget silently does not render
```

So in the `content` JSON, a block's `number_card_name` / `card_name` / `chart_name`
is really **"the label to look for"**. It must equal the `label` on the matching
child row — not the child row's `number_card_name`.

Concretely, for one card:

| Where | Field | Value |
|---|---|---|
| `content` block | `number_card_name` | `Awaiting Receipt` ← the label |
| `number_cards` child row | `label` | `Awaiting Receipt` |
| `number_cards` child row | `number_card_name` | `Gate Pass Pending Receipt` ← the real doc |
| `Number Card` doc | `name` | `Gate Pass Pending Receipt` |

Get these out of step and the card vanishes from the page with no error and
nothing in the console. Change a label in one place and you must change it in
both.

## 2. `modified` must be bumped for a re-sync to happen

Frappe only re-imports a standard record when the file's `modified` timestamp is
**newer** than the row already in the database. A fixed timestamp in a generated
file means every later edit is invisible on any site that already installed it.

After editing any workspace, number card, chart or report JSON by hand, bump its
`modified` field. Otherwise `bench migrate` reports success and changes nothing.
