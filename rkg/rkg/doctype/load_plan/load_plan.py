# Copyright (c) 2025, beetashoke.chakraborty@clapgrow.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class LoadPlan(Document):
	def validate(self):
		"""Calculate total quantity from child table items."""
		self.calculate_total_quantity()
	
	def calculate_total_quantity(self):
		"""Sum up quantity from all Load Plan Item child table rows."""
		total_quantity = 0
		if self.table_tezh:
			for item in self.table_tezh:
				total_quantity += flt(item.quantity) or 0
		self.total_quantity = total_quantity


def update_load_plan_status_from_document(doc, method=None):
	"""
	Update Load Plan status based on Purchase Receipt or Purchase Invoice submission.
	Called from hooks when Purchase Receipt or Purchase Invoice is submitted.
	
	Logic:
	- Get load_reference_no from the submitted document (custom_load_reference_no or load_reference_to)
	- Find all submitted Purchase Receipt/Invoice documents with that load_reference_no
	- Sum total_quantity from those documents
	- Compare with Load Plan's total_quantity:
	  - If total_quantity >= Load Plan total_quantity: 'Dispatched'
	  - If total_quantity < Load Plan total_quantity and > 0: 'Partial Dispatched'
	  - Otherwise: 'In-Transit'
	
	Args:
		doc: Purchase Receipt or Purchase Invoice document
		method: Hook method name (optional)
	"""
	# Get load_reference_no from the document
	load_reference_no = None
	
	# Check for different possible field names
	if hasattr(doc, 'custom_load_reference_no') and doc.custom_load_reference_no:
		load_reference_no = doc.custom_load_reference_no
	elif hasattr(doc, 'load_reference_to') and doc.load_reference_to:
		load_reference_no = doc.load_reference_to
	elif hasattr(doc, 'load_reference_no') and doc.load_reference_no:
		load_reference_no = doc.load_reference_no
	
	if not load_reference_no:
		# No load reference found, skip status update
		return
	
	# For Purchase Invoice, only update status if update_stock is enabled
	if doc.doctype == "Purchase Invoice":
		update_stock = flt(doc.get("update_stock")) or 0
		if update_stock != 1:
			# Purchase Invoice with update_stock disabled, skip status update
			return
	
	# Check if Load Plan exists
	if not frappe.db.exists("Load Plan", load_reference_no):
		return
	
	# Get Load Plan total_quantity
	load_plan = frappe.get_doc("Load Plan", load_reference_no)
	total_load_quantity = flt(load_plan.total_quantity) or 0
	
	if total_load_quantity == 0:
		# No quantity in Load Plan, skip update
		return
	
	# Get doctype name
	doctype = doc.doctype
	
	# Calculate total quantity from all submitted Purchase Receipt/Invoice documents
	# with the same load_reference_no
	total_quantity = 0
	
	# Check both Purchase Receipt and Purchase Invoice
	for doc_type in ["Purchase Receipt", "Purchase Invoice"]:
		# Get all submitted documents matching the load_reference_no
		# Try different possible field names
		all_doc_names = set()
		
		# Build base filters
		base_filters = {"docstatus": 1}
		
		# For Purchase Invoice, only include documents with update_stock = 1
		if doc_type == "Purchase Invoice":
			base_filters["update_stock"] = 1
		
		# Check custom_load_reference_no
		if frappe.db.has_column(doc_type, "custom_load_reference_no"):
			filters = base_filters.copy()
			filters["custom_load_reference_no"] = load_reference_no
			docs1 = frappe.get_all(
				doc_type,
				filters=filters,
				fields=["name"]
			)
			all_doc_names.update([d.name for d in docs1])
		
		# Check load_reference_to
		if frappe.db.has_column(doc_type, "load_reference_to"):
			filters = base_filters.copy()
			filters["load_reference_to"] = load_reference_no
			docs2 = frappe.get_all(
				doc_type,
				filters=filters,
				fields=["name"]
			)
			all_doc_names.update([d.name for d in docs2])
		
		# Check load_reference_no
		if frappe.db.has_column(doc_type, "load_reference_no"):
			filters = base_filters.copy()
			filters["load_reference_no"] = load_reference_no
			docs3 = frappe.get_all(
				doc_type,
				filters=filters,
				fields=["name"]
			)
			all_doc_names.update([d.name for d in docs3])
		
		# Get quantities from all matching documents
		for doc_name in all_doc_names:
			doc_obj = frappe.get_doc(doc_type, doc_name)
			
			# For Purchase Invoice, double-check update_stock (in case it was changed after submission)
			if doc_type == "Purchase Invoice":
				update_stock = flt(doc_obj.get("update_stock")) or 0
				if update_stock != 1:
					continue
			
			# Try to get total_qty from the document
			doc_qty = flt(doc_obj.get("total_qty")) or 0
			
			# If total_qty is not available or zero, sum from items
			if doc_qty == 0 and hasattr(doc_obj, "items"):
				doc_qty = sum(flt(item.get("qty") or item.get("stock_qty") or 0) for item in doc_obj.items)
			
			total_quantity += doc_qty
	
	# Determine status based on comparison
	if total_quantity >= total_load_quantity:
		new_status = "Dispatched"
	elif total_quantity > 0:
		new_status = "Partial Dispatched"
	else:
		new_status = "In-Transit"
	
	# Update Load Plan status
	if load_plan.status != new_status:
		load_plan.status = new_status
		load_plan.save(ignore_permissions=True)
		frappe.db.commit()

	# ---------------------------------------------------------------------
	# Additionally, update Load Dispatch totals (received & billed)
	# ---------------------------------------------------------------------
	# We use dispatch_no field on Purchase Receipt / Invoice to find Load Dispatch
	load_dispatch_name = None
	dispatch_no = None

	# Try to read dispatch_no field from the document
	if hasattr(doc, "dispatch_no") and doc.dispatch_no:
		dispatch_no = doc.dispatch_no
		# Find Load Dispatch by matching dispatch_no
		load_dispatch_name = frappe.db.get_value("Load Dispatch", {"dispatch_no": dispatch_no}, "name")
	
	# Fallback: try other possible field names
	if not load_dispatch_name:
		for fieldname in ("custom_load_dispatch_no", "load_dispatch_no", "load_dispatch", "load_dispatch_name"):
			if hasattr(doc, fieldname) and getattr(doc, fieldname):
				load_dispatch_name = getattr(doc, fieldname)
				break

	if not load_dispatch_name:
		# No Load Dispatch reference; nothing more to do
		return

	if not frappe.db.exists("Load Dispatch", load_dispatch_name):
		return

	# Helper to compute total quantity from a list of documents of a given doctype
	def _get_total_qty_for_docs(doctype_name, doc_names):
		total = 0
		for name in doc_names:
			dobj = frappe.get_doc(doctype_name, name)

			# Always sum from items for accurate quantity
			doc_qty = 0
			if hasattr(dobj, "items") and dobj.items:
				doc_qty = sum(
					flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0)
					for item in dobj.items
				)
			
			# If items sum is 0, try total_qty as fallback
			if doc_qty == 0:
				doc_qty = flt(dobj.get("total_qty")) or 0

			total += doc_qty

		return total

	# -------------------------------
	# Total Received Quantity
	# -------------------------------
	total_received_qty = 0

	# 1) From Purchase Receipt (always counted)
	# Try dispatch_no first, then fallback to other field names
	pr_filters = {"docstatus": 1}
	if dispatch_no and frappe.db.has_column("Purchase Receipt", "dispatch_no"):
		pr_filters["dispatch_no"] = dispatch_no
		pr_names = frappe.get_all("Purchase Receipt", filters=pr_filters, pluck="name")
		total_received_qty += _get_total_qty_for_docs("Purchase Receipt", pr_names)
	elif frappe.db.has_column("Purchase Receipt", "custom_load_dispatch_no"):
		pr_filters["custom_load_dispatch_no"] = load_dispatch_name
		pr_names = frappe.get_all("Purchase Receipt", filters=pr_filters, pluck="name")
		total_received_qty += _get_total_qty_for_docs("Purchase Receipt", pr_names)

	# 2) From Purchase Invoice, but only where update_stock = 1
	pi_stock_filters = {"docstatus": 1, "update_stock": 1}
	if dispatch_no and frappe.db.has_column("Purchase Invoice", "dispatch_no"):
		pi_stock_filters["dispatch_no"] = dispatch_no
		pi_stock_names = frappe.get_all("Purchase Invoice", filters=pi_stock_filters, pluck="name")
		total_received_qty += _get_total_qty_for_docs("Purchase Invoice", pi_stock_names)
	elif frappe.db.has_column("Purchase Invoice", "custom_load_dispatch_no"):
		pi_stock_filters["custom_load_dispatch_no"] = load_dispatch_name
		pi_stock_names = frappe.get_all("Purchase Invoice", filters=pi_stock_filters, pluck="name")
		total_received_qty += _get_total_qty_for_docs("Purchase Invoice", pi_stock_names)

	# -------------------------------
	# Total Billed Quantity
	# -------------------------------
	total_billed_qty = 0

	# Always fetched from Purchase Invoice total quantity (regardless of update_stock),
	# filtered by dispatch_no or custom_load_dispatch_no
	pi_all_filters = {"docstatus": 1}
	if dispatch_no and frappe.db.has_column("Purchase Invoice", "dispatch_no"):
		pi_all_filters["dispatch_no"] = dispatch_no
		pi_all_names = frappe.get_all("Purchase Invoice", filters=pi_all_filters, pluck="name")
		total_billed_qty = _get_total_qty_for_docs("Purchase Invoice", pi_all_names)
	elif frappe.db.has_column("Purchase Invoice", "custom_load_dispatch_no"):
		pi_all_filters["custom_load_dispatch_no"] = load_dispatch_name
		pi_all_names = frappe.get_all("Purchase Invoice", filters=pi_all_filters, pluck="name")
		total_billed_qty = _get_total_qty_for_docs("Purchase Invoice", pi_all_names)

	# Update Load Dispatch document using db_set (works for submitted documents)
	frappe.db.set_value(
		"Load Dispatch",
		load_dispatch_name,
		{
			"total_received_quantity": total_received_qty,
			"total_billed_quantity": total_billed_qty
		},
		update_modified=False
	)
	frappe.db.commit()