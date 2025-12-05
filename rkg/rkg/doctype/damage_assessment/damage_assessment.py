import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt, nowdate, now_datetime


class DamageAssessment(Document):
	def validate(self):
		"""Validate and calculate totals."""
		self.calculate_total_estimated_cost()
		self.set_approval_status()
		self.calculate_final_approved_amount()
		self.calculate_difference_amount()
	
	def calculate_total_estimated_cost(self):
		"""Calculate total estimated cost from child table items."""
		total = 0
		if self.damage_assessment_item:
			for item in self.damage_assessment_item:
				total += flt(item.estimated_cost) or 0
		self.total_estimated_cost = total
	
	def set_approval_status(self):
		"""Set approval status based on approval actions."""
		# Check if rejected at any step
		if self.godown_owner_action == "Rejected" or self.sales_manager_action == "Rejected":
			self.approval_status = "Rejected"
			return
		
		# Check if sent back for re-estimation
		if self.godown_owner_action == "Sent Back for Re-estimation" or self.sales_manager_action == "Sent Back for Re-estimation":
			self.approval_status = "Pending"
			return
		
		# Check approval progress
		godown_approved = self.godown_owner_action in ["Approved", "Edited & Approved"]
		sm_approved = self.sales_manager_action in ["Approved", "Edited & Approved"]
		
		if godown_approved and sm_approved:
			self.approval_status = "Approved"
		elif godown_approved and not sm_approved:
			self.approval_status = "Pending Sales Manager"
		elif not godown_approved:
			self.approval_status = "Pending Godown Owner"
		else:
			self.approval_status = "Pending"
	
	def calculate_final_approved_amount(self):
		"""Calculate final approved amount based on approvals."""
		if self.approval_status != "Approved":
			self.final_approved_amount = 0
			return
		
		# Priority: Sales Manager's amount > Godown Owner's amount > Estimated Cost
		if self.sales_manager_action == "Edited & Approved" and self.sales_manager_amount:
			self.final_approved_amount = flt(self.sales_manager_amount)
		elif self.godown_owner_action == "Edited & Approved" and self.godown_owner_amount:
			self.final_approved_amount = flt(self.godown_owner_amount)
		else:
			self.final_approved_amount = flt(self.total_estimated_cost)
	
	def calculate_difference_amount(self):
		"""Calculate difference between approved amount and actual repair cost."""
		if self.repair_status == "Completed" and self.actual_repair_cost:
			# Positive = Refund to delivery person, Negative = Charge extra
			self.difference_amount = flt(self.final_approved_amount) - flt(self.actual_repair_cost)
		else:
			self.difference_amount = 0
	
	def on_submit(self):
		"""Actions on submit."""
		# Only create stock entry if warehouses are specified
		if self.from_warehouse and self.to_warehouse and self.stock_entry_type:
			self.create_stock_entry()
	
	def on_cancel(self):
		"""Cancel linked Stock Entries when Damage Assessment is cancelled."""
		if self.stock_entry:
			self.cancel_stock_entry(self.stock_entry)
		
		if self.return_stock_entry:
			self.cancel_stock_entry(self.return_stock_entry)
	
	def create_stock_entry(self):
		"""Create a Stock Entry to move items to Damage Godown."""
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
		if stock_entry_name:
			stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
			if stock_entry.docstatus == 1:
				stock_entry.cancel()
				frappe.msgprint(
					_("Stock Entry {0} cancelled").format(stock_entry_name),
					alert=True,
					indicator="orange"
				)


@frappe.whitelist()
def get_serial_no_count(item_code):
	"""Get total count of Serial Nos for a given item_code."""
	if not item_code:
		return 0
	
	count = frappe.db.count("Serial No", filters={"item_code": item_code})
	return count or 0


@frappe.whitelist()
def approve_as_godown_owner(docname, action, amount=None, remarks=None):
	"""Approve/Reject as Godown Owner."""
	doc = frappe.get_doc("Damage Assessment", docname)
	
	if doc.docstatus != 0:
		frappe.throw(_("Cannot modify a submitted document"))
	
	doc.godown_owner = frappe.session.user
	doc.godown_owner_date = now_datetime()
	doc.godown_owner_action = action
	
	if action == "Edited & Approved" and amount:
		doc.godown_owner_amount = flt(amount)
	
	if remarks:
		doc.godown_owner_remarks = remarks
	
	doc.save()
	
	return {"status": "success", "message": _("Godown Owner approval recorded")}


