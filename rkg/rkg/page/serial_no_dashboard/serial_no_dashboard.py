# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_serial_no_data():
	"""
	Demo function for Serial No Dashboard page.
	This page redirects to Frame No Dashboard.
	"""
	return {
		"message": "This is a demo page. Please use Frame No Dashboard for serial number information.",
		"redirect_to": "frame-no-dashboard"
	}

