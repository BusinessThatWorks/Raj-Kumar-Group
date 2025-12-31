# Copyright (c) 2025, RKG and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WarehouseTransfer(Document):
	def validate(self):
		"""Validate warehouse mappings."""
		# Check for duplicate from_warehouse entries
		from_warehouses = [item.from_warehouse for item in self.warehouse_transfer_item if item.from_warehouse]
		duplicates = [wh for wh in from_warehouses if from_warehouses.count(wh) > 1]
		
		if duplicates:
			frappe.throw(f"Duplicate From Warehouse found: {', '.join(set(duplicates))}")


@frappe.whitelist()
def get_damage_warehouse(from_warehouse):
	"""
	Get the corresponding damage warehouse (to_warehouse) for a given from_warehouse
	from the active Warehouse Transfer document.
	
	Args:
		from_warehouse: The source warehouse name
		
	Returns:
		The damage warehouse name if found, None otherwise
	"""
	if not from_warehouse:
		return None
	
	# Get the active Warehouse Transfer document
	active_wt = frappe.db.get_value(
		"Warehouse Transfer",
		{"is_active": 1},
		"name",
		order_by="modified desc"
	)
	
	if not active_wt:
		return None
	
	# Get the to_warehouse from the child table
	to_warehouse = frappe.db.get_value(
		"Warehouse Transfer Item",
		{
			"parent": active_wt,
			"from_warehouse": from_warehouse
		},
		"to_warehouse"
	)
	
	return to_warehouse


