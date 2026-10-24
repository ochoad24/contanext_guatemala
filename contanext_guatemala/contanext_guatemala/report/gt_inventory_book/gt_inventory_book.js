frappe.query_reports["GT Inventory Book"] = {
	filters: [
		{ fieldname: "book_run", label: __("Emisión de Inventarios"), fieldtype: "Link", options: "GT Accounting Book Run", reqd: 1,
			get_query: () => ({ filters: { book_type: "INVENTORY" } }) },
	],
};
