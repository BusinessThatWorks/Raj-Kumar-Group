import csv
import os

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file


class LoadPlan(Document):
	def before_insert(self):
		"""Clean invalid fields before insert to prevent LinkValidationError."""
		self.clean_child_table_fields()
	
	def validate(self):
		"""Calculate total quantity from child table items and clean invalid fields."""
		# Skip mandatory validation during file upload - validation happens after Load Plans are created
		if self.flags.get("from_file_upload") or self.flags.get("ignore_mandatory"):
			pass
		else:
			# Normal validation - check mandatory fields
			if not self.load_reference_no:
				frappe.throw(_("Load Reference No is required"))
			if not self.dispatch_plan_date:
				frappe.throw(_("Dispatch Plan Date is required"))
			if not self.payment_plan_date:
				frappe.throw(_("Payment Plan Date is required"))
		
		self.clean_child_table_fields()
		self.calculate_total_quantity()
		self.update_status()
	
	def clean_child_table_fields(self):
		"""Remove invalid fields from child table rows that don't exist in the doctype."""
		if not self.table_tezh:
			return
		
		# Valid fields for Load Plan Item (from load_plan_item.json)
		valid_child_fields = {
			"model", "model_name", "model_type", "model_variant",
			"model_color", "group_color", "option", "quantity"
		}
		
		# Remove invalid fields directly from each row's __dict__
		# This is safer than rebuilding the entire table and preserves internal state
		for item in self.table_tezh:
			if not hasattr(item, '__dict__'):
				continue
			
			# Ensure flags attribute exists (Frappe requires this for Document objects)
			if not hasattr(item, 'flags'):
				# Initialize flags as a simple object if it doesn't exist
				item.flags = type('Flags', (), {})()
			
			# Ensure _table_fieldnames attribute exists (Frappe requires this for child table items)
			if not hasattr(item, '_table_fieldnames'):
				# Initialize _table_fieldnames as a set if it doesn't exist
				item._table_fieldnames = set(valid_child_fields)
				
			# Get list of fields to remove
			fields_to_remove = []
			for fieldname in item.__dict__.keys():
				# Skip Frappe internal fields and valid child fields
				if fieldname not in valid_child_fields and fieldname not in {
					"name", "idx", "parent", "parentfield", "parenttype", "doctype",
					"owner", "creation", "modified", "modified_by", "_meta", "_flags",
					"flags", "_table_fieldnames"  # Ensure internal Frappe attributes are never removed
				}:
					fields_to_remove.append(fieldname)
			
			# Remove invalid fields from __dict__
			for fieldname in fields_to_remove:
				try:
					del item.__dict__[fieldname]
				except (KeyError, TypeError):
					# Field might have been removed already or is protected
					pass
	
	def calculate_total_quantity(self):
		"""Sum up quantity from all Load Plan Item child table rows."""
		total_quantity = 0
		if self.table_tezh:
			for item in self.table_tezh:
				total_quantity += flt(item.quantity) or 0
		self.total_quantity = total_quantity
	
	def update_status(self):
		"""Update status based on dates, Load Dispatch, and Purchase Receipt."""
		if self.flags.get("from_file_upload") or self.flags.get("ignore_mandatory"):
			return
		
		# Skip if document doesn't have a name yet (new document)
		if not self.name:
			return
		
		try:
			new_status = get_load_plan_status(self.name)
			if new_status and self.status != new_status:
				self.status = new_status
		except Exception as e:
			frappe.log_error(
				message=f"Error updating status for Load Plan {self.name}: {str(e)}",
				title="Load Plan Status Update Error"
			)
	
	def get_dashboard_data(self):
		"""Return dashboard connections to show related Load Dispatch documents with their IDs."""
		# Get all Load Dispatch documents linked to this Load Plan
		load_dispatches = frappe.get_all(
			'Load Dispatch',
			filters={'load_reference_no': self.name},
			fields=['name', 'dispatch_no', 'status', 'docstatus'],
			order_by='creation desc'
		)
		
		# Format the document names/IDs for display
		dispatch_names = [ld.name for ld in load_dispatches]
		dispatch_count = len(load_dispatches)
		
		# Build dashboard data with transactions and custom data
		dashboard_data = {
			'transactions': [
				{
					'label': _('Related Documents'),
					'items': ['Load Dispatch']
				}
			]
		}
		
		# Add custom data to show Load Dispatch IDs
		if dispatch_count > 0:
			dashboard_data['load_dispatch_ids'] = dispatch_names
			dashboard_data['load_dispatch_count'] = dispatch_count
			dashboard_data['load_dispatch_details'] = [
				{
					'name': ld.name,
					'dispatch_no': ld.dispatch_no or ld.name,
					'status': ld.status,
					'docstatus': ld.docstatus
				}
				for ld in load_dispatches
			]
		
		return dashboard_data


