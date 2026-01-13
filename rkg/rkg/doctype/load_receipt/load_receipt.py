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
		
		# Calculate total receipt quantity
		self.calculate_total_receipt_quantity()
	
	def calculate_total_receipt_quantity(self):
		"""Count the number of rows with non-empty frame_no in Load Receipt Item child table."""
		self.total_receipt_quantity = sum(1 for item in (self.items or []) if item.frame_no and str(item.frame_no).strip())
	
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
		
		# Calculate total receipt quantity
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



