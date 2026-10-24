app_name = "contanext_guatemala"
app_title = "ContaNext Guatemala"
app_publisher = "ContaNext"
app_description = "Localización fiscal y operativa de Guatemala para ContaNext"
app_email = "engineering@contanext.invalid"
app_license = "MIT"

required_apps = ["erpnext"]
after_install = "contanext_guatemala.install.after_install"
after_migrate = "contanext_guatemala.install.configure_branding"

app_include_css = "/assets/contanext_guatemala/css/contanext.css"
app_include_js = "/assets/contanext_guatemala/js/branding.js"
web_include_js = "/assets/contanext_guatemala/js/branding.js"