@frappe.whitelist()
def approve_as_sales_manager(docname, action, amount=None, remarks=None):
	"""Approve/Reject as Sales Manager."""
	doc = frappe.get_doc("Damage Assessment", docname)
	
	if doc.docstatus != 0:
		frappe.throw(_("Cannot modify a submitted document"))
	
	doc.sales_manager = frappe.session.user
	doc.sales_manager_date = now_datetime()
	doc.sales_manager_action = action
	
	if action == "Edited & Approved" and amount:
		doc.sales_manager_amount = flt(amount)
	
	if remarks:
		doc.sales_manager_remarks = remarks
	
	doc.save()
	
	return {"status": "success", "message": _("Sales Manager approval recorded")}


@frappe.whitelist()
def record_recoupment(docname, amount, method, journal_entry=None, remarks=None):
	"""Record recoupment from delivery person."""
	doc = frappe.get_doc("Damage Assessment", docname)
	
	doc.amount_deducted = flt(amount)
	doc.deduction_method = method
	doc.recoupment_date = nowdate()
	
	if journal_entry:
		doc.recoupment_journal_entry = journal_entry
	
	if remarks:
		doc.recoupment_remarks = remarks
	
	# Check if fully deducted
	if flt(amount) >= flt(doc.final_approved_amount):
		doc.recoupment_status = "Fully Deducted"
	else:
		doc.recoupment_status = "Partially Deducted"
	
	doc.save()
	
	return {"status": "success", "message": _("Recoupment recorded")}


@frappe.whitelist()
def record_repair_completion(docname, actual_cost, repaired_by=None, remarks=None):
	"""Record repair completion."""
	doc = frappe.get_doc("Damage Assessment", docname)
	
	doc.actual_repair_cost = flt(actual_cost)
	doc.repair_completion_date = nowdate()
	doc.repair_status = "Completed"
	
	if repaired_by:
		doc.repaired_by = repaired_by
	
	if remarks:
		doc.repair_remarks = remarks
	
	doc.save()
	
	return {"status": "success", "message": _("Repair completion recorded")}


@frappe.whitelist()
def record_settlement(docname, action, journal_entry=None, remarks=None):
	"""Record final settlement."""
	doc = frappe.get_doc("Damage Assessment", docname)
	
	doc.settlement_action = action
	doc.settlement_date = nowdate()
	doc.settlement_status = "Settled"
	
	if journal_entry:
		doc.settlement_journal_entry = journal_entry
	
	if remarks:
		doc.settlement_remarks = remarks
	
	doc.save()
	
	return {"status": "success", "message": _("Settlement recorded")}


@frappe.whitelist()
def return_to_stores(docname, remarks=None):
	"""
	Create Stock Entry to return repaired items from Damage Godown back to Stores.
	This is called after repair is completed.
	"""
	doc = frappe.get_doc("Damage Assessment", docname)
	
	if doc.docstatus != 1:
		frappe.throw(_("Document must be submitted before returning items"))
	
	if doc.return_status == "Fully Returned":
		frappe.throw(_("Items have already been returned"))
	
	if not doc.from_warehouse or not doc.to_warehouse:
		frappe.throw(_("Warehouses not specified. Cannot create return Stock Entry."))
	
	if not doc.stock_entry_type:
		frappe.throw(_("Stock Entry Type not specified."))
	
	if not doc.damage_assessment_item:
		frappe.throw(_("No items to return"))
	
	# Create Stock Entry (reverse direction: from damage godown back to stores)
	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.stock_entry_type = doc.stock_entry_type
	stock_entry.from_warehouse = doc.to_warehouse  # Damage Godown
	stock_entry.to_warehouse = doc.from_warehouse  # Original Stores
	stock_entry.posting_date = nowdate()
	
	# Add reference to Damage Assessment
	stock_entry.custom_damage_assessment = doc.name
	
	for item in doc.damage_assessment_item:
		if not item.item_code:
			continue
		
		stock_entry.append("items", {
			"item_code": item.item_code,
			"custom_serial_no": item.serial_no,
			"qty": item.damaged_qty or 1,
			"s_warehouse": doc.to_warehouse,  # From Damage Godown
			"t_warehouse": doc.from_warehouse,  # To Original Stores
		})
	
	if not stock_entry.items:
		frappe.throw(_("No valid items to return"))
	
	stock_entry.insert(ignore_permissions=True)
	stock_entry.submit()
	
	# Update Damage Assessment with return info
	frappe.db.set_value("Damage Assessment", docname, {
		"return_stock_entry": stock_entry.name,
		"return_date": nowdate(),
		"return_status": "Fully Returned",
		"return_remarks": remarks or ""
	}, update_modified=False)
	
	frappe.msgprint(
		_("Stock Entry {0} created - Items returned to {1}").format(
			frappe.utils.get_link_to_form("Stock Entry", stock_entry.name),
			doc.from_warehouse
		),
		alert=True,
		indicator="green"
	)
	
	return {
		"status": "success", 
		"message": _("Items returned to stores"),
		"stock_entry": stock_entry.name
	}
