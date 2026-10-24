frappe.ui.form.on("GT Accounting Book Run", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "Draft") {
			frm.add_custom_button(__("Ejecutar preflight"), () => {
				frappe.call({
					method: "contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_run.gt_accounting_book_run.run_preflight",
					args: { book_run: frm.doc.name },
					freeze: true,
					freeze_message: __("Validando configuración y contabilidad…"),
					callback: () => frm.reload_doc(),
				});
			}, __("Libros contables"));
		}
		if (!frm.is_new() && ["Draft", "Validation Failed", "Rejected"].includes(frm.doc.status)
			&& frm.doc.preflight_status === "Passed") {
			frm.add_custom_button(__("Generar borrador"), () => {
				frappe.call({
					method: "contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_run.gt_accounting_book_run.request_generation",
					args: { book_run: frm.doc.name },
					freeze: true,
					freeze_message: __("Encolando generación…"),
					callback: () => frm.reload_doc(),
				});
			}, __("Libros contables"));
		}
		if (!frm.is_new() && frm.doc.status === "Generated") {
			frm.add_custom_button(__("Enviar a revisión"), () => call_action(
				frm,
				"submit_for_review",
				{},
				__("Enviando a revisión…"),
			), __("Revisión"));
		}
		if (!frm.is_new() && frm.doc.status === "Ready for Review" && !frm.doc.reviewed_by
			&& frappe.user.has_role("GT Books Reviewer")) {
			frm.add_custom_button(__("Registrar revisión"), () => {
				frappe.prompt({ fieldname: "comment", fieldtype: "Small Text", label: __("Comentario") },
					(values) => call_action(frm, "review_book_run", values, __("Registrando revisión…")),
					__("Revisión contable"));
			}, __("Revisión"));
		}
		if (!frm.is_new() && frm.doc.status === "Ready for Review" && frm.doc.reviewed_by
			&& frappe.user.has_role("GT Books Manager")) {
			frm.add_custom_button(__("Aprobar"), () => call_action(
				frm, "decide_book_run", { decision: "Approved" }, __("Aprobando…"),
			), __("Revisión"));
		}
		if (!frm.is_new() && frm.doc.status === "Ready for Review"
			&& frappe.user.has_role("GT Books Reviewer")) {
			frm.add_custom_button(__("Rechazar"), () => {
				frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Motivo"), reqd: 1 },
					(values) => call_action(frm, "decide_book_run", { ...values, decision: "Rejected" }, __("Rechazando…")),
					__("Rechazar emisión"));
			}, __("Revisión"));
		}
		if (!frm.is_new() && frm.doc.status === "Approved" && frappe.user.has_role("GT Books Manager")) {
			frm.add_custom_button(__("Preparar PDF técnico simulado"), () => call_action(
				frm, "request_sealing", {}, __("Preparando PDF y reserva simulada…"),
			), __("Validación técnica"));
		}
		if (!frm.is_new() && frm.doc.status === "Awaiting Print Confirmation"
			&& frappe.user.has_role("GT Books Manager")) {
			frm.add_custom_button(__("Confirmar impresión completa"), () => call_action(
				frm, "confirm_print", { success: 1, idempotency_key: event_key() },
				__("Confirmando impresión física…"),
			), __("Validación técnica"));
			frm.add_custom_button(__("Registrar falla"), () => {
				frappe.prompt([
					{ fieldname: "failed_pages", fieldtype: "Data", label: __("Páginas (ej. 2,3)"), reqd: 1 },
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Motivo"), reqd: 1 },
				], (values) => call_action(frm, "confirm_print", {
					success: 0,
					idempotency_key: event_key(),
					failed_pages: JSON.stringify(values.failed_pages.split(",").map(Number)),
					reason: values.reason,
				}, __("Registrando excepción…")), __("Falla de impresión"));
			}, __("Validación técnica"));
		}
		if (!frm.is_new() && frm.doc.status === "Print Exception"
			&& frappe.user.has_role("GT Books Manager")) {
			frm.add_custom_button(__("Autorizar reimpresión exacta"), () => {
				frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Motivo"), reqd: 1 },
					(values) => call_action(frm, "authorize_exact_reprint", {
						...values, idempotency_key: event_key(),
					}, __("Autorizando reimpresión…")), __("Reimpresión exacta"));
			}, __("Validación técnica"));
		}
	},
});

function call_action(frm, action, args, freeze_message) {
	return frappe.call({
		method: `contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_run.gt_accounting_book_run.${action}`,
		args: { book_run: frm.doc.name, ...args },
		freeze: true,
		freeze_message,
		callback: () => frm.reload_doc(),
	});
}

function event_key() {
	return crypto.randomUUID().replaceAll("-", "");
}
