import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt
from frappe.model.mapper import get_mapped_doc


class LoadReceipt(Document):
	def validate(self):
		"""Validate Load Receipt."""
		# For submitted documents, ALWAYS ensure status is "Submitted"
		# This prevents "Not Saved" status from appearing in form view
		if self.docstatus == 1:
			# Always set status to "Submitted" for submitted documents
			# This fixes the issue where status shows "Not Saved" after PI submission
			if self.status != "Submitted":
				# Reload status from database first to ensure accuracy
				db_status = frappe.db.get_value("Load Receipt", self.name, "status")
				if db_status == "Submitted":
					self.status = "Submitted"
				else:
					# If database status is also wrong, force it to "Submitted"
					self.status = "Submitted"
					# Update database to ensure consistency
					frappe.db.set_value("Load Receipt", self.name, "status", "Submitted", update_modified=False)
		elif self.docstatus == 0:
			# For draft documents, set status to "Draft" if not set
			if not self.status:
				self.status = "Draft"
			elif self.status not in ["Draft", "Not Saved"]:
				# If status is something else for a draft, set to Draft
				self.status = "Draft"
		
		if self.load_dispatch:
			# Validate Load Dispatch exists and is submitted
			if not frappe.db.exists("Load Dispatch", self.load_dispatch):
				frappe.throw(_("Load Dispatch {0} does not exist").format(self.load_dispatch))
			
			load_dispatch = frappe.get_doc("Load Dispatch", self.load_dispatch)
			if load_dispatch.docstatus != 1:
				frappe.throw(_("Load Dispatch {0} must be submitted before creating Load Receipt").format(self.load_dispatch))
		
		# Calculate totals from Purchase Receipts/Invoices
		if self.load_dispatch:
			self.calculate_totals_from_purchase_documents()
		else:
			# Fallback: count items with frame_no if no load_dispatch
			self.calculate_total_receipt_quantity()
	
	def calculate_total_receipt_quantity(self):
		"""Count the number of rows with non-empty frame_no in Load Receipt Item child table."""
		self.total_receipt_quantity = sum(1 for item in (self.items or []) if item.frame_no and str(item.frame_no).strip())
	
	def calculate_totals_from_purchase_documents(self):
		"""Calculate total_receipt_quantity and total_billed_quantity from Purchase Receipts/Invoices linked to Load Dispatch."""
		if not self.load_dispatch:
			self.total_receipt_quantity = 0
			self.total_billed_quantity = 0
			return
		
		# Initialize totals
		total_received_qty = 0
		total_billed_qty = 0
		
		# Calculate total_received_qty from ALL Purchase Receipts linked to this Load Dispatch
		if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
			pr_list = frappe.get_all(
				"Purchase Receipt",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": self.load_dispatch
				},
				fields=["name", "total_qty"]
			)
			
			for pr in pr_list:
				try:
					pr_qty = flt(pr.get("total_qty")) or 0
					if pr_qty == 0:
						try:
							pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
							if hasattr(pr_doc, "items") and pr_doc.items:
								pr_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pr_doc.items)
						except Exception:
							pass
					total_received_qty += pr_qty
				except Exception:
					continue
		
		# Calculate total_billed_qty from ALL Purchase Invoices linked to this Load Dispatch
		if frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
			pi_list = frappe.get_all(
				"Purchase Invoice",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": self.load_dispatch
				},
				fields=["name", "total_qty"]
			)
			
			for pi in pi_list:
				try:
					pi_qty = flt(pi.get("total_qty")) or 0
					if pi_qty == 0:
						try:
							pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
							if hasattr(pi_doc, "items") and pi_doc.items:
								pi_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pi_doc.items)
						except Exception:
							pass
					total_billed_qty += pi_qty
				except Exception:
					continue
			
			# Check if any Purchase Invoice was created from Purchase Receipt(s) linked to this Load Dispatch
			# If so, both totals should show the same value
			for pi in pi_list:
				try:
					pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
					if hasattr(pi_doc, "items") and pi_doc.items:
						linked_purchase_receipts = {item.purchase_receipt for item in pi_doc.items if hasattr(item, "purchase_receipt") and item.purchase_receipt}
						if linked_purchase_receipts:
							# Check if any linked PR is linked to this Load Dispatch
							for pr_name in linked_purchase_receipts:
								if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
									pr_load_dispatch = frappe.db.get_value("Purchase Receipt", pr_name, "custom_load_dispatch")
									if pr_load_dispatch == self.load_dispatch:
										# When Invoice is created from Receipt, both should show the same value
										total_received_qty = total_billed_qty
										break
				except Exception:
					continue
		
		self.total_receipt_quantity = total_received_qty
		self.total_billed_quantity = total_billed_qty
	
	def on_submit(self):
		"""Set status on submit."""
		self.status = "Submitted"
		frappe.db.set_value("Load Receipt", self.name, "status", "Submitted", update_modified=False)
		self.reload()
	
	def validate(self):
		"""Validate Load Receipt."""
		# For submitted documents, ALWAYS ensure status is "Submitted"
		# This prevents "Not Saved" status from appearing in form view
		if self.docstatus == 1:
			# Always set status to "Submitted" for submitted documents
			# This fixes the issue where status shows "Not Saved" after PI submission
			if self.status != "Submitted":
				# Reload status from database first to ensure accuracy
				db_status = frappe.db.get_value("Load Receipt", self.name, "status")
				if db_status == "Submitted":
					self.status = "Submitted"
				else:
					# If database status is also wrong, force it to "Submitted"
					self.status = "Submitted"
					# Update database to ensure consistency
					frappe.db.set_value("Load Receipt", self.name, "status", "Submitted", update_modified=False)
		elif self.docstatus == 0:
			# For draft documents, set status to "Draft" if not set
			if not self.status:
				self.status = "Draft"
			elif self.status not in ["Draft", "Not Saved"]:
				# If status is something else for a draft, set to Draft
				self.status = "Draft"
		
		if self.load_dispatch:
			# Validate Load Dispatch exists and is submitted
			if not frappe.db.exists("Load Dispatch", self.load_dispatch):
				frappe.throw(_("Load Dispatch {0} does not exist").format(self.load_dispatch))
			
			load_dispatch = frappe.get_doc("Load Dispatch", self.load_dispatch)
			if load_dispatch.docstatus != 1:
				frappe.throw(_("Load Dispatch {0} must be submitted before creating Load Receipt").format(self.load_dispatch))
		
		# Calculate totals from Purchase Receipts/Invoices
		if self.load_dispatch:
			self.calculate_totals_from_purchase_documents()
		else:
			# Fallback: count items with frame_no if no load_dispatch
			self.calculate_total_receipt_quantity()
	
	def before_cancel(self):
		"""Cancel linked Damage Assessment before cancelling Load Receipt (parent-child hierarchy)."""
		if self.damage_assessment:
			try:
				da_name = self.damage_assessment
				
				# Check if Damage Assessment exists and is submitted
				if frappe.db.exists("Damage Assessment", da_name):
					da_docstatus = frappe.db.get_value("Damage Assessment", da_name, "docstatus")
					
					# Auto-cancel Damage Assessment if it's submitted
					if da_docstatus == 1:
						da_doc = frappe.get_doc("Damage Assessment", da_name)
						da_doc.cancel()
				
				# Clear the link and reset frame counts
				frappe.db.set_value("Load Receipt", self.name, {
					"damage_assessment": None,
					"frames_ok": 0,
					"frames_not_ok": 0
				}, update_modified=False)
				
				# Update the in-memory document as well
				self.damage_assessment = None
				self.frames_ok = 0
				self.frames_not_ok = 0
			except Exception as e:
				frappe.log_error(
					f"Error cancelling Damage Assessment {self.damage_assessment} when cancelling Load Receipt {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
					"Load Receipt Cancel Error"
				)
	
	def on_cancel(self):
		"""Set status on cancel."""
		self.status = "Draft"
		frappe.db.set_value("Load Receipt", self.name, "status", "Draft", update_modified=False)
		self.reload()
	
	def before_trash(self):
		"""Clear damage_assessment link before deletion."""
		if self.damage_assessment:
			try:
				frappe.db.set_value("Load Receipt", self.name, {
					"damage_assessment": None,
					"frames_ok": 0,
					"frames_not_ok": 0
				}, update_modified=False)
				frappe.flags.ignore_links = True
			except Exception as e:
				frappe.log_error(
					f"Error clearing damage_assessment link when deleting Load Receipt {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
					"Load Receipt Delete Error"
				)