def update_load_plan_status_from_document(doc, method=None):
	"""
	Update Load Plan status based on Purchase Receipt or Purchase Invoice submission.
	Called from hooks when Purchase Receipt or Purchase Invoice is submitted/cancelled.
	
	Purchase Receipt/Invoice -> Load Dispatch (via custom_load_dispatch) -> Load Plan (via load_reference_no)
	OR
	Purchase Receipt/Invoice -> Load Plan (via custom_load_reference_no, load_reference_to, or load_reference_no)
	
	Args:
		doc: Purchase Receipt or Purchase Invoice document
		method: Hook method name (optional)
	"""
	# For Purchase Invoice, only update status if update_stock is enabled
	if doc.doctype == "Purchase Invoice":
		update_stock = flt(doc.get("update_stock")) or 0
		if update_stock != 1:
			return
	
	load_reference_no = None
	
	# Method 1: Get Load Plan via Load Dispatch (PR/PI -> LD -> LP)
	load_dispatch_name = None
	
	# Check custom_load_dispatch field (primary link from PR/PI to Load Dispatch)
	if hasattr(doc, 'custom_load_dispatch') and doc.custom_load_dispatch:
		load_dispatch_name = doc.custom_load_dispatch
	elif frappe.db.has_column(doc.doctype, "custom_load_dispatch"):
		load_dispatch_name = frappe.db.get_value(doc.doctype, doc.name, "custom_load_dispatch")
	
	if load_dispatch_name and frappe.db.exists("Load Dispatch", load_dispatch_name):
		# Get Load Plan from Load Dispatch
		load_dispatch = frappe.get_doc("Load Dispatch", load_dispatch_name)
		load_reference_no = load_dispatch.get("load_reference_no")
	
	# Method 2: Fallback - Try direct link to Load Plan (if PR/PI has direct link)
	if not load_reference_no:
		if hasattr(doc, 'custom_load_reference_no') and doc.custom_load_reference_no:
			load_reference_no = doc.custom_load_reference_no
		elif hasattr(doc, 'load_reference_to') and doc.load_reference_to:
			load_reference_no = doc.load_reference_to
		elif hasattr(doc, 'load_reference_no') and doc.load_reference_no:
			load_reference_no = doc.load_reference_no
		elif frappe.db.has_column(doc.doctype, "custom_load_reference_no"):
			load_reference_no = frappe.db.get_value(doc.doctype, doc.name, "custom_load_reference_no")
	
	if not load_reference_no:
		# No Load Plan link found, skip status update
		# Log for debugging
		frappe.logger().warning(
			f"Load Plan status update skipped: No Load Plan link found for {doc.doctype} {doc.name}. "
			f"LD: {load_dispatch_name or 'N/A'}"
		)
		return
	
	# Update Load Plan status using centralized get_load_plan_status function
	if frappe.db.exists("Load Plan", load_reference_no):
		try:
			new_status = get_load_plan_status(load_reference_no)
			if new_status:
				current_status = frappe.db.get_value("Load Plan", load_reference_no, "status")
				if current_status != new_status:
					frappe.db.set_value("Load Plan", load_reference_no, "status", new_status)
					frappe.db.commit()
					# Log status change for debugging
					frappe.logger().info(
						f"Load Plan {load_reference_no} status updated: {current_status} -> {new_status} "
						f"(triggered by {doc.doctype} {doc.name}, LD: {load_dispatch_name or 'N/A'})"
					)
			else:
				# Log if status calculation returned None
				frappe.logger().warning(
					f"Load Plan {load_reference_no} status calculation returned None "
					f"(triggered by {doc.doctype} {doc.name}, LD: {load_dispatch_name or 'N/A'})"
				)
		except Exception as e:
			frappe.log_error(
				f"Error updating Load Plan status for {load_reference_no}: {str(e)}\n"
				f"PR/PI: {doc.doctype} {doc.name}, LD: {load_dispatch_name or 'N/A'}\n"
				f"Traceback: {frappe.get_traceback()}",
				"Load Plan Status Update Error"
			)


