# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
import os
import csv
import re
from frappe.utils import get_site_path, getdate


class BatteryKeyUpload(Document):
	def validate(self):
		"""Validate the document before save."""
		# Only validate file attachment on submit, not on save
		# Allow saving in draft state without file
		
		# Clear child table when new file is attached
		if self.has_value_changed("excel_file"):
			self.upload_items = []
			self.total_frames_updated = 0
	
	def on_submit(self):
		"""Process the file and update Serial No records on submit."""
		if not self.excel_file:
			frappe.throw(_("No file attached"))
		
		# Process file
		try:
			self.process_excel_file()
			# Don't show msgprint here - let the client-side handle messaging after reload
			# This prevents messages from appearing before the form reloads
		except Exception as e:
			# Log error
			frappe.log_error(
				f"Error processing Battery Key Upload {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
				"Battery Key Upload Error"
			)
			# Show user-friendly error
			frappe.throw(_("Error processing file: {0}").format(str(e)))
	
	def process_excel_file(self):
		"""Read Excel and update Serial No records. Uses existing child table data if available."""
		# If child table already has data (from file upload), use it instead of reprocessing
		if self.upload_items and len(self.upload_items) > 0:
			# Process existing child table data
			total_updated = 0
			total_errors = 0
			
			for item in self.upload_items:
				if item.status == 'Error':
					total_errors += 1
					continue
				elif item.status == 'Skipped':
					# Skip rows with Skipped status, but don't count them
					continue
				elif item.status == 'Pending' or item.status == 'Updated':
					# Process this row
					try:
						serial_no = item.frame_no
						if not serial_no:
							item.status = 'Error'
							item.error_message = 'Frame No is missing'
							total_errors += 1
							continue
						
						# Update Serial No custom fields
						update_fields = {}
						if item.key_no:
							if frappe.db.has_column("Serial No", "custom_key_no"):
								update_fields["custom_key_no"] = str(item.key_no).strip()
						
						# Always update battery_serial_no to battery_no in Serial No if provided
						# Check if battery_serial_no has a value (not None and not empty string)
						battery_serial_no_value = getattr(item, 'battery_serial_no', None)
						if battery_serial_no_value and str(battery_serial_no_value).strip():
							# Try both battery_no and custom_battery_no fields
							if frappe.db.has_column("Serial No", "battery_no"):
								update_fields["battery_no"] = str(battery_serial_no_value).strip()
							elif frappe.db.has_column("Serial No", "custom_battery_no"):
								update_fields["custom_battery_no"] = str(battery_serial_no_value).strip()
						
						# Update Serial No with custom fields
						if update_fields:
							frappe.db.set_value("Serial No", serial_no, update_fields, update_modified=False)
							frappe.db.commit()  # Commit immediately to ensure it's saved
						
						# Create/Update Battery Details
						if item.battery_serial_no or item.battery_brand or item.battery_type or item.charging_date:
							self.create_or_update_battery_details(
								serial_no=serial_no,
								battery_serial_no=item.battery_serial_no,
								battery_brand=item.battery_brand,
								battery_type=item.battery_type,
								charging_date=item.charging_date
							)
						
						item.status = 'Updated'
						total_updated += 1
						
					except Exception as e:
						item.status = 'Error'
						item.error_message = str(e)
						total_errors += 1
						frappe.log_error(
							f"Error updating Serial No {item.frame_no}: {str(e)}",
							"Battery Key Upload Error"
						)
			
			# Update summary
			self.total_frames_updated = total_updated
			
			# Update child table status in database using frame_no to match rows
			# This ensures status updates persist even during submit
			if self.name:  # Document must be saved first (it should be before on_submit)
				for item in self.upload_items:
					if item.frame_no:
						# Find child table row by parent and frame_no
						child_row_name = frappe.db.get_value(
							"Battery Key Upload Item",
							{"parent": self.name, "frame_no": item.frame_no},
							"name",
							order_by="idx asc"  # Get first match if multiple
						)
						if child_row_name:
							frappe.db.set_value(
								"Battery Key Upload Item",
								child_row_name,
								{
									"status": item.status,
									"error_message": getattr(item, 'error_message', '') or '',
									"item_code": getattr(item, 'item_code', '') or ''
								},
								update_modified=False
							)
			
			# Commit to ensure all changes are persisted
			frappe.db.commit()
			return
		
		# If no child table data, process file from scratch (fallback)
		file_path = self.get_file_path()
		
		# Check if file exists
		if not os.path.exists(file_path):
			frappe.throw(_("File not found: {0}").format(file_path))
		
		# Read file based on extension
		file_ext = os.path.splitext(file_path)[1].lower()
		
		rows = []
		try:
			if file_ext == '.csv':
				# Read CSV file using Python's csv module
				with open(file_path, 'r', encoding='utf-8-sig') as f:
					reader = csv.DictReader(f)
					rows = list(reader)
			elif file_ext in ['.xlsx', '.xls']:
				# Read Excel file using pandas
				try:
					import pandas as pd
					df = pd.read_excel(file_path)
					rows = df.to_dict('records')
				except ImportError:
					frappe.throw(_("pandas library is required for Excel files. Please install it or use CSV format."))
			else:
				frappe.throw(_("Unsupported file format. Please upload CSV or Excel file."))
		except Exception as e:
			frappe.throw(_("Error reading file: {0}").format(str(e)))
		
		if not rows:
			frappe.throw(_("No data found in the file. Please check the file format."))
		
		# Normalize column names
		column_map = self.normalize_columns([col for col in rows[0].keys()] if rows else [])
		
		# Process rows
		total_updated = 0
		total_errors = 0
		
		# Clear existing items
		child_table_data = []
		
		for idx, row in enumerate(rows, start=1):
			# Extract values from row
			frame_no = self.get_value(row, column_map, ['frame_no', 'frame no', 'frame number', 'serial_no', 'serial no'])
			key_no = self.get_value(row, column_map, ['key_no', 'key no', 'key number'])
			battery_serial_no = self.get_value(row, column_map, [
				'battery_serial_no', 'battery serial no', 'sample battery serial no', 
				'battery_no', 'battery no', 'battery number'
			])
			battery_brand = self.get_value(row, column_map, ['battery_brand', 'battery brand', 'brand'])
			battery_type = self.get_value(row, column_map, ['battery_type', 'battery type', 'type', 'batery type'])
			charging_date_str = self.get_value(row, column_map, [
				'charging_date', 'charging date', 'sample battery charging date'
			])
			# Parse charging date to proper format
			charging_date = self.parse_date(charging_date_str) if charging_date_str else None
			
			# Validate Frame No is required
			if not frame_no:
				child_table_data.append({
					'frame_no': '',
					'status': 'Error',
					'error_message': f'Row {idx}: Frame No is required'
				})
				total_errors += 1
				continue
			
			# Find Serial No by frame_no (serial_no field or name)
			serial_no = self.find_serial_no(frame_no)
			
			if not serial_no:
				child_table_data.append({
					'frame_no': frame_no,
					'status': 'Error',
					'error_message': f'Row {idx}: Serial No {frame_no} not found'
				})
				total_errors += 1
				continue
			
			# Update Serial No
			try:
				item_code = frappe.db.get_value('Serial No', serial_no, 'item_code')
				
				# Update Serial No custom fields
				update_fields = {}
				if key_no:
					if frappe.db.has_column("Serial No", "custom_key_no"):
						update_fields["custom_key_no"] = str(key_no).strip()
				
				# Always update battery_serial_no to battery_no in Serial No if provided
				# Check if battery_serial_no has a value (not None and not empty string)
				if battery_serial_no and str(battery_serial_no).strip():
					# Try both battery_no and custom_battery_no fields
					if frappe.db.has_column("Serial No", "battery_no"):
						update_fields["battery_no"] = str(battery_serial_no).strip()
					elif frappe.db.has_column("Serial No", "custom_battery_no"):
						update_fields["custom_battery_no"] = str(battery_serial_no).strip()
				
				# Update Serial No with custom fields
				if update_fields:
					frappe.db.set_value("Serial No", serial_no, update_fields, update_modified=False)
					frappe.db.commit()  # Commit immediately to ensure it's saved
				
				# Create/Update Battery Details if battery information is provided
				if battery_serial_no or battery_brand or battery_type or charging_date:
					self.create_or_update_battery_details(
						serial_no=serial_no,
						battery_serial_no=battery_serial_no,
						battery_brand=battery_brand,
						battery_type=battery_type,
						charging_date=charging_date
					)
				
				child_table_data.append({
					'frame_no': serial_no,
					'key_no': str(key_no).strip() if key_no else '',
					'battery_serial_no': str(battery_serial_no).strip() if battery_serial_no else '',
					'battery_brand': str(battery_brand).strip() if battery_brand else '',
					'battery_type': str(battery_type).strip() if battery_type else '',
					'charging_date': charging_date,  # Already parsed to date object or None
					'status': 'Updated',
					'item_code': item_code or '',
					'error_message': ''
				})
				total_updated += 1
				
			except Exception as e:
				child_table_data.append({
					'frame_no': serial_no,
					'status': 'Error',
					'error_message': f'Row {idx}: {str(e)}'
				})
				total_errors += 1
				frappe.log_error(
					f"Error updating Serial No {serial_no}: {str(e)}",
					"Battery Key Upload Error"
				)
		
		# Update summary fields in document object
		self.total_frames_updated = total_updated
		
		# Clear existing child table and populate with new data
		self.upload_items = []
		
		# Populate child table using document's append method (this makes it immediately visible)
		if child_table_data:
			for row_data in child_table_data:
				child_row = self.append("upload_items", {})
				child_row.frame_no = row_data.get("frame_no", "") or ""
				child_row.key_no = row_data.get("key_no", "") or ""
				child_row.battery_serial_no = row_data.get("battery_serial_no", "") or ""
				child_row.battery_brand = row_data.get("battery_brand", "") or ""
				child_row.battery_type = row_data.get("battery_type", "") or ""
				child_row.charging_date = row_data.get("charging_date")  # Already parsed date or None
				child_row.status = row_data.get("status", "") or ""
				child_row.item_code = row_data.get("item_code", "") or ""
				child_row.error_message = row_data.get("error_message", "") or ""
		
		# Save the document with child table populated (this happens in on_submit, so it will be saved)
		# Note: In on_submit, the document is automatically saved after this method completes
		# But we need to ensure the child table is part of the document before save
		frappe.db.commit()
	
	def get_file_path(self):
		"""Get file path from file_url."""
		file_url = self.excel_file
		if file_url.startswith('/files/'):
			file_path = get_site_path('public', file_url[1:])
		elif file_url.startswith('/private/files/'):
			file_path = get_site_path('private', 'files', file_url.split('/')[-1])
		else:
			file_path = get_site_path('public', 'files', file_url)
		return file_path
	
	def normalize_columns(self, columns):
		"""Normalize column names to handle case-insensitive matching and variations."""
		column_map = {}
		for col in columns:
			if not col:
				continue
			# Convert to lowercase and strip whitespace
			normalized = str(col).lower().strip()
			# Remove special characters and normalize spaces
			normalized = normalized.replace('.', '').replace('_', ' ').replace('-', ' ')
			# Remove extra spaces
			normalized = ' '.join(normalized.split())
			column_map[normalized] = col
		return column_map
	
	def get_value(self, row, column_map, possible_names):
		"""Get value from row using normalized column names."""
		for name in possible_names:
			normalized = name.lower().strip().replace('.', '').replace('_', ' ').replace('-', ' ')
			normalized = ' '.join(normalized.split())
			if normalized in column_map:
				original_col = column_map[normalized]
				value = row.get(original_col)
				if value is not None:
					# Handle pandas NaN
					if isinstance(value, float):
						import math
						if math.isnan(value):
							continue
					# Convert to string and strip
					value_str = str(value).strip()
					if value_str:
						return value_str
		return None
	
	def parse_date(self, date_value):
		"""Parse date from various formats and return date object or None."""
		if not date_value:
			return None
		
		# If already a date object, return it
		if hasattr(date_value, 'strftime'):
			return date_value
		
		# Convert to string
		date_str = str(date_value).strip()
		if not date_str:
			return None
		
		# Try Frappe's getdate which handles multiple formats
		try:
			parsed_date = getdate(date_str)
			return parsed_date
		except:
			# If getdate fails, try manual parsing
			try:
				# Try MM/DD/YYYY or DD/MM/YYYY format (e.g., 3/26/2025, 26/3/2025)
				match = re.match(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
				if match:
					part1, part2, year = match.groups()
					# If first part > 12, it's likely DD/MM/YYYY, otherwise MM/DD/YYYY
					if int(part1) > 12:
						day, month = part1, part2  # DD/MM/YYYY
					else:
						month, day = part1, part2  # MM/DD/YYYY
					# Create date string in YYYY-MM-DD format
					date_str_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
					return getdate(date_str_formatted)
				
				# Try YYYY-MM-DD format
				match = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
				if match:
					year, month, day = match.groups()
					date_str_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
					return getdate(date_str_formatted)
			except:
				pass
		
		# If all parsing fails, return None
		frappe.log_error(f"Could not parse date: {date_str}", "Date Parsing Error")
		return None
	
	def find_serial_no(self, frame_no):
		"""Find Serial No by frame_no (checks both serial_no field and name)."""
		if not frame_no:
			return None
		
		frame_no = str(frame_no).strip()
		
		# First try to find by serial_no field
		serial_no = frappe.db.get_value("Serial No", {"serial_no": frame_no}, "name")
		if serial_no:
			return serial_no
		
		# Then try to find by name
		if frappe.db.exists("Serial No", frame_no):
			return frame_no
		
		return None
	
	
	def create_or_update_battery_details(self, serial_no, battery_serial_no=None, battery_brand=None, 
	                                    battery_type=None, charging_date=None):
		"""Create or update Battery Details record linked to Serial No."""
		if not frappe.db.exists("DocType", "Battery Details"):
			# Battery Details doctype doesn't exist, skip
			return
		
		# Parse charging date (should already be a date object, but handle string just in case)
		parsed_charging_date = None
		if charging_date:
			if hasattr(charging_date, 'strftime'):
				# Already a date object
				parsed_charging_date = charging_date
			else:
				# Try to parse string
				try:
					parsed_charging_date = getdate(charging_date)
				except:
					pass
		
		# Check if Battery Details already exists for this frame_no
		existing_battery = frappe.db.get_value(
			"Battery Details",
			{"frame_no": serial_no},
			"name"
		)
		
		if existing_battery:
			# Update existing Battery Details
			update_fields = {}
			if battery_serial_no:
				update_fields["battery_serial_no"] = str(battery_serial_no).strip()
			if battery_brand:
				update_fields["battery_brand"] = str(battery_brand).strip()
			if battery_type:
				update_fields["battery_type"] = str(battery_type).strip()
			if parsed_charging_date:
				update_fields["charging_date"] = parsed_charging_date
			
			if update_fields:
				frappe.db.set_value("Battery Details", existing_battery, update_fields, update_modified=False)
		else:
			# Create new Battery Details
			try:
				battery_doc = frappe.get_doc({
					"doctype": "Battery Details",
					"frame_no": serial_no,
					"battery_serial_no": str(battery_serial_no).strip() if battery_serial_no else "",
					"battery_brand": str(battery_brand).strip() if battery_brand else "",
					"battery_type": str(battery_type).strip() if battery_type else "",
					"charging_date": parsed_charging_date if parsed_charging_date else None,
					"status": "In Stock"
				})
				battery_doc.insert(ignore_permissions=True)
				frappe.db.commit()
			except Exception as e:
				# Log error but don't fail the whole process
				frappe.log_error(
					f"Error creating Battery Details for Serial No {serial_no}: {str(e)}",
					"Battery Details Creation Error"
				)


@frappe.whitelist()
def process_excel_file_for_preview(file_url):
	"""Process Excel file and return all rows data for populating child table immediately. Does NOT update Serial No records."""
	try:
		# Get file path
		if file_url.startswith('/files/'):
			file_path = get_site_path('public', file_url[1:])
		elif file_url.startswith('/private/files/'):
			file_path = get_site_path('private', 'files', file_url.split('/')[-1])
		else:
			file_path = get_site_path('public', 'files', file_url)
		
		# Check if file exists
		if not os.path.exists(file_path):
			return {"error": f"File not found: {file_path}"}
		
		# Read file
		file_ext = os.path.splitext(file_path)[1].lower()
		rows = []
		
		if file_ext == '.csv':
			with open(file_path, 'r', encoding='utf-8-sig') as f:
				reader = csv.DictReader(f)
				rows = list(reader)
		elif file_ext in ['.xlsx', '.xls']:
			try:
				import pandas as pd
				df = pd.read_excel(file_path)
				rows = df.to_dict('records')
			except ImportError:
				return {"error": "pandas library is required for Excel files"}
		else:
			return {"error": "Unsupported file format"}
		
		if not rows:
			return {"error": "No data found in the file"}
		
		# Normalize columns
		column_map = {}
		for col in rows[0].keys():
			if not col:
				continue
			normalized = str(col).lower().strip().replace('.', '').replace('_', ' ').replace('-', ' ')
			normalized = ' '.join(normalized.split())
			column_map[normalized] = col
		
		# Process ALL rows (not just preview)
		child_table_data = []
		total_updated = 0
		total_errors = 0
		
		for idx, row in enumerate(rows, start=1):
			# Extract values
			frame_no = _get_value_from_row(row, column_map, ['frame_no', 'frame no', 'frame number', 'serial_no', 'serial no'])
			key_no = _get_value_from_row(row, column_map, ['key_no', 'key no', 'key number'])
			battery_serial_no = _get_value_from_row(row, column_map, [
				'battery_serial_no', 'battery serial no', 'sample battery serial no', 
				'battery_no', 'battery no', 'battery number'
			])
			battery_brand = _get_value_from_row(row, column_map, ['battery_brand', 'battery brand', 'brand'])
			battery_type = _get_value_from_row(row, column_map, ['battery_type', 'battery type', 'type', 'batery type'])
			charging_date_str = _get_value_from_row(row, column_map, [
				'charging_date', 'charging date', 'sample battery charging date'
			])
			
			# Parse charging date
			charging_date = None
			if charging_date_str:
				charging_date = _parse_date_value(charging_date_str)
			
			# Validate Frame No is required
			if not frame_no:
				child_table_data.append({
					'frame_no': '',
					'key_no': '',
					'battery_serial_no': '',
					'battery_brand': '',
					'battery_type': '',
					'charging_date': None,
					'status': 'Error',
					'item_code': '',
					'error_message': f'Row {idx}: Frame No is required'
				})
				total_errors += 1
				continue
			
			# Find Serial No
			serial_no = _find_serial_no(frame_no)
			
			if not serial_no:
				child_table_data.append({
					'frame_no': frame_no,
					'key_no': key_no or '',
					'battery_serial_no': battery_serial_no or '',
					'battery_brand': battery_brand or '',
					'battery_type': battery_type or '',
					'charging_date': charging_date,
					'status': 'Error',
					'item_code': '',
					'error_message': f'Row {idx}: Serial No {frame_no} not found'
				})
				total_errors += 1
				continue
			
			# Valid row - will be processed on submit
			item_code = frappe.db.get_value('Serial No', serial_no, 'item_code') or ''
			child_table_data.append({
				'frame_no': serial_no,
				'key_no': key_no or '',
				'battery_serial_no': battery_serial_no or '',
				'battery_brand': battery_brand or '',
				'battery_type': battery_type or '',
				'charging_date': charging_date,
				'status': 'Pending',  # Will be updated to 'Updated' on submit
				'item_code': item_code,
				'error_message': ''
			})
			total_updated += 1
		
		return {
			'child_table_data': child_table_data,
			'total_rows': len(rows),
			'total_updated': total_updated,
			'total_errors': total_errors
		}
		
	except Exception as e:
		frappe.log_error(f"Error processing file for preview: {str(e)}", "Battery Key Upload Preview Error")
		return {"error": str(e)}


def _parse_date_value(date_value):
	"""Parse date from various formats and return date object or None."""
	if not date_value:
		return None
	
	# If already a date object, return it
	if hasattr(date_value, 'strftime'):
		return date_value
	
	# Convert to string
	date_str = str(date_value).strip()
	if not date_str:
		return None
	
	# Try Frappe's getdate which handles multiple formats
	try:
		parsed_date = getdate(date_str)
		return parsed_date
	except:
		# If getdate fails, try manual parsing
		try:
			# Try MM/DD/YYYY or DD/MM/YYYY format (e.g., 3/26/2025, 26/3/2025)
			match = re.match(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
			if match:
				part1, part2, year = match.groups()
				# If first part > 12, it's likely DD/MM/YYYY, otherwise MM/DD/YYYY
				if int(part1) > 12:
					day, month = part1, part2  # DD/MM/YYYY
				else:
					month, day = part1, part2  # MM/DD/YYYY
				# Create date string in YYYY-MM-DD format
				date_str_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
				return getdate(date_str_formatted)
			
			# Try YYYY-MM-DD format
			match = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
			if match:
				year, month, day = match.groups()
				date_str_formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
				return getdate(date_str_formatted)
		except:
			pass
		
		# If all parsing fails, return None
		return None


@frappe.whitelist()
def preview_excel_file(file_url):
	"""Preview Excel file and return summary without processing. Used for validation before submit."""
	try:
		# Get file path
		if file_url.startswith('/files/'):
			file_path = get_site_path('public', file_url[1:])
		elif file_url.startswith('/private/files/'):
			file_path = get_site_path('private', 'files', file_url.split('/')[-1])
		else:
			file_path = get_site_path('public', 'files', file_url)
		
		# Read file
		file_ext = os.path.splitext(file_path)[1].lower()
		rows = []
		
		if file_ext == '.csv':
			with open(file_path, 'r', encoding='utf-8-sig') as f:
				reader = csv.DictReader(f)
				rows = list(reader)
		elif file_ext in ['.xlsx', '.xls']:
			try:
				import pandas as pd
				df = pd.read_excel(file_path)
				rows = df.to_dict('records')
			except ImportError:
				return {"error": "pandas library is required for Excel files"}
		else:
			return {"error": "Unsupported file format"}
		
		if not rows:
			return {"error": "No data found in the file"}
		
		# Normalize columns
		column_map = {}
		for col in rows[0].keys():
			if not col:
				continue
			normalized = str(col).lower().strip().replace('.', '').replace('_', ' ').replace('-', ' ')
			normalized = ' '.join(normalized.split())
			column_map[normalized] = col
		
		# Process rows for preview
		total_rows = len(rows)
		valid_frames = 0
		frames_not_found = 0
		sample_rows = []
		
		for idx, row in enumerate(rows[:10], start=1):  # Only check first 10 for preview
			# Extract values
			frame_no = _get_value_from_row(row, column_map, ['frame_no', 'frame no', 'frame number', 'serial_no', 'serial no'])
			
			if not frame_no:
				sample_rows.append({
					'frame_no': '',
					'key_no': '',
					'battery_serial_no': '',
					'battery_brand': '',
					'battery_type': '',
					'status': 'Error: Frame No missing'
				})
				continue
			
			# Check if Serial No exists
			serial_no = _find_serial_no(frame_no)
			
			if not serial_no:
				frames_not_found += 1
				sample_rows.append({
					'frame_no': frame_no,
					'key_no': _get_value_from_row(row, column_map, ['key_no', 'key no', 'key number']) or '',
					'battery_serial_no': _get_value_from_row(row, column_map, ['battery_serial_no', 'battery serial no', 'sample battery serial no', 'battery_no', 'battery no']) or '',
					'battery_brand': _get_value_from_row(row, column_map, ['battery_brand', 'battery brand', 'brand']) or '',
					'battery_type': _get_value_from_row(row, column_map, ['battery_type', 'battery type', 'type', 'batery type']) or '',
					'status': 'Error: Frame No not found'
				})
				continue
			
			valid_frames += 1
			sample_rows.append({
				'frame_no': frame_no,
				'key_no': _get_value_from_row(row, column_map, ['key_no', 'key no', 'key number']) or '',
				'battery_serial_no': _get_value_from_row(row, column_map, ['battery_serial_no', 'battery serial no', 'sample battery serial no', 'battery_no', 'battery no']) or '',
				'battery_brand': _get_value_from_row(row, column_map, ['battery_brand', 'battery brand', 'brand']) or '',
				'battery_type': _get_value_from_row(row, column_map, ['battery_type', 'battery type', 'type', 'batery type']) or '',
				'status': 'Valid'
			})
		
		return {
			'total_rows': total_rows,
			'valid_frames': valid_frames,
			'frames_not_found': frames_not_found,
			'sample_rows': sample_rows[:5]  # Return first 5 for preview
		}
		
	except Exception as e:
		frappe.log_error(f"Error previewing file: {str(e)}", "Battery Key Upload Preview Error")
		return {"error": str(e)}


def _get_value_from_row(row, column_map, possible_names):
	"""Helper function to get value from row using normalized column names."""
	for name in possible_names:
		normalized = name.lower().strip().replace('.', '').replace('_', ' ').replace('-', ' ')
		normalized = ' '.join(normalized.split())
		if normalized in column_map:
			original_col = column_map[normalized]
			value = row.get(original_col)
			if value is not None:
				if isinstance(value, float):
					import math
					if math.isnan(value):
						continue
				value_str = str(value).strip()
				if value_str:
					return value_str
	return None


def _find_serial_no(frame_no):
	"""Helper function to find Serial No by frame_no."""
	if not frame_no:
		return None
	
	frame_no = str(frame_no).strip()
	
	# First try to find by serial_no field
	serial_no = frappe.db.get_value("Serial No", {"serial_no": frame_no}, "name")
	if serial_no:
		return serial_no
	
	# Then try to find by name
	if frappe.db.exists("Serial No", frame_no):
		return frame_no
	
	return None




def _update_upload_items_child_table(parent_name, child_table_data):
	"""Helper function to update child table after document submission."""
	if not parent_name:
		raise ValueError("Parent name is required")
	
	if not child_table_data:
		return  # Nothing to insert
	
	try:
		# Delete existing child table rows
		frappe.db.sql("""
			DELETE FROM `tabBattery Key Upload Item`
			WHERE parent = %s
		""", (parent_name,))
		
		# Insert new rows directly
		for idx, row_data in enumerate(child_table_data, start=1):
			# Parse charging_date if it's a string
			charging_date = row_data.get("charging_date")
			if charging_date:
				if isinstance(charging_date, str):
					try:
						charging_date = getdate(charging_date)
					except:
						charging_date = None
				# If it's already a date object, keep it
				elif hasattr(charging_date, 'strftime'):
					pass  # Already a date object
				else:
					charging_date = None
			else:
				charging_date = None
			
			# Generate unique name for child row
			child_name = frappe.generate_hash(length=10)
			
			# Get all field values with defaults
			frame_no = row_data.get("frame_no", "") or ""
			key_no = row_data.get("key_no", "") or ""
			battery_serial_no = row_data.get("battery_serial_no", "") or ""
			battery_brand = row_data.get("battery_brand", "") or ""
			battery_type = row_data.get("battery_type", "") or ""
			status = row_data.get("status", "") or ""
			item_code = row_data.get("item_code", "") or ""
			error_message = row_data.get("error_message", "") or ""
			
			# Insert row
			frappe.db.sql("""
				INSERT INTO `tabBattery Key Upload Item`
				(name, creation, modified, modified_by, owner, docstatus, parent, parentfield, parenttype, idx,
				 frame_no, key_no, battery_serial_no, battery_brand, battery_type, charging_date, status, item_code, error_message)
				VALUES
				(%s, NOW(), NOW(), %s, %s, 0, %s, 'upload_items', 'Battery Key Upload', %s,
				 %s, %s, %s, %s, %s, %s, %s, %s, %s)
			""", (
				child_name,
				frappe.session.user,
				frappe.session.user,
				parent_name,
				idx,
				frame_no,
				key_no,
				battery_serial_no,
				battery_brand,
				battery_type,
				charging_date,
				status,
				item_code,
				error_message
			))
		
		# Commit after all inserts
		frappe.db.commit()
		
	except Exception as sql_err:
		# Log detailed error
		error_msg = f"Error inserting child table rows via SQL: {str(sql_err)}\nParent: {parent_name}\nRows to insert: {len(child_table_data)}\nTraceback: {frappe.get_traceback()}"
		frappe.log_error(
			message=error_msg,
			title="Battery Key Upload Child Table SQL Error"
		)
		raise