@frappe.whitelist()
def create_load_receipt(source_name, target_doc=None):
	"""Create Load Receipt from Load Dispatch."""
	# Check if Load Receipt already exists for this Load Dispatch
	if frappe.db.has_column("Load Receipt", "load_dispatch"):
		existing = frappe.get_all(
			"Load Receipt",
			filters={"load_dispatch": source_name},
			fields=["name"],
			limit=1
		)
		if existing:
			frappe.throw(_("Load Receipt {0} already exists for this Load Dispatch.").format(existing[0].name))
	
	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		target.load_dispatch = source_name
		target.load_reference_no = source.load_reference_no
		# Set status to Draft
		target.status = "Draft"
	
	def update_item(source, target, source_parent):
		# Copy all fields from Load Dispatch Item to Load Receipt Item
		# Note: Status field removed from child table
		pass
	
	doc = get_mapped_doc(
		"Load Dispatch",
		source_name,
		{
			"Load Dispatch": {
				"doctype": "Load Receipt",
				"validation": {"docstatus": ["=", 1]},
				"field_map": {
					"load_reference_no": "load_reference_no"
				}
			},
			"Load Dispatch Item": {
				"doctype": "Load Receipt Item",
				"field_map": {},
				"postprocess": update_item
			}
		},
		target_doc,
		set_missing_values
	)
	
	if doc:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"name": doc.name}
	return None