@frappe.whitelist()
def get_first_row_for_mandatory_fields(file_url):
	"""Quickly get the first row from the file to populate mandatory fields and child table immediately. Returns the first row with parent fields and child table data. This is called immediately when file is attached to prevent validation errors."""
	if not file_url:
		return None
	
	try:
		# Reuse the existing process_tabular_file but only get first row
		# This ensures consistency with the main processing logic
		all_rows = process_tabular_file(file_url)
		if all_rows and len(all_rows) > 0:
			first_row = all_rows[0]
			# Return all fields including parent and child fields
			result = {}
			# Parent fields
			if first_row.get("load_reference_no"):
				result["load_reference_no"] = first_row["load_reference_no"]
			if first_row.get("dispatch_plan_date"):
				result["dispatch_plan_date"] = first_row["dispatch_plan_date"]
			if first_row.get("payment_plan_date"):
				result["payment_plan_date"] = first_row["payment_plan_date"]
			# Child table fields
			child_fields = ["model", "model_name", "model_type", "model_variant", 
			               "model_color", "group_color", "option", "quantity"]
			result["child_row"] = {}
			for field in child_fields:
				if field in first_row:
					result["child_row"][field] = first_row[field]
			return result if result else None
	except Exception as e:
		# If processing fails, return None - full processing will handle the error
		frappe.log_error(f"Error getting first row: {str(e)}", "Load Plan First Row Error")
		return None
	
	return None


@frappe.whitelist()
def process_tabular_file(file_url):
	"""Read the attached file row-wise (CSV or Excel) and map it to Load Plan Item fields. Returns a list of dicts ready to be added to the child table."""
	if not file_url:
		frappe.throw(_("No file provided"))

	# Reusable header normalizer
	def _norm_header(h):
		if not h:
			return ""
		normalized = str(h).replace("\ufeff", "").replace("\u200b", "").strip()
		return " ".join(normalized.lower().split())

	# Header → fieldname mapping (parent fields included to pass back)
	column_mapping = {
		# Parent
		"load reference no": "load_reference_no",
		"dispatch plan date": "dispatch_plan_date",
		"payment plan date": "payment_plan_date",
		# Alternate (from Load Dispatch CSV)
		"hmsi load reference no": "load_reference_no",
		"dispatch date": "dispatch_plan_date",
		# Child
		"model": "model",
		"model name": "model_name",
		"type": "model_type",
		"variant": "model_variant",
		"color": "model_color",
		"colour": "model_color",
		"group color": "group_color",
		"group colour": "group_color",
		"group co": "group_color",
		"tax rate": "group_color",  # fallback
		"option": "option",
		"qty": "quantity",
		"quantity": "quantity",
	}

	required_headers = [
		"Load Reference No",
		"Dispatch Plan Date",
		"Payment Plan Date",
		"Model",
		"Model Name",
		"Type",
		"Variant",
		"Color",
		"Group Color",
		"Option",
		"Quantity",
	]
	optional_headers = []

	# Try Excel first (works even if extension is .csv but content is xlsx)
	data = None
	try:
		data = read_xlsx_file_from_attached_file(file_url=file_url)
	except Exception:
		data = None

	if data:
		result = _process_tabular_rows(data, column_mapping, required_headers, optional_headers, _norm_header)
		if not result:
			frappe.log_error(
				message=f"Load Plan import: no rows built from Excel. Headers={data[0] if data else 'N/A'}",
				title="Load Plan Import Empty (Excel)"
			)
		return result

	# CSV path (fallback to previous logic)
	result = _process_load_plan_csv(file_url, column_mapping, required_headers, optional_headers)
	if not result:
		frappe.log_error(
			message="Load Plan import: no rows built from CSV after fallback.",
			title="Load Plan Import Empty (CSV)"
		)
	return result


