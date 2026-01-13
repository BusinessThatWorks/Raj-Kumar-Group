# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today, date_diff, now_datetime


class FrameBundle(Document):
	@property
	def is_battery_expired(self):
		"""Check if battery is expired based on discard_history.
		Since is_battery_expired is a Button field (doesn't store values),
		we determine expiration status from the discard_history table."""
		return bool(self.discard_history and len(self.discard_history) > 0)
	
	def validate(self):
		"""Validate Frame Bundle before save (DRAFT ONLY)"""
		if self.docstatus != 0:
			return
		
		self.check_duplicate_frame_no()
		self.validate_swap_history()
		self.validate_discard_history()
	
	def before_save(self):
		"""Initialize battery_installed_on and calculate battery aging (DRAFT ONLY)"""
		if self.docstatus != 0:
			return

		if self.battery_serial_no and not self.battery_installed_on:
			self.battery_installed_on = today()

		self.update_battery_type()
		self.update_warehouse()
		self.calculate_battery_aging()
	
	def update_battery_type(self):
		"""Update battery_type from Battery Information when battery_serial_no changes"""
		if self.battery_serial_no:
			battery_type = frappe.db.get_value("Battery Information", self.battery_serial_no, "battery_type")
			self.battery_type = battery_type or None
		else:
			self.battery_type = None
	
	def update_warehouse(self):
		"""Update warehouse from Serial No when frame_no changes"""
		if self.frame_no:
			# Find Serial No by frame_no (try by serial_no field first, then by name)
			serial_no_name = frappe.db.get_value("Serial No", {"serial_no": self.frame_no}, "name")
			if not serial_no_name and frappe.db.exists("Serial No", self.frame_no):
				serial_no_name = self.frame_no
			
			if serial_no_name:
				warehouse = frappe.db.get_value("Serial No", serial_no_name, "warehouse")
				self.warehouse = warehouse or None
			else:
				self.warehouse = None
		else:
			self.warehouse = None
	
	def before_submit(self):
		if self.battery_serial_no and not self.battery_installed_on:
			self.battery_installed_on = today()

		self.update_battery_type()
		self.update_warehouse()
		self.calculate_battery_aging()
	
	def check_duplicate_frame_no(self):
		"""Prevent duplicate Frame Bundles for the same Frame No"""
		if not self.frame_no:
			return
		
		# Check for existing Frame Bundle with same frame_no
		existing = frappe.db.get_value(
			"Frame Bundle",
			{"frame_no": self.frame_no, "name": ["!=", self.name]},
			["name", "docstatus"],
			as_dict=True
		)
		
		if existing:
			# Allow if existing is cancelled, otherwise throw error
			if existing.docstatus != 2:
				frappe.throw(
					f"Frame Bundle with Frame No {self.frame_no} already exists: {existing.name}",
					title="Duplicate Frame No"
				)
	
	def validate_swap_history(self):
		"""Prevent manual modifications to Swap History child table"""
		# Allow modifications if coming from swap_batteries function
		if getattr(frappe.flags, 'allow_swap_history_modification', False):
			return
		
		# Check if document is new (not yet saved to database)
		# For new documents, autoname may set self.name, but document doesn't exist yet
		is_new = self.is_new() or not frappe.db.exists("Frame Bundle", self.name)
		
		if is_new:
			# New document - allow swap_history to be empty only
			if self.swap_history:
				frappe.throw(
					"Swap History cannot be manually added. It is system-controlled and populated automatically during battery swaps.",
					title="System-Controlled Field"
				)
			return
		
		# For existing documents, check if swap_history is being modified
		existing_doc = frappe.get_doc("Frame Bundle", self.name)
		existing_rows = {row.name: row for row in existing_doc.swap_history if row.name}
		current_rows = {row.name: row for row in self.swap_history if row.name}
		
		# Check for deleted rows
		deleted_row_names = set(existing_rows.keys()) - set(current_rows.keys())
		if deleted_row_names:
			frappe.throw(
				"Swap History rows cannot be manually deleted. It is system-controlled and populated automatically during battery swaps.",
				title="System-Controlled Field"
			)
		
		# Check for new rows (manual additions)
		new_row_names = set(current_rows.keys()) - set(existing_rows.keys())
		if new_row_names:
			frappe.throw(
				"Swap History cannot be manually added. It is system-controlled and populated automatically during battery swaps.",
				title="System-Controlled Field"
			)
		
		# Check for modified rows
		modified_rows = []
		for row_name in set(existing_rows.keys()) & set(current_rows.keys()):
			existing_row = existing_rows[row_name]
			current_row = current_rows[row_name]
			# Check if any field has been modified
			for field in ['swap_date', 'swapped_with_frame', 'swapped_by', 'old_battery_serial_no', 'new_battery_serial_no']:
				if getattr(existing_row, field, None) != getattr(current_row, field, None):
					modified_rows.append(row_name)
					break
		
		if modified_rows:
			frappe.throw(
				"Swap History rows cannot be manually modified. It is system-controlled and populated automatically during battery swaps.",
				title="System-Controlled Field"
			)
	
	def validate_discard_history(self):
		"""Prevent manual modifications to Discard History child table"""
		# Allow modifications if coming from mark_battery_expired function
		if getattr(frappe.flags, 'allow_discard_history_modification', False):
			return
		
		# Check if document is new (not yet saved to database)
		# For new documents, autoname may set self.name, but document doesn't exist yet
		is_new = self.is_new() or not frappe.db.exists("Frame Bundle", self.name)
		
		if is_new:
			# New document - allow discard_history to be empty only
			if self.discard_history:
				frappe.throw(
					"Discard History cannot be manually added. It is system-controlled and populated automatically when battery is marked as discarded.",
					title="System-Controlled Field"
				)
			return
		
		# For existing documents, check if discard_history is being modified
		existing_doc = frappe.get_doc("Frame Bundle", self.name)
		existing_rows = {row.name: row for row in existing_doc.discard_history if row.name}
		current_rows = {row.name: row for row in self.discard_history if row.name}
		
		# Check for deleted rows
		deleted_row_names = set(existing_rows.keys()) - set(current_rows.keys())
		if deleted_row_names:
			frappe.throw(
				"Discard History rows cannot be manually deleted. It is system-controlled and populated automatically when battery is marked as discarded.",
				title="System-Controlled Field"
			)
		
		# Check for new rows (manual additions)
		new_row_names = set(current_rows.keys()) - set(existing_rows.keys())
		if new_row_names:
			frappe.throw(
				"Discard History cannot be manually added. It is system-controlled and populated automatically when battery is marked as discarded.",
				title="System-Controlled Field"
			)
		
		# Check for modified rows
		modified_rows = []
		for row_name in set(existing_rows.keys()) & set(current_rows.keys()):
			existing_row = existing_rows[row_name]
			current_row = current_rows[row_name]
			# Check if any field has been modified
			for field in ['discarded_date', 'discarded_by', 'discarded_battery_serial_no']:
				if getattr(existing_row, field, None) != getattr(current_row, field, None):
					modified_rows.append(row_name)
					break
		
		if modified_rows:
			frappe.throw(
				"Discard History rows cannot be manually modified. It is system-controlled and populated automatically when battery is marked as discarded.",
				title="System-Controlled Field"
			)
	
	def on_update(self):
		"""Post-update hooks must NOT mutate submitted documents.
		Only updates Battery Information status when battery is expired."""
		# Skip for submitted/cancelled documents to prevent any mutations
		if self.docstatus != 0:
			return
		
		self.update_battery_status()
	
	def refresh_battery_aging(self):
		"""Refresh battery aging for submitted documents.
		Safe to call on submitted documents - only updates battery_aging_days field."""
		if self.docstatus == 1 and not self.is_battery_expired:
			if self.battery_installed_on:
				installed_date = getdate(self.battery_installed_on)
				current_date = getdate(today())
				aging_days = date_diff(current_date, installed_date)
				aging_days = max(aging_days, 0)
				# Update using db_set_value to preserve docstatus
				frappe.db.set_value("Frame Bundle", self.name, "battery_aging_days", aging_days, update_modified=False)
			else:
				frappe.db.set_value("Frame Bundle", self.name, "battery_aging_days", 0, update_modified=False)
	
	def calculate_battery_aging(self):
		"""Calculate the number of days from battery_installed_on to today.
		This tracks the CURRENT battery lifecycle, not the document lifecycle.
		Never mutates submitted documents except during submit or explicit backend operations."""
		# Skip if battery is expired (aging becomes informational)
		if self.is_battery_expired:
			return
		
		# Only calculate for draft documents or during submit
		# Submitted documents are updated via explicit backend operations (swap_batteries, etc.)
		if self.docstatus == 1:
			return
		
		if self.battery_installed_on:
			installed_date = getdate(self.battery_installed_on)
			current_date = getdate(today())
			aging_days = date_diff(current_date, installed_date)
			self.battery_aging_days = max(aging_days, 0)
		else:
			self.battery_aging_days = 0
	
	def update_battery_status(self):
		"""Update Battery Information status to Discarded when battery is expired.
		Idempotent: only updates if status is not already 'Discarded'."""
		if self.is_battery_expired and self.battery_serial_no:
			if frappe.db.exists("Battery Information", self.battery_serial_no):
				# Check current status to make operation idempotent
				current_status = frappe.db.get_value("Battery Information", self.battery_serial_no, "status")
				if current_status != "Discarded":
					frappe.db.set_value(
						"Battery Information",
						self.battery_serial_no,
						"status",
						"Discarded",
						update_modified=False
					)
	
	def on_cancel(self):
		"""Clear swapped_with_frame links in swap_history when document is cancelled to allow deletion."""
		if self.swap_history:
			# Get all linked Frame Bundles from swap history
			linked_frames = []
			for item in self.swap_history:
				if item.swapped_with_frame:
					linked_frames.append(item.swapped_with_frame)
					# Clear the link in this document's swap history
					frappe.db.set_value("Frame Bundle Swap History", item.name, "swapped_with_frame", None, update_modified=False)
			
			# Clear reciprocal links in the linked Frame Bundles' swap history
			for linked_frame in linked_frames:
				if frappe.db.exists("Frame Bundle", linked_frame):
					# Find swap history rows in the linked frame that reference this frame
					swap_history_rows = frappe.db.get_all(
						"Frame Bundle Swap History",
						filters={"parent": linked_frame, "swapped_with_frame": self.name},
						fields=["name"]
					)
					for row in swap_history_rows:
						frappe.db.set_value("Frame Bundle Swap History", row.name, "swapped_with_frame", None, update_modified=False)
			
			frappe.db.commit()


