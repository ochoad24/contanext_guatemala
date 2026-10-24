frappe.ui.form.on("GT Requirement Package", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.status === "Draft") {
			frm.add_custom_button(__("Generar paquete"), () => call_action(frm, "generate"));
		}
		if (frm.doc.status === "Generated") {
			frm.add_custom_button(__("Liberar"), () => call_action(frm, "release"));
		}
		if (frm.doc.status === "Released") {
			frm.add_custom_button(__("Descargar con auditoría"), () => {
				window.location.href = `/api/method/contanext_guatemala.contanext_guatemala.doctype.gt_requirement_package.gt_requirement_package.download?package_name=${encodeURIComponent(frm.doc.name)}`;
			});
		}
	},
});

function call_action(frm, action) {
	frappe.call({
		method: `contanext_guatemala.contanext_guatemala.doctype.gt_requirement_package.gt_requirement_package.${action}`,
		args: { package_name: frm.doc.name },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}