def _process_tabular_rows(data, column_mapping, required_headers, optional_headers, norm_func):
	if not data or len(data) == 0:
		return []

	headers = [(cell or "").strip() for cell in data[0]]
	norm_csv_headers = {norm_func(h): h for h in headers if h}
	frappe.log_error(
		message=f"Load Plan import: headers detected={headers}",
		title="Load Plan Import Debug"
	)

	# Validate headers (accept either primary set or dispatch-style set)
	def _missing(headers, norm_headers):
		miss = []
		for req in headers:
			if norm_func(req) not in norm_headers:
				miss.append(req)
		return miss

	missing_headers = _missing(required_headers, norm_csv_headers)
	missing_optional = _missing(optional_headers, norm_csv_headers)

	# Fallback: accept dispatch CSV headers (subset) when primary missing
	dispatch_min_headers = [
		"HMSI Load Reference No",
		"Dispatch Date",
		"Model",
		"Model Name",
		"Colour",
		"Variant",
		"Qty",
	]
	dispatch_missing = _missing(dispatch_min_headers, norm_csv_headers)
	if missing_headers and not dispatch_missing:
		missing_headers = []

	if missing_headers:
		# If we still have at least one mapped column, just warn and continue
		has_any_mapped = any(norm_func(col) in norm_csv_headers for col in column_mapping.keys())
		if has_any_mapped:
			frappe.msgprint(
				_("Missing headers (processing will continue):<br>{0}").format(
					"<br>".join([f"• {h}" for h in missing_headers])
				),
				indicator="orange",
				alert=True,
			)
		else:
			found_headers_str = "\n".join([f"• {h}" for h in headers[:20]])
			if len(headers) > 20:
				found_headers_str += f"\n... and {len(headers) - 20} more"
			frappe.throw(
				_("Header Validation Failed!\n\n"
				  "<b>Missing Headers:</b>\n{0}\n\n"
				  "<b>Expected Headers:</b>\n{1}\n\n"
				  "<b>Found Headers:</b>\n{2}").format(
					"\n".join([f"• {h}" for h in missing_headers]),
					"\n".join([f"• {h}" for h in required_headers + optional_headers]),
					found_headers_str
				),
				title=_("Invalid Headers")
			)
	elif missing_optional:
		frappe.msgprint(
			_("Optional headers missing (processing will continue):<br>{0}").format(
				"<br>".join([f"• {h}" for h in missing_optional])
			),
			indicator="orange",
			alert=True,
		)

	rows = []
	for row in data[1:]:
		row_data = {}
		for csv_col, fieldname in column_mapping.items():
			actual_col = norm_csv_headers.get(norm_func(csv_col))
			if not actual_col:
				continue

			try:
				col_idx = headers.index(actual_col)
			except ValueError:
				continue

			raw_value = row[col_idx] if col_idx < len(row) else ""
			value = raw_value.strip() if isinstance(raw_value, str) else raw_value

			if fieldname in ["dispatch_plan_date", "payment_plan_date"]:
				if value:
					try:
						from frappe.utils import getdate
						row_data[fieldname] = getdate(value)
					except Exception:
						row_data[fieldname] = value
				else:
					row_data[fieldname] = None
			elif fieldname == "quantity":
				if value or value == 0:
					try:
						row_data[fieldname] = int(float(value))
					except Exception:
						row_data[fieldname] = value
				else:
					row_data[fieldname] = None
			else:
				row_data[fieldname] = value

		rows.append(row_data)

	child_fields = {
		"model",
		"model_name",
		"model_type",
		"model_variant",
		"model_color",
		"group_color",
		"option",
		"quantity",
	}

	def _has_child_fields(row):
		return any(k in child_fields for k in row.keys())

	if (not rows) or all(not _has_child_fields(r) for r in rows):
		frappe.log_error(
			message=f"Load Plan import: no rows built. First data rows={data[1:6]}",
			title="Load Plan Import Debug (no rows)"
		)
		# Fallback: positional mapping using expected order
		expected_order = [
			"load reference no",
			"dispatch plan date",
			"payment plan date",
			"model",
			"model name",
			"type",
			"variant",
			"color",
			"group color",
			"option",
			"quantity",
		]
		for row in data[1:]:
			row_data = {}
			for idx, key in enumerate(expected_order):
				if idx >= len(row):
					break
				raw_value = row[idx]
				value = raw_value.strip() if isinstance(raw_value, str) else raw_value
				fieldname = column_mapping.get(key, key)
				if fieldname in ["dispatch_plan_date", "payment_plan_date"]:
					if value:
						try:
							from frappe.utils import getdate
							row_data[fieldname] = getdate(value)
						except Exception:
							row_data[fieldname] = value
					else:
						row_data[fieldname] = None
				elif fieldname == "quantity":
					if value or value == 0:
						try:
							row_data[fieldname] = int(float(value))
						except Exception:
							row_data[fieldname] = value
					else:
						row_data[fieldname] = None
				else:
					row_data[fieldname] = value
			rows.append(row_data)

	# Filter out invalid fields that don't exist in Load Plan Item doctype
	valid_child_fields = {
		"model", "model_name", "model_type", "model_variant",
		"model_color", "group_color", "option", "quantity",
		"load_reference_no", "dispatch_plan_date", "payment_plan_date"
	}
	
	# Remove invalid fields from each row (like item_code)
	filtered_rows = []
	for row in rows:
		filtered_row = {k: v for k, v in row.items() if k in valid_child_fields}
		filtered_rows.append(filtered_row)
	
	return filtered_rows


