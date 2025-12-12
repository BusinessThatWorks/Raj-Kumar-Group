import csv
import os

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file


class LoadPlan(Document):
	def validate(self):
		"""Calculate total quantity from child table items."""
		self.calculate_total_quantity()
	
	def calculate_total_quantity(self):
		"""Sum up quantity from all Load Plan Item child table rows."""
		total_quantity = 0
		if self.table_tezh:
			for item in self.table_tezh:
				total_quantity += flt(item.quantity) or 0
		self.total_quantity = total_quantity


def update_load_plan_status_from_document(doc, method=None):
	"""
	Update Load Plan status based on Purchase Receipt or Purchase Invoice submission.
	Called from hooks when Purchase Receipt or Purchase Invoice is submitted.
	
	Logic:
	- Get load_reference_no from the submitted document (custom_load_reference_no or load_reference_to)
	- Find all submitted Purchase Receipt/Invoice documents with that load_reference_no
	- Sum total_quantity from those documents
	- Compare with Load Plan's total_quantity:
	  - If total_quantity >= Load Plan total_quantity: 'Dispatched'
	  - If total_quantity < Load Plan total_quantity and > 0: 'Partial Dispatched'
	  - Otherwise: 'In-Transit'
	
	Args:
		doc: Purchase Receipt or Purchase Invoice document
		method: Hook method name (optional)
	"""
	# Get load_reference_no from the document
	load_reference_no = None
	
	# Check for different possible field names
	if hasattr(doc, 'custom_load_reference_no') and doc.custom_load_reference_no:
		load_reference_no = doc.custom_load_reference_no
	elif hasattr(doc, 'load_reference_to') and doc.load_reference_to:
		load_reference_no = doc.load_reference_to
	elif hasattr(doc, 'load_reference_no') and doc.load_reference_no:
		load_reference_no = doc.load_reference_no
	
	if not load_reference_no:
		# No load reference found, skip status update
		return
	
	# For Purchase Invoice, only update status if update_stock is enabled
	if doc.doctype == "Purchase Invoice":
		update_stock = flt(doc.get("update_stock")) or 0
		if update_stock != 1:
			# Purchase Invoice with update_stock disabled, skip status update
			return
	
	# Check if Load Plan exists
	if not frappe.db.exists("Load Plan", load_reference_no):
		return
	
	# Get Load Plan total_quantity
	load_plan = frappe.get_doc("Load Plan", load_reference_no)
	total_load_quantity = flt(load_plan.total_quantity) or 0
	
	if total_load_quantity == 0:
		# No quantity in Load Plan, skip update
		return
	
	# Get doctype name
	doctype = doc.doctype
	
	# Calculate total quantity from all submitted Purchase Receipt/Invoice documents
	# with the same load_reference_no
	total_quantity = 0
	
	# Check both Purchase Receipt and Purchase Invoice
	for doc_type in ["Purchase Receipt", "Purchase Invoice"]:
		# Get all submitted documents matching the load_reference_no
		# Try different possible field names
		all_doc_names = set()
		
		# Build base filters
		base_filters = {"docstatus": 1}
		
		# For Purchase Invoice, only include documents with update_stock = 1
		if doc_type == "Purchase Invoice":
			base_filters["update_stock"] = 1
		
		# Check custom_load_reference_no
		if frappe.db.has_column(doc_type, "custom_load_reference_no"):
			filters = base_filters.copy()
			filters["custom_load_reference_no"] = load_reference_no
			docs1 = frappe.get_all(
				doc_type,
				filters=filters,
				fields=["name"]
			)
			all_doc_names.update([d.name for d in docs1])
		
		# Check load_reference_to
		if frappe.db.has_column(doc_type, "load_reference_to"):
			filters = base_filters.copy()
			filters["load_reference_to"] = load_reference_no
			docs2 = frappe.get_all(
				doc_type,
				filters=filters,
				fields=["name"]
			)
			all_doc_names.update([d.name for d in docs2])
		
		# Check load_reference_no
		if frappe.db.has_column(doc_type, "load_reference_no"):
			filters = base_filters.copy()
			filters["load_reference_no"] = load_reference_no
			docs3 = frappe.get_all(
				doc_type,
				filters=filters,
				fields=["name"]
			)
			all_doc_names.update([d.name for d in docs3])
		
		# Get quantities from all matching documents
		for doc_name in all_doc_names:
			doc_obj = frappe.get_doc(doc_type, doc_name)
			
			# For Purchase Invoice, double-check update_stock (in case it was changed after submission)
			if doc_type == "Purchase Invoice":
				update_stock = flt(doc_obj.get("update_stock")) or 0
				if update_stock != 1:
					continue
			
			# Try to get total_qty from the document
			doc_qty = flt(doc_obj.get("total_qty")) or 0
			
			# If total_qty is not available or zero, sum from items
			if doc_qty == 0 and hasattr(doc_obj, "items"):
				doc_qty = sum(flt(item.get("qty") or item.get("stock_qty") or 0) for item in doc_obj.items)
			
			total_quantity += doc_qty
	
	# Determine status based on comparison
	if total_quantity >= total_load_quantity:
		new_status = "Dispatched"
	elif total_quantity > 0:
		new_status = "Partial Dispatched"
	else:
		new_status = "In-Transit"
	
	# Update Load Plan status
	if load_plan.status != new_status:
		load_plan.status = new_status
		load_plan.save(ignore_permissions=True)
		frappe.db.commit()


