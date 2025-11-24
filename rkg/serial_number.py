import frappe


def update_item_frame_number(doc, method):
	"""
	Update the Item's custom_frame_numbers field with the Serial Number
	when a Serial Number is saved.
	"""
	if not doc.item_code:
		return
	
	# Get the serial number (which is the name of the document)
	serial_number = doc.name
	
	# Update the Item's custom_frame_numbers field directly
	try:
		frappe.db.set_value("Item", doc.item_code, "custom_frame_numbers", serial_number)
	except frappe.DoesNotExistError:
		frappe.log_error(f"Item {doc.item_code} not found for Serial Number {serial_number}")
	except Exception as e:
		frappe.log_error(f"Error updating Item frame number: {str(e)}")