def _process_load_plan_csv(file_url, column_mapping, required_headers, optional_headers):
	"""CSV-only processing reused by process_tabular_file."""
	if file_url.startswith("/files/"):
		file_name = file_url.split("/files/")[-1]
		file_path = frappe.get_site_path("public", "files", file_name)
	else:
		file_path = frappe.get_site_path("public", file_url.lstrip("/"))

	if not os.path.exists(file_path):
		frappe.throw(_("File not found: {0}").format(file_url))

	# Try multiple encodings
	encodings = ["utf-8-sig", "utf-8", "utf-16-le", "utf-16-be", "latin-1", "cp1252"]
	csvfile = None
	for encoding in encodings:
		try:
			csvfile = open(file_path, "r", encoding=encoding)
			sample = csvfile.read(1024)
			csvfile.seek(0)
			break
		except (UnicodeDecodeError, UnicodeError):
			if csvfile:
				csvfile.close()
			csvfile = None
			continue

	if not csvfile:
		frappe.throw(_("Unable to read the file. Please ensure it is saved as CSV."))

	try:
		def _norm_header(h):
			if not h:
				return ""
			normalized = str(h).replace("\ufeff", "").replace("\u200b", "").strip()
			return " ".join(normalized.lower().split())

		# Detect delimiter
		try:
			delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
		except Exception:
			delimiter = ","

		# Build reader and headers
		csvfile.seek(0)
		reader = csv.DictReader(csvfile, delimiter=delimiter)
		reader_headers = [h.strip() if h else "" for h in (reader.fieldnames or [])]
		csv_headers = reader_headers
		norm_csv_headers = {_norm_header(h): h for h in csv_headers if h}

		if not csv_headers:
			frappe.throw(_("CSV file appears to have no headers. Please ensure the first row contains column headers."))

		# Check missing headers
		missing_headers = []
		for req in required_headers:
			if _norm_header(req) not in norm_csv_headers:
				missing_headers.append(req)
		missing_optional = []
		for opt in optional_headers:
			if _norm_header(opt) not in norm_csv_headers:
				missing_optional.append(opt)

		if missing_headers:
			has_any_mapped = any(_norm_header(col) in norm_csv_headers for col in column_mapping.keys())
			if has_any_mapped:
				frappe.msgprint(
					_("Missing headers (processing will continue):<br>{0}").format(
						"<br>".join([f"• {h}" for h in missing_headers])
					),
					indicator="orange",
					alert=True,
				)
			else:
				# Don't block; just warn and continue
				frappe.msgprint(
					_("Missing headers (processing will continue):<br>{0}").format(
						"<br>".join([f"• {h}" for h in missing_headers])
					),
					indicator="orange",
					alert=True,
				)
		elif missing_optional:
			frappe.msgprint(
				_("Optional headers missing (processing will continue):<br>{0}").format(
					"<br>".join([f"• {h}" for h in missing_optional])
				),
				indicator="orange",
				alert=True,
			)

		rows = []
		for csv_row in reader:
			row_data = {}
			for csv_col, fieldname in column_mapping.items():
				actual_col = norm_csv_headers.get(_norm_header(csv_col))
				if not actual_col:
					continue

				raw_value = csv_row.get(actual_col, "")
				value = raw_value.strip() if isinstance(raw_value, str) else raw_value

				if fieldname in ["dispatch_plan_date", "payment_plan_date"]:
					if value:
						try:
							from frappe.utils import getdate
							row_data[fieldname] = getdate(value)
						except Exception:
							row_data[fieldname] = value
					else:
						row_data[fieldname] = None
				elif fieldname == "quantity":
					if value or value == 0:
						try:
							row_data[fieldname] = int(float(value))
						except Exception:
							row_data[fieldname] = value
					else:
						row_data[fieldname] = None
				else:
					row_data[fieldname] = value

			rows.append(row_data)

		child_fields = {
			"model",
			"model_name",
			"model_type",
			"model_variant",
			"model_color",
			"group_color",
			"option",
			"quantity",
		}

		def _has_child_fields(row):
			return any(k in child_fields for k in row.keys())

		# Fallback positional mapping if still empty or no child fields populated
		if (not rows) or all(not _has_child_fields(r) for r in rows):
			try:
				csvfile.seek(0)
				raw_reader = csv.reader(csvfile, delimiter=delimiter)
				raw_headers = next(raw_reader, [])
				expected_order = [
					"load reference no",
					"dispatch plan date",
					"payment plan date",
					"model",
					"model name",
					"type",
					"variant",
					"color",
					"group color",
					"option",
					"quantity",
				]
				for raw_row in raw_reader:
					row_data = {}
					for idx, key in enumerate(expected_order):
						if idx >= len(raw_row):
							break
						raw_value = raw_row[idx]
						value = raw_value.strip() if isinstance(raw_value, str) else raw_value
						fieldname = column_mapping.get(key, key)
						if fieldname in ["dispatch_plan_date", "payment_plan_date"]:
							if value:
								try:
									from frappe.utils import getdate
									row_data[fieldname] = getdate(value)
								except Exception:
									row_data[fieldname] = value
							else:
								row_data[fieldname] = None
						elif fieldname == "quantity":
							if value or value == 0:
								try:
									row_data[fieldname] = int(float(value))
								except Exception:
									row_data[fieldname] = value
							else:
								row_data[fieldname] = None
						else:
							row_data[fieldname] = value
					rows.append(row_data)
			except Exception:
				pass

		# Filter out invalid fields that don't exist in Load Plan Item doctype
		valid_child_fields = {
			"model", "model_name", "model_type", "model_variant",
			"model_color", "group_color", "option", "quantity",
			"load_reference_no", "dispatch_plan_date", "payment_plan_date"
		}
		
		# Remove invalid fields from each row (like item_code)
		filtered_rows = []
		for row in rows:
			filtered_row = {k: v for k, v in row.items() if k in valid_child_fields}
			filtered_rows.append(filtered_row)
		
		return filtered_rows
	finally:
		if csvfile:
			csvfile.close()