@frappe.whitelist()
def process_tabular_file(file_url, current_load_reference_no=None):
	"""
	Read the attached file row-wise (CSV or Excel) and map it to Load Plan Item fields.
	Returns a list of dicts ready to be added to the child table.
	"""
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
		# Child (vehicle_model_variant now optional)
		"vehicle model variant": "vehicle_model_variant",
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
		return _filter_rows_for_primary_ref(result, current_load_reference_no, file_url)

	# CSV path (fallback to previous logic)
	result = _process_load_plan_csv(file_url, column_mapping, required_headers, optional_headers)
	if not result:
		frappe.log_error(
			message="Load Plan import: no rows built from CSV after fallback.",
			title="Load Plan Import Empty (CSV)"
		)
	else:
		# If multiple load_reference_no values are present, auto-create Load Plans for other refs
		return _filter_rows_for_primary_ref(result, current_load_reference_no, file_url)

	return result


def _enqueue_load_plan_creation(rows):
	"""Enqueue background creation of Load Plan docs grouped by load_reference_no."""
	from frappe.utils.background_jobs import enqueue

	unique_refs = {r.get("load_reference_no") for r in rows if r.get("load_reference_no")}
	# Only act when there are multiple distinct load reference numbers
	if not unique_refs or len(unique_refs) < 2:
		return

	enqueue(
		_create_load_plans_from_rows,
		queue="default",
		rows=rows,
		now=False,
	)


def _create_load_plans_from_rows(rows, file_url=None, exclude_reference=None):
	"""Create Load Plan documents grouped by load_reference_no."""
	if not rows:
		return

	created = []
	skipped = []

	# Group rows by load_reference_no
	grouped = {}
	for row in rows:
		ref = (row.get("load_reference_no") or "").strip()
		if not ref:
			continue
		if exclude_reference and ref == exclude_reference:
			continue
		grouped.setdefault(ref, []).append(row)

	for ref, items in grouped.items():
		# Skip if Load Plan already exists
		if frappe.db.exists("Load Plan", ref):
			skipped.append(ref)
			continue

		try:
			doc = frappe.new_doc("Load Plan")
			doc.load_reference_no = ref
			# Attach the same file used for import if the field is mandatory
			if file_url:
				doc.attach_load_plan = file_url

			# Use first row for parent dates when present
			first = items[0] if items else {}
			if first.get("dispatch_plan_date"):
				doc.dispatch_plan_date = first["dispatch_plan_date"]
			if first.get("payment_plan_date"):
				doc.payment_plan_date = first["payment_plan_date"]

			# Add child rows
			for item in items:
				child = doc.append("table_tezh", {})
				for key, val in item.items():
					child.set(key, val)

			# Compute totals and insert
			doc.calculate_total_quantity()
			doc.insert(ignore_permissions=True, ignore_mandatory=True)
			created.append(ref)
		except Exception as exc:
			frappe.log_error(
				message=f"Auto Load Plan creation failed for {ref}: {exc}",
				title="Load Plan Auto-Creation",
			)

	if created or skipped:
		frappe.logger().info(
			{
				"event": "load_plan_auto_creation",
				"created": created,
				"skipped_existing": skipped,
				"file_url": file_url,
			}
		)


