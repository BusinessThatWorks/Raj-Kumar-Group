# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_serial_no_data():
	"""Return data for Serial No Dashboard."""
	return {
		"message": "Serial No Dashboard",
		"data": []
	}