@frappe.whitelist()
def get_frames_status_counts(damage_assessment):
	"""Get count of OK and Not OK frames from Damage Assessment."""
	if not damage_assessment:
		return {"frames_ok": 0, "frames_not_ok": 0}
	
	# Get Load Receipt linked to this Damage Assessment
	load_receipt = frappe.db.get_value("Load Receipt", {"damage_assessment": damage_assessment}, "name")
	if not load_receipt:
		return {"frames_ok": 0, "frames_not_ok": 0}
	
	# Get total frames from Load Receipt
	total_frames = frappe.db.get_value("Load Receipt", load_receipt, "total_receipt_quantity") or 0
	
	# Check if Damage Assessment is submitted
	damage_assessment_doc = frappe.get_doc("Damage Assessment", damage_assessment)
	
	if damage_assessment_doc.docstatus == 1:
		# For submitted DA, OK items are removed, so count only Not OK items
		# Calculate OK as total - Not OK
		not_ok_count = frappe.db.count("Damage Assessment Item", {
			"parent": damage_assessment,
			"status": "Not OK"
		})
		ok_count = max(0, total_frames - not_ok_count)
	else:
		# For draft DA, count both OK and Not OK items
		ok_count = frappe.db.count("Damage Assessment Item", {
			"parent": damage_assessment,
			"status": "OK"
		})
		not_ok_count = frappe.db.count("Damage Assessment Item", {
			"parent": damage_assessment,
			"status": "Not OK"
		})
	
	return {
		"frames_ok": ok_count,
		"frames_not_ok": not_ok_count
	}


