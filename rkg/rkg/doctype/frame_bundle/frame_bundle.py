# Copyright (c) 2026, beetashoke.chakraborty@clapgrow.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today, date_diff, now_datetime


class FrameBundle(Document):
	def validate(self):
		"""Validate Frame Bundle before save"""
		self.check_duplicate_frame_no()
		self.validate_swap_history()
	
	def before_save(self):
		"""Calculate battery aging days from creation date and update discarded history"""
		self.calculate_battery_aging()
		# Update discarded history when battery is marked as discarded
		if self.is_battery_expired and not self.discarded_date:
			self.discarded_date = now_datetime()
			self.discarded_by = frappe.session.user
			self.discarded_battery_serial_no = self.battery_serial_no
	
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
	
	def on_update(self):
		"""Recalculate aging after update and update battery status"""
		self.calculate_battery_aging()
		self.update_battery_status()
	
	def calculate_battery_aging(self):
		"""Calculate the number of days from creation date to today"""
		if self.creation:
			creation_date = getdate(self.creation)
			current_date = getdate(today())
			aging_days = date_diff(current_date, creation_date)
			self.battery_aging_days = aging_days if aging_days >= 0 else 0
		else:
			self.battery_aging_days = 0
	
	def update_battery_status(self):
		"""Update Battery Information status to Discarded when battery is expired"""
		if self.is_battery_expired and self.battery_serial_no:
			if frappe.db.exists("Battery Information", self.battery_serial_no):
				frappe.db.set_value(
					"Battery Information",
					self.battery_serial_no,
					"status",
					"Discarded",
					update_modified=False
				)


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
	
	# Store old values
	current_old_battery = current_doc.battery_serial_no
	target_old_battery = target_doc.battery_serial_no
	
	# Prepare swap history data
	swap_date = now_datetime()
	swapped_by = frappe.session.user
	
	# Set flag to allow swap_history modification
	frappe.flags.allow_swap_history_modification = True
	frappe.flags.ignore_permissions = True
	
	# Swap batteries using db_set (preserves docstatus)
	frappe.db.set_value("Frame Bundle", current_frame, "battery_serial_no", target_old_battery, update_modified=False)
	frappe.db.set_value("Frame Bundle", target_frame, "battery_serial_no", current_old_battery, update_modified=False)
	
	# Reload documents to add swap history
	current_doc = frappe.get_doc("Frame Bundle", current_frame)
	target_doc = frappe.get_doc("Frame Bundle", target_frame)
	
	# Add swap history to current frame
	current_doc.append("swap_history", {
		"swap_date": swap_date,
		"swapped_with_frame": target_frame,
		"swapped_by": swapped_by,
		"old_battery_serial_no": current_old_battery,
		"new_battery_serial_no": target_old_battery
	})
	
	# Add swap history to target frame
	target_doc.append("swap_history", {
		"swap_date": swap_date,
		"swapped_with_frame": current_frame,
		"swapped_by": swapped_by,
		"old_battery_serial_no": target_old_battery,
		"new_battery_serial_no": current_old_battery
	})
	
	# Save swap history (docstatus remains unchanged)
	current_doc.save(ignore_permissions=True)
	target_doc.save(ignore_permissions=True)
	
	# Clear flags
	frappe.flags.allow_swap_history_modification = False
	frappe.flags.ignore_permissions = False
	
	# Commit transaction
	frappe.db.commit()
	
	return {"success": True}

