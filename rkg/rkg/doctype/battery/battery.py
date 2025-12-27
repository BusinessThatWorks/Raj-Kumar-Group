import frappe
import csv
import os
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt


class Battery(Document):
	def validate(self):
		"""Validate Battery document."""
		if self.items:
			self.calculate_total_quantity()
			self.set_item_code()
	
	def before_save(self):
		"""Set item_code if Item exists."""
		if self.items:
			self.set_item_code()
	
	def before_submit(self):
		"""Create Items before submitting Battery."""
		if not self.items:
			return
		
		# Validate all rows have battery_serial_no
		missing_serial_nos = []
		for item in self.items:
			if not item.battery_serial_no or not str(item.battery_serial_no).strip():
				missing_serial_nos.append(f"Row #{getattr(item, 'idx', 'Unknown')}")
		
		if missing_serial_nos:
			frappe.throw(
				_("Cannot submit Battery. The following rows are missing Battery Serial No:\n{0}").format(
					"\n".join(missing_serial_nos[:20]) + ("\n..." if len(missing_serial_nos) > 20 else "")
				),
				title=_("Missing Battery Serial No")
			)
		
		# Collect all item codes to check existence in batch
		item_codes_to_check = []
		item_code_to_row_map = {}
		
		for item in self.items:
			# Skip if item_code already set and exists
			if item.item_code and str(item.item_code).strip():
				if not frappe.db.exists("Item", item.item_code):
					frappe.throw(
						_("Row #{0}: Item '{1}' does not exist.").format(
							getattr(item, 'idx', 'Unknown'), item.item_code
						),
						title=_("Invalid Item Code")
					)
				continue
			
			if not item.battery_serial_no:
				continue
			
			item_code = str(item.battery_serial_no).strip()
			item_codes_to_check.append(item_code)
			item_code_to_row_map[item_code] = item
		
		# Batch check for existing items (optimized)
		existing_items = set()
		if item_codes_to_check:
			existing_items = set(
				frappe.db.get_all(
					"Item",
					filters={"item_code": ["in", item_codes_to_check]},
					pluck="item_code"
				)
			)
		
		# Track skipped and created items
		skipped_items = []
		created_items = []
		failed_items = []
		
		# Process items
		for item_code in item_codes_to_check:
			item = item_code_to_row_map[item_code]
			row_num = getattr(item, 'idx', 'Unknown')
			
			# Skip if item already exists
			if item_code in existing_items:
				item.item_code = item_code
				skipped_items.append({
					"item_code": item_code,
					"row": row_num
				})
				continue
			
			# Create new item
			try:
				self._create_item_from_battery_item(item, item_code)
				frappe.clear_cache(doctype="Item")
				frappe.db.commit()
				
				# Verify item was created
				if frappe.db.exists("Item", item_code):
					item.item_code = item_code
					created_items.append({
						"item_code": item_code,
						"row": row_num
					})
				else:
					failed_items.append({
						"item_code": item_code,
						"row": row_num,
						"error": "Item was not created"
					})
			except Exception as e:
				frappe.log_error(
					f"Failed to create Item {item_code}: {str(e)}\nTraceback: {frappe.get_traceback()}",
					"Battery Item Creation Error"
				)
				failed_items.append({
					"item_code": item_code,
					"row": row_num,
					"error": str(e)
				})
		
		# Show summary message
		total_items = len(item_codes_to_check)
		skipped_count = len(skipped_items)
		created_count = len(created_items)
		failed_count = len(failed_items)
		
		# Build message
		message_parts = []
		
		if created_count > 0:
			message_parts.append(_("{0} item(s) created successfully.").format(created_count))
		
		if skipped_count > 0:
			skipped_codes = [s["item_code"] for s in skipped_items[:10]]
			skipped_msg = ", ".join(skipped_codes)
			if skipped_count > 10:
				skipped_msg += _(" and {0} more").format(skipped_count - 10)
			message_parts.append(
				_("{0} item(s) already exist and were skipped: {1}").format(skipped_count, skipped_msg)
			)
		
		if failed_count > 0:
			failed_codes = [f["item_code"] for f in failed_items[:5]]
			failed_msg = ", ".join(failed_codes)
			if failed_count > 5:
				failed_msg += _(" and {0} more").format(failed_count - 5)
			message_parts.append(
				_("{0} item(s) failed to create: {1}").format(failed_count, failed_msg)
			)
		
		# Show message if there are skipped or failed items
		if skipped_count > 0 or failed_count > 0:
			message = "\n".join(message_parts)
			indicator = "orange" if failed_count == 0 else "red"
			
			frappe.msgprint(
				message,
				title=_("Item Creation Summary"),
				indicator=indicator,
				alert=True
			)
		
		# Throw error if any items failed to create
		if failed_count > 0:
			error_details = []
			for failed in failed_items[:10]:
				error_details.append(
					_("Row #{0}: {1} - {2}").format(
						failed["row"], failed["item_code"], failed["error"]
					)
				)
			
			frappe.throw(
				_("Cannot submit Battery. Failed to create {0} item(s):\n\n{1}").format(
					failed_count,
					"\n".join(error_details) + ("\n..." if failed_count > 10 else "")
				),
				title=_("Item Creation Failed")
			)
	
	def set_item_code(self):
		"""Set item_code only if Item exists."""
		if not self.items:
			return
		
		for item in self.items:
			if not item.battery_serial_no:
				continue
			
			item_code = str(item.battery_serial_no).strip()
			if frappe.db.exists("Item", item_code):
				item.item_code = item_code
			else:
				item.item_code = None
	
	def calculate_total_quantity(self):
		"""Calculate total battery quantity."""
		total = 0
		if self.items:
			for item in self.items:
				if item.battery_serial_no and str(item.battery_serial_no).strip():
					total += 1
		self.total_battery_quantity = total
	
	def _create_item_from_battery_item(self, battery_item, item_code):
		"""Create Item from Battery Item."""
		battery_brand = getattr(battery_item, "battery_brand", None)
		battery_type = getattr(battery_item, "battery_type", None)
		battery_charging_code = getattr(battery_item, "battery_charging_code", None)
		charging_date = getattr(battery_item, "charging_date", None)
		unit = getattr(battery_item, "unit", None) or "Pcs"
		
		# Calculate item_name
		item_name = f"{battery_brand} {battery_type}".strip() if battery_brand and battery_type else item_code
		
		# Get or create hierarchical Item Group
		item_group = _get_or_create_battery_item_group(battery_brand, battery_type)
		if not item_group:
			frappe.throw(_("Could not determine Item Group. Brand: {0}, Type: {1}").format(
				battery_brand or 'N/A', battery_type or 'N/A'
			))
		
		# Create Item
		item_dict = {
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_group": item_group,
			"stock_uom": str(unit).strip(),
			"is_stock_item": 1,
			"has_serial_no": 0,
		}
		
		item_doc = frappe.get_doc(item_dict)
		
		# Add custom fields if they exist
		if hasattr(item_doc, "custom_battery_brand") and battery_brand:
			item_doc.custom_battery_brand = battery_brand
		
		if hasattr(item_doc, "custom_battery_type") and battery_type:
			item_doc.custom_battery_type = battery_type
		
		if hasattr(item_doc, "custom_battery_charging_code") and battery_charging_code:
			item_doc.custom_battery_charging_code = battery_charging_code
		
		if hasattr(item_doc, "custom_charging_date") and charging_date:
			item_doc.custom_charging_date = charging_date
		
		# Add Supplier and HSN from RKG Settings
		try:
			rkg_settings = frappe.get_single("RKG Settings")
			if rkg_settings.get("default_supplier"):
				if hasattr(item_doc, "supplier_items"):
					item_doc.append("supplier_items", {
						"supplier": rkg_settings.default_supplier,
						"is_default": 1
					})
			if rkg_settings.get("default_hsn_code"):
				if hasattr(item_doc, "gst_hsn_code"):
					item_doc.gst_hsn_code = rkg_settings.default_hsn_code
				elif hasattr(item_doc, "custom_gst_hsn_code"):
					item_doc.custom_gst_hsn_code = rkg_settings.default_hsn_code
		except:
			pass
		
		item_doc.insert(ignore_permissions=True)


