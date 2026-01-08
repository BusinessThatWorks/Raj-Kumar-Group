# Copyright (c) 2026, beetashoke.chakraborty@clapgrow.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today, date_diff, now_datetime


class FrameBundle(Document):
	def before_save(self):
		"""Calculate battery aging days from creation date and update discarded history"""
		self.calculate_battery_aging()
		# Update discarded history when battery is marked as discarded
		if self.is_battery_expired and not self.discarded_date:
			self.discarded_date = now_datetime()
			self.discarded_by = frappe.session.user
			self.discarded_battery_serial_no = self.battery_serial_no
	
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
	"""Swap batteries between two Frame Bundle documents atomically"""
	if current_frame == target_frame:
		frappe.throw("Cannot swap with the same frame")
	
	if not frappe.db.exists("Frame Bundle", current_frame):
		frappe.throw(f"Frame Bundle {current_frame} does not exist")
	
	if not frappe.db.exists("Frame Bundle", target_frame):
		frappe.throw(f"Frame Bundle {target_frame} does not exist")
	
	current_doc = frappe.get_doc("Frame Bundle", current_frame)
	target_doc = frappe.get_doc("Frame Bundle", target_frame)
	
	# Store old values
	current_old_battery = current_doc.battery_serial_no
	target_old_battery = target_doc.battery_serial_no
	swap_date = now_datetime()
	swapped_by = frappe.session.user
	
	# Swap batteries
	current_doc.battery_serial_no = target_old_battery
	target_doc.battery_serial_no = current_old_battery
	
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
	
	# Save atomically
	current_doc.save(ignore_permissions=True)
	target_doc.save(ignore_permissions=True)
	
	frappe.db.commit()
	
	return {"success": True}