def update_frames_status_counts_in_load_receipt(load_receipt_name, damage_assessment_name):
	"""Update frames OK/Not OK counts in Load Receipt from Damage Assessment."""
	if not load_receipt_name or not damage_assessment_name:
		return
	
	counts = get_frames_status_counts(damage_assessment_name)
	if isinstance(counts, dict):
		frappe.db.set_value("Load Receipt", load_receipt_name, {
			"frames_ok": counts.get("frames_ok", 0),
			"frames_not_ok": counts.get("frames_not_ok", 0)
		}, update_modified=False)
		frappe.db.commit()


@frappe.whitelist()
def get_totals_from_purchase_documents(load_dispatch):
	"""Get total_receipt_quantity and total_billed_quantity from Purchase Receipts/Invoices linked to Load Dispatch."""
	if not load_dispatch:
		return {"total_receipt_quantity": 0, "total_billed_quantity": 0}
	
	# Initialize totals
	total_received_qty = 0
	total_billed_qty = 0
	
	# Calculate total_received_qty from ALL Purchase Receipts linked to this Load Dispatch
	if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
		pr_list = frappe.get_all(
			"Purchase Receipt",
			filters={
				"docstatus": 1,
				"custom_load_dispatch": load_dispatch
			},
			fields=["name", "total_qty"]
		)
		
		for pr in pr_list:
			try:
				pr_qty = flt(pr.get("total_qty")) or 0
				if pr_qty == 0:
					try:
						pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
						if hasattr(pr_doc, "items") and pr_doc.items:
							pr_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pr_doc.items)
					except Exception:
						pass
				total_received_qty += pr_qty
			except Exception:
				continue
	
	# Calculate total_billed_qty from ALL Purchase Invoices linked to this Load Dispatch
	if frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
		pi_list = frappe.get_all(
			"Purchase Invoice",
			filters={
				"docstatus": 1,
				"custom_load_dispatch": load_dispatch
			},
			fields=["name", "total_qty"]
		)
		
		for pi in pi_list:
			try:
				pi_qty = flt(pi.get("total_qty")) or 0
				if pi_qty == 0:
					try:
						pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
						if hasattr(pi_doc, "items") and pi_doc.items:
							pi_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pi_doc.items)
					except Exception:
						pass
				total_billed_qty += pi_qty
			except Exception:
				continue
		
		# Check if any Purchase Invoice was created from Purchase Receipt(s) linked to this Load Dispatch
		# If so, both totals should show the same value
		for pi in pi_list:
			try:
				pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
				if hasattr(pi_doc, "items") and pi_doc.items:
					linked_purchase_receipts = {item.purchase_receipt for item in pi_doc.items if hasattr(item, "purchase_receipt") and item.purchase_receipt}
					if linked_purchase_receipts:
						# Check if any linked PR is linked to this Load Dispatch
						for pr_name in linked_purchase_receipts:
							if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
								pr_load_dispatch = frappe.db.get_value("Purchase Receipt", pr_name, "custom_load_dispatch")
								if pr_load_dispatch == load_dispatch:
									# When Invoice is created from Receipt, both should show the same value
									total_received_qty = total_billed_qty
									break
			except Exception:
				continue
	
	return {
		"total_receipt_quantity": total_received_qty,
		"total_billed_quantity": total_billed_qty
	}


@frappe.whitelist()
def create_purchase_receipt_from_load_receipt(source_name, target_doc=None):
	"""Create Purchase Receipt from Load Receipt."""
	from rkg.rkg.doctype.load_dispatch.load_dispatch import create_purchase_receipt
	
	load_receipt = frappe.get_doc("Load Receipt", source_name)
	
	# Reload warehouse from database in case it was just set
	load_receipt.reload()
	
	if not load_receipt.warehouse:
		frappe.throw(_("Warehouse must be set in Load Receipt before creating Purchase Receipt"))
	
	if not load_receipt.load_dispatch:
		frappe.throw(_("Load Dispatch is required to create Purchase Receipt"))
	
	return create_purchase_receipt(load_receipt.load_dispatch, target_doc, load_receipt.warehouse)


