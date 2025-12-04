import frappe
from frappe.model.document import Document
from frappe import _


class DamageAssessment(Document):
	def on_submit(self):
		"""Create Stock Entry when Damage Assessment is submitted"""
		self.create_stock_entry()
		
		# If this is a Return Transfer, update the original Damage Assessment
		if self.transfer_direction == "Return Transfer" and self.original_damage_assessment:
			self.update_original_damage_assessment()
	
	def on_cancel(self):
		"""Cancel linked Stock Entry when Damage Assessment is cancelled"""
		self.cancel_stock_entry()
		
		# If this is a Return Transfer, revert the original Damage Assessment status
		if self.transfer_direction == "Return Transfer" and self.original_damage_assessment:
			self.revert_original_damage_assessment()
	
	def update_original_damage_assessment(self):
		"""Update the original Damage Assessment with return reference and status"""
		original = frappe.get_doc("Damage Assessment", self.original_damage_assessment)
		
		# Count items in original vs items being returned
		original_item_count = len(original.damage_assessment_item)
		return_item_count = len(self.damage_assessment_item)
		
		# Determine return status
		if return_item_count >= original_item_count:
			return_status = "Fully Returned"
		else:
			return_status = "Partially Returned"
		
		# Update original document
		frappe.db.set_value("Damage Assessment", self.original_damage_assessment, {
			"return_status": return_status,
			"return_damage_assessment": self.name
		})
		
		frappe.msgprint(
			_("Original Damage Assessment {0} marked as {1}").format(
				self.original_damage_assessment, return_status
			),
			alert=True,
			indicator="blue"
		)
	
	def revert_original_damage_assessment(self):
		"""Revert the original Damage Assessment status when return is cancelled"""
		frappe.db.set_value("Damage Assessment", self.original_damage_assessment, {
			"return_status": "Not Returned",
			"return_damage_assessment": ""
		})
	
	def create_stock_entry(self):
		"""Create a Stock Entry from Damage Assessment items"""
		if not self.damage_assessment_item:
			frappe.throw(_("Please add at least one item to create Stock Entry"))
		
		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.stock_entry_type = self.stock_entry_type
		stock_entry.from_warehouse = self.from_warehouse
		stock_entry.to_warehouse = self.to_warehouse
		stock_entry.posting_date = self.date or frappe.utils.today()
		
		# Add reference to Damage Assessment
		stock_entry.custom_damage_assessment = self.name
		
		for item in self.damage_assessment_item:
			if not item.item_code:
				continue
			
			stock_entry.append("items", {
				"item_code": item.item_code,
				"custom_serial_no": item.serial_no,  # Use custom field to avoid Serial and Batch Bundle
				"qty": item.damaged_qty or 1,
				"s_warehouse": self.from_warehouse,
				"t_warehouse": self.to_warehouse,
			})
		
		if not stock_entry.items:
			frappe.throw(_("No valid items to create Stock Entry"))
		
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		
		# Store reference to the created Stock Entry
		try:
			self.db_set("stock_entry", stock_entry.name, update_modified=False)
		except Exception:
			# Column may not exist if migration hasn't been run
			pass
		
		frappe.msgprint(
			_("Stock Entry {0} created and submitted").format(
				frappe.utils.get_link_to_form("Stock Entry", stock_entry.name)
			),
			alert=True,
			indicator="green"
		)
	
	def cancel_stock_entry(self):
		"""Cancel the linked Stock Entry"""
		if self.stock_entry:
			stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
			if stock_entry.docstatus == 1:
				stock_entry.cancel()
				frappe.msgprint(
					_("Stock Entry {0} cancelled").format(self.stock_entry),
					alert=True,
					indicator="orange"
				)


@frappe.whitelist()
def get_serial_no_count(item_code):
	"""Get total count of Serial Nos for a given item_code"""
	if not item_code:
		return 0
	
	count = frappe.db.count("Serial No", filters={"item_code": item_code})
	return count or 0


@frappe.whitelist()
def get_damage_assessment_items(damage_assessment):
	"""Get items and details from a Damage Assessment for populating Return Transfer"""
	if not damage_assessment:
		return None
	
	doc = frappe.get_doc("Damage Assessment", damage_assessment)
	
	items = []
	for item in doc.damage_assessment_item:
		items.append({
			"item_code": item.item_code,
			"serial_no": item.serial_no,
			"total_qty_received": item.total_qty_received,
			"type_of_damage": item.type_of_damage,
			"damaged_qty": item.damaged_qty,
			"item_remarks": item.item_remarks
		})
	
	return {
		"from_warehouse": doc.from_warehouse,
		"to_warehouse": doc.to_warehouse,
		"stock_entry_type": doc.stock_entry_type,
		"items": items
	}
