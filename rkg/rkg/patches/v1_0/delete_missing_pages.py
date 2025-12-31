# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe
import os

def execute():
	"""
	Delete Page doctype records for pages that don't exist in the file system.
	This fixes errors where Page records exist but the corresponding page directories are missing.
	"""
	pages_to_delete = [
		'serial-batch-visual',
		'serial-no-dashboard'
	]
	
	app_path = frappe.get_app_path('rkg')
	page_base_path = os.path.join(app_path, 'rkg', 'rkg', 'page')
	
	for page_name in pages_to_delete:
		# Convert page name to directory name (hyphens to underscores)
		dir_name = page_name.replace('-', '_')
		page_dir_path = os.path.join(page_base_path, dir_name)
		
		# Check if directory exists
		if not os.path.exists(page_dir_path):
			# Directory doesn't exist, delete the Page record
			try:
				# Try deleting by name
				if frappe.db.exists('Page', page_name):
					frappe.delete_doc('Page', page_name, force=1, ignore_permissions=True)
					print(f"Deleted Page: {page_name} (directory {dir_name} does not exist)")
				
				# Also check by page_name field
				pages = frappe.get_all('Page', filters={'page_name': page_name}, fields=['name'])
				for page in pages:
					if page.name != page_name:  # Avoid double deletion
						frappe.delete_doc('Page', page.name, force=1, ignore_permissions=True)
						print(f"Deleted Page: {page.name} (found by page_name)")
				
				frappe.db.commit()
			except Exception as e:
				frappe.log_error(f"Error deleting Page {page_name}: {str(e)}")
				print(f"Error deleting Page {page_name}: {str(e)}")
		else:
			print(f"Page directory exists for {page_name}, skipping deletion")
