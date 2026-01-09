app_name = "rkg"
app_title = "rkg"
app_publisher = "beetashoke.chakraborty@clapgrow.com"
app_description = "CUSTOM APP FOR RKG"
app_email = "beetashoke.chakraborty@clapgrow.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "rkg",
# 		"logo": "/assets/rkg/logo.png",
# 		"title": "rkg",
# 		"route": "/rkg",
# 		"has_permission": "rkg.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/rkg/css/rkg.css"
app_include_js = "/assets/rkg/js/rkg.js"

# include js, css files in header of web template
# web_include_css = "/assets/rkg/css/rkg.css"
# web_include_js = "/assets/rkg/js/rkg.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "rkg/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Purchase Invoice": "public/js/purchase_invoice.js"
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "rkg/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "rkg.utils.jinja_methods",
# 	"filters": "rkg.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "rkg.install.before_install"
# after_install = "rkg.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "rkg.uninstall.before_uninstall"
# after_uninstall = "rkg.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "rkg.utils.before_app_install"
# after_app_install = "rkg.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "rkg.utils.before_app_uninstall"
# after_app_uninstall = "rkg.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "rkg.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Purchase Receipt": {
        "validate": [
            "rkg.rkg.doctype.load_dispatch.load_dispatch.preserve_purchase_receipt_uom",
            "rkg.rkg.doctype.load_dispatch.load_dispatch.set_purchase_receipt_serial_batch_fields_readonly"
        ],
        "on_submit": [
            "rkg.rkg.doctype.load_plan.load_plan.update_load_plan_status_from_document",
            "rkg.rkg.doctype.load_dispatch.load_dispatch.update_load_dispatch_totals_from_document"
        ],
        "on_cancel": [
            "rkg.rkg.doctype.load_dispatch.load_dispatch.update_load_dispatch_totals_from_document",
            "rkg.rkg.doctype.load_dispatch.load_dispatch.update_load_receipt_status_from_document"
        ]
    },
    "Purchase Invoice": {
        "validate": [
            "rkg.rkg.doctype.load_dispatch.load_dispatch.validate_purchase_invoice_requires_receipt",
            "rkg.rkg.doctype.load_dispatch.load_dispatch.preserve_purchase_invoice_uom",
            "rkg.rkg.doctype.load_dispatch.load_dispatch.preserve_purchase_invoice_serial_no_from_receipt"
        ],
        "on_submit": [
            "rkg.rkg.doctype.load_plan.load_plan.update_load_plan_status_from_document",
            "rkg.rkg.doctype.load_dispatch.load_dispatch.update_load_dispatch_totals_from_document",
            "rkg.rkg.doctype.load_dispatch.load_dispatch.update_load_receipt_status_from_document"
        ],
        "on_cancel": [
            "rkg.rkg.doctype.load_dispatch.load_dispatch.update_load_dispatch_totals_from_document",
            "rkg.rkg.doctype.load_dispatch.load_dispatch.update_load_receipt_status_from_document"
        ],
        "on_trash": [
            "rkg.rkg.doctype.load_dispatch.load_dispatch.update_load_receipt_status_from_document"
        ]
    }    
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"rkg.tasks.all"
# 	],
# 	"daily": [
# 		"rkg.tasks.daily"
# 	],
# 	"hourly": [
# 		"rkg.tasks.hourly"
# 	],
# 	"weekly": [
# 		"rkg.tasks.weekly"
# 	],
# 	"monthly": [
# 		"rkg.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "rkg.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "rkg.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "rkg.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]
ignore_links_on_delete = ["Battery Key Upload Item", "Frame Bundle Swap History"]

# Request Events
# ----------------
# before_request = ["rkg.utils.before_request"]
# after_request = ["rkg.utils.after_request"]

# Job Events
# ----------
# before_job = ["rkg.utils.before_job"]
# after_job = ["rkg.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"rkg.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
fixtures = [{"doctype": "Custom Field", "filters":{"module":"rkg"}}]
