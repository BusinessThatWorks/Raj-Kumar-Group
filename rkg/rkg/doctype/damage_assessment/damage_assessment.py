import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt, nowdate, now_datetime


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
		# Only create stock entry if warehouses are specified
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
			if not item.item_code:
				continue
			
			stock_entry.append("items", {
				"item_code": item.item_code,
				"custom_serial_no": item.serial_no,
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
def force_cancel_damage_assessment(docname):
	"""
	Force cancel a Damage Assessment and all its linked documents.
	Use this when normal cancellation fails.
	
	This function:
	1. Clears references on the Damage Assessment
	2. Cancels linked Stock Entries
	3. Cancels the Damage Assessment
	
	Args:
		docname: Name of the Damage Assessment to cancel
	
	Returns:
		dict with status and message
	"""
	if not frappe.has_permission("Damage Assessment", "cancel"):
		frappe.throw(_("Not permitted to cancel Damage Assessment"))
	
	doc = frappe.get_doc("Damage Assessment", docname)
	
	if doc.docstatus == 2:
		return {"status": "info", "message": _("Document is already cancelled")}
	
	if doc.docstatus == 0:
		return {"status": "info", "message": _("Document is in draft state, cannot cancel")}
	
	try:
		# Step 1: Get list of Stock Entries to cancel
		linked_stock_entries = []
		if doc.stock_entry:
			linked_stock_entries.append(doc.stock_entry)
		
		# Step 2: Clear references on the Damage Assessment side (in DB directly to avoid validation)
		frappe.db.set_value(
			"Damage Assessment", docname,
			{"stock_entry": None},
			update_modified=False
		)
		
		frappe.db.commit()
		
		# Step 3: Cancel Stock Entries (with ignore_links flag)
		cancelled_entries = []
		for se_name in linked_stock_entries:
			if frappe.db.exists("Stock Entry", se_name):
				se_doc = frappe.get_doc("Stock Entry", se_name)
				if se_doc.docstatus == 1:
					se_doc.flags.ignore_links = True
					se_doc.cancel()
					cancelled_entries.append(se_name)
		
		# Step 4: Cancel the Damage Assessment
		doc.reload()
		doc.flags.ignore_links = True
		doc.cancel()
		
		msg = _("Successfully cancelled Damage Assessment {0}").format(docname)
		if cancelled_entries:
			msg += _(". Also cancelled Stock Entries: {0}").format(", ".join(cancelled_entries))
		
		frappe.msgprint(msg, alert=True, indicator="green")
		
		return {"status": "success", "message": msg, "cancelled_stock_entries": cancelled_entries}
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Force cancel failed for {docname}: {str(e)}\n{frappe.get_traceback()}",
			title="Damage Assessment Force Cancel Error"
		)
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def force_delete_damage_assessment(docname):
	"""
	Force delete a Damage Assessment and clean up all linked documents.
	Use this as a last resort when even force_cancel fails.
	
	WARNING: This will permanently delete the document.
	
	Args:
		docname: Name of the Damage Assessment to delete
	
	Returns:
		dict with status and message
	"""
	if not frappe.has_permission("Damage Assessment", "delete"):
		frappe.throw(_("Not permitted to delete Damage Assessment"))
	
	if not frappe.db.exists("Damage Assessment", docname):
		return {"status": "error", "message": _("Document does not exist")}
	
	try:
		# Get the document and delete
		doc = frappe.get_doc("Damage Assessment", docname)
		doc.flags.ignore_links = True
		doc.flags.ignore_permissions = True
		
		# If submitted, cancel first
		if doc.docstatus == 1:
			doc.cancel()
			doc.reload()
		
		# Delete the document
		frappe.delete_doc(
			"Damage Assessment", docname,
			force=True,
			ignore_permissions=True,
			delete_permanently=True
		)
		
		return {"status": "success", "message": _("Damage Assessment {0} deleted").format(docname)}
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Force delete failed for {docname}: {str(e)}\n{frappe.get_traceback()}",
			title="Damage Assessment Force Delete Error"
		)
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_serial_no_count(item_code):
	"""Get total count of Serial Nos for a given item_code."""
	if not item_code:
		return 0
	
	count = frappe.db.count("Serial No", filters={"item_code": item_code})
	return count or 0


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
