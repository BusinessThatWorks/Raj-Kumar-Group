# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_serial_batch_data():
	"""
	Demo function for Serial Batch Visual page.
	This page redirects to Frame No Dashboard.
	"""
	return {
		"message": "This is a demo page. Please use Frame No Dashboard for serial batch visualization.",
		"redirect_to": "frame-no-dashboard"
	}