@frappe.whitelist()
def create_load_plans_from_file(file_url, create_multiple=True):
	"""Process file and create Load Plan documents. If create_multiple=True and file contains multiple load_reference_no values, creates separate Load Plan documents for each unique load_reference_no. Args: file_url: URL of the attached file, create_multiple: If True, create separate Load Plans for each load_reference_no. Returns: dict with created_load_plans list and summary."""
	if not file_url:
		frappe.throw(_("No file provided"))
	
	# Process the file to get all rows
	all_rows = process_tabular_file(file_url)
	
	if not all_rows:
		frappe.throw(_("No data found in the file"))
	
	# Group rows by load_reference_no
	grouped_data = {}
	for idx, row in enumerate(all_rows):
		load_ref = row.get("load_reference_no")
		if not load_ref:
			# Skip rows without load_reference_no
			continue
		
		load_ref = str(load_ref).strip()
		if load_ref not in grouped_data:
			grouped_data[load_ref] = {
				"load_reference_no": load_ref,
				"dispatch_plan_date": row.get("dispatch_plan_date"),
				"payment_plan_date": row.get("payment_plan_date"),
				"rows": []
			}
		
		# Add child table row (exclude parent fields)
		# Extract all child fields from the row - ALWAYS include all child fields
		child_fields = ["model", "model_name", "model_type", "model_variant", 
		               "model_color", "group_color", "option", "quantity"]
		child_row = {}
		for field in child_fields:
			# Always include field - use value from row if exists, otherwise None
			child_row[field] = row.get(field)
		
		# ALWAYS append child_row for every row with load_reference_no
		grouped_data[load_ref]["rows"].append(child_row)
	
	if not grouped_data:
		frappe.throw(_("No valid Load Reference Numbers found in the file"))
	
	# Determine if we should create multiple Load Plans
	unique_load_refs = list(grouped_data.keys())
	should_create_multiple = create_multiple and len(unique_load_refs) > 1
	
	created_load_plans = []
	errors = []
	
	if should_create_multiple:
		# Create multiple Load Plans
		for load_ref, data in grouped_data.items():
			try:
				load_plan = _create_single_load_plan(
					load_ref,
					data.get("dispatch_plan_date"),
					data.get("payment_plan_date"),
					data.get("rows", []),
					file_url
				)
				created_load_plans.append({
					"name": load_plan.name,
					"load_reference_no": load_ref,
					"rows_count": len(data.get("rows", [])),
					"total_quantity": load_plan.total_quantity
				})
			except Exception as e:
				error_msg = str(e)
				errors.append({
					"load_reference_no": load_ref,
					"error": error_msg
				})
				frappe.log_error(
					message=f"Error creating Load Plan {load_ref}: {error_msg}",
					title="Load Plan Creation Error"
				)
	else:
		# Create single Load Plan (use first load_reference_no or current form)
		first_load_ref = unique_load_refs[0]
		data = grouped_data[first_load_ref]
		try:
			load_plan = _create_single_load_plan(
				first_load_ref,
				data.get("dispatch_plan_date"),
				data.get("payment_plan_date"),
				data.get("rows", []),
				file_url
			)
			created_load_plans.append({
				"name": load_plan.name,
				"load_reference_no": first_load_ref,
				"rows_count": len(data.get("rows", [])),
				"total_quantity": load_plan.total_quantity
			})
		except Exception as e:
			error_msg = str(e)
			errors.append({
				"load_reference_no": first_load_ref,
				"error": error_msg
			})
			frappe.log_error(
				message=f"Error creating Load Plan {first_load_ref}: {error_msg}",
				title="Load Plan Creation Error"
			)
	
	return {
		"created_load_plans": created_load_plans,
		"errors": errors,
		"total_created": len(created_load_plans),
		"total_errors": len(errors),
		"unique_load_refs": unique_load_refs,
		"multiple_created": should_create_multiple
	}


