import frappe
import csv
import os
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt


class BatteryTransaction(Document):
	def validate(self):
		"""Validate Battery Transaction document."""
		# For "Out" transactions, validate battery_serial_no is selected
		if self.transaction_type == "Out":
			if not self.battery_serial_no:
				frappe.throw(_("Battery Serial No is required for Out transactions."))
			# Auto-populate fields from Battery Details
			self._populate_fields_from_battery_details()
		# For "In" transactions, validate items
		elif self.transaction_type == "In":
			if self.items:
				self.calculate_total_quantity()
	
	def before_submit(self):
		"""Create Battery Details and update Serial No before submitting Battery Transaction."""
		if self.transaction_type == "Out":
			# For Out transactions, update Battery Details status and clear Serial No
			if self.battery_serial_no:
				self._update_battery_details_status("Out")
			return
		
		# For In transactions, process items
		if not self.items:
			return
		
		# Validate all rows have battery_serial_no
		missing_serial_nos = []
		for item in self.items:
			if not item.battery_serial_no or not str(item.battery_serial_no).strip():
				missing_serial_nos.append(f"Row #{getattr(item, 'idx', 'Unknown')}")
		
		if missing_serial_nos:
			frappe.throw(
				_("Cannot submit Battery Transaction. The following rows are missing Battery Serial No:\n{0}").format(
					"\n".join(missing_serial_nos[:20]) + ("\n..." if len(missing_serial_nos) > 20 else "")
				),
				title=_("Missing Battery Serial No")
			)
		
		# Create Battery Details for each item
		self._create_battery_details()
		
		# Update Serial No with battery_serial_no for each frame_no
		self._update_serial_no_battery_no()
	
	def calculate_total_quantity(self):
		"""Calculate total battery quantity."""
		total = 0
		if self.items:
			for item in self.items:
				if item.battery_serial_no and str(item.battery_serial_no).strip():
					total += 1
		self.total_battery_quantity = total
	
	def _create_battery_details(self):
		"""Create Battery Details records for each item in In transaction.
		Since battery_serial_no is now a Link field, if it's set, Battery Details already exists.
		We only need to update the battery_transaction link if needed.
		"""
		if not self.items:
			return
		
		updated_details = []
		for item in self.items:
			if not item.battery_serial_no:
				continue
			
			# battery_serial_no is now a Link to Battery Details (contains the name like "BD-01")
			battery_details_name = str(item.battery_serial_no).strip()
			
			try:
				# Get the Battery Details document
				battery_details = frappe.get_doc("Battery Details", battery_details_name)
				
				# Update fields from child table if they're different
				updated = False
				if getattr(item, "battery_brand", None) and battery_details.battery_brand != item.battery_brand:
					battery_details.battery_brand = item.battery_brand
					updated = True
				if getattr(item, "battery_type", None) and battery_details.battery_type != item.battery_type:
					battery_details.battery_type = item.battery_type
					updated = True
				if getattr(item, "frame_no", None) and battery_details.frame_no != item.frame_no:
					battery_details.frame_no = item.frame_no
					updated = True
				if getattr(item, "battery_charging_code", None) and battery_details.battery_charging_code != item.battery_charging_code:
					battery_details.battery_charging_code = item.battery_charging_code
					updated = True
				if getattr(item, "charging_date", None) and battery_details.charging_date != item.charging_date:
					battery_details.charging_date = item.charging_date
					updated = True
				
				# Update battery_transaction link
				if battery_details.battery_transaction != self.name:
					battery_details.battery_transaction = self.name
					updated = True
				
				# Ensure status is "In Stock"
				if battery_details.status != "In Stock":
					battery_details.status = "In Stock"
					updated = True
				
				if updated:
					battery_details.save(ignore_permissions=True)
					updated_details.append(battery_details.battery_serial_no)
			except frappe.DoesNotExistError:
				frappe.log_error(
					f"Battery Details '{battery_details_name}' not found for item",
					"Battery Details Not Found"
				)
			except Exception as e:
				frappe.log_error(
					f"Failed to update Battery Details {battery_details_name}: {str(e)}",
					"Battery Details Update Error"
				)
		
		if updated_details:
			frappe.db.commit()
			if len(updated_details) > 0:
				frappe.msgprint(
					_("Updated {0} Battery Details record(s).").format(len(updated_details)),
					indicator="green"
				)
	
	def _populate_fields_from_battery_details(self):
		"""Populate fields from Battery Details for Out transactions."""
		if not self.battery_serial_no:
			return
		
		# Get Battery Details (battery_serial_no is now a Link to Battery Details)
		battery_details = frappe.get_doc("Battery Details", self.battery_serial_no)
		
		if battery_details:
			# Populate fields (these will be set via JavaScript, but we validate here)
			self.battery_brand_out = battery_details.battery_brand
			self.battery_type_out = battery_details.battery_type
			self.frame_no_out = battery_details.frame_no
			self.battery_charging_code_out = battery_details.battery_charging_code
			self.charging_date_out = battery_details.charging_date
	
	def _update_battery_details_status(self, status):
		"""Update Battery Details status for Out transactions and clear battery_no from Serial No."""
		if not self.battery_serial_no:
			return
		
		try:
			# battery_serial_no is now a Link to Battery Details
			battery_details = frappe.get_doc("Battery Details", self.battery_serial_no)
			
			# Validate status is "In Stock" before updating to "Out"
			if battery_details.status == "In Stock":
				battery_details.status = status
				battery_details.save(ignore_permissions=True)
				
				# Clear battery_no from Serial No when battery goes Out
				if status == "Out" and battery_details.frame_no:
					self._clear_serial_no_battery_no(battery_details.frame_no)
				
				frappe.db.commit()
			else:
				frappe.throw(
					_("Battery Details '{0}' is not in 'In Stock' status. Current status: {1}").format(
						self.battery_serial_no, battery_details.status
					)
				)
		except frappe.DoesNotExistError:
			frappe.throw(_("Battery Details '{0}' does not exist.").format(self.battery_serial_no))
		except Exception as e:
			frappe.log_error(
				f"Failed to update Battery Details status for {self.battery_serial_no}: {str(e)}",
				"Battery Details Update Error"
			)
			raise
	
	def _clear_serial_no_battery_no(self, frame_no):
		"""Clear battery_no field from Serial No when battery goes Out."""
		if not frame_no:
			return
		
		frame_no = str(frame_no).strip()
		if not frame_no:
			return
		
		# Check if Serial No exists
		if not frappe.db.exists("Serial No", frame_no):
			return
		
		try:
			# Determine the correct field name (battery_no or custom_battery_no)
			field_name = "battery_no"
			if not frappe.db.has_column("Serial No", "battery_no"):
				field_name = "custom_battery_no"
				if not frappe.db.has_column("Serial No", "custom_battery_no"):
					return  # Field doesn't exist, nothing to clear
			
			# Clear the battery_no field
			frappe.db.set_value("Serial No", frame_no, field_name, None, update_modified=False)
		except Exception as e:
			frappe.log_error(
				f"Failed to clear battery_no from Serial No {frame_no}: {str(e)}",
				"Serial No Battery Clear Error"
			)
	
	def _update_serial_no_battery_no(self):
		"""Update Serial No battery_no field with battery_serial_no for each frame_no."""
		if not self.items:
			return
		
		updated_serial_nos = []
		failed_updates = []
		
		for item in self.items:
			if not item.frame_no or not item.battery_serial_no:
				continue
			
			frame_no = str(item.frame_no).strip()
			# battery_serial_no is now a Link to Battery Details, get the actual battery_serial_no value
			battery_details_name = str(item.battery_serial_no).strip()
			
			if not frame_no or not battery_details_name:
				continue
			
			# Get the actual battery_serial_no value from Battery Details
			try:
				battery_serial_no = frappe.db.get_value("Battery Details", battery_details_name, "battery_serial_no")
				if not battery_serial_no:
					failed_updates.append({
						"frame_no": frame_no,
						"battery_details": battery_details_name,
						"error": "battery_serial_no not found in Battery Details"
					})
					continue
			except Exception as e:
				failed_updates.append({
					"frame_no": frame_no,
					"battery_details": battery_details_name,
					"error": f"Failed to get battery_serial_no: {str(e)}"
				})
				continue
			
			# Check if Serial No exists with this frame_no
			if not frappe.db.exists("Serial No", frame_no):
				failed_updates.append({
					"frame_no": frame_no,
					"battery_serial_no": battery_serial_no,
					"error": "Serial No not found"
				})
				continue
			
			try:
				# Update battery_no field in Serial No
				# Check if the field exists (it's a custom field, so fieldname might be battery_no or custom_battery_no)
				field_name = "battery_no"
				if not frappe.db.has_column("Serial No", "battery_no"):
					# Try custom field name
					field_name = "custom_battery_no"
					if not frappe.db.has_column("Serial No", "custom_battery_no"):
						failed_updates.append({
							"frame_no": frame_no,
							"battery_serial_no": battery_serial_no,
							"error": "battery_no field not found in Serial No"
						})
						continue
				
				frappe.db.set_value("Serial No", frame_no, field_name, battery_serial_no, update_modified=False)
				updated_serial_nos.append({
					"frame_no": frame_no,
					"battery_serial_no": battery_serial_no
				})
			except Exception as e:
				frappe.log_error(
					f"Failed to update Serial No {frame_no} with battery_no {battery_serial_no}: {str(e)}",
					"Serial No Battery Update Error"
				)
				failed_updates.append({
					"frame_no": frame_no,
					"battery_serial_no": battery_serial_no,
					"error": str(e)
				})
		
		# Commit updates
		if updated_serial_nos:
			frappe.db.commit()
			frappe.msgprint(
				_("Updated {0} Serial No record(s) with Battery Serial No.").format(len(updated_serial_nos)),
				indicator="green"
			)
		
		# Show warnings for failed updates
		if failed_updates:
			failed_messages = []
			for failed in failed_updates[:10]:
				failed_messages.append(
					_("Frame No {0}: {1}").format(failed["frame_no"], failed["error"])
				)
			
			frappe.msgprint(
				_("Failed to update {0} Serial No record(s):\n{1}").format(
					len(failed_updates),
					"\n".join(failed_messages) + ("\n..." if len(failed_updates) > 10 else "")
				),
				title=_("Serial No Update Warnings"),
				indicator="orange",
				alert=True
			)


