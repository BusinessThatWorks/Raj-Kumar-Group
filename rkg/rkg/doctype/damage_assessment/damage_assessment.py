import frappe
from frappe.model.document import Document


class DamageAssessment(Document):
	pass


@frappe.whitelist()
def get_serial_no_count(item_code):
	"""Get total count of Serial Nos for a given item_code"""
	if not item_code:
		return 0
	
	count = frappe.db.count("Serial No", filters={"item_code": item_code})
	return count or 0
