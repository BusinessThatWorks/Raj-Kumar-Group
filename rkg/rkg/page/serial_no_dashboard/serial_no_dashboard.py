# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe

# This file can be used for server-side methods for the Serial No Dashboard page
# Currently, the page uses client-side JavaScript only

@frappe.whitelist()
def get_dashboard_data():
	"""Placeholder method for Serial No Dashboard data."""
	return {
		"message": "Serial No Dashboard is under construction"
	}