def update_load_receipt_totals_from_document(doc, method=None):
	"""Update Load Receipt totals (total_receipt_quantity and total_billed_quantity) when Purchase Receipt/Invoice is submitted or cancelled."""
	try:
		# Get custom_load_dispatch field value from the document
		load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
			else (frappe.db.get_value(doc.doctype, doc.name, "custom_load_dispatch") if frappe.db.has_column(doc.doctype, "custom_load_dispatch") else None))

		if not load_dispatch_name:
			return

		# STEP 1: Verify Load Dispatch document exists with this name/ID
		if not frappe.db.exists("Load Dispatch", load_dispatch_name):
			return

		# Find all Load Receipts linked to this Load Dispatch
		if not frappe.db.has_column("Load Receipt", "load_dispatch"):
			return

		load_receipts = frappe.get_all(
			"Load Receipt",
			filters={"load_dispatch": load_dispatch_name},
			fields=["name"]
		)

		if not load_receipts:
			return

		# Initialize totals
		total_received_qty = 0
		total_billed_qty = 0

		# Case 1: Purchase Receipt
		if doc.doctype == "Purchase Receipt":
			if not frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
				return
			
			# Find all submitted Purchase Receipts (docstatus=1) with this Load Dispatch. This automatically excludes cancelled documents (docstatus=2)
			pr_list = frappe.get_all(
				"Purchase Receipt",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": load_dispatch_name
				},
				fields=["name", "total_qty"]
			)
			
			# Sum total_qty from all submitted Purchase Receipts
			for pr in pr_list:
				try:
					pr_qty = flt(pr.get("total_qty")) or 0
					if pr_qty == 0:
						try:
							pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
							if hasattr(pr_doc, "items") and pr_doc.items:
								pr_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pr_doc.items)
						except Exception:
							# If we can't get the document, skip it
							pass
					total_received_qty += pr_qty
				except Exception as e:
					frappe.log_error(
						f"Error processing Purchase Receipt {pr.get('name', 'Unknown')}: {str(e)}",
						"Load Receipt Totals Update Error"
					)
					continue

		# Case 2: Purchase Invoice
		elif doc.doctype == "Purchase Invoice":
			if not frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
				return
			
			# First, calculate total_received_qty from ALL Purchase Receipts linked to this Load Dispatch
			pr_list = frappe.get_all(
				"Purchase Receipt",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": load_dispatch_name
				},
				fields=["name", "total_qty"]
			)
			
			for pr in pr_list:
				try:
					pr_qty = flt(pr.get("total_qty")) or 0
					if pr_qty == 0:
						try:
							pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
							if hasattr(pr_doc, "items") and pr_doc.items:
								pr_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pr_doc.items)
						except Exception:
							# If we can't get the document, skip it
							pass
					total_received_qty += pr_qty
				except Exception as e:
					frappe.log_error(
						f"Error processing Purchase Receipt {pr.get('name', 'Unknown')}: {str(e)}",
						"Load Receipt Totals Update Error"
					)
					continue
			
			# Check if this Purchase Invoice was created from a Purchase Receipt by checking if any items have purchase_receipt field set
			linked_purchase_receipts = set()
			try:
				if doc.items:
					linked_purchase_receipts = {item.purchase_receipt for item in doc.items if hasattr(item, "purchase_receipt") and item.purchase_receipt}
			except Exception as e:
				frappe.log_error(
					f"Error getting linked purchase receipts: {str(e)}",
					"Load Receipt Totals Update Error"
				)
			has_purchase_receipt_link = bool(linked_purchase_receipts)
			
			# Calculate total_billed_qty from ALL Purchase Invoices linked to this Load Dispatch
			pi_list = frappe.get_all(
				"Purchase Invoice",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": load_dispatch_name
				},
				fields=["name", "total_qty"]
			)
			
			for pi in pi_list:
				try:
					pi_qty = flt(pi.get("total_qty")) or 0
					if pi_qty == 0:
						try:
							pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
							if hasattr(pi_doc, "items") and pi_doc.items:
								pi_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pi_doc.items)
						except Exception:
							# If we can't get the document, skip it
							pass
					total_billed_qty += pi_qty
				except Exception as e:
					frappe.log_error(
						f"Error processing Purchase Invoice {pi.get('name', 'Unknown')}: {str(e)}",
						"Load Receipt Totals Update Error"
					)
					continue
			
			# If Purchase Invoice was created from Purchase Receipt(s) that came from Load Dispatch, both total_received_qty and total_billed_qty should show the same value
			if has_purchase_receipt_link and linked_purchase_receipts:
				# Check if any of the linked Purchase Receipts are linked to this Load Dispatch
				pr_from_ld = []
				for pr_name in linked_purchase_receipts:
					pr_load_dispatch = None
					if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
						pr_load_dispatch = frappe.db.get_value("Purchase Receipt", pr_name, "custom_load_dispatch")
					
					# If this Purchase Receipt is linked to the same Load Dispatch
					if pr_load_dispatch == load_dispatch_name:
						pr_from_ld.append(pr_name)
				
				# If Purchase Invoice is created from Purchase Receipt(s) that came from Load Dispatch
				if pr_from_ld:
					# When Invoice is created from Receipt, both should show the same value. Use the Purchase Invoice total_billed_qty for both totals
					total_received_qty = total_billed_qty

		# Update all Load Receipts linked to this Load Dispatch
		for lr in load_receipts:
			try:
				frappe.db.set_value(
					"Load Receipt",
					lr.name,
					{
						"total_receipt_quantity": total_received_qty,
						"total_billed_quantity": total_billed_qty
					},
					update_modified=False
				)
			except Exception as e:
				frappe.log_error(
					f"Error updating Load Receipt {lr.name}: {str(e)}",
					"Load Receipt Totals Update Error"
				)
				continue

		frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Error updating Load Receipt totals from {doc.doctype} {doc.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Load Receipt Totals Update Error"
		)
		# Don't raise the error to prevent blocking document submission
		# The error is logged for debugging
	#---------------------------------------------------------