@frappe.whitelist()
def process_battery_file(file_url):
	"""Process CSV/Excel file and return normalized data with frame_no support."""
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
			'frame no': 'frame_no',
			'frame number': 'frame_no',
			'frameno': 'frame_no',
		}
		
		# Process rows
		processed_rows = []
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
				# Also check for frame_no variations directly
				elif normalized_col and ('frame' in normalized_col and 'no' in normalized_col):
					normalized_row['frame_no'] = str(value).strip()
			
			if normalized_row.get('battery_serial_no'):
				# Since battery_serial_no is now a Link field, we need to find or create Battery Details
				battery_serial_no_value = normalized_row.get('battery_serial_no')
				
				# Check if Battery Details exists with this battery_serial_no
				battery_details_name = frappe.db.get_value(
					"Battery Details",
					{"battery_serial_no": battery_serial_no_value},
					"name"
				)
				
				if not battery_details_name:
					# Create Battery Details if it doesn't exist
					try:
						battery_details = frappe.get_doc({
							"doctype": "Battery Details",
							"battery_serial_no": battery_serial_no_value,
							"battery_brand": normalized_row.get('battery_brand'),
							"battery_type": normalized_row.get('battery_type'),
							"frame_no": normalized_row.get('frame_no'),
							"battery_charging_code": normalized_row.get('battery_charging_code'),
							"charging_date": normalized_row.get('charging_date'),
							"status": "In Stock"
						})
						battery_details.insert(ignore_permissions=True)
						battery_details_name = battery_details.name
						frappe.db.commit()
					except Exception as e:
						frappe.log_error(
							f"Failed to create Battery Details for {battery_serial_no_value}: {str(e)}",
							"Battery Details Creation Error"
						)
						# Skip this row if creation fails
						continue
				
				# Replace battery_serial_no value with Battery Details name (for Link field)
				normalized_row['battery_serial_no'] = battery_details_name
				processed_rows.append(normalized_row)
		
		# Return processed rows
		return {
			"rows": processed_rows
		}
		
	except Exception as e:
		frappe.log_error(
			f"Error processing battery file {file_url}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Battery File Processing Error"
		)
		frappe.throw(_("Error processing file: {0}").format(str(e)))


@frappe.whitelist()
def get_battery_details_for_out(battery_details_name):
	"""Get Battery Details for Out transaction to auto-populate fields."""
	if not battery_details_name:
		return None
	
	try:
		battery_details = frappe.get_doc("Battery Details", battery_details_name)
		
		# Validate status is "In Stock"
		if battery_details.status != "In Stock":
			return {
				"error": _("Battery Details is not in 'In Stock' status. Current status: {0}").format(battery_details.status)
			}
		
		return {
			"battery_serial_no": battery_details.battery_serial_no,
			"battery_brand": battery_details.battery_brand,
			"battery_type": battery_details.battery_type,
			"frame_no": battery_details.frame_no,
			"battery_charging_code": battery_details.battery_charging_code,
			"charging_date": battery_details.charging_date
		}
	except frappe.DoesNotExistError:
		return {"error": _("Battery Details '{0}' does not exist.").format(battery_details_name)}
	except Exception as e:
		frappe.log_error(f"Error getting Battery Details: {str(e)}", "Get Battery Details Error")
		return {"error": str(e)}
