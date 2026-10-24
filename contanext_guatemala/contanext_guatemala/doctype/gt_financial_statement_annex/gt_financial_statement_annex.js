frappe.ui.form.on("GT Financial Statement Annex", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Draft"
			|| !(frappe.user.has_role("GT Books Reviewer") || frappe.user.has_role("GT Books Manager"))) {
			return;
		}
		frm.add_custom_button(__("Aprobar"), () => decide(frm, "Approved"), __("Decisión"));
		frm.add_custom_button(__("Rechazar"), () => {
			frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Motivo"), reqd: 1 },
				(values) => decide(frm, "Rejected", values.reason), __("Rechazar anexo"));
		}, __("Decisión"));
	},
});

function decide(frm, decision, reason = null) {
	return frappe.call({
		method: "contanext_guatemala.contanext_guatemala.doctype.gt_financial_statement_annex.gt_financial_statement_annex.decide_annex",
		args: { annex: frm.doc.name, decision, reason },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}