@frappe.whitelist()
def fix_load_receipt_statuses():
	"""Utility function to fix Load Receipt statuses that are incorrect.
	This fixes existing Load Receipts where status doesn't match docstatus.
	Can be called from console or as a scheduled job."""
	try:
		# Get all Load Receipts
		load_receipts = frappe.get_all(
			"Load Receipt",
			fields=["name", "docstatus", "status"]
		)
		
		fixed_count = 0
		for lr in load_receipts:
			needs_fix = False
			correct_status = None
			
			if lr.docstatus == 1:
				# Submitted documents should have status "Submitted"
				if lr.status != "Submitted":
					needs_fix = True
					correct_status = "Submitted"
			elif lr.docstatus == 0:
				# Draft documents should have status "Draft"
				if lr.status not in ["Draft", "Not Saved", None]:
					needs_fix = True
					correct_status = "Draft"
			
			if needs_fix:
				frappe.db.set_value("Load Receipt", lr.name, "status", correct_status, update_modified=False)
				fixed_count += 1
				frappe.log_error(
					f"Fixed Load Receipt {lr.name}: Changed status from '{lr.status}' to '{correct_status}'",
					"Load Receipt Status Fix"
				)
		
		frappe.db.commit()
		
		return {
			"message": f"Fixed {fixed_count} Load Receipt(s) with incorrect status",
			"fixed_count": fixed_count,
			"total_checked": len(load_receipts)
		}
	except Exception as e:
		frappe.log_error(
			f"Error fixing Load Receipt statuses: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Load Receipt Status Fix Error"
		)
		raise



