app_name = "contanext_guatemala"
app_title = "ContaNext Guatemala"
app_publisher = "ContaNext"
app_description = "Localización fiscal de Guatemala para ContaNext"
app_email = "dev@contanext.com"
app_license = "AGPL-3.0-only"

after_install = "contanext_guatemala.install.after_install"

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "ContaNext Guatemala"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "ContaNext Guatemala"]]},
]
