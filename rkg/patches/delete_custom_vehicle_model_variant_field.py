"""
Patch to delete the custom field 'custom_vehicle_model_variant' from Purchase Order Item,
Purchase Receipt Item, and Purchase Invoice Item which references a non-existing doctype
'Vehicle Model Variant'.
"""

import frappe


def execute():
	"""Delete the custom field from all Purchase doctypes if it exists."""
	doctypes = [
		"Purchase Order Item",
		"Purchase Receipt Item",
		"Purchase Invoice Item"
	]
	
	deleted_count = 0
	skipped_count = 0
	error_count = 0
	
	for doctype in doctypes:
		custom_field_name = f"{doctype}-custom_vehicle_model_variant"
		
		if frappe.db.exists("Custom Field", custom_field_name):
			try:
				frappe.delete_doc(
					"Custom Field",
					custom_field_name,
					force=True,
					ignore_permissions=True
				)
				frappe.db.commit()
				print(f"Deleted custom field: {custom_field_name}")
				deleted_count += 1
			except Exception as e:
				frappe.log_error(
					f"Error deleting custom field {custom_field_name}: {str(e)}",
					"Delete Custom Field Error"
				)
				print(f"Error deleting custom field {custom_field_name}: {str(e)}")
				error_count += 1
		else:
			print(f"Custom field {custom_field_name} does not exist. Skipping deletion.")
			skipped_count += 1
	
	print(f"\nSummary: Deleted {deleted_count}, Skipped {skipped_count}, Errors {error_count}")
