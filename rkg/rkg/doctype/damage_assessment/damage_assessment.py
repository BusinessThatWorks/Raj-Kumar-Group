import frappe
from frappe.model.document import Document
from frappe import _


class DamageAssessment(Document):
	def on_submit(self):
		"""Create Stock Entry when Damage Assessment is submitted"""
		self.create_stock_entry()
	
	def on_cancel(self):
		"""Cancel linked Stock Entry when Damage Assessment is cancelled"""
		self.cancel_stock_entry()
	
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
