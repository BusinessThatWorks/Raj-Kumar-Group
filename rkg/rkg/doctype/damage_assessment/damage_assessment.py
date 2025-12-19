import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt


class DamageAssessment(Document):
	def validate(self):
		"""Validate and calculate totals."""
		self.calculate_total_estimated_cost()
	
	def calculate_total_estimated_cost(self):
		"""Calculate total estimated cost from child table items."""
		total = 0
		if self.damage_assessment_item:
			for item in self.damage_assessment_item:
				total += flt(item.estimated_cost) or 0
		self.total_estimated_cost = total
	
	def on_submit(self):
		"""Actions on submit."""
		# Create stock entry if warehouses are specified
		if self.from_warehouse and self.to_warehouse and self.stock_entry_type:
			self.create_stock_entry()
	
	def on_cancel(self):
		"""Cancel linked Stock Entries when Damage Assessment is cancelled."""
		if self.stock_entry:
			self.cancel_stock_entry(self.stock_entry)
	
	def create_stock_entry(self):
		"""Create a Stock Entry to move items to Damage Godown."""
		if not self.damage_assessment_item:
			frappe.throw(_("Please add at least one item to create Stock Entry"))
		
		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.stock_entry_type = self.stock_entry_type
		stock_entry.from_warehouse = self.from_warehouse
		stock_entry.to_warehouse = self.to_warehouse
		stock_entry.posting_date = self.date or frappe.utils.today()
		
		for item in self.damage_assessment_item:
			if not item.serial_no:
				continue
			
			# Get item_code from Serial No
			item_code = frappe.db.get_value("Serial No", item.serial_no, "item_code")
			if not item_code:
				frappe.throw(_("Item Code not found for Serial No: {0}").format(item.serial_no))
			
			stock_entry.append("items", {
				"item_code": item_code,
				"custom_serial_no": item.serial_no,
				"qty": 1,
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
			pass
		
		frappe.msgprint(
			_("Stock Entry {0} created - Items moved to Damage Godown").format(
				frappe.utils.get_link_to_form("Stock Entry", stock_entry.name)
			),
			alert=True,
			indicator="green"
		)
	
	def cancel_stock_entry(self, stock_entry_name):
		"""Cancel a linked Stock Entry."""
		if not stock_entry_name:
			return
		
		if not frappe.db.exists("Stock Entry", stock_entry_name):
			return
		
		stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
		if stock_entry.docstatus != 1:
			return
		
		stock_entry.cancel()
		frappe.msgprint(
			_("Stock Entry {0} cancelled").format(stock_entry_name),
			alert=True,
			indicator="orange"
		)


@frappe.whitelist()
def get_load_dispatch_from_serial_no(serial_no):
	"""
	Get the Load Dispatch document from which a Serial No (frame) originated.
	
	The Serial No name is the same as the frame_no in Load Dispatch Item.
	This function looks up which Load Dispatch Item has this frame_no
	and returns the parent Load Dispatch name.
	
	Args:
		serial_no: The Serial No (frame_no) to look up
	
	Returns:
		dict with load_dispatch name or None if not found
	"""
	if not serial_no:
		return {"load_dispatch": None}
	
	# Look up Load Dispatch Item where frame_no matches the serial_no
	load_dispatch_item = frappe.db.get_value(
		"Load Dispatch Item",
		{"frame_no": serial_no},
		["parent"],
		as_dict=True
	)
	
	if load_dispatch_item and load_dispatch_item.get("parent"):
		return {"load_dispatch": load_dispatch_item.parent}
	
	return {"load_dispatch": None}
