frappe.ui.form.on("GT Physical Count Import", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Draft") return;
		if (frappe.user.has_role("GT Books Reviewer") || frappe.user.has_role("GT Books Manager")) {
			frm.add_custom_button(__("Aprobar"), () => decide_count(frm, "Approved"), __("Decisión"));
			frm.add_custom_button(__("Rechazar"), () => {
				frappe.prompt(
					[{ fieldname: "reason", label: __("Motivo"), fieldtype: "Small Text", reqd: 1 }],
					(values) => decide_count(frm, "Rejected", values.reason),
					__("Rechazar conteo")
				);
			}, __("Decisión"));
		}
	},
});

function decide_count(frm, decision, reason = null) {
	frappe.call({
		method: "contanext_guatemala.contanext_guatemala.doctype.gt_physical_count_import.gt_physical_count_import.decide_physical_count",
		args: { import_name: frm.doc.name, decision, reason },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}
