# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_serial_batch_data():
	"""Return data for Serial Batch Visual dashboard."""
	return {
		"message": "Serial Batch Visual Dashboard",
		"data": []
	}