@frappe.whitelist()
def mark_battery_expired(frame_name):
	"""Mark battery as expired. Can be called even when document is submitted.
	This action can only be performed once per document."""
	
	# Validate input
	if not frappe.db.exists("Frame Bundle", frame_name):
		frappe.throw(f"Frame Bundle {frame_name} does not exist")
	
	# Get document to check current state
	doc = frappe.get_doc("Frame Bundle", frame_name)
	
	# Backend safety: Check if already discarded (check discard_history table)
	if doc.discard_history and len(doc.discard_history) > 0:
		frappe.throw("Battery has already been marked as discarded. This action can only be performed once.")
	
	# Validate battery exists
	if not doc.battery_serial_no:
		frappe.throw("No battery serial number found for this frame bundle")
	
	# Set flags to allow discard_history modification
	frappe.flags.allow_discard_history_modification = True
	frappe.flags.ignore_permissions = True
	
	try:
		# Note: is_battery_expired is a Button field and doesn't store values.
		# The expiration status is determined by the discard_history table.
		
		# Get current battery serial number
		battery_serial_no = frappe.db.get_value("Frame Bundle", frame_name, "battery_serial_no")
		
		# Insert discard history row directly using SQL (avoids save() on submitted docs)
		now = now_datetime()
		
		# Get the next idx for the discard history table
		max_idx = frappe.db.sql("""
			SELECT COALESCE(MAX(idx), 0) + 1
			FROM `tabFrame Bundle Discard History`
			WHERE parent = %s
		""", (frame_name,), as_dict=False)
		next_idx = max_idx[0][0] if max_idx else 1
		
		# Generate a unique name for the child table row
		child_name = frappe.generate_hash(length=10)
		
		# Insert discard history row directly
		frappe.db.sql("""
			INSERT INTO `tabFrame Bundle Discard History`
			(name, creation, modified, modified_by, owner, docstatus, parent, parenttype, parentfield, idx,
			 discarded_date, discarded_by, discarded_battery_serial_no)
			VALUES (%s, %s, %s, %s, %s, 0, %s, 'Frame Bundle', 'discard_history', %s,
				%s, %s, %s)
		""", (
			child_name, now, now, frappe.session.user, frappe.session.user,
			frame_name, next_idx, now, frappe.session.user, battery_serial_no
		))
		
		# Update Battery Information status to Discarded
		if battery_serial_no and frappe.db.exists("Battery Information", battery_serial_no):
			frappe.db.set_value(
				"Battery Information",
				battery_serial_no,
				"status",
				"Discarded",
				update_modified=False
			)
		
		# Commit transaction
		frappe.db.commit()
		
		return {"success": True, "message": "Battery marked as discarded successfully"}
	finally:
		# Clear flags
		frappe.flags.allow_discard_history_modification = False
		frappe.flags.ignore_permissions = False