def _create_single_load_plan(load_reference_no, dispatch_plan_date, payment_plan_date, child_rows, file_url):
	"""Create a single Load Plan document with the provided data. Args: load_reference_no: Load Reference Number, dispatch_plan_date: Dispatch Plan Date, payment_plan_date: Payment Plan Date, child_rows: List of child table row dictionaries, file_url: File URL for attachment. Returns: Created LoadPlan document."""
	# Filter to only include valid child fieldnames - never filter by values
	valid_child_fields = {
		"model", "model_name", "model_type", "model_variant",
		"model_color", "group_color", "option", "quantity"
	}
	
	# Build child table rows - filter ONLY by fieldname, append ALL rows
	child_table_rows = []
	for row_data in child_rows:
		filtered_row = {k: v for k, v in row_data.items() if k in valid_child_fields}
		child_table_rows.append(filtered_row)
	
	# Check if Load Plan already exists
	if frappe.db.exists("Load Plan", load_reference_no):
		# Update existing Load Plan - fully rebuild to handle pre-created documents
		load_plan = frappe.get_doc("Load Plan", load_reference_no)
		load_plan.dispatch_plan_date = dispatch_plan_date or load_plan.dispatch_plan_date
		load_plan.payment_plan_date = payment_plan_date or load_plan.payment_plan_date
		load_plan.attach_load_plan = file_url
		# Clear ALL existing child table rows completely
		load_plan.table_tezh = []
	else:
		# Create new Load Plan
		load_plan = frappe.get_doc({
			"doctype": "Load Plan",
			"load_reference_no": load_reference_no,
			"dispatch_plan_date": dispatch_plan_date,
			"payment_plan_date": payment_plan_date,
			"attach_load_plan": file_url
		})
	
	# Add all rows to the child table - ALWAYS append ALL rows
	for filtered_row in child_table_rows:
		load_plan.append("table_tezh", filtered_row)
	
	# Set flags to bypass mandatory validation during file upload
	load_plan.flags.from_file_upload = True
	load_plan.flags.ignore_mandatory = True
	
	# Save the document
	load_plan.save(ignore_permissions=True)
	frappe.db.commit()
	
	# Submit the Load Plan if it's in Draft state
	# Reload the document to ensure it's in the correct state
	load_plan.reload()
	
	if load_plan.docstatus == 0:
		try:
			# Keep ignore_mandatory flag during submit to ensure it goes through
			# All mandatory fields are already set, so this is safe
			load_plan.flags.ignore_mandatory = True
			load_plan.flags.ignore_permissions = True
			load_plan.submit()
			frappe.db.commit()
		except Exception as e:
			# Log error but don't fail the entire process
			frappe.log_error(
				message=f"Error submitting Load Plan {load_reference_no}: {str(e)}\nTraceback: {frappe.get_traceback()}",
				title="Load Plan Submit Error"
			)
			# Document remains in Draft state if submit fails
	
	return load_plan


