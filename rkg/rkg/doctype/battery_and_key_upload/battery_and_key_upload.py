# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
import os
import csv
import re
from frappe.utils import get_site_path, getdate


class BatteryandKeyUpload(Document):
	def validate(self):
		"""Validate the document before save."""
		# Only validate file attachment on submit, not on save
		# Allow saving in draft state without file
		
		# Clear child table when new file is attached
		if self.has_value_changed("excel_file"):
			self.upload_items = []
	
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
				f"Error processing Battery and Key Upload {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
				"Battery and Key Upload Error"
			)
			# Show user-friendly error
			frappe.throw(_("Error processing file: {0}").format(str(e)))
	
	def process_excel_file(self):
		"""Read Excel and update Battery Information and Frame Bundle records. Uses existing child table data if available."""
		# If child table already has data (from file upload), use it instead of reprocessing
		if self.upload_items and len(self.upload_items) > 0:
			# Process existing child table data
			total_errors = 0
			
			for item in self.upload_items:
				# Process this row
				try:
					serial_no = item.frame_no
					if not serial_no:
						total_errors += 1
						continue
					
					# Create/Update Battery Information
					battery_info_name = None
					if item.battery_serial_no:
						sample_charging_date = getattr(item, 'sample_charging_date', None)
						battery_info_name = self.create_or_update_battery_information(
							battery_serial_no=item.battery_serial_no,
							battery_brand=item.battery_brand,
							battery_type=item.battery_type,
							sample_charging_date=sample_charging_date,
							charging_date=item.charging_date
						)
						
						# Create/Update Frame Bundle
						if battery_info_name:
							item_code = frappe.db.get_value('Serial No', serial_no, 'item_code')
							if item_code:
								self.create_or_update_frame_bundle(
									frame_no=serial_no,
									item_code=item_code,
									battery_serial_no=battery_info_name,
									key_number=getattr(item, 'key_no', None)
								)
					
				except Exception as e:
					total_errors += 1
					frappe.log_error(
						f"Error updating Serial No {item.frame_no}: {str(e)}",
						"Battery and Key Upload Error"
					)
			
			# Update child table in database using frame_no to match rows
			# This ensures updates persist even during submit
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
			# Extract sample_charging_date as raw string
			sample_charging_date = self.get_value(row, column_map, [
				'sample_charging_date', 'sample charging date', 'sample battery charging date'
			])
			charging_date_str = self.get_value(row, column_map, [
				'charging_date', 'charging date'
			])
			# If charging_date not found but sample_charging_date exists, use that for parsing
			if not charging_date_str and sample_charging_date:
				charging_date_str = sample_charging_date
			# Parse charging date to proper format
			charging_date = self.parse_date(charging_date_str) if charging_date_str else None
			
			# Validate Frame No is required
			if not frame_no:
				child_table_data.append({
					'frame_no': '',
					'key_no': '',
					'battery_serial_no': '',
					'battery_brand': '',
					'battery_type': '',
					'sample_charging_date': str(sample_charging_date).strip() if sample_charging_date else '',
					'charging_date': None,
					'item_code': ''
				})
				total_errors += 1
				continue
			
			# Find Serial No by frame_no (serial_no field or name)
			serial_no = self.find_serial_no(frame_no)
			
			if not serial_no:
				child_table_data.append({
					'frame_no': frame_no,
					'key_no': str(key_no).strip() if key_no else '',
					'battery_serial_no': str(battery_serial_no).strip() if battery_serial_no else '',
					'battery_brand': str(battery_brand).strip() if battery_brand else '',
					'battery_type': str(battery_type).strip() if battery_type else '',
					'sample_charging_date': str(sample_charging_date).strip() if sample_charging_date else '',
					'charging_date': None,
					'item_code': ''
				})
				total_errors += 1
				continue
			
			# Update Serial No
			try:
				item_code = frappe.db.get_value('Serial No', serial_no, 'item_code')
				
				# Create/Update Battery Information
				battery_info_name = None
				if battery_serial_no:
					battery_info_name = self.create_or_update_battery_information(
						battery_serial_no=battery_serial_no,
						battery_brand=battery_brand,
						battery_type=battery_type,
						sample_charging_date=sample_charging_date,
						charging_date=charging_date
					)
					
					# Create/Update Frame Bundle
					if battery_info_name and item_code:
						self.create_or_update_frame_bundle(
							frame_no=serial_no,
							item_code=item_code,
							battery_serial_no=battery_info_name,
							key_number=key_no
						)
				
				child_table_data.append({
					'frame_no': serial_no,
					'key_no': str(key_no).strip() if key_no else '',
					'battery_serial_no': str(battery_serial_no).strip() if battery_serial_no else '',
					'battery_brand': str(battery_brand).strip() if battery_brand else '',
					'battery_type': str(battery_type).strip() if battery_type else '',
					'sample_charging_date': str(sample_charging_date).strip() if sample_charging_date else '',
					'charging_date': charging_date,  # Already parsed to date object or None
					'item_code': item_code or ''
				})
				
			except Exception as e:
				child_table_data.append({
					'frame_no': serial_no,
					'key_no': str(key_no).strip() if key_no else '',
					'battery_serial_no': str(battery_serial_no).strip() if battery_serial_no else '',
					'battery_brand': str(battery_brand).strip() if battery_brand else '',
					'battery_type': str(battery_type).strip() if battery_type else '',
					'sample_charging_date': str(sample_charging_date).strip() if sample_charging_date else '',
					'charging_date': None,
					'item_code': ''
				})
				total_errors += 1
				frappe.log_error(
					f"Error updating Serial No {serial_no}: {str(e)}",
					"Battery and Key Upload Error"
				)
		
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
				child_row.sample_charging_date = row_data.get("sample_charging_date", "") or ""
				child_row.charging_date = row_data.get("charging_date")  # Already parsed date or None
				child_row.item_code = row_data.get("item_code", "") or ""
		
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
	
	def create_or_update_battery_information(self, battery_serial_no=None, battery_brand=None, 
	                                        battery_type=None, sample_charging_date=None, charging_date=None):
		"""Create or update Battery Information record based on battery_serial_no.
		Returns the name of the Battery Information record (which is the battery_serial_no)."""
		if not frappe.db.exists("DocType", "Battery Information"):
			# Battery Information doctype doesn't exist, skip
			return None
		
		# Battery Information must have battery_serial_no
		if not battery_serial_no or not str(battery_serial_no).strip():
			return None
		
		battery_serial_no = str(battery_serial_no).strip()
		
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
		
		# Check if Battery Information already exists for this battery_serial_no
		existing_battery_info = frappe.db.get_value(
			"Battery Information",
			{"battery_serial_no": battery_serial_no},
			"name"
		)
		
		if existing_battery_info:
			# Update existing Battery Information
			update_fields = {}
			if battery_brand:
				update_fields["battery_brand"] = str(battery_brand).strip()
			if battery_type:
				update_fields["battery_type"] = str(battery_type).strip()
			if sample_charging_date:
				update_fields["sample_charging_date"] = str(sample_charging_date).strip()
			if parsed_charging_date:
				update_fields["charging_date"] = parsed_charging_date
			
			if update_fields:
				frappe.db.set_value("Battery Information", existing_battery_info, update_fields, update_modified=False)
				frappe.db.commit()
			return existing_battery_info
		else:
			# Create new Battery Information
			try:
				battery_info_doc = frappe.get_doc({
					"doctype": "Battery Information",
					"battery_serial_no": battery_serial_no,
					"battery_brand": str(battery_brand).strip() if battery_brand else "",
					"battery_type": str(battery_type).strip() if battery_type else "",
					"sample_charging_date": str(sample_charging_date).strip() if sample_charging_date else "",
					"charging_date": parsed_charging_date if parsed_charging_date else None
				})
				battery_info_doc.insert(ignore_permissions=True)
				# Submit the document to make it in submitted state
				battery_info_doc.submit()
				frappe.db.commit()
				# Return the name (which is the battery_serial_no based on autoname format)
				return battery_info_doc.name
			except Exception as e:
				# Log error but don't fail the whole process
				frappe.log_error(
					f"Error creating Battery Information for battery_serial_no {battery_serial_no}: {str(e)}",
					"Battery Information Creation Error"
				)
				return None
	
	def create_or_update_frame_bundle(self, frame_no=None, item_code=None, battery_serial_no=None, key_number=None):
		"""Create or update Frame Bundle record based on frame_no and item_code.
		Frame Bundle autoname format: {frame_no}-{item_code}"""
		if not frappe.db.exists("DocType", "Frame Bundle"):
			# Frame Bundle doctype doesn't exist, skip
			return None
		
		# Frame Bundle must have frame_no and item_code (required fields)
		if not frame_no or not item_code:
			return None
		
		# Get the actual frame number from Serial No (serial_no field)
		actual_frame_no = frappe.db.get_value('Serial No', frame_no, 'serial_no') or frame_no
		
		# Frame Bundle name format is: {frame_no}-{item_code}
		frame_bundle_name = f"{actual_frame_no}-{item_code}"
		
		# Check if Frame Bundle already exists
		existing_frame_bundle = None
		if frappe.db.exists("Frame Bundle", frame_bundle_name):
			existing_frame_bundle = frame_bundle_name
		
		# Prepare update/create fields
		update_fields = {}
		if battery_serial_no:
			# Verify Battery Information exists before linking
			if frappe.db.exists("Battery Information", battery_serial_no):
				update_fields["battery_serial_no"] = battery_serial_no
		if key_number:
			update_fields["key_number"] = str(key_number).strip()
		
		try:
			if existing_frame_bundle:
				# Update existing Frame Bundle
				if update_fields:
					frappe.db.set_value("Frame Bundle", existing_frame_bundle, update_fields, update_modified=False)
					frappe.db.commit()
			else:
				# Create new Frame Bundle
				frame_bundle_doc = frappe.get_doc({
					"doctype": "Frame Bundle",
					"frame_no": actual_frame_no,
					"item_code": item_code,
					"battery_serial_no": battery_serial_no if (battery_serial_no and frappe.db.exists("Battery Information", battery_serial_no)) else None,
					"key_number": str(key_number).strip() if key_number else None
				})
				frame_bundle_doc.insert(ignore_permissions=True)
				frappe.db.commit()
				frame_bundle_name = frame_bundle_doc.name
			
			return frame_bundle_name
		except Exception as e:
			# Log error but don't fail the whole process
			frappe.log_error(
				f"Error creating/updating Frame Bundle for frame_no {actual_frame_no}, item_code {item_code}: {str(e)}",
				"Frame Bundle Creation Error"
			)
			return None


