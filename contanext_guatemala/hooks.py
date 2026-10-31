app_name = "contanext_guatemala"
app_title = "ContaNext Guatemala"
app_publisher = "ContaNext"
app_description = "Localización fiscal y operativa de Guatemala para ContaNext"
app_email = "engineering@contanext.invalid"
app_license = "MIT"

required_apps = ["erpnext"]
after_install = "contanext_guatemala.install.after_install"
after_migrate = "contanext_guatemala.install.after_migrate"

app_include_css = "/assets/contanext_guatemala/css/contanext.css"
app_include_js = "/assets/contanext_guatemala/js/branding.js"
web_include_js = "/assets/contanext_guatemala/js/branding.js"

doctype_js = {
	"Company": "public/js/company_fiscal.js",
}

doc_events = {
	"Company": {
		"validate": "contanext_guatemala.fiscal.company.validate_company_fiscal_configuration",
	},
	"Customer": {
		"validate": "contanext_guatemala.fel.taxpayer.invalidate_customer_validation_on_identity_change",
	},
	"File": {
		"before_save": "contanext_guatemala.books.file_security.protect_book_file_before_save",
		"on_trash": "contanext_guatemala.books.file_security.protect_book_file_on_trash",
	}
}

has_permission = {
	"File": "contanext_guatemala.books.file_security.restrict_controlled_book_file",
}

scheduler_events = {
	"daily": ["contanext_guatemala.books.monitoring.run_operational_monitoring"],
}
