// Loaded on every desk page via app_include_js.
//
// The shared source/target helpers must be here rather than in doctype_js: the
// per-doctype scripts are one-line calls into them, and doctype_js gives no
// ordering guarantee, so a helper loaded that way may not exist yet when the
// stub runs.
import "./gate_pass_utils";
import "./source_forms/_source_form";
import "./target_forms/_target_form";
