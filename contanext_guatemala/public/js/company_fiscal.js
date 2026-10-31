function render_contanext_gt_identity_summary(frm) {
	const field = frm.fields_dict.contanext_gt_identity_summary;
	if (!field) return;

	const missing_value = __("Sin definir");
	const legal_name = frappe.utils.escape_html(frm.doc.company_name || missing_value);
	const nit = frappe.utils.escape_html(frm.doc.tax_id || missing_value);

	field.$wrapper.html(`
		<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem;">
			<div style="min-width: 0;">
				<div class="text-muted small" style="margin-bottom: 0.375rem;">
					${__("Razón social")}
				</div>
				<div style="min-height: 2.375rem; padding: 0.5rem 0.75rem; border: 1px solid var(--border-color); border-radius: var(--border-radius); background: var(--control-bg); overflow-wrap: anywhere;">
					${legal_name}
				</div>
			</div>
			<div style="min-width: 0;">
				<div class="text-muted small" style="margin-bottom: 0.375rem;">
					${__("NIT")}
				</div>
				<div style="min-height: 2.375rem; padding: 0.5rem 0.75rem; border: 1px solid var(--border-color); border-radius: var(--border-radius); background: var(--control-bg); overflow-wrap: anywhere;">
					${nit}
				</div>
			</div>
		</div>
		<p class="text-muted small mt-2">
			${__("Estos valores usan los campos nativos Nombre de la empresa e Identificación fiscal; no se guardan copias fiscales.")}
		</p>
	`);
}

function configure_contanext_gt_fiscal_address_query(frm) {
	frm.set_query("contanext_gt_fiscal_address", () => ({
		query: "contanext_guatemala.fiscal.company.get_company_fiscal_address_options",
		filters: {
			company: frm.is_new() ? "" : frm.doc.name,
		},
	}));
}

function apply_contanext_gt_fiscal_role_policy(frm) {
	const can_edit_fiscal_fields = ["System Manager", "GT Books Manager"].some((role) =>
		frappe.user.has_role(role)
	);
	const native_fiscal_fields = new Set(["company_name", "tax_id"]);
	const fiscal_fields = Object.values(frm.fields_dict).filter(
		(field) =>
			native_fiscal_fields.has(field.df.fieldname) ||
			(field.df.fieldname.startsWith("contanext_gt_") && field.df.permlevel === 1)
	);

	for (const field of fiscal_fields) {
		frm.set_df_property(field.df.fieldname, "read_only", can_edit_fiscal_fields ? 0 : 1);
	}
}

function defer_company_dashboard_graph_until_visible(frm) {
	const dashboard = frm.dashboard;
	if (!dashboard || dashboard.__contanext_graph_visibility_patch) return;

	dashboard.__contanext_graph_visibility_patch = true;
	const render_graph = dashboard.render_graph.bind(dashboard);
	let resize_observer;

	const render_pending_graph = () => {
		if (!dashboard.__contanext_pending_graph) return;
		if (!dashboard.parent.is(":visible") || dashboard.parent.width() <= 30) return;

		const args = dashboard.__contanext_pending_graph;
		dashboard.__contanext_pending_graph = null;
		resize_observer?.disconnect();
		resize_observer = null;
		render_graph(args);
	};

	dashboard.render_graph = (args) => {
		dashboard.__contanext_pending_graph = args;
		render_pending_graph();

		if (dashboard.__contanext_pending_graph && window.ResizeObserver && !resize_observer) {
			resize_observer = new ResizeObserver(() => render_pending_graph());
			resize_observer.observe(dashboard.parent.get(0));
		}
	};

	const dashboard_tab = frm.layout?.tabs?.find((tab) => tab.df.show_dashboard);
	dashboard_tab?.tab_link
		.find(".nav-link")
		.off("click.contanext-dashboard-graph")
		.on("click.contanext-dashboard-graph", () => {
			requestAnimationFrame(() => requestAnimationFrame(render_pending_graph));
		});
}

frappe.ui.form.on("Company", {
	setup(frm) {
		defer_company_dashboard_graph_until_visible(frm);
	},

	refresh(frm) {
		render_contanext_gt_identity_summary(frm);
		configure_contanext_gt_fiscal_address_query(frm);
		apply_contanext_gt_fiscal_role_policy(frm);
	},

	company_name(frm) {
		render_contanext_gt_identity_summary(frm);
	},

	tax_id(frm) {
		render_contanext_gt_identity_summary(frm);
	},
});