@frappe.whitelist()
def process_excel_file_for_preview(file_url):
	"""Process Excel file and return all rows data for populating child table immediately. Does NOT update Battery Information or Frame Bundle records."""
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
			# Extract sample_charging_date as raw string
			sample_charging_date = _get_value_from_row(row, column_map, [
				'sample_charging_date', 'sample charging date', 'sample battery charging date'
			])
			charging_date_str = _get_value_from_row(row, column_map, [
				'charging_date', 'charging date'
			])
			# If charging_date not found but sample_charging_date exists, use that for parsing
			if not charging_date_str and sample_charging_date:
				charging_date_str = sample_charging_date
			
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
					'sample_charging_date': '',
					'charging_date': None,
					'item_code': ''
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
					'sample_charging_date': sample_charging_date or '',
					'charging_date': charging_date,
					'item_code': ''
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
				'sample_charging_date': sample_charging_date or '',
				'charging_date': charging_date,
				'item_code': item_code
			})
			total_updated += 1
		
		return {
			'child_table_data': child_table_data,
			'total_rows': len(rows),
			'total_updated': total_updated,
			'total_errors': total_errors
		}
		
	except Exception as e:
		frappe.log_error(f"Error processing file for preview: {str(e)}", "Battery and Key Upload Preview Error")
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
					'battery_type': ''
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
					'battery_type': _get_value_from_row(row, column_map, ['battery_type', 'battery type', 'type', 'batery type']) or ''
				})
				continue
			
			valid_frames += 1
			sample_rows.append({
				'frame_no': frame_no,
				'key_no': _get_value_from_row(row, column_map, ['key_no', 'key no', 'key number']) or '',
				'battery_serial_no': _get_value_from_row(row, column_map, ['battery_serial_no', 'battery serial no', 'sample battery serial no', 'battery_no', 'battery no']) or '',
				'battery_brand': _get_value_from_row(row, column_map, ['battery_brand', 'battery brand', 'brand']) or '',
				'battery_type': _get_value_from_row(row, column_map, ['battery_type', 'battery type', 'type', 'batery type']) or ''
			})
		
		return {
			'total_rows': total_rows,
			'valid_frames': valid_frames,
			'frames_not_found': frames_not_found,
			'sample_rows': sample_rows[:5]  # Return first 5 for preview
		}
		
	except Exception as e:
		frappe.log_error(f"Error previewing file: {str(e)}", "Battery and Key Upload Preview Error")
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

