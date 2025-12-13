import frappe
import csv
import os
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt

# Canonical list of Item custom fieldnames that must be populated.
ITEM_CUSTOM_FIELDS = [
	"net_dealer_price",
	"ex_showroom_price",
	"dealer_billing_price",
	"credit_of_gst",
	"cgst_amount",
	"sgst_amount",
	"igst_amount",
	"gstin",
]


class LoadDispatch(Document):
	def before_save(self):
		"""Populate item_code from mtoc before saving and create Items if needed."""
		# Populate item_code from mtoc for all items on save
		if self.items:
			self.set_item_code()
			self.create_serial_nos()
			self.set_fields_value()
			self.update_item_pricing_fields()
			self.set_item_group()
			self.set_supplier()
	def validate(self):
		"""Ensure linked Load Plan exists and is submitted before creating Load Dispatch."""
		# Also populate item_code in validate as backup
		if self.items:
			self.set_item_code()
			self.create_serial_nos()
			self.set_fields_value()
			self.update_item_pricing_fields()
			self.set_item_group()
		
		# Prevent changing load_reference_no if document has imported items (works for both new and existing documents)
		has_imported_items = False
		if self.items:
			for item in self.items:
				if item.frame_no and str(item.frame_no).strip():
					has_imported_items = True
					break
		
		# Check if load_reference_no is being changed
		if has_imported_items:
			if self.is_new():
				# For new documents with imported items, check if load_reference_no was set from CSV
				# We track this via a custom property set during CSV import
				if hasattr(self, '_load_reference_no_from_csv') and self._load_reference_no_from_csv:
					if self.load_reference_no != self._load_reference_no_from_csv:
						frappe.throw(
							_(
								"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported from CSV. The CSV data belongs to Load Reference Number '{0}'. Please clear all items first or use a CSV file that matches the desired Load Reference Number."
							).format(self._load_reference_no_from_csv, self.load_reference_no)
						)
				# If no flag is set but items exist, it means items were imported
				# In this case, we need to prevent changes - but we can't know the original value
				# So we'll rely on client-side validation for new documents
			else:
				# For existing documents, check if value changed
				if self.has_value_changed("load_reference_no"):
					old_value = self.get_doc_before_save().get("load_reference_no") if self.get_doc_before_save() else None
					frappe.throw(
						_(
							"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported. Please clear all items first or create a new Load Dispatch document."
						).format(old_value or "None", self.load_reference_no)
					)
		
		if self.load_reference_no:
			# Check if Load Plan with given Load Reference No exists
			if not frappe.db.exists("Load Plan", self.load_reference_no):
				frappe.throw(
					_(
						"Load Plan with Load Reference No {0} does not exist."
					).format(self.load_reference_no)
				)

			load_plan = frappe.get_doc("Load Plan", self.load_reference_no)
			if load_plan.docstatus != 1:
				frappe.throw(
					_(
						"Please submit Load Plan against this Load Reference No before creating Load Dispatch."
					)
				)
		
		# Calculate total dispatch quantity from child table
		self.calculate_total_dispatch_quantity()
	
	def create_serial_nos(self):
		"""Create serial nos for all items on save."""
		if self.items:
			has_purchase_date = frappe.db.has_column("Serial No", "purchase_date")
			for item in self.items:
				# Debug: Print all relevant field values
				print(f"=== DEBUG: Processing Load Dispatch Item ===")
				print(f"item_code: {item.item_code}")
				print(f"frame_no: {item.frame_no}")
				print(f"engnie_no_motor_no: {getattr(item, 'engnie_no_motor_no', None)}")
				print(f"key_no: {getattr(item, 'key_no', None)}")
				print(f"key_no type: {type(getattr(item, 'key_no', None))}")
				
				if item.item_code and item.frame_no:
					serial_no_name = str(item.frame_no).strip()

					# Check if Serial No already exists
					if not frappe.db.exists("Serial No", serial_no_name):
						print(f"=== DEBUG: Creating NEW Serial No: {serial_no_name} ===")
						try:
							# IMPORTANT:
							# - Serial No doctype still has a mandatory standard field `serial_no`
							# - Your DB table currently does NOT have a `serial_no` column
							#   so you MUST fix the schema (see explanation in assistant message)
							#   so this insert works without SQL errors.
							serial_no = frappe.get_doc({
								"doctype": "Serial No",
								"item_code": item.item_code,
								"serial_no": serial_no_name,  # Frame Number -> Serial No field
							})

							# Map Engine No / Motor No from Load Dispatch Item to Serial No custom field
							# Assumes Serial No has a custom field named `custom_engine_number`
							if getattr(item, "engnie_no_motor_no", None):
								print(f"=== DEBUG: Setting custom_engine_number to: {item.engnie_no_motor_no} ===")
								setattr(serial_no, "custom_engine_number", item.engnie_no_motor_no)

							# Map Key No from Load Dispatch Item to Serial No custom field
							# Assumes Serial No has a custom field named `custom_key_no`
							# Use 'is not None' check since key_no is Int and 0 is a valid value
							key_no_value = getattr(item, "key_no", None)
							print(f"=== DEBUG: key_no_value = {key_no_value}, type = {type(key_no_value)} ===")
							if key_no_value is not None and str(key_no_value).strip():
								print(f"=== DEBUG: Setting custom_key_no to: {str(key_no_value)} ===")
								setattr(serial_no, "custom_key_no", str(key_no_value))
							else:
								print(f"=== DEBUG: key_no is None or empty, NOT setting custom_key_no ===")

							# Map purchase_date for aging (prefer dispatch_date -> planned_arrival_date -> parent.dispatch_date) when column exists
							if has_purchase_date:
								purchase_date = (
									getattr(item, "dispatch_date", None)
									or getattr(item, "planned_arrival_date", None)
									or getattr(self, "dispatch_date", None)
								)
								if purchase_date:
									try:
										from frappe.utils import getdate
										setattr(serial_no, "purchase_date", getdate(purchase_date))
										print(f"=== DEBUG: Setting purchase_date to: {purchase_date} ===")
									except Exception:
										print(f"=== DEBUG: purchase_date parsing failed for value: {purchase_date}")

							serial_no.insert(ignore_permissions=True)
							print(f"=== DEBUG: Serial No created successfully ===")
							print(serial_no.as_dict())
						except Exception as e:
							print(f"=== DEBUG: Error creating Serial No: {str(e)} ===")
							frappe.log_error(f"Error creating Serial No {serial_no_name}: {str(e)}", "Serial No Creation Error")
					else:
						print(f"=== DEBUG: Serial No already exists: {serial_no_name}, UPDATING ===")
						# If Serial No already exists, update the custom engine number if provided
						if getattr(item, "engnie_no_motor_no", None):
							try:
								print(f"=== DEBUG: Updating custom_engine_number to: {item.engnie_no_motor_no} ===")
								frappe.db.set_value(
									"Serial No",
									serial_no_name,
									"custom_engine_number",
									item.engnie_no_motor_no,
								)
							except Exception as e:
								frappe.log_error(
									f"Error updating custom_engine_number for Serial No {serial_no_name}: {str(e)}",
									"Serial No Update Error",
								)
						# If Serial No already exists, update the custom key no if provided
						# Use 'is not None' check since key_no is Int and 0 is a valid value
						key_no_value = getattr(item, "key_no", None)
						print(f"=== DEBUG: (update) key_no_value = {key_no_value}, type = {type(key_no_value)} ===")
						if key_no_value is not None and str(key_no_value).strip():
							try:
								print(f"=== DEBUG: Updating custom_key_no to: {str(key_no_value)} ===")
								frappe.db.set_value(
									"Serial No",
									serial_no_name,
									"custom_key_no",
									str(key_no_value),
								)
							except Exception as e:
								print(f"=== DEBUG: Error updating custom_key_no: {str(e)} ===")
								frappe.log_error(
									f"Error updating custom_key_no for Serial No {serial_no_name}: {str(e)}",
									"Serial No Update Error",
								)
						else:
							print(f"=== DEBUG: (update) key_no is None or empty, NOT updating custom_key_no ===")

						# Backfill purchase_date when missing to support aging buckets (only if column exists)
						if has_purchase_date:
							purchase_date = (
								getattr(item, "dispatch_date", None)
								or getattr(item, "planned_arrival_date", None)
								or getattr(self, "dispatch_date", None)
							)
							if purchase_date:
								try:
									from frappe.utils import getdate
									frappe.db.set_value(
										"Serial No",
										serial_no_name,
										"purchase_date",
										getdate(purchase_date),
									)
									print(f"=== DEBUG: (update) purchase_date set to: {purchase_date} ===")
								except Exception as e:
									print(f"=== DEBUG: Error setting purchase_date: {str(e)} ===")
									frappe.log_error(
										f"Error setting purchase_date for Serial No {serial_no_name}: {str(e)}",
										"Serial No Update Error",
									)
	
	def set_item_code(self):
		if self.items:
			for item in self.items:
				if item.mtoc and str(item.mtoc).strip():
					if frappe.db.exists("Item", str(item.mtoc).strip()):
						item_doc = frappe.get_doc("Item", str(item.mtoc).strip())
						item.item_code = item_doc.item_code
					else:
						self.create_items_from_dispatch_items()
	
	def set_fields_value(self):
		"""Set default values from RKG Settings if not already set."""
		if not self.items:
			return
		
		try:
			rkg_settings = frappe.get_single("RKG Settings")
		except frappe.DoesNotExistError:
			# RKG Settings not found, skip setting default values
			return
		
		# Set default values if not already set
		for item in self.items:
			# You can add more field mappings here if needed
			pass

	def update_item_pricing_fields(self):
		"""
		Update Item doctypes with pricing/GST values from Load Dispatch Items.
		This runs on save/validate so existing Items get refreshed too.
		"""
		if not self.items:
			return

		custom_field_map = {field: field for field in ITEM_CUSTOM_FIELDS}

		for item in self.items:
			print(
				f"DEBUG pricing sync: row frame={getattr(item, 'frame_no', None)}, "
				f"item_code={getattr(item, 'item_code', None)}, "
				f"mtoc={getattr(item, 'mtoc', None)}, "
				f"values={{"
				f"ndp={getattr(item, 'net_dealer_price', None)}, "
				f"cogst={getattr(item, 'credit_of_gst', None)}, "
				f"dbp={getattr(item, 'dealer_billing_price', None)}, "
				f"cgst={getattr(item, 'cgst_amount', None)}, "
				f"sgst={getattr(item, 'sgst_amount', None)}, "
				f"igst={getattr(item, 'igst_amount', None)}, "
				f"exs={getattr(item, 'ex_showroom_price', None)}, "
				f"gstin={getattr(item, 'gstin', None)}}}"
			)
			item_code = (item.item_code or item.mtoc or "").strip()
			if not item_code:
				print("DEBUG pricing sync: skip row (no item_code/mtoc)", getattr(item, "frame_no", None))
				continue
			if not frappe.db.exists("Item", item_code):
				print(f"DEBUG pricing sync: Item {item_code} not found; skipping")
				continue

			item_doc = frappe.get_doc("Item", item_code)
			updated = False

			for child_field, item_field in custom_field_map.items():
				if hasattr(item, child_field):
					child_value = getattr(item, child_field)
					# Allow zero/falsey numeric values to flow through; skip only if None or empty string
					if child_value is not None and child_value != "":
						if hasattr(item_doc, item_field):
							print(f"DEBUG pricing sync: setting {item_code}.{item_field} = {child_value}")
							setattr(item_doc, item_field, child_value)
							updated = True
						else:
							print(f"DEBUG pricing sync: Item field {item_field} missing on {item_code}")
					else:
						print(f"DEBUG pricing sync: empty value for {child_field} on row {getattr(item, 'frame_no', None)}")
				else:
					print(f"DEBUG pricing sync: child field {child_field} not on row {getattr(item, 'frame_no', None)}")

			if updated:
				item_doc.save(ignore_permissions=True)
				print(f"DEBUG pricing sync: saved Item {item_code}")
			else:
				print(f"DEBUG pricing sync: no updates applied for Item {item_code}")
	
	def set_item_group(self):
		"""Set item_group for Load Dispatch Items based on model_name or default."""
		if not self.items:
			return
		
		for item in self.items:
			if not item.item_group and item.model_name:
				# Check if model_name exists as an Item Group
				if frappe.db.exists("Item Group", item.model_name):
					item.item_group = item.model_name
				else:
					# Fall back to "Two Wheeler Vehicle" if model_name not found
					if frappe.db.exists("Item Group", "Two Wheeler Vehicle"):
						item.item_group = "Two Wheeler Vehicle"
	
	def set_supplier(self):
		"""Set supplier for items from RKG Settings."""
		if not self.items:
			return
		
		try:
			rkg_settings = frappe.get_single("RKG Settings")
			default_supplier = rkg_settings.get("default_supplier")
			
			if default_supplier:
				# Set supplier on items if needed
				# Note: This depends on whether Load Dispatch Item has a supplier field
				# If not, supplier is set on the Item doctype itself
				pass
		except frappe.DoesNotExistError:
			# RKG Settings not found, skip setting supplier
			pass

	def on_submit(self):
		# Set Load Dispatch status to "In-Transit" when submitted
		self.db_set("status", "In-Transit")
		self.add_dispatch_quanity_to_load_plan(docstatus=1)
	
	def on_cancel(self):
		self.add_dispatch_quanity_to_load_plan(docstatus=2)
	
	def update_status(self):
		"""
		Update Load Dispatch status based on received quantity.
		- If total_received_quantity >= total_dispatch_quantity: status = 'Received'
		- Otherwise: status = 'In-Transit'
		"""
		total_dispatch = flt(self.total_dispatch_quantity) or 0
		total_received = flt(self.total_received_quantity) or 0
		
		if total_dispatch > 0 and total_received >= total_dispatch:
			new_status = "Received"
		else:
			new_status = "In-Transit"
		
		# Update status if changed
		if self.status != new_status:
			frappe.db.set_value("Load Dispatch", self.name, "status", new_status, update_modified=False)
			self.status = new_status
	
	def add_dispatch_quanity_to_load_plan(self, docstatus):
		"""
		Update load_dispatch_quantity in Load Plan when Load Dispatch is submitted or cancelled.
		
		Args:
			docstatus: 1 for submit (add quantity), 2 for cancel (subtract quantity)
		"""
		if not self.load_reference_no:
			return
		
		# Ensure total_dispatch_quantity is calculated
		if not self.total_dispatch_quantity:
			self.calculate_total_dispatch_quantity()
		
		# Get current load_dispatch_quantity from database (works for submitted documents)
		current_quantity = frappe.db.get_value("Load Plan", self.load_reference_no, "load_dispatch_quantity") or 0
		
		# Calculate new quantity based on docstatus
		if docstatus == 1:  # Submit - add quantity
			new_quantity = current_quantity + (self.total_dispatch_quantity or 0)
		elif docstatus == 2:  # Cancel - subtract quantity
			new_quantity = max(0, current_quantity - (self.total_dispatch_quantity or 0))
		else:
			return
		
		# Update directly in database using db_set (works for submitted documents)
		status = 'In-Transit' if flt(new_quantity) > 0 else 'Submitted'
		
		frappe.db.set_value("Load Plan", self.load_reference_no, "load_dispatch_quantity", new_quantity, update_modified=False)
		frappe.db.set_value("Load Plan", self.load_reference_no, "status", status, update_modified=False)
	
	def calculate_total_dispatch_quantity(self):
		"""Count the number of rows with non-empty frame_no in Load Dispatch Item child table."""
		total_dispatch_quantity = 0
		if self.items:
			for item in self.items:
				# Count rows that have a non-empty frame_no
				if item.frame_no and str(item.frame_no).strip():
					total_dispatch_quantity += 1
		self.total_dispatch_quantity = total_dispatch_quantity
	
	def create_items_from_dispatch_items(self):
		"""
		Create Items in Item doctype for all load_dispatch_items that have item_code.
		Populates Supplier and HSN Code from RKG Settings.
		"""
		if not self.items:
			return
		
		# Fetch RKG Settings data (single doctype)
		try:
			rkg_settings = frappe.get_single("RKG Settings")
		except frappe.DoesNotExistError:
			frappe.throw(_("RKG Settings not found. Please create RKG Settings first before submitting Load Dispatch."))
		
		created_items = []
		updated_items = []
		skipped_items = []
		
		for item in self.items:
			# Prefer explicit item_code, else fall back to mtoc as the item code
			item_code = None
			if item.item_code and str(item.item_code).strip():
				item_code = str(item.item_code).strip()
			elif item.mtoc and str(item.mtoc).strip():
				item_code = str(item.mtoc).strip()
			
			# Nothing to create if we still don't have a code
			if not item_code:
				continue

			# Ensure the child row reflects the chosen item_code
			item.item_code = item_code
			
			# Check if Item already exists
			try:
				# Map pricing/GST custom fields from Load Dispatch Item -> Item custom fields
				custom_field_map = {field: field for field in ITEM_CUSTOM_FIELDS}

				if frappe.db.exists("Item", item_code):
					# Update existing Item with pricing/GST values when provided
					item_doc = frappe.get_doc("Item", item_code)
					updated = False

					for child_field, item_field in custom_field_map.items():
						child_value = getattr(item, child_field, None)
						# Allow zero/falsey numeric values to flow through; skip only if None or empty string
						if child_value is not None and child_value != "" and hasattr(item_doc, item_field):
							setattr(item_doc, item_field, child_value)
							updated = True

					if updated:
						item_doc.save(ignore_permissions=True)
						updated_items.append(item_code)
					else:
						skipped_items.append(item_code)
					continue

				# Determine item_group - try model_name first, then fall back to parent group
				item_group = None
				if item.model_name:
					# Check if model_name exists as an Item Group
					if frappe.db.exists("Item Group", item.model_name):
						item_group = item.model_name
				
				# Fall back to parent group "Two Wheeler Vehicle" if model_name not found
				if not item_group:
					if frappe.db.exists("Item Group", "Two Wheeler Vehicle"):
						item_group = "Two Wheeler Vehicle"
					else:
						# Last resort: get the first available item group
						first_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name", order_by="name")
						if first_group:
							item_group = first_group
						else:
							frappe.throw(_("No Item Group found. Please create an Item Group first."))
				
				# Create new Item
				item_doc = frappe.get_doc({
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item.model_variant or item_code,
					"item_group": item_group,
					"stock_uom": "Nos",  # Adjust as needed
					"is_stock_item": 1,
					"has_serial_no": 1,

				})
				
				# Populate Supplier from RKG Settings (uses default_supplier on the single doctype)
				if rkg_settings.get("default_supplier"):
					# Item uses Item Supplier child table
					if hasattr(item_doc, "supplier_items"):
						item_doc.append("supplier_items", {
							"supplier": rkg_settings.default_supplier,
							"is_default": 1
						})
					# Fallback: if Item has direct supplier field
					elif hasattr(item_doc, "supplier"):
						item_doc.supplier = rkg_settings.default_supplier
				
				# Populate HSN Code from RKG Settings (uses default_hsn_code on the single doctype)
				if rkg_settings.get("default_hsn_code"):
					# Try common field names for HSN Code
					if hasattr(item_doc, "gst_hsn_code"):
						item_doc.gst_hsn_code = rkg_settings.default_hsn_code
					elif hasattr(item_doc, "custom_gst_hsn_code"):
						item_doc.custom_gst_hsn_code = rkg_settings.default_hsn_code
				
				# Save the Item
				for child_field, item_field in custom_field_map.items():
					if hasattr(item, child_field):
						child_value = getattr(item, child_field)
						# Allow zero/falsey numeric values to flow through; skip only if None or empty string
						if child_value is not None and child_value != "":
							if hasattr(item_doc, item_field):
								setattr(item_doc, item_field, child_value)

				item_doc.insert(ignore_permissions=True)
				created_items.append(item_code)
				
			except Exception as e:
				frappe.log_error(
					f"Error creating Item {item_code}: {str(e)}", 
					"Item Creation Error"
				)
				frappe.throw(_("Error creating Item '{0}': {1}").format(item_code, str(e)))
		
		# Show summary message
		if created_items:
			frappe.msgprint(
				_("Created {0} Item(s): {1}").format(
					len(created_items), 
					", ".join(created_items[:10]) + ("..." if len(created_items) > 10 else "")
				),
				indicator="green",
				alert=True
			)
		
		if updated_items:
			frappe.msgprint(
				_("Updated {0} Item(s): {1}").format(
					len(updated_items),
					", ".join(updated_items[:10]) + ("..." if len(updated_items) > 10 else "")
				),
				indicator="blue",
				alert=True
			)
		
		if skipped_items:
			frappe.msgprint(
				_("Skipped {0} Item(s) (already exist): {1}").format(
					len(skipped_items),
					", ".join(skipped_items[:10]) + ("..." if len(skipped_items) > 10 else "")
				),
				indicator="orange",
				alert=True
			)


