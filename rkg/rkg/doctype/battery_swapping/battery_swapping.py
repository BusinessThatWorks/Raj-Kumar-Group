# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class BatterySwapping(Document):
	def validate(self):
		"""Validate Battery Swapping document."""
		# Auto-fill current battery serial number when frame is selected
		if self.frame_number:
			self._fetch_current_battery()
		
		# Validate that swap and expired cannot both be selected
		if self.swap_battery and self.is_expired:
			frappe.throw(_("Cannot swap and expire battery at the same time. Please select only one action."))
		
		# Validate swap requirements
		if self.swap_battery:
			if not self.new_frame_number:
				frappe.throw(_("New Frame Number is required when Swap Battery is selected."))
			if not self.new_battery_serial_no:
				frappe.throw(_("New Battery Serial No is required when Swap Battery is selected."))
		
		# Validate expired requirements
		if self.is_expired:
			if not self.current_battery_serial_no:
				frappe.throw(_("No battery found in the selected frame. Cannot mark as expired."))
	
	def _fetch_current_battery(self):
		"""Fetch current battery serial number from frame."""
		if not self.frame_number:
			return
		
		# Get battery number from Serial No custom field
		# Try custom_battery_no first (most likely), then battery_no
		battery_no = None
		try:
			if frappe.db.has_column("Serial No", "custom_battery_no"):
				battery_no = frappe.db.get_value("Serial No", self.frame_number, "custom_battery_no")
			elif frappe.db.has_column("Serial No", "battery_no"):
				battery_no = frappe.db.get_value("Serial No", self.frame_number, "battery_no")
			else:
				# Try accessing via document
				frame_doc = frappe.get_doc("Serial No", self.frame_number)
				battery_no = getattr(frame_doc, "custom_battery_no", None) or getattr(frame_doc, "battery_no", None)
		except Exception:
			pass
		
		self.current_battery_serial_no = battery_no or ""
	
	def on_submit(self):
		"""Handle battery swapping or expiration on submit."""
		if self.swap_battery:
			self._perform_battery_swap()
		elif self.is_expired:
			self._mark_battery_as_expired()
	
	def _perform_battery_swap(self):
		"""Perform battery swap: remove old battery from old frame, assign new battery to new frame."""
		try:
			# Remove old battery from old frame
			if self.frame_number and self.current_battery_serial_no:
				self._update_frame_battery(self.frame_number, None)
			
			# Assign new battery to new frame
			if self.new_frame_number and self.new_battery_serial_no:
				self._update_frame_battery(self.new_frame_number, self.new_battery_serial_no)
			
			# Ensure all changes are committed
			frappe.db.commit()
			
			frappe.msgprint(_("Battery swap completed successfully. Serial No documents have been updated."))
		except Exception as e:
			frappe.db.rollback()
			frappe.throw(_("Error performing battery swap: {0}").format(str(e)))
	
	def _mark_battery_as_expired(self):
		"""Mark battery as expired: create Expired Battery Details record and remove from frame."""
		if not self.current_battery_serial_no:
			frappe.throw(_("No battery found to mark as expired."))
		
		try:
			# Create Expired Battery Details record
			expired_battery = frappe.get_doc({
				"doctype": "Expired Battery Details",
				"battery_serial_no": self.current_battery_serial_no,
				"expired_date": self.date,
				"old_frame_number": self.frame_number,
				"swapped_from_battery_swapping": self.name
			})
			expired_battery.insert(ignore_permissions=True)
			
			# Remove battery from frame
			if self.frame_number:
				self._update_frame_battery(self.frame_number, None)
			
			# Ensure all changes are committed
			frappe.db.commit()
			
			frappe.msgprint(_("Battery marked as expired and moved to Expired Battery Details. Serial No document has been updated."))
		except Exception as e:
			frappe.db.rollback()
			frappe.throw(_("Error marking battery as expired: {0}").format(str(e)))
	
	def _update_frame_battery(self, frame_number, battery_serial_no):
		"""Update battery serial number in frame (Serial No doctype) and save immediately."""
		if not frame_number:
			return
		
		# Get the Serial No document
		try:
			frame_doc = frappe.get_doc("Serial No", frame_number)
			
			# Update battery field - try custom_battery_no first (most likely), then battery_no
			updated = False
			if frappe.db.has_column("Serial No", "custom_battery_no"):
				if hasattr(frame_doc, "custom_battery_no"):
					frame_doc.custom_battery_no = battery_serial_no
					updated = True
				else:
					# Fallback to db.set_value if attribute doesn't exist
					frappe.db.set_value("Serial No", frame_number, "custom_battery_no", battery_serial_no)
					updated = True
			elif frappe.db.has_column("Serial No", "battery_no"):
				if hasattr(frame_doc, "battery_no"):
					frame_doc.battery_no = battery_serial_no
					updated = True
				else:
					# Fallback to db.set_value if attribute doesn't exist
					frappe.db.set_value("Serial No", frame_number, "battery_no", battery_serial_no)
					updated = True
			else:
				# Try both field names via document attributes
				if hasattr(frame_doc, "custom_battery_no"):
					frame_doc.custom_battery_no = battery_serial_no
					updated = True
				elif hasattr(frame_doc, "battery_no"):
					frame_doc.battery_no = battery_serial_no
					updated = True
			
			# Save the document to ensure changes are persisted immediately
			if updated:
				frame_doc.save(ignore_permissions=True)
				# Commit to ensure the change is persisted right away
				frappe.db.commit()
			else:
				frappe.throw(_("Battery field not found in Serial No doctype. Please ensure custom_battery_no or battery_no field exists."))
				
		except frappe.DoesNotExistError:
			frappe.throw(_("Frame Number '{0}' not found.").format(frame_number))
		except Exception as e:
			frappe.log_error(f"Error updating battery in Serial No {frame_number}: {str(e)}", "Battery Swapping Error")
			frappe.throw(_("Error updating battery in frame: {0}").format(str(e)))
	
	def on_cancel(self):
		"""Handle cancellation: reverse the swap or expiration."""
		if self.swap_battery:
			self._reverse_battery_swap()
		elif self.is_expired:
			self._reverse_battery_expiration()
	
	def _reverse_battery_swap(self):
		"""Reverse battery swap on cancellation."""
		# Restore old battery to old frame
		if self.frame_number and self.current_battery_serial_no:
			self._update_frame_battery(self.frame_number, self.current_battery_serial_no)
		
		# Remove new battery from new frame
		if self.new_frame_number:
			# Get the battery that was in the new frame before swap
			# Note: This is a simplified reversal - in production, you might want to track the previous state
			self._update_frame_battery(self.new_frame_number, None)
		
		frappe.msgprint(_("Battery swap reversed."))
	
	def _reverse_battery_expiration(self):
		"""Reverse battery expiration on cancellation."""
		# Restore battery to frame
		if self.frame_number and self.current_battery_serial_no:
			self._update_frame_battery(self.frame_number, self.current_battery_serial_no)
		
		# Delete the Expired Battery Details record
		expired_battery = frappe.db.get_value(
			"Expired Battery Details",
			{"swapped_from_battery_swapping": self.name},
			"name"
		)
		if expired_battery:
			frappe.delete_doc("Expired Battery Details", expired_battery, ignore_permissions=True)
		
		frappe.msgprint(_("Battery expiration reversed."))


@frappe.whitelist()
def get_current_battery(frame_number):
	"""Get current battery serial number for a frame."""
	if not frame_number:
		return {"battery_serial_no": ""}
	
	battery_no = None
	try:
		if frappe.db.has_column("Serial No", "custom_battery_no"):
			battery_no = frappe.db.get_value("Serial No", frame_number, "custom_battery_no")
		elif frappe.db.has_column("Serial No", "battery_no"):
			battery_no = frappe.db.get_value("Serial No", frame_number, "battery_no")
		else:
			# Try accessing via document
			frame_doc = frappe.get_doc("Serial No", frame_number)
			battery_no = getattr(frame_doc, "custom_battery_no", None) or getattr(frame_doc, "battery_no", None)
	except Exception:
		pass
	
	return {"battery_serial_no": battery_no or ""}