@frappe.whitelist()
def get_load_plan_status(load_plan_name):
	"""Get the status of a Load Plan based on dates, Load Dispatch, and Purchase Receipt.
	
	Logic:
	1. If Purchase Receipt exists for Load Dispatches linked to this Load Plan: Status = "Received"
	2. If Load Dispatch exists for this Load Plan: Status = "In-Transit"
	3. If dispatch_plan_date exists (any date): Status = "Planned"
	4. Otherwise: Default to "Planned"
	
	Args:
		load_plan_name: Name of the Load Plan document
		
	Returns:
		str: Status of the Load Plan
	"""
	from frappe.utils import getdate, today
	
	if not load_plan_name:
		return "Planned"
	
	# Get Load Plan document
	if not frappe.db.exists("Load Plan", load_plan_name):
		return "Planned"
	
	load_plan = frappe.get_doc("Load Plan", load_plan_name)
	
	# Priority 1: Check if Purchase Receipt exists for Load Dispatches linked to this Load Plan
	# First, get all Load Dispatches for this Load Plan
	load_dispatches = frappe.get_all(
		'Load Dispatch',
		filters={'load_reference_no': load_plan_name},
		fields=['name'],
		limit_page_length=1000
	)
	
	# Check if any Purchase Receipt exists for these Load Dispatches
	# Purchase Receipt can link to Load Plan via custom_load_reference_no, load_reference_to, or load_reference_no
	# Or it might link to Load Dispatch directly - need to check both
	
	# Check PR linked to Load Plan
	pr_filters = {"docstatus": 1}
	pr_found = False
	
	# Check custom_load_reference_no
	if frappe.db.has_column("Purchase Receipt", "custom_load_reference_no"):
		prs = frappe.get_all(
			"Purchase Receipt",
			filters={**pr_filters, "custom_load_reference_no": load_plan_name},
			limit=1
		)
		if prs:
			pr_found = True
	
	# Check load_reference_to
	if not pr_found and frappe.db.has_column("Purchase Receipt", "load_reference_to"):
		prs = frappe.get_all(
			"Purchase Receipt",
			filters={**pr_filters, "load_reference_to": load_plan_name},
			limit=1
		)
		if prs:
			pr_found = True
	
	# Check load_reference_no
	if not pr_found and frappe.db.has_column("Purchase Receipt", "load_reference_no"):
		prs = frappe.get_all(
			"Purchase Receipt",
			filters={**pr_filters, "load_reference_no": load_plan_name},
			limit=1
		)
		if prs:
			pr_found = True
	
	# Check if PR links to Load Dispatch directly via custom_load_dispatch
	if not pr_found and load_dispatches:
		ld_names = [ld.name for ld in load_dispatches]
		
		# Check custom_load_dispatch field (primary link from PR to Load Dispatch)
		# Use exact match for each Load Dispatch name
		for ld_name in ld_names:
			if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
				prs = frappe.get_all(
					"Purchase Receipt",
					filters={**pr_filters, "custom_load_dispatch": ld_name},
					limit=1
				)
				if prs:
					pr_found = True
					break
		
		# Also check Purchase Invoice with update_stock
		if not pr_found:
			for ld_name in ld_names:
				if frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
					pi_filters = {**pr_filters, "update_stock": 1}
					pis = frappe.get_all(
						"Purchase Invoice",
						filters={**pi_filters, "custom_load_dispatch": ld_name},
						limit=1
					)
					if pis:
						pr_found = True
						break
	
	if pr_found:
		return "Received"
	
	# Priority 2: If Load Dispatch exists but no PR - return "In-Transit"
	if load_dispatches:
		return "In-Transit"
	
	# Priority 3: If dispatch_plan_date exists, return "Planned"
	dispatch_plan_date = load_plan.get("dispatch_plan_date")
	if dispatch_plan_date:
		return "Planned"
	
	# Default: Planned
	return "Planned"


@frappe.whitelist()
def batch_update_load_plan_status(load_plan_names):
	"""Batch update status for multiple Load Plans.
	
	Args:
		load_plan_names: List of Load Plan names
		
	Returns:
		dict: Summary of updates with 'updated' count
	"""
	if not load_plan_names:
		return {"updated": 0}
	
	updated_count = 0
	
	for load_plan_name in load_plan_names:
		try:
			# Get calculated status
			new_status = get_load_plan_status(load_plan_name)
			
			# Update the status field if it's different
			current_status = frappe.db.get_value("Load Plan", load_plan_name, "status")
			
			if current_status != new_status:
				frappe.db.set_value("Load Plan", load_plan_name, "status", new_status)
				updated_count += 1
		except Exception as e:
			frappe.log_error(
				message=f"Error updating status for Load Plan {load_plan_name}: {str(e)}",
				title="Batch Update Load Plan Status Error"
			)
			continue
	
	if updated_count > 0:
		frappe.db.commit()
	
	return {"updated": updated_count}