@frappe.whitelist()
def get_frame_battery(frame_name):
	"""Get frame number and battery serial number for a Frame Bundle"""
	if not frappe.db.exists("Frame Bundle", frame_name):
		return None
	
	frame = frappe.get_doc("Frame Bundle", frame_name)
	return {
		"frame_no": frame.frame_no,
		"battery_serial_no": frame.battery_serial_no
	}


@frappe.whitelist()
def refresh_battery_aging(frame_name):
	"""Refresh battery aging days for a submitted Frame Bundle.
	Safe to call on submitted documents - only updates battery_aging_days field."""
	if not frappe.db.exists("Frame Bundle", frame_name):
		frappe.throw(f"Frame Bundle {frame_name} does not exist")
	
	frame = frappe.get_doc("Frame Bundle", frame_name)
	frame.refresh_battery_aging()
	frappe.db.commit()
	
	return {"success": True, "battery_aging_days": frame.battery_aging_days}


@frappe.whitelist()
def swap_batteries(current_frame, target_frame):
	"""Swap batteries between two Frame Bundle documents atomically.
	Documents remain in submitted state (docstatus = 1) throughout the swap."""
	
	# Validate inputs
	if current_frame == target_frame:
		frappe.throw("Cannot swap with the same frame")
	
	if not frappe.db.exists("Frame Bundle", current_frame):
		frappe.throw(f"Frame Bundle {current_frame} does not exist")
	
	if not frappe.db.exists("Frame Bundle", target_frame):
		frappe.throw(f"Frame Bundle {target_frame} does not exist")
	
	# Get documents
	current_doc = frappe.get_doc("Frame Bundle", current_frame)
	target_doc = frappe.get_doc("Frame Bundle", target_frame)
	
	# Validate both are submitted
	if current_doc.docstatus != 1:
		frappe.throw(f"Frame Bundle {current_frame} must be submitted to swap batteries")
	
	if target_doc.docstatus != 1:
		frappe.throw(f"Frame Bundle {target_frame} must be submitted to swap batteries")
	
	# Validate batteries are not discarded
	if current_doc.is_battery_expired:
		frappe.throw(f"Cannot swap battery from {current_frame} - battery is discarded")
	
	if target_doc.is_battery_expired:
		frappe.throw(f"Cannot swap battery from {target_frame} - battery is discarded")
	
	# Validate both frames have batteries
	if not current_doc.battery_serial_no:
		frappe.throw(f"Cannot swap - {current_frame} has no battery")
	
	if not target_doc.battery_serial_no:
		frappe.throw(f"Cannot swap - {target_frame} has no battery")
	
	# Validate both frames have the same battery_type
	current_battery_type = current_doc.battery_type
	target_battery_type = target_doc.battery_type
	
	if current_battery_type and target_battery_type:
		if current_battery_type != target_battery_type:
			frappe.throw(f"Cannot swap batteries - Battery types do not match. Current frame has '{current_battery_type}' and target frame has '{target_battery_type}'. Battery swap can only be performed between frames with the same battery type.")
	
	# Store old values
	current_old_battery = current_doc.battery_serial_no
	target_old_battery = target_doc.battery_serial_no
	
	# Prepare swap history data
	swap_date = now_datetime()
	swapped_by = frappe.session.user
	
	# Set flag to allow swap_history modification
	frappe.flags.allow_swap_history_modification = True
	frappe.flags.ignore_permissions = True
	
	# Get battery_type for both batteries to update after swap
	current_new_battery_type = frappe.db.get_value("Battery Information", target_old_battery, "battery_type") if target_old_battery else None
	target_new_battery_type = frappe.db.get_value("Battery Information", current_old_battery, "battery_type") if current_old_battery else None
	
	# Swap batteries using db_set (preserves docstatus)
	# Reset battery_installed_on for both frames when batteries are swapped
	installed_date = today()
	frappe.db.set_value("Frame Bundle", current_frame, "battery_serial_no", target_old_battery, update_modified=False)
	frappe.db.set_value("Frame Bundle", current_frame, "battery_installed_on", installed_date, update_modified=False)
	frappe.db.set_value("Frame Bundle", current_frame, "battery_type", current_new_battery_type, update_modified=False)
	frappe.db.set_value("Frame Bundle", target_frame, "battery_serial_no", current_old_battery, update_modified=False)
	frappe.db.set_value("Frame Bundle", target_frame, "battery_installed_on", installed_date, update_modified=False)
	frappe.db.set_value("Frame Bundle", target_frame, "battery_type", target_new_battery_type, update_modified=False)
	
	# Recalculate battery aging for both frames (aging resets to 0 after swap)
	frappe.db.set_value("Frame Bundle", current_frame, "battery_aging_days", 0, update_modified=False)
	frappe.db.set_value("Frame Bundle", target_frame, "battery_aging_days", 0, update_modified=False)
	
	# Insert swap history rows directly using SQL (avoids save() on submitted docs)
	# Get next idx for both frames
	current_max_idx = frappe.db.sql("""
		SELECT COALESCE(MAX(idx), 0) + 1
		FROM `tabFrame Bundle Swap History`
		WHERE parent = %s
	""", (current_frame,), as_dict=False)
	current_next_idx = current_max_idx[0][0] if current_max_idx else 1
	
	target_max_idx = frappe.db.sql("""
		SELECT COALESCE(MAX(idx), 0) + 1
		FROM `tabFrame Bundle Swap History`
		WHERE parent = %s
	""", (target_frame,), as_dict=False)
	target_next_idx = target_max_idx[0][0] if target_max_idx else 1
	
	# Generate unique names for child table rows
	current_child_name = frappe.generate_hash(length=10)
	target_child_name = frappe.generate_hash(length=10)
	
	# Insert swap history for current frame
	frappe.db.sql("""
		INSERT INTO `tabFrame Bundle Swap History`
		(name, creation, modified, modified_by, owner, docstatus, parent, parenttype, parentfield, idx,
		 swap_date, swapped_with_frame, swapped_by, old_battery_serial_no, new_battery_serial_no)
		VALUES (%s, %s, %s, %s, %s, 0, %s, 'Frame Bundle', 'swap_history', %s,
			%s, %s, %s, %s, %s)
	""", (
		current_child_name, swap_date, swap_date, swapped_by, swapped_by,
		current_frame, current_next_idx, swap_date, target_frame, swapped_by,
		current_old_battery, target_old_battery
	))
	
	# Insert swap history for target frame
	frappe.db.sql("""
		INSERT INTO `tabFrame Bundle Swap History`
		(name, creation, modified, modified_by, owner, docstatus, parent, parenttype, parentfield, idx,
		 swap_date, swapped_with_frame, swapped_by, old_battery_serial_no, new_battery_serial_no)
		VALUES (%s, %s, %s, %s, %s, 0, %s, 'Frame Bundle', 'swap_history', %s,
			%s, %s, %s, %s, %s)
	""", (
		target_child_name, swap_date, swap_date, swapped_by, swapped_by,
		target_frame, target_next_idx, swap_date, current_frame, swapped_by,
		target_old_battery, current_old_battery
	))
	
	# Clear flags
	frappe.flags.allow_swap_history_modification = False
	frappe.flags.ignore_permissions = False
	
	# Commit transaction
	frappe.db.commit()
	
	return {"success": True}