def _get_or_create_battery_item_group(battery_brand, battery_type):
	"""Create Item Group: Batteries (all items stored directly under it)."""
	# Ensure "All Item Groups" exists
	all_groups = "All Item Groups"
	if not frappe.db.exists("Item Group", all_groups):
		try:
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": all_groups,
				"is_group": 1
			}).insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"Failed to create 'All Item Groups': {str(e)}", "Item Group Creation")
	
	# Ensure "Batteries" exists (Items go directly here)
	batteries_group = "Batteries"
	if not frappe.db.exists("Item Group", batteries_group):
		try:
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": batteries_group,
				"is_group": 0,  # Leaf group - items go here
				"parent_item_group": all_groups
			}).insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"Failed to create 'Batteries' group: {str(e)}", "Item Group Creation")
	
	return batteries_group


@frappe.whitelist()
def process_battery_file(file_url):
	"""Process CSV/Excel file and return normalized data with existing items check."""
	from frappe.utils import get_site_path
	
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
				frappe.throw(_("pandas library is required for Excel files."))
		else:
			frappe.throw(_("Unsupported file format. Please upload CSV or Excel file."))
		
		# Normalize column names
		def normalize_column_name(col_name):
			if not col_name:
				return None
			return str(col_name).lower().strip().replace('.', '').replace('_', ' ').replace('-', ' ')
		
		column_mapping = {
			'battery brand': 'battery_brand',
			'battery type': 'battery_type',
			'batery type': 'battery_type',
			'sample battery serial no': 'battery_serial_no',
			'battery serial no': 'battery_serial_no',
			'sample battery charging date': 'battery_charging_code',
			'battery charging code': 'battery_charging_code',
			'charging date': 'charging_date',
		}
		
		# Process rows
		processed_rows = []
		item_codes = []
		for row in rows:
			normalized_row = {}
			for excel_col, value in row.items():
				if not value or (isinstance(value, float) and str(value).lower() == 'nan'):
					continue
				
				normalized_col = normalize_column_name(excel_col)
				if normalized_col and normalized_col in column_mapping:
					field_name = column_mapping[normalized_col]
					
					# Parse dates
					if field_name == 'charging_date':
						try:
							from frappe.utils import getdate
							parsed_date = getdate(value)
							normalized_row[field_name] = parsed_date.strftime('%Y-%m-%d')
						except:
							pass
					else:
						normalized_row[field_name] = str(value).strip()
			
			if normalized_row.get('battery_serial_no'):
				item_code = str(normalized_row.get('battery_serial_no')).strip()
				item_codes.append(item_code)
				processed_rows.append(normalized_row)
		
		# Check for existing items (batch query for optimization)
		existing_items = set()
		if item_codes:
			existing_items = set(
				frappe.db.get_all(
					"Item",
					filters={"item_code": ["in", item_codes]},
					pluck="item_code"
				)
			)
		
		# Mark existing items in processed rows
		for row in processed_rows:
			item_code = str(row.get('battery_serial_no', '')).strip()
			if item_code in existing_items:
				row['item_exists'] = True
				row['item_code'] = item_code
			else:
				row['item_exists'] = False
		
		# Return data with existing items info
		return {
			"rows": processed_rows,
			"existing_count": len(existing_items),
			"new_count": len(processed_rows) - len(existing_items),
			"existing_items": list(existing_items)[:20]  # Limit to first 20 for display
		}
		
	except Exception as e:
		frappe.log_error(
			f"Error processing battery file {file_url}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Battery File Processing Error"
		)
		frappe.throw(_("Error processing file: {0}").format(str(e)))

