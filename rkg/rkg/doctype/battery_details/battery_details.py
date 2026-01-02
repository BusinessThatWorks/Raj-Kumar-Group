import frappe
from frappe.model.document import Document
from datetime import timedelta


class BatteryDetails(Document):
	def validate(self):
		# Clear orphaned battery_transaction links
		if self.battery_transaction and not frappe.db.exists("Battery Transaction", self.battery_transaction):
			self.battery_transaction = None
		
		if self.battery_swapping and self.new_frame_number and self.battery_serial_no:
			self.update_serial_no_battery_no()
		
		self.calculate_battery_expiry_date()

	def on_trash(self):
		"""Clear battery_transaction link before deletion to avoid circular dependency."""
		if self.battery_transaction:
			# Clear the link using direct SQL to bypass validation
			frappe.db.sql(
				"UPDATE `tabBattery Details` SET battery_transaction = NULL WHERE name = %s",
				self.name
			)
			frappe.db.commit()

	def calculate_battery_expiry_date(self):
		"""Calculate battery expiry date from charging date + days from RKG Settings."""
		if not self.charging_date:
			self.battery_expiry_date = None
			return

		days = frappe.db.get_single_value("RKG Settings", "default_no_of_days_for_the_expiration_of_the_battery")
		if not days:
			days = 60  # Default to 60 days if not set

		from datetime import datetime
		if isinstance(self.charging_date, str):
			charging_date = datetime.strptime(self.charging_date, "%Y-%m-%d").date()
		else:
			charging_date = self.charging_date

		self.battery_expiry_date = charging_date + timedelta(days=days)

	def update_serial_no_battery_no(self):
		"""Update Serial No battery_no field with battery_serial_no."""
		if not self.new_frame_number or not self.battery_serial_no:
			return

		frame_no = str(self.new_frame_number).strip()
		battery_serial_no = str(self.battery_serial_no).strip()

		if not frappe.db.exists("Serial No", frame_no):
			frappe.throw(f"Serial No {frame_no} not found")

		field_name = "battery_no"
		if not frappe.db.has_column("Serial No", "battery_no"):
			field_name = "custom_battery_no"
			if not frappe.db.has_column("Serial No", "custom_battery_no"):
				return

		frappe.db.set_value("Serial No", frame_no, field_name, battery_serial_no, update_modified=False)


@frappe.whitelist()
def update_serial_no_battery_no(serial_no, battery_serial_no):
	"""Update Serial No battery_no field with battery_serial_no."""
	if not serial_no or not battery_serial_no:
		return

	frame_no = str(serial_no).strip()
	battery_serial_no = str(battery_serial_no).strip()

	if not frappe.db.exists("Serial No", frame_no):
		frappe.throw(f"Serial No {frame_no} not found")

	field_name = "battery_no"
	if not frappe.db.has_column("Serial No", "battery_no"):
		field_name = "custom_battery_no"
		if not frappe.db.has_column("Serial No", "custom_battery_no"):
			return

	frappe.db.set_value("Serial No", frame_no, field_name, battery_serial_no, update_modified=False)


@frappe.whitelist()
def calculate_expiry_date(charging_date):
	"""Calculate battery expiry date from charging date + days from RKG Settings."""
	if not charging_date:
		return None

	days = frappe.db.get_single_value("RKG Settings", "default_no_of_days_for_the_expiration_of_the_battery")
	if not days:
		days = 60  # Default to 60 days if not set

	from datetime import datetime, timedelta
	if isinstance(charging_date, str):
		charging_date_obj = datetime.strptime(charging_date, "%Y-%m-%d").date()
	else:
		charging_date_obj = charging_date

	expiry_date = charging_date_obj + timedelta(days=days)
	return expiry_date.strftime("%Y-%m-%d")