@frappe.whitelist()
def process_csv_file(file_url, selected_load_reference_no=None):
	"""
	Process CSV file and extract data for child table
	Maps CSV columns to Load Dispatch Item fields
	
	Args:
		file_url: Path to the CSV file
		selected_load_reference_no: The manually selected Load Reference No to validate against
	"""
	try:
		# Get file path from file_url
		# file_url format: /files/filename.csv
		if file_url.startswith("/files/"):
			file_name = file_url.split("/files/")[-1]
			file_path = frappe.get_site_path("public", "files", file_name)
		else:
			file_path = frappe.get_site_path("public", file_url.lstrip("/"))
		
		# Check if file exists
		if not os.path.exists(file_path):
			frappe.throw(f"File not found: {file_url}")
		
		# Try different encodings to handle various file formats
		encodings = ['utf-8-sig', 'utf-8', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252']
		csvfile = None
		sample = None
		
		for encoding in encodings:
			try:
				csvfile = open(file_path, 'r', encoding=encoding)
				# Try to read a sample to verify encoding works and detect delimiter
				sample = csvfile.read(1024)
				csvfile.seek(0)
				break
			except (UnicodeDecodeError, UnicodeError):
				if csvfile:
					csvfile.close()
				csvfile = None
				sample = None
				continue
		
		if not csvfile or not sample:
			frappe.throw(f"Unable to read file with supported encodings. Please ensure the file is in UTF-8, UTF-16, or Latin-1 format.")
		
		try:
			def _norm_header(h):
				# Normalize header for comparison: strip, lower, collapse spaces, remove BOM and special chars
				if not h:
					return ""
				# Remove BOM and other invisible characters
				normalized = str(h).replace("\ufeff", "").replace("\u200b", "").strip()
				# Convert to lowercase and collapse multiple spaces/tabs into single space
				normalized = " ".join(normalized.lower().split())
				return normalized

			# Mapping from CSV column names to child table fieldnames
			column_mapping = {
				"HMSI Load Reference No": "hmsi_load_reference_no",
				"Invoice No": "invoice_no",
				"Dispatch Date": "dispatch_date",
				"Frame No": "frame_no",
				"Engine no": "engnie_no_motor_no",
				"Engine No": "engnie_no_motor_no",  # alternate spelling
				"Key No": "key_no",
				"Model": "model",
				"Model Name": "model_name",
				"Colour": "color_code",
				"Color": "color_code",  # alternate spelling
				"Tax Rate": "tax_rate",
				"Print Name": "print_name",
				"DOR": "dor",
				"HSN Code": "hsn_code",
				"Qty": "qty",
				"Unit": "unit",
				"Price/Unit": "price_unit",
				"Price/unit": "price_unit",  # alternate spelling
				# Legacy mappings for backward compatibility
				"HMSI/InterDealer Load Reference No": "hmsi_load_reference_no",
				"Invoice No.": "invoice_no",
				"Frame #": "frame_no",
				"Engine No/Motor No": "engnie_no_motor_no",
				"Color Code": "color_code",
			}
			
			# Required headers that MUST be present in the CSV (core), case/space-insensitive
			required_headers_core = [
				"HMSI Load Reference No",
				"Invoice No",
				"Dispatch Date",
				"Frame No",
				"Engine no",
				"Key No",
				"Model",
				"Model Name",
				"Colour",
				"Tax Rate",
				"Print Name",
				"DOR",
				"HSN Code",
				"Qty",
				"Unit",
				"Price/Unit"
			]

			# Optional headers (ignored if absent)
			optional_headers = []
			
			# Detect delimiter from sample, with fallbacks for common delimiters
			try:
				delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
			except Exception:
				# If sniffer cannot determine, start with comma as default
				delimiter = ","

			# Try multiple delimiters to find one that satisfies required headers
			delimiters_to_try = []
			for d in [delimiter, ",", "\t", ";", "|"]:
				if d not in delimiters_to_try:
					delimiters_to_try.append(d)

			best_delimiter = delimiter
			best_missing = None
			best_headers = []
			for delim in delimiters_to_try:
				csvfile.seek(0)
				test_reader = csv.DictReader(csvfile, delimiter=delim)
				test_headers = [h.strip() if h else "" for h in (test_reader.fieldnames or [])]
				norm_test_headers = {_norm_header(h) for h in test_headers}

				missing = []
				for required_header in required_headers_core:
					norm_req = _norm_header(required_header)
					# Check for alternate spellings
					alternates = {
						_norm_header("Engine no"): [_norm_header("Engine No"), _norm_header("Engine No/Motor No")],
						_norm_header("Colour"): [_norm_header("Color"), _norm_header("Color Code")],
						_norm_header("Price/Unit"): [_norm_header("Price/unit")],
						_norm_header("Frame No"): [_norm_header("Frame #")],
						_norm_header("Invoice No"): [_norm_header("Invoice No.")],
						_norm_header("HMSI Load Reference No"): [_norm_header("HMSI/InterDealer Load Reference No")]
					}
					
					found = norm_req in norm_test_headers
					if not found and norm_req in alternates:
						for alt in alternates[norm_req]:
							if alt in norm_test_headers:
								found = True
								break
					
					if not found:
						missing.append(required_header)

				if best_missing is None or len(missing) < len(best_missing):
					best_missing = missing
					best_delimiter = delim
					best_headers = test_headers

				# Perfect match found; stop searching
				if not missing:
					break

			# Use the best delimiter found - recreate reader to get actual headers
			csvfile.seek(0)
			reader = csv.DictReader(csvfile, delimiter=best_delimiter)
			
			# Always get headers from the reader to ensure we have the actual headers from the file
			reader_headers = [h.strip() if h else "" for h in (reader.fieldnames or [])]
			
			# Use reader headers (they're the actual headers from the file)
			csv_headers = reader_headers
			
			# Create normalized header mapping after csv_headers is finalized
			norm_csv_headers = {_norm_header(h): h for h in csv_headers if h}  # Filter out empty headers
			
			# Debug: Log found headers for troubleshooting
			if not csv_headers:
				frappe.throw(_("CSV file appears to have no headers. Please ensure the first row contains column headers."))
			
			# Check for missing headers using the chosen delimiter (case/space-insensitive)
			missing_core_headers = []
			for required_header in required_headers_core:
				norm_req = _norm_header(required_header)
				# Check for alternate spellings
				alternates = {
					_norm_header("Engine no"): [_norm_header("Engine No"), _norm_header("Engine No/Motor No")],
					_norm_header("Colour"): [_norm_header("Color"), _norm_header("Color Code")],
					_norm_header("Price/Unit"): [_norm_header("Price/unit")],
					_norm_header("Frame No"): [_norm_header("Frame #")],
					_norm_header("Invoice No"): [_norm_header("Invoice No.")],
					_norm_header("HMSI Load Reference No"): [_norm_header("HMSI/InterDealer Load Reference No")]
				}
				
				found = norm_req in norm_csv_headers
				if not found and norm_req in alternates:
					for alt in alternates[norm_req]:
						if alt in norm_csv_headers:
							found = True
							break
				
				if not found:
					missing_core_headers.append(required_header)

			# Optional headers: warn only
			missing_optional_headers = []
			for optional_header in optional_headers:
				if _norm_header(optional_header) not in norm_csv_headers:
					missing_optional_headers.append(optional_header)

			if missing_core_headers:
				expected_headers_str = "\n".join([f"• {h}" for h in required_headers_core + optional_headers])
				missing_headers_str = "\n".join([f"• {h}" for h in missing_core_headers + missing_optional_headers])
				found_headers_str = "\n".join([f"• {h}" for h in csv_headers[:20]])  # Show first 20 headers found
				if len(csv_headers) > 20:
					found_headers_str += f"\n... and {len(csv_headers) - 20} more"
				
				frappe.throw(
					_("CSV Header Validation Failed!\n\n"
					  "<b>Missing Headers:</b>\n{0}\n\n"
					  "<b>Expected Headers (CSV should contain these columns):</b>\n{1}\n\n"
					  "<b>Found Headers in CSV:</b>\n{2}").format(
						missing_headers_str,
						expected_headers_str,
						found_headers_str
					),
					title=_("Invalid CSV Headers")
				)
			elif missing_optional_headers:
				missing_headers_str = "\n".join([f"• {h}" for h in missing_optional_headers])
				frappe.msgprint(
					_("CSV missing optional headers (processing will continue):\n{0}").format(missing_headers_str),
					title=_("CSV Optional Headers Missing"),
					indicator="orange",
					alert=True,
				)
			
			rows = []
			csv_load_reference_nos = set()  # Track all load_reference_no values from CSV
			
			for csv_row in reader:
				# Skip empty rows
				if not any(csv_row.values()):
					continue
				
				row_data = {}
				for csv_col, fieldname in column_mapping.items():
					# Resolve actual CSV column using normalized header lookup
					actual_col = norm_csv_headers.get(_norm_header(csv_col))
					if not actual_col:
						continue

					raw_value = csv_row.get(actual_col, "")
					value = raw_value.strip() if isinstance(raw_value, str) else raw_value
					
					if value:
						# Handle date fields
						if fieldname in ["dispatch_date", "dor"]:
							# Try to parse date (assuming format YYYY-MM-DD or similar)
							try:
								from frappe.utils import getdate
								row_data[fieldname] = getdate(value)
							except:
								row_data[fieldname] = value
						# Handle integer fields
						elif fieldname in ["key_no", "hsn_code", "qty"]:
							try:
								row_data[fieldname] = int(float(value)) if value else None
							except:
								row_data[fieldname] = value
						# Handle currency fields
						elif fieldname in ["price_unit"]:
							try:
								row_data[fieldname] = float(value) if value else 0.0
							except:
								row_data[fieldname] = 0.0
						else:
							row_data[fieldname] = value
					
					# Track hmsi_load_reference_no from CSV (for validation)
					if fieldname == "hmsi_load_reference_no" and value:
						csv_load_reference_nos.add(value)
					# Also track invoice_no for parent document
					if fieldname == "invoice_no" and value:
						row_data[fieldname] = value
				
				if row_data:
					rows.append(row_data)
			
			# Validate hmsi_load_reference_no match if manually selected
			if selected_load_reference_no:
				if len(csv_load_reference_nos) == 0:
					frappe.throw(_("CSV file does not contain any Load Reference Number. Please ensure the CSV has 'HMSI Load Reference No' column."))
				elif len(csv_load_reference_nos) > 1:
					frappe.throw(_("CSV file contains multiple different Load Reference Numbers: {0}. All rows must have the same Load Reference Number.").format(", ".join(sorted(csv_load_reference_nos))))
				else:
					csv_load_ref = list(csv_load_reference_nos)[0]
					if csv_load_ref != selected_load_reference_no:
						frappe.throw(_("Load Reference Number mismatch! You have selected '{0}', but the CSV file contains '{1}'. Please ensure the CSV file matches the selected Load Reference Number.").format(selected_load_reference_no, csv_load_ref))
			
			return rows
		finally:
			if csvfile:
				csvfile.close()
			
	except Exception as e:
		frappe.log_error(f"Error processing CSV file: {str(e)}", "CSV Import Error")
		frappe.throw(f"Error processing CSV file: {str(e)}")
@frappe.whitelist()
def create_purchase_order(source_name, target_doc=None):
	"""Create Purchase Order from Load Dispatch"""
	from frappe.model.mapper import get_mapped_doc
	
	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		# Set load_reference_no from source
		target.custom_load_reference_no = source.load_reference_no
		
		# Set supplier and gst_hsn_code from RKG Settings on parent document
		try:
			rkg_settings = frappe.get_single("RKG Settings")
			if rkg_settings.get("default_supplier"):
				target.supplier = rkg_settings.default_supplier
			
			# Set gst_hsn_code from RKG Settings on parent document
			if rkg_settings.get("default_hsn_code"):
				# Set gst_hsn_code on Purchase Order
				if hasattr(target, "gst_hsn_code"):
					target.gst_hsn_code = rkg_settings.default_hsn_code
				elif hasattr(target, "custom_gst_hsn_code"):
					target.custom_gst_hsn_code = rkg_settings.default_hsn_code
		except frappe.DoesNotExistError:
			# RKG Settings not found, skip setting supplier and gst_hsn_code
			pass
	
	def update_item(source, target, source_parent):
		# Map item_code from Load Dispatch Item to Purchase Order Item
		target.item_code = source.item_code
		# Set quantity to 1
		target.qty = 1
		
		# Ensure UOM matches the Item's stock UOM
		if target.item_code:
			stock_uom = frappe.db.get_value("Item", target.item_code, "stock_uom")
			if stock_uom:
				if hasattr(target, "uom"):
					target.uom = stock_uom
				if hasattr(target, "stock_uom"):
					target.stock_uom = stock_uom
		
		# Set item_group from source if available, otherwise get from Item
		if source.item_group:
			# If Purchase Order Item has item_group field, set it
			if hasattr(target, "item_group"):
				target.item_group = source.item_group
		elif target.item_code:
			# Get item_group from Item doctype
			item_group = frappe.db.get_value("Item", target.item_code, "item_group")
			if item_group and hasattr(target, "item_group"):
				target.item_group = item_group

	doc = get_mapped_doc(
		"Load Dispatch",  # Source doctype
		source_name,
		{
			"Load Dispatch": {
				"doctype": "Purchase Order",
				"validation": {
					"docstatus": ["=", 1],
				},
				"field_map": {
					"load_reference_no": "load_reference_no"
				}
			},
			"Load Dispatch Item": {
				"doctype": "Purchase Order Item",
				"field_map": {
					"item_code": "item_code",
					"model_variant": "item_name",
					"frame_no": "serial_no",
					"item_group": "item_group",
				},
				"postprocess": update_item
			},
		},
		target_doc,
		set_missing_values
	)
	
	return doc

@frappe.whitelist()
def create_purchase_receipt(source_name, target_doc=None):
	"""Create Purchase Receipt from Load Dispatch"""
	from frappe.model.mapper import get_mapped_doc
	
	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		# Set load_reference_no from source
		target.custom_load_reference_no = source.load_reference_no
		
		# Set supplier and gst_hsn_code from RKG Settings on parent document
		try:
			rkg_settings = frappe.get_single("RKG Settings")
			if rkg_settings.get("default_supplier"):
				target.supplier = rkg_settings.default_supplier
			
			# Set gst_hsn_code from RKG Settings on parent document
			if rkg_settings.get("default_hsn_code"):
				# Set gst_hsn_code on Purchase Receipt
				if hasattr(target, "gst_hsn_code"):
					target.gst_hsn_code = rkg_settings.default_hsn_code
				elif hasattr(target, "custom_gst_hsn_code"):
					target.custom_gst_hsn_code = rkg_settings.default_hsn_code
		except frappe.DoesNotExistError:
			# RKG Settings not found, skip setting supplier and gst_hsn_code
			pass
	
	def update_item(source, target, source_parent):
		# Map item_code from Load Dispatch Item to Purchase Receipt Item
		target.item_code = source.item_code
		# Set quantity to 1
		target.qty = 1
		
		# Ensure UOM matches the Item's stock UOM
		if target.item_code:
			stock_uom = frappe.db.get_value("Item", target.item_code, "stock_uom")
			if stock_uom:
				if hasattr(target, "uom"):
					target.uom = stock_uom
				if hasattr(target, "stock_uom"):
					target.stock_uom = stock_uom
		
		# Set item_group from source if available, otherwise get from Item
		if source.item_group:
			# If Purchase Receipt Item has item_group field, set it
			if hasattr(target, "item_group"):
				target.item_group = source.item_group
		elif target.item_code:
			# Get item_group from Item doctype
			item_group = frappe.db.get_value("Item", target.item_code, "item_group")
			if item_group and hasattr(target, "item_group"):
				target.item_group = item_group

	doc = get_mapped_doc(
		"Load Dispatch",  # Source doctype
		source_name,
		{
			"Load Dispatch": {
				"doctype": "Purchase Receipt",
				"validation": {
					"docstatus": ["=", 1],
				},
				"field_map": {
					"load_reference_no": "load_reference_no"
				}
			},
			"Load Dispatch Item": {
				"doctype": "Purchase Receipt Item",
				"field_map": {
					"item_code": "item_code",
					"model_variant": "item_name",
					"frame_no": "serial_no",
					"item_group": "item_group",
				},
				"postprocess": update_item
			},
		},
		target_doc,
		set_missing_values
	)
	
	return doc

@frappe.whitelist()
def create_purchase_invoice(source_name, target_doc=None):
	"""Create Purchase Invoice from Load Dispatch"""
	from frappe.model.mapper import get_mapped_doc
	
	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		# Set load_reference_no from source
		target.custom_load_reference_no = source.load_reference_no
		
		# Set supplier and gst_hsn_code from RKG Settings on parent document
		try:
			rkg_settings = frappe.get_single("RKG Settings")
			if rkg_settings.get("default_supplier"):
				target.supplier = rkg_settings.default_supplier
			
			# Set gst_hsn_code from RKG Settings on parent document
			if rkg_settings.get("default_hsn_code"):
				# Set gst_hsn_code on Purchase Invoice
				if hasattr(target, "gst_hsn_code"):
					target.gst_hsn_code = rkg_settings.default_hsn_code
				elif hasattr(target, "custom_gst_hsn_code"):
					target.custom_gst_hsn_code = rkg_settings.default_hsn_code
		except frappe.DoesNotExistError:
			# RKG Settings not found, skip setting supplier and gst_hsn_code
			pass
	
	def update_item(source, target, source_parent):
		# Map item_code from Load Dispatch Item to Purchase Invoice Item
		target.item_code = source.item_code
		# Set quantity to 1
		target.qty = 1
		
		# Ensure UOM matches the Item's stock UOM
		if target.item_code:
			stock_uom = frappe.db.get_value("Item", target.item_code, "stock_uom")
			if stock_uom:
				if hasattr(target, "uom"):
					target.uom = stock_uom
				if hasattr(target, "stock_uom"):
					target.stock_uom = stock_uom
		
		# Set item_group from source if available, otherwise get from Item
		if source.item_group:
			# If Purchase Invoice Item has item_group field, set it
			if hasattr(target, "item_group"):
				target.item_group = source.item_group
		elif target.item_code:
			# Get item_group from Item doctype
			item_group = frappe.db.get_value("Item", target.item_code, "item_group")
			if item_group and hasattr(target, "item_group"):
				target.item_group = item_group

	doc = get_mapped_doc(
		"Load Dispatch",  # Source doctype
		source_name,
		{
			"Load Dispatch": {
				"doctype": "Purchase Invoice",
				"validation": {
					"docstatus": ["=", 1],
				},
				"field_map": {
					"load_reference_no": "load_reference_no"
				}
			},
			"Load Dispatch Item": {
				"doctype": "Purchase Invoice Item",
				"field_map": {
					"item_code": "item_code",
					"model_variant": "item_name",
					"frame_no": "serial_no",
					"item_group": "item_group",
				},
				"postprocess": update_item
			},
		},
		target_doc,
		set_missing_values
	)
	
	return doc


def update_load_dispatch_totals_from_document(doc, method=None):
	"""
	Update Load Dispatch totals (total_received_quantity and total_billed_quantity)
	when Purchase Receipt or Purchase Invoice is submitted or cancelled.
	
	On Submit: Updates with the submitted document's total_qty
	On Cancel: Recalculates totals from all remaining submitted documents (excludes cancelled one)
	
	Args:
		doc: Purchase Receipt or Purchase Invoice document
		method: Hook method name (optional)
	"""
	print(f"\n{'='*60}")
	print(f"DEBUG: update_load_dispatch_totals_from_document called")
	print(f"DEBUG: Document Type: {doc.doctype}")
	print(f"DEBUG: Document Name: {doc.name}")
	print(f"DEBUG: Document Status: {doc.docstatus}")
	print(f"DEBUG: Method: {method}")
	print(f"{'='*60}\n")
	
	# For Purchase Invoice, only run this logic when "Update Stock" is enabled
	if doc.doctype == "Purchase Invoice" and getattr(doc, "update_stock", 0) != 1:
		print("DEBUG: Purchase Invoice has update_stock != 1. Skipping Load Dispatch totals update.")
		return

	# Get custom_load_dispatch field value from the document
	load_dispatch_name = None
	
	# Try to get custom_load_dispatch from the document
	if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch:
		load_dispatch_name = doc.custom_load_dispatch
		print(f"DEBUG: Found custom_load_dispatch from doc attribute: {load_dispatch_name}")
	elif frappe.db.has_column(doc.doctype, "custom_load_dispatch"):
		load_dispatch_name = frappe.db.get_value(doc.doctype, doc.name, "custom_load_dispatch")
		print(f"DEBUG: Found custom_load_dispatch from DB: {load_dispatch_name}")

	if not load_dispatch_name:
		print(f"DEBUG: No custom_load_dispatch field found or empty. Exiting.")
		return

	print(f"DEBUG: Load Dispatch Name/ID from custom_load_dispatch: {load_dispatch_name}")

	# STEP 1: Verify Load Dispatch document exists with this name/ID
	if not frappe.db.exists("Load Dispatch", load_dispatch_name):
		print(f"DEBUG: Load Dispatch document with name '{load_dispatch_name}' does not exist. Exiting.")
		return
	
	print(f"DEBUG: ✓ Load Dispatch document '{load_dispatch_name}' found. Proceeding...")

	# Initialize totals
	total_received_qty = 0
	total_billed_qty = 0

	# Case 1: Purchase Receipt
	if doc.doctype == "Purchase Receipt":
		print(f"\nDEBUG: ===== Processing Purchase Receipt =====")
		
		if not frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
			print(f"DEBUG: custom_load_dispatch field does not exist. Exiting.")
			return
		
		# Find all submitted Purchase Receipts (docstatus=1) with this Load Dispatch
		# This automatically excludes cancelled documents (docstatus=2)
		pr_list = frappe.get_all(
			"Purchase Receipt",
			filters={
				"docstatus": 1,
				"custom_load_dispatch": load_dispatch_name
			},
			fields=["name", "total_qty"]
		)
		
		print(f"DEBUG: Found {len(pr_list)} submitted Purchase Receipt(s) with custom_load_dispatch = {load_dispatch_name}")
		
		# Sum total_qty from all submitted Purchase Receipts
		for pr in pr_list:
			pr_qty = flt(pr.get("total_qty")) or 0
			print(f"DEBUG: Purchase Receipt {pr.name} - total_qty: {pr_qty}")
			
			if pr_qty == 0:
				pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
				if hasattr(pr_doc, "items") and pr_doc.items:
					pr_qty = sum(
						flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0)
						for item in pr_doc.items
					)
					print(f"DEBUG: Purchase Receipt {pr.name} - calculated from items: {pr_qty}")
			
			# From PR we only update RECEIVED quantity; billed qty comes from Purchase Invoices only
			total_received_qty += pr_qty
		
		print(f"DEBUG: Total Received Qty = {total_received_qty}")
		print(f"DEBUG: Total Billed Qty = {total_billed_qty}")

	# Case 2: Purchase Invoice
	elif doc.doctype == "Purchase Invoice":
		print(f"\nDEBUG: ===== Processing Purchase Invoice =====")
		
		if not frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
			print(f"DEBUG: custom_load_dispatch field does not exist. Exiting.")
			return
		
		# Find all submitted Purchase Invoices (docstatus=1) with this Load Dispatch
		pi_list = frappe.get_all(
			"Purchase Invoice",
			filters={
				"docstatus": 1,
				"custom_load_dispatch": load_dispatch_name
			},
			fields=["name", "total_qty"]
		)
		
		print(f"DEBUG: Found {len(pi_list)} submitted Purchase Invoice(s) with custom_load_dispatch = {load_dispatch_name}")
		
		# Filter out Purchase Invoices that have Purchase Receipt linked
		pi_without_pr = []
		for pi in pi_list:
			pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
			has_pr = False
			
			if hasattr(pi_doc, "items") and pi_doc.items:
				for item in pi_doc.items:
					if hasattr(item, "purchase_receipt") and item.purchase_receipt:
						has_pr = True
						print(f"DEBUG: Purchase Invoice {pi.name} has Purchase Receipt. Skipping.")
						break
			
			if not has_pr:
				pi_without_pr.append(pi)
				print(f"DEBUG: Purchase Invoice {pi.name} does NOT have Purchase Receipt. Including.")
		
		# Sum total_qty from Purchase Invoices without Purchase Receipt
		for pi in pi_without_pr:
			pi_qty = flt(pi.get("total_qty")) or 0
			print(f"DEBUG: Purchase Invoice {pi.name} - total_qty: {pi_qty}")
			
			if pi_qty == 0:
				pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
				if hasattr(pi_doc, "items") and pi_doc.items:
					pi_qty = sum(
						flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0)
						for item in pi_doc.items
					)
					print(f"DEBUG: Purchase Invoice {pi.name} - calculated from items: {pi_qty}")
			
			total_received_qty += pi_qty
			total_billed_qty += pi_qty
		
	

	
	
	# Get total_dispatch_quantity to determine status
	total_dispatch_qty = frappe.db.get_value("Load Dispatch", load_dispatch_name, "total_dispatch_quantity") or 0
	
	# Determine status based on received quantity
	# If total_received_quantity >= total_dispatch_quantity: status = 'Received'
	# Otherwise: status = 'In-Transit'
	if flt(total_dispatch_qty) > 0 and flt(total_received_qty) >= flt(total_dispatch_qty):
		new_status = "Received"
	else:
		new_status = "In-Transit"
	
	print(f"DEBUG: total_dispatch_quantity = {total_dispatch_qty}")
	print(f"DEBUG: Setting status = {new_status}")
	
	frappe.db.set_value(
		"Load Dispatch",
		load_dispatch_name,
		{
			"total_received_quantity": total_received_qty,
			"total_billed_quantity": total_billed_qty,
			"status": new_status
		},
		update_modified=False
	)
	frappe.db.commit()
	
	print(f"DEBUG: Load Dispatch '{load_dispatch_name}' updated successfully!")
	print(f"{'='*60}\n")