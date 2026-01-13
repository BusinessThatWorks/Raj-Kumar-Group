# For license information, please see license.txt

"""
Patch to initialize battery_installed_on field for existing Frame Bundle records.

This patch sets battery_installed_on = creation date for all existing records
where battery_installed_on is NULL. This ensures existing records continue to
show correct aging until batteries are swapped.

This is a non-destructive migration - it only sets values where battery_installed_on
is NULL and does not overwrite existing values.
"""

import frappe
from frappe.utils import getdate


def execute():
	"""Set battery_installed_on = creation date for existing Frame Bundle records where battery_installed_on is NULL"""
	
	# Get all Frame Bundle records where battery_installed_on is NULL
	frames = frappe.db.sql("""
		SELECT name, creation
		FROM `tabFrame Bundle`
		WHERE battery_installed_on IS NULL
	""", as_dict=True)
	
	updated_count = 0
	for frame in frames:
		if frame.creation:
			# Extract date part from creation datetime
			creation_date = getdate(frame.creation)
			
			# Set battery_installed_on = creation date
			frappe.db.set_value(
				"Frame Bundle",
				frame.name,
				"battery_installed_on",
				creation_date,
				update_modified=False
			)
			updated_count += 1
	
	frappe.db.commit()
	
	# Log the update count (patches run during migrations, so no user-facing messages)
	if updated_count > 0:
		frappe.logger().info(f"Updated battery_installed_on for {updated_count} Frame Bundle record(s)")