def _filter_rows_for_primary_ref(rows, current_load_reference_no, file_url=None):
	"""Return only rows matching the primary reference; create others automatically."""
	if not rows:
		return []

	# Determine primary reference: current form value, else first row's reference
	primary_ref = (current_load_reference_no or (rows[0].get("load_reference_no") if rows else "")) or ""
	primary_ref = primary_ref.strip()

	# Create other Load Plans (excluding primary)
	_create_load_plans_from_rows(rows, file_url=file_url, exclude_reference=primary_ref)

	# Filter rows for primary
	if primary_ref:
		filtered = [r for r in rows if (r.get("load_reference_no") or "").strip() == primary_ref]
		if filtered:
			return filtered

	# Fallback: return all rows if filtering yielded nothing (to avoid empty UI)
	return rows


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
		if not any(row):
			continue

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

			if value or value == 0:
				if fieldname in ["dispatch_plan_date", "payment_plan_date"]:
					try:
						from frappe.utils import getdate
						row_data[fieldname] = getdate(value)
					except Exception:
						row_data[fieldname] = value
				elif fieldname == "quantity":
					try:
						row_data[fieldname] = int(float(value)) if value or value == 0 else None
					except Exception:
						row_data[fieldname] = value
				else:
					row_data[fieldname] = value

		if row_data:
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
			if not any(row):
				continue
			row_data = {}
			for idx, key in enumerate(expected_order):
				if idx >= len(row):
					break
				raw_value = row[idx]
				value = raw_value.strip() if isinstance(raw_value, str) else raw_value
				fieldname = column_mapping.get(key, key)
				if value or value == 0:
					if fieldname in ["dispatch_plan_date", "payment_plan_date"]:
						try:
							from frappe.utils import getdate
							row_data[fieldname] = getdate(value)
						except Exception:
							row_data[fieldname] = value
					elif fieldname == "quantity":
						try:
							row_data[fieldname] = int(float(value)) if value or value == 0 else None
						except Exception:
							row_data[fieldname] = value
					else:
						row_data[fieldname] = value
			if row_data:
				rows.append(row_data)

	return rows


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
			if not any(csv_row.values()):
				continue

			row_data = {}
			for csv_col, fieldname in column_mapping.items():
				actual_col = norm_csv_headers.get(_norm_header(csv_col))
				if not actual_col:
					continue

				raw_value = csv_row.get(actual_col, "")
				value = raw_value.strip() if isinstance(raw_value, str) else raw_value

				if value or value == 0:
					if fieldname in ["dispatch_plan_date", "payment_plan_date"]:
						try:
							from frappe.utils import getdate
							row_data[fieldname] = getdate(value)
						except Exception:
							row_data[fieldname] = value
					elif fieldname == "quantity":
						try:
							row_data[fieldname] = int(float(value)) if value or value == 0 else None
						except Exception:
							row_data[fieldname] = value
					else:
						row_data[fieldname] = value

			if row_data:
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
					if not any(raw_row):
						continue
					row_data = {}
					for idx, key in enumerate(expected_order):
						if idx >= len(raw_row):
							break
						raw_value = raw_row[idx]
						value = raw_value.strip() if isinstance(raw_value, str) else raw_value
						fieldname = column_mapping.get(key, key)
						if value or value == 0:
							if fieldname in ["dispatch_plan_date", "payment_plan_date"]:
								try:
									from frappe.utils import getdate
									row_data[fieldname] = getdate(value)
								except Exception:
									row_data[fieldname] = value
							elif fieldname == "quantity":
								try:
									row_data[fieldname] = int(float(value)) if value or value == 0 else None
								except Exception:
									row_data[fieldname] = value
							else:
								row_data[fieldname] = value
					if row_data:
						rows.append(row_data)
			except Exception:
				pass

		return rows
	finally:
		if csvfile:
			csvfile.close()