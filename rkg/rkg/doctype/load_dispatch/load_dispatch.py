import frappe
import csv
import os
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt

# Canonical list of Item custom fieldnames that must be populated.
ITEM_CUSTOM_FIELDS = []


class LoadDispatch(Document):
	def has_valid_load_plan(self):
		"""Check if Load Dispatch has a valid Load Plan linked."""
		if not self.load_reference_no:
			return False
		if not frappe.db.exists("Load Plan", self.load_reference_no):
			return False
		return True
	#---------------------------------------------------------
	
	def _create_single_item_from_dispatch_item(self, dispatch_item, item_code):
		"""Create a single Item from a Load Dispatch Item."""
		# Get print_name from the map we created in before_submit
		print_name_from_map = None
		
		# Try from instance attribute
		if hasattr(self, '_print_name_map') and self._print_name_map:
			print_name_from_map = self._print_name_map.get(item_code)
		
		# Try from frappe.local
		if not print_name_from_map and hasattr(frappe.local, 'load_dispatch_print_name_map'):
			print_name_from_map = frappe.local.load_dispatch_print_name_map.get(item_code)
		
		if print_name_from_map:
			# Set it on the dispatch_item object using multiple methods
			dispatch_item.print_name = print_name_from_map
			# Also set it as an attribute directly
			setattr(dispatch_item, 'print_name', print_name_from_map)
			# Store it in frappe.local for the unified function to access
			if not hasattr(frappe.local, 'item_print_name_map'):
				frappe.local.item_print_name_map = {}
			frappe.local.item_print_name_map[item_code] = print_name_from_map
		
		# Pass print_name directly to unified function
		return _create_item_unified(dispatch_item, item_code, source_type="dispatch_item", print_name=print_name_from_map)
	#---------------------------------------------------------
	
	
	def before_insert(self):
		"""Verify item_code exists if set; Items created in before_submit hook."""
		if not self.items:
			return
		
		# Final verification: Ensure all set item_codes have corresponding Items
		# This prevents link validation errors
		# Note: item_code can be None/blank - those will be handled on submit
		missing_items = []
		for item in self.items:
			if item.item_code and str(item.item_code).strip():
				item_code = str(item.item_code).strip()
				if not frappe.db.exists("Item", item_code):
					missing_items.append(f"Row #{getattr(item, 'idx', 'Unknown')}: Item '{item_code}' does not exist")
		
		if missing_items:
			frappe.throw(
				_("The following Items do not exist:\n{0}\n\n"
				  "Items will be created on submit if they have Model Serial No.").format(
					"\n".join(missing_items[:20]) + ("\n..." if len(missing_items) > 20 else "")
				),
				title=_("Invalid Item Codes")
			)
	#---------------------------------------------------------
	
	def before_save(self):
		"""Populate item_code from model_serial_no before saving (only if Item exists)."""
		if not self.is_new() and self.items:
			# For existing documents, set item_code only if Item exists
			self.set_item_code()
		
		# Process additional operations if Load Plan exists
		if self.items and self.has_valid_load_plan():
			self.create_serial_nos()
			self.set_fields_value()
			self.set_item_group()
			self.set_supplier()
		
		# Sync print_name from Load Dispatch Item to Item doctype
		if self.items:
			self.sync_print_name_to_items()
	#---------------------------------------------------------
	
	def on_submit(self):
		"""
		On submit, set status and update Load Plan.
		Note: Items are created in before_submit() hook, not here.
		"""
		# Set Load Dispatch status to "In-Transit" when submitted
		self.db_set("status", "In-Transit")
		self.add_dispatch_quanity_to_load_plan(docstatus=1)
	#---------------------------------------------------------
	
	def validate(self):
		"""Validate Load Dispatch (Items created in before_submit, not here)."""
		if not self.items:
			# Calculate total dispatch quantity
			self.calculate_total_dispatch_quantity()
			return
		
		# CRITICAL: Only set item_code if Item already exists
		# This prevents LinkValidationError when saving draft documents
		# Items will be created in before_submit() before link validation runs
		for item in self.items:
			if item.model_serial_no and str(item.model_serial_no).strip():
				item_code = str(item.model_serial_no).strip()
				# Only set item_code if Item exists, otherwise leave it empty
				if frappe.db.exists("Item", item_code):
					item.item_code = item_code
				else:
					# Clear item_code if Item doesn't exist to prevent LinkValidationError
					# Items will be created in before_submit()
					item.item_code = None
		
		# Process items if Load Plan exists (for additional operations)
		if self.items and self.has_valid_load_plan():
			self.create_serial_nos()
			self.set_fields_value()
			self.set_item_group()
		
		# Sync print_name from Load Dispatch Item to Item doctype for existing items
		if self.items:
			self.sync_print_name_to_items()
		
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
			else:
				# For existing documents, check if value changed
				if self.has_value_changed("load_reference_no"):
					old_value = self.get_doc_before_save().get("load_reference_no") if self.get_doc_before_save() else None
					frappe.throw(
						_(
							"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported. Please clear all items first or create a new Load Dispatch document."
						).format(old_value or "None", self.load_reference_no)
					)
		
		# Note: Load Plan validation is done in before_submit to allow saving without Load Plan
		# This enables importing CSV data first, then creating/submitting Load Plan later
		
		# Check for duplicate frame numbers in Serial No doctype from submitted Load Dispatch documents
		# and skip those items
		self._filter_duplicate_frame_numbers()
		
		# Calculate total dispatch quantity from child table
		self.calculate_total_dispatch_quantity()
	#---------------------------------------------------------
	
	def create_serial_nos(self):
		"""Create serial nos for all items on save."""
		# Only create serial nos if Load Plan exists
		if not self.has_valid_load_plan():
			return
		
		if self.items:
			has_purchase_date = frappe.db.has_column("Serial No", "purchase_date")
			for item in self.items:
				item_code = str(item.model_serial_no).strip() if item.model_serial_no else ""
				if item_code and item.frame_no:
					serial_no_name = str(item.frame_no).strip()

					# Check if Serial No already exists
					if not frappe.db.exists("Serial No", serial_no_name):
						try:
							# IMPORTANT:
							# - Serial No doctype still has a mandatory standard field `serial_no`
							# - Your DB table currently does NOT have a `serial_no` column
							#   so you MUST fix the schema (see explanation in assistant message)
							#   so this insert works without SQL errors.
							serial_no = frappe.get_doc({
								"doctype": "Serial No",
								"item_code": item_code,
								"serial_no": serial_no_name,  # Frame Number -> Serial No field
							})

							# Map Engine No / Motor No from Load Dispatch Item to Serial No custom field
							# Assumes Serial No has a custom field named `custom_engine_number`
							if getattr(item, "engnie_no_motor_no", None):
								setattr(serial_no, "custom_engine_number", item.engnie_no_motor_no)

							# Map Key No from Load Dispatch Item to Serial No custom field
							# Assumes Serial No has a custom field named `custom_key_no`
							# Use 'is not None' check since key_no is Int and 0 is a valid value
							key_no_value = getattr(item, "key_no", None)
							if key_no_value is not None and str(key_no_value).strip():
								setattr(serial_no, "custom_key_no", str(key_no_value))

							# Map Color Code from Load Dispatch Item to Serial No color_code field
							if getattr(item, "color_code", None):
								setattr(serial_no, "color_code", item.color_code)

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
									except Exception:
										pass

							serial_no.insert(ignore_permissions=True)
						except Exception as e:
							frappe.log_error(f"Error creating Serial No {serial_no_name}: {str(e)}", "Serial No Creation Error")
					else:
						# If Serial No already exists, update the custom engine number if provided
						if getattr(item, "engnie_no_motor_no", None):
							try:
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
						if key_no_value is not None and str(key_no_value).strip():
							try:
								frappe.db.set_value(
									"Serial No",
									serial_no_name,
									"custom_key_no",
									str(key_no_value),
								)
							except Exception as e:
								frappe.log_error(
									f"Error updating custom_key_no for Serial No {serial_no_name}: {str(e)}",
									"Serial No Update Error",
								)

						# If Serial No already exists, update the color_code if provided
						if getattr(item, "color_code", None):
							try:
								frappe.db.set_value(
									"Serial No",
									serial_no_name,
									"color_code",
									item.color_code,
								)
							except Exception as e:
								frappe.log_error(
									f"Error updating color_code for Serial No {serial_no_name}: {str(e)}",
									"Serial No Update Error",
								)

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
								except Exception as e:
									frappe.log_error(
										f"Error setting purchase_date for Serial No {serial_no_name}: {str(e)}",
										"Serial No Update Error",
									)
	#---------------------------------------------------------
	
	def set_item_code(self):
		"""Populate item_code from model_serial_no, only if Item already exists."""
		if not self.items:
			return
		
		for item in self.items:
			if not item.model_serial_no or not str(item.model_serial_no).strip():
				continue
			
			item_code = str(item.model_serial_no).strip()
			
			# Only set item_code if Item exists
			# This prevents LinkValidationError when saving draft documents
			if frappe.db.exists("Item", item_code):
				# Item exists - just populate item_code
				item.item_code = item_code
			else:
				# Item doesn't exist - leave item_code empty
				# Items will be created in before_submit()
				item.item_code = None
	#---------------------------------------------------------
	
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
			# Calculate print_name from model_name and model_serial_no if model_serial_no exists
			if hasattr(item, "model_serial_no") and item.model_serial_no:
				model_name = getattr(item, "model_name", None)
				if not hasattr(item, "print_name") or not item.print_name:
					item.print_name = calculate_print_name(item.model_serial_no, model_name)
				# Also recalculate if model_serial_no changed (for manual edits)
				elif hasattr(item, "print_name") and item.model_serial_no:
					# Recalculate to ensure it's always correct
					item.print_name = calculate_print_name(item.model_serial_no, model_name)
			
			# Calculate rate from price_unit (excluding 18% GST)
			# rate = price_unit / 1.18 (standard GST exclusion formula)
			# Note: price_unit remains unchanged from Excel, only rate is calculated
			if hasattr(item, "price_unit") and item.price_unit:
				price_unit = flt(item.price_unit)
				if price_unit > 0:
					# Always calculate rate from price_unit (excluding 18% GST)
					# This ensures rate is always in sync with price_unit
					calculated_rate = price_unit / 1.18
					item.rate = calculated_rate
	#---------------------------------------------------------

	def set_item_group(self):
		"""Set item_group for Load Dispatch Items based on model_name using unified function."""
		# Only set item_group if Load Plan exists
		if not self.has_valid_load_plan():
			return
		
		if not self.items:
			return
		
		for item in self.items:
			# Only set item_group if the field exists on LoadDispatchItem
			if hasattr(item, 'item_group') and not item.item_group and item.model_name:
				# Use unified function to get or create Item Group with correct hierarchy
				item.item_group = _get_or_create_item_group_unified(item.model_name)
	#---------------------------------------------------------
	
	def set_supplier(self):
		"""Set supplier for items from RKG Settings."""
		# Only set supplier if Load Plan exists
		if not self.has_valid_load_plan():
			return
		
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
	#---------------------------------------------------------
	
	def sync_print_name_to_items(self):
		"""Sync print_name from Load Dispatch Item to Item doctype for all items with item_code."""
		if not self.items:
			return
		
		# Check if Item doctype has print_name field
		if not frappe.db.has_column("Item", "print_name"):
			return
		
		updated_items = []
		for item in self.items:
			# Only sync if item_code exists and print_name is set
			if not item.item_code or not str(item.item_code).strip():
				continue
			
			item_code = str(item.item_code).strip()
			
			# Check if Item exists
			if not frappe.db.exists("Item", item_code):
				continue
			
			# Get print_name from Load Dispatch Item
			print_name = None
			if hasattr(item, "print_name") and item.print_name:
				print_name = str(item.print_name).strip()
			
			# If print_name is not set, calculate it
			if not print_name:
				model_name = getattr(item, "model_name", None)
				model_serial_no = getattr(item, "model_serial_no", None)
				if model_serial_no:
					print_name = calculate_print_name(model_serial_no, model_name)
					# Also set it on the Load Dispatch Item for consistency
					item.print_name = print_name
			
			# Only update if print_name is available
			if print_name:
				# Get current print_name from Item
				current_print_name = frappe.db.get_value("Item", item_code, "print_name")
				
				# Update only if different
				if current_print_name != print_name:
					try:
						frappe.db.set_value("Item", item_code, "print_name", print_name, update_modified=False)
						updated_items.append(item_code)
					except Exception as e:
						frappe.log_error(
							f"Failed to sync print_name for Item {item_code}: {str(e)}",
							"Print Name Sync Error"
						)
		
		# Commit changes if any items were updated
		if updated_items:
			frappe.db.commit()
			frappe.clear_cache(doctype="Item")
	#---------------------------------------------------------

	def before_submit(self):
		"""Validate Load Plan and create Items before submitting Load Dispatch."""
		# Validate Load Plan exists and is submitted
		if self.load_reference_no:
			# Check if Load Plan with given Load Reference No exists
			if not frappe.db.exists("Load Plan", self.load_reference_no):
				frappe.throw(
					_(
						"Load Plan with Load Reference No {0} does not exist. Please create and submit the Load Plan before submitting Load Dispatch."
					).format(self.load_reference_no)
				)

			load_plan = frappe.get_doc("Load Plan", self.load_reference_no)
			if load_plan.docstatus != 1:
				frappe.throw(
					_(
						"Please submit Load Plan with Load Reference No {0} before submitting Load Dispatch."
					).format(self.load_reference_no)
				)
		
		# Validate and create Items for rows with model_serial_no but no item_code
		if not self.items:
			return
		
		# Validate that all rows have model_serial_no
		missing_model_serial_nos = []
		for item in self.items:
			if not item.model_serial_no or not str(item.model_serial_no).strip():
				missing_model_serial_nos.append(f"Row #{getattr(item, 'idx', 'Unknown')}")
		
		if missing_model_serial_nos:
			frappe.throw(
				_("Cannot submit Load Dispatch. The following rows are missing Model Serial No:\n{0}\n\n"
				  "Please ensure all rows have a Model Serial No before submitting.").format(
					"\n".join(missing_model_serial_nos[:20]) + ("\n..." if len(missing_model_serial_nos) > 20 else "")
				),
				title=_("Missing Model Serial No")
			)
		
		# Ensure print_name is calculated for all items before creating Items
		print_name_map = {}  # Map item_code to print_name
		
		for item in self.items:
			if hasattr(item, "model_serial_no") and item.model_serial_no:
				model_name = getattr(item, "model_name", None)
				model_serial_no = item.model_serial_no
				item_code = str(model_serial_no).strip()
				
				if not hasattr(item, "print_name") or not item.print_name or not str(item.print_name).strip():
					item.print_name = calculate_print_name(model_serial_no, model_name)
				
				# Store in map for later use
				print_name_map[item_code] = item.print_name
		
		# Store the map in the document for later use
		self._print_name_map = print_name_map
		
		# Also store it in frappe.local for global access
		if not hasattr(frappe.local, 'load_dispatch_print_name_map'):
			frappe.local.load_dispatch_print_name_map = {}
		frappe.local.load_dispatch_print_name_map.update(print_name_map)
		
		# Create Items for rows that don't have item_code but have model_serial_no
		# This happens AFTER saving print_name values, so Items will have correct print_name
		for item in self.items:
			
			# If item_code is already present → verify Item exists
			if item.item_code and str(item.item_code).strip():
				item_code = str(item.item_code).strip()
				if not frappe.db.exists("Item", item_code):
					frappe.throw(
						_("Row #{0}: Item '{1}' does not exist. Please check the Item Code.").format(
							getattr(item, 'idx', 'Unknown'), item_code
						),
						title=_("Invalid Item Code")
					)
				continue
			
			# If item_code is empty AND model_serial_no is present → create Item
			if not item.model_serial_no or not str(item.model_serial_no).strip():
				continue
			
			item_code = str(item.model_serial_no).strip()
			
			# Check if Item exists with item_code = model_serial_no
			if frappe.db.exists("Item", item_code):
				# Item exists → set item_code
				item.item_code = item_code
			else:
				# Item does NOT exist → create Item
				try:
					# Get print_name from the map we created earlier and set it on the item
					print_name_for_item = self._print_name_map.get(item_code) if hasattr(self, '_print_name_map') and self._print_name_map else None
					if print_name_for_item:
						item.print_name = print_name_for_item
					
					self._create_single_item_from_dispatch_item(item, item_code)
					# Clear cache and commit
					frappe.clear_cache(doctype="Item")
					frappe.db.commit()
					
					# Verify Item was created
					if frappe.db.exists("Item", item_code):
						# Set item_code after Item is created
						item.item_code = item_code
					else:
						frappe.throw(
							_("Item '{0}' was not created for Row #{1} before submit. Please check Error Log.").format(
								item_code, getattr(item, 'idx', 'Unknown')
							),
							title=_("Item Creation Failed")
						)
				except Exception as e:
					# Log error and throw
					frappe.log_error(
						f"Failed to create Item {item_code} for Row #{getattr(item, 'idx', 'Unknown')} before submit: {str(e)}\nTraceback: {frappe.get_traceback()}",
						"Item Creation Error in before_submit"
					)
					frappe.throw(
						_("Failed to create Item '{0}' for Row #{1} before submit.\n\nError: {2}\n\nPlease check Error Log for details.").format(
							item_code, getattr(item, 'idx', 'Unknown'), str(e)
						),
						title=_("Item Creation Failed")
					)
		
		# Final verification: Ensure all rows with model_serial_no have item_code
		missing_items = []
		for item in self.items:
			if item.model_serial_no and str(item.model_serial_no).strip():
				item_code = str(item.model_serial_no).strip()
				if not item.item_code or not str(item.item_code).strip():
					missing_items.append(f"Row #{getattr(item, 'idx', 'Unknown')}: Model Serial No '{item_code}'")
		
		if missing_items:
			frappe.throw(
				_("CRITICAL ERROR: {0} row(s) have Model Serial No but no Item Code after item creation:\n{1}\n\n"
				  "Items should have been created. Please check Error Log.").format(
					len(missing_items),
					"\n".join(missing_items[:20]) + ("\n..." if len(missing_items) > 20 else "")
				),
					title=_("Item Code Missing")
				)
	#---------------------------------------------------------
	
	def on_cancel(self):
		self.add_dispatch_quanity_to_load_plan(docstatus=2)
	#---------------------------------------------------------
	
	def update_status(self):
		"""Update Load Dispatch status based on received quantity (Received if >= dispatch quantity, otherwise In-Transit)."""
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
	#---------------------------------------------------------
	
	def add_dispatch_quanity_to_load_plan(self, docstatus):
		"""Update load_dispatch_quantity in Load Plan when Load Dispatch is submitted or cancelled."""
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
	#---------------------------------------------------------
	
	def calculate_total_dispatch_quantity(self):
		"""Count the number of rows with non-empty frame_no in Load Dispatch Item child table."""
		total_dispatch_quantity = 0
		if self.items:
			for item in self.items:
				# Count rows that have a non-empty frame_no
				if item.frame_no and str(item.frame_no).strip():
					total_dispatch_quantity += 1
		self.total_dispatch_quantity = total_dispatch_quantity
	#---------------------------------------------------------
	
	def _filter_duplicate_frame_numbers(self):
		"""Filter out Load Dispatch Items with frame numbers already existing in Serial No doctype."""
		if not self.items:
			return
		
		items_to_remove = []
		skipped_items = []
		
		for item in self.items:
			# Only check if frame_no and item_code are provided
			if not item.frame_no:
				continue
			
			frame_no = str(item.frame_no).strip()
			if not frame_no:
				continue
			
			# Get item_code from model_serial_no or item_code field
			item_code = None
			if item.model_serial_no and str(item.model_serial_no).strip():
				item_code = str(item.model_serial_no).strip()
			elif hasattr(item, 'item_code') and item.item_code and str(item.item_code).strip():
				item_code = str(item.item_code).strip()
			
			if not item_code:
				continue
			
			# Check if frame number (Serial No) already exists using frappe.db.exists
			if frappe.db.exists("Serial No", frame_no):
				# Frame number exists in Serial No doctype
				# Now check if it's from a submitted Load Dispatch document
				# We need to find which Load Dispatch Item has this frame_no
				# and check if the parent Load Dispatch is submitted
				# Exclude the current document if it exists
				if self.name:
					# Existing document - exclude it from the check
					existing_load_dispatch_item = frappe.db.sql("""
						SELECT 
							ldi.name,
							ldi.frame_no,
							ldi.item_code,
							ld.name as load_dispatch_name,
							ld.docstatus
						FROM `tabLoad Dispatch Item` ldi
						INNER JOIN `tabLoad Dispatch` ld ON ldi.parent = ld.name
						WHERE ldi.frame_no = %s
							AND ldi.item_code = %s
							AND ld.docstatus = 1
							AND ld.name != %s
					""", (frame_no, item_code, self.name), as_dict=True)
				else:
					# New document - check all submitted Load Dispatch documents
					existing_load_dispatch_item = frappe.db.sql("""
						SELECT 
							ldi.name,
							ldi.frame_no,
							ldi.item_code,
							ld.name as load_dispatch_name,
							ld.docstatus
						FROM `tabLoad Dispatch Item` ldi
						INNER JOIN `tabLoad Dispatch` ld ON ldi.parent = ld.name
						WHERE ldi.frame_no = %s
							AND ldi.item_code = %s
							AND ld.docstatus = 1
					""", (frame_no, item_code), as_dict=True)
				
				if existing_load_dispatch_item:
					# Frame number exists in a submitted Load Dispatch document
					existing_doc_name = existing_load_dispatch_item[0].get('load_dispatch_name', 'Unknown')
					items_to_remove.append(item)
					skipped_items.append({
						'frame_no': frame_no,
						'item_code': item_code,
						'existing_doc': existing_doc_name
					})
		
		# Remove duplicate items from the items list
		if items_to_remove:
			for item in items_to_remove:
				self.remove(item)
			
			# Show message for skipped items
			skipped_messages = []
			for skipped in skipped_items:
				skipped_messages.append(
					_("Frame Number {0} already exists for Item Code {1} in submitted Load Dispatch {2}").format(
						skipped['frame_no'], skipped['item_code'], skipped['existing_doc']
					)
				)
			
			frappe.msgprint(
				_("Skipped {0} item(s) with duplicate frame numbers:\n{1}").format(
					len(skipped_items),
					"\n".join(skipped_messages[:10]) + ("\n..." if len(skipped_messages) > 10 else "")
				),
				indicator="orange",
				alert=True
			)
	#---------------------------------------------------------
	
	def create_items_from_dispatch_items(self):
		"""Create Items from Load Dispatch Items, populating Supplier and HSN Code from RKG Settings."""
		if not self.items:
			return
		
		# Fetch RKG Settings data (single doctype) - optional, use defaults if not found
		rkg_settings = None
		try:
			rkg_settings = frappe.get_single("RKG Settings")
		except frappe.DoesNotExistError:
			# RKG Settings not found - continue with defaults (no supplier/HSN code)
			pass
		
		created_items = []
		updated_items = []
		skipped_items = []
		failed_items = []  # Track Items that failed to create
		
		for item in self.items:
			# Use model_serial_no as the item code (primary source)
			# Fall back to item_code if model_serial_no is not set
			item_code = None
			if item.model_serial_no and str(item.model_serial_no).strip():
				item_code = str(item.model_serial_no).strip()
			elif hasattr(item, 'item_code') and item.item_code and str(item.item_code).strip():
				# Fallback: use item_code if model_serial_no is not available
				item_code = str(item.item_code).strip()
			
			# Nothing to create if we still don't have a code
			if not item_code:
				continue
			
			# Ensure item_code is set on the item (in case we used model_serial_no)
			# This ensures item_code is always set from model_serial_no when available
			item.item_code = item_code
			
			# Note: item_code is set from model_serial_no or existing item_code
			
			# Ensure print_name is calculated before creating/updating Item
			if not hasattr(item, "print_name") or not item.print_name:
				model_name = getattr(item, "model_name", None)
				item.print_name = calculate_print_name(item.model_serial_no, model_name)
			
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
					
					# Update print_name from Load Dispatch Item's print_name
					if hasattr(item, "print_name") and item.print_name:
						if hasattr(item_doc, "print_name"):
							item_doc.print_name = item.print_name
							updated = True

					if updated:
						item_doc.save(ignore_permissions=True)
						updated_items.append(item_code)
					else:
						skipped_items.append(item_code)
					continue

				# Determine item_group - use unified function to ensure correct hierarchy
				# This ensures: All Item Groups -> Two Wheelers Vehicle -> Model Name
				model_name = str(item.model_name).strip() if (item.model_name and str(item.model_name).strip()) else None
				item_group = _get_or_create_item_group_unified(model_name)
				
				# Get UOM from Load Dispatch Item's unit field, default to "Pcs" if not set
				stock_uom = "Pcs"  # Default to "Pcs"
				if hasattr(item, "unit") and item.unit:
					stock_uom = str(item.unit).strip()
				elif hasattr(item, "unit") and not item.unit:
					# If unit field exists but is empty, use default "Pcs"
					stock_uom = "Pcs"
				
				# Create new Item
				item_doc = frappe.get_doc({
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item.model_variant or item_code,
					"item_group": item_group,
					"stock_uom": stock_uom,
					"is_stock_item": 1,
					"has_serial_no": 1,

				})
				
				# Populate Supplier from RKG Settings (uses default_supplier on the single doctype)
				if rkg_settings and rkg_settings.get("default_supplier"):
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
				if rkg_settings and rkg_settings.get("default_hsn_code"):
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
				
				# Set print_name from Load Dispatch Item's print_name
				if hasattr(item, "print_name") and item.print_name:
					if hasattr(item_doc, "print_name"):
						item_doc.print_name = item.print_name

				# Insert Item - this will create the Item in the database
				item_doc.insert(ignore_permissions=True)
				created_items.append(item_code)
				
			except Exception as e:
				# Log detailed error but continue creating other Items
				import traceback
				error_details = traceback.format_exc()
				frappe.log_error(
					f"Error creating Item {item_code}: {str(e)}\n{error_details}", 
					"Item Creation Error"
				)
				# Track failed Items instead of throwing immediately
				# We'll throw at the end if any Items failed
				failed_items.append({
					"item_code": item_code,
					"error": str(e),
					"row": getattr(item, 'idx', 'Unknown')
				})
				continue  # Continue with next Item
		
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
		
		# If any Items failed to create, throw comprehensive error
		if failed_items:
			failed_list = "\n".join([
				f"Row #{f['row']}: {f['item_code']} - {f['error']}"
				for f in failed_items[:20]
			])
			if len(failed_items) > 20:
				failed_list += f"\n... and {len(failed_items) - 20} more"
			
			frappe.throw(
				_("Failed to create {0} Item(s). Please check error logs for details:\n\n{1}\n\n"
				  "Common causes:\n"
				  "• Missing Item Group (ensure 'Two Wheelers Vehicle' Item Group exists)\n"
				  "• Validation errors in Item creation\n"
				  "• Database constraints").format(
					len(failed_items),
					failed_list
				),
				title=_("Item Creation Failed")
			)
	#---------------------------------------------------------


def calculate_print_name(model_serial_no, model_name=None):
	"""Calculate Print Name: Model Name + (Model Serial Number up to "-ID") + (BS-VI)"""
	if not model_serial_no:
		return ""
	
	model_serial_no = str(model_serial_no).strip()
	if not model_serial_no:
		return ""
	
	# Extract Model Serial Number part up to "-ID" (including "-ID")
	# Search for "-ID" pattern (case-insensitive)
	model_serial_upper = model_serial_no.upper()
	id_index = model_serial_upper.find("-ID")
	
	if id_index != -1:
		# Take everything up to and including "-ID"
		# Add 3 to include "-ID" (3 characters)
		serial_part = model_serial_no[:id_index + 3]
	else:
		# If "-ID" not found, try to find "ID" (without dash) and take up to it
		id_index = model_serial_upper.find("ID")
		if id_index != -1:
			# Take everything up to "ID" and add "-ID"
			serial_part = model_serial_no[:id_index] + "-ID"
		else:
			# If "ID" not found at all, use the whole model_serial_no
			serial_part = model_serial_no
	
	# Build the result: Model Name + (Serial Part) + (BS-VI)
	if model_name:
		model_name = str(model_name).strip()
		if model_name:
			return f"{model_name} ({serial_part}) (BS-VI)"
	
	# If no model_name, just use serial_part
	return f"{serial_part} (BS-VI)"
	#---------------------------------------------------------
@frappe.whitelist()
def preserve_purchase_receipt_uom(doc, method=None):
	"""Preserve UOM from Load Dispatch Item's unit field when Purchase Receipt is validated."""
	preserve_uom_from_load_dispatch(doc, "Purchase Receipt")
	#---------------------------------------------------------

@frappe.whitelist()
def preserve_purchase_invoice_uom(doc, method=None):
	"""Preserve UOM from Load Dispatch Item's unit field when Purchase Invoice is validated."""
	preserve_uom_from_load_dispatch(doc, "Purchase Invoice")
	#---------------------------------------------------------

def preserve_uom_from_load_dispatch(doc, doctype_name):
	"""Preserve UOM from Load Dispatch Item's unit field for Purchase Receipt and Purchase Invoice."""
	if not doc.items:
		return
	
	# Check if document was created from Load Dispatch
	load_dispatch_name = None
	if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch:
		load_dispatch_name = doc.custom_load_dispatch
	elif frappe.db.has_column(doctype_name, "custom_load_dispatch"):
		load_dispatch_name = frappe.db.get_value(doctype_name, doc.name, "custom_load_dispatch")
	
	if not load_dispatch_name:
		return
	
	# Get Load Dispatch document
	try:
		load_dispatch = frappe.get_doc("Load Dispatch", load_dispatch_name)
	except frappe.DoesNotExistError:
		return
	
	# Create a mapping of item_code to unit from Load Dispatch Items
	item_uom_map = {}
	if load_dispatch.items:
		for ld_item in load_dispatch.items:
			if ld_item.item_code and hasattr(ld_item, "unit") and ld_item.unit:
				item_uom_map[ld_item.item_code] = str(ld_item.unit).strip()
	
	# Update document Items with UOM from Load Dispatch
		if item_uom_map:
			for doc_item in doc.items:
				if doc_item.item_code and doc_item.item_code in item_uom_map:
					uom_value = item_uom_map[doc_item.item_code]
					if hasattr(doc_item, "uom") and doc_item.uom != uom_value:
						doc_item.uom = uom_value
					if hasattr(doc_item, "stock_uom") and doc_item.stock_uom != uom_value:
						doc_item.stock_uom = uom_value
	#---------------------------------------------------------

def preserve_purchase_invoice_serial_no_from_receipt(doc, method=None):
	"""
	Preserve serial_no from Purchase Receipt Item when creating Purchase Invoice from Purchase Receipt.
	This ensures the serial_no field is populated when Purchase Invoice is created from Purchase Receipt.
	"""
	if not doc.items:
		return
	
	# Get unique purchase receipts from items
	purchase_receipts = set()
	for item in doc.items:
		if hasattr(item, "purchase_receipt") and item.purchase_receipt:
			purchase_receipts.add(item.purchase_receipt)
	
	if not purchase_receipts:
		return
	
	# Create a mapping of item_code and idx to serial_no from Purchase Receipt Items
	# We use both item_code and idx to match items correctly
	receipt_item_map = {}
	
	# Process each purchase receipt
	for pr_name in purchase_receipts:
		try:
			purchase_receipt = frappe.get_doc("Purchase Receipt", pr_name)
			if not purchase_receipt.items:
				continue
			
			for pr_item in purchase_receipt.items:
				if pr_item.item_code and hasattr(pr_item, "serial_no") and pr_item.serial_no:
					# Use purchase_receipt, item_code and idx as key to match items
					key = (pr_name, pr_item.item_code, pr_item.idx)
					receipt_item_map[key] = pr_item.serial_no
		except frappe.DoesNotExistError:
			continue
	
	# Update Purchase Invoice Items with serial_no from Purchase Receipt
	if receipt_item_map:
		for pi_item in doc.items:
			if pi_item.item_code and hasattr(pi_item, "purchase_receipt") and pi_item.purchase_receipt:
				pr_name = pi_item.purchase_receipt
				# Try to match by purchase_receipt, item_code and idx first
				key = (pr_name, pi_item.item_code, pi_item.idx)
				if key in receipt_item_map:
					serial_no_value = receipt_item_map[key]
					if serial_no_value:
						# Set use_serial_batch_fields if not already set
						if hasattr(pi_item, "use_serial_batch_fields") and not pi_item.use_serial_batch_fields:
							pi_item.use_serial_batch_fields = 1
						# Set serial_no
						if hasattr(pi_item, "serial_no"):
							pi_item.serial_no = serial_no_value
				else:
					# Fallback: match by purchase_receipt and item_code only (first match)
					for (pr_key, item_code, idx), serial_no_value in receipt_item_map.items():
						if pr_key == pr_name and item_code == pi_item.item_code:
							if serial_no_value:
								# Set use_serial_batch_fields if not already set
								if hasattr(pi_item, "use_serial_batch_fields") and not pi_item.use_serial_batch_fields:
									pi_item.use_serial_batch_fields = 1
								# Set serial_no
								if hasattr(pi_item, "serial_no"):
									pi_item.serial_no = serial_no_value
							break
	
	# Only set update_stock to 1 if the Purchase Invoice is NOT created from a Purchase Receipt
	# If it's created from PR, stock was already updated and we shouldn't update again
	# This prevents the validation error: "Stock cannot be updated against Purchase Receipt"
	has_purchase_receipt = False
	if doc.items:
		for item in doc.items:
			if hasattr(item, "purchase_receipt") and item.purchase_receipt:
				has_purchase_receipt = True
				break
	
	if not has_purchase_receipt and hasattr(doc, "update_stock") and not doc.update_stock:
		# Set update_stock to 1 only if not created from Purchase Receipt
		# This ensures serial_no field is visible when creating directly from Load Dispatch
		doc.update_stock = 1
	#---------------------------------------------------------

@frappe.whitelist()
def set_purchase_receipt_serial_batch_fields_readonly(doc, method=None):
	"""
	Set "Use Serial No / Batch Fields" to checked on child table items
	for Purchase Receipts created from Load Dispatch.
	"""
	# Check if this Purchase Receipt was created from Load Dispatch
	load_dispatch_name = None
	if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch:
		load_dispatch_name = doc.custom_load_dispatch
	elif frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
		load_dispatch_name = frappe.db.get_value("Purchase Receipt", doc.name, "custom_load_dispatch")
	
	# Only apply if created from Load Dispatch
	if load_dispatch_name and doc.items:
		# Set use_serial_batch_fields to 1 (checked) on all child table items
		for item in doc.items:
			if hasattr(item, "use_serial_batch_fields"):
				if not item.use_serial_batch_fields:
					item.use_serial_batch_fields = 1
	#---------------------------------------------------------

def _create_purchase_document_unified(source_name, doctype, target_doc=None, warehouse=None, frame_warehouse_mapping=None):
	"""Unified Purchase Receipt/Invoice creation from Load Dispatch"""
	from frappe.model.mapper import get_mapped_doc
	import json
	
	if frappe.db.has_column(doctype, "custom_load_dispatch"):
		existing = frappe.get_all(doctype, filters={"custom_load_dispatch": source_name}, fields=["name"], limit=1)
		if existing:
			frappe.throw(_("{0} {1} already exists for this Load Dispatch.").format(doctype, existing[0].name))
	
	frame_warehouse_map, selected_warehouse = {}, None
	if frame_warehouse_mapping:
		if isinstance(frame_warehouse_mapping, str):
			try:
				frame_warehouse_mapping = json.loads(frame_warehouse_mapping)
			except:
				frame_warehouse_mapping = frappe.parse_json(frame_warehouse_mapping)
		if isinstance(frame_warehouse_mapping, list):
			for m in frame_warehouse_mapping:
				m = frappe.parse_json(m) if isinstance(m, str) else m
				if isinstance(m, dict):
					fn, wh = str(m.get("frame_no", "")).strip(), str(m.get("warehouse", "")).strip()
					if fn and wh:
						frame_warehouse_map[fn] = wh
	elif warehouse:
		selected_warehouse = warehouse
	
	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		target.custom_load_reference_no = source.load_reference_no
		if hasattr(target, "custom_load_dispatch"):
			target.custom_load_dispatch = source_name
		elif frappe.db.has_column(doctype, "custom_load_dispatch"):
			target.db_set("custom_load_dispatch", source_name)
		
		has_pr = any(getattr(item, "purchase_receipt", None) for item in (target.items or []))
		if not has_pr and hasattr(target, "update_stock"):
			target.update_stock = 1
		
		try:
			rkg = frappe.get_single("RKG Settings")
			if rkg.get("default_supplier"):
				target.supplier = rkg.default_supplier
			if rkg.get("default_hsn_code"):
				if hasattr(target, "gst_hsn_code"):
					target.gst_hsn_code = rkg.default_hsn_code
				elif hasattr(target, "custom_gst_hsn_code"):
					target.custom_gst_hsn_code = rkg.default_hsn_code
		except:
			pass
		
		if (frame_warehouse_map or selected_warehouse) and target.items and doctype == "Purchase Invoice":
			for item in target.items:
				wh = None
				if frame_warehouse_map and hasattr(item, "serial_no") and item.serial_no:
					wh = frame_warehouse_map.get(str(item.serial_no).strip())
				if not wh and selected_warehouse:
					wh = selected_warehouse
				if wh:
					if hasattr(item, "warehouse"):
						item.warehouse = wh
					if hasattr(item, "target_warehouse"):
						item.target_warehouse = wh
	
	def update_item(source, target, source_parent):
		target.item_code, target.qty = source.item_code, 1
		if hasattr(target, "use_serial_batch_fields"):
			target.use_serial_batch_fields = 1

		# Pricing: when creating Purchase Receipt / Purchase Invoice from Load Dispatch,
		# use Load Dispatch Item's Price/Unit (`price_unit`) instead of `rate`.
		# Some sites may have a custom `price_unit` field on the target item row; if so, populate it too.
		try:
			price_unit = flt(getattr(source, "price_unit", 0) or 0)
		except Exception:
			price_unit = 0

		if price_unit and price_unit > 0:
			if hasattr(target, "price_unit"):
				target.price_unit = price_unit
			# Fallback to standard ERPNext field
			if hasattr(target, "rate"):
				target.rate = price_unit
		
		if doctype == "Purchase Invoice" and hasattr(source, "frame_no") and source.frame_no:
			fn = str(source.frame_no).strip()
			if hasattr(target, "serial_no"):
				target.serial_no = fn
			if hasattr(target, "__dict__"):
				target.__dict__["serial_no"] = fn
			try:
				setattr(target, "serial_no", fn)
			except:
				pass
		
		uom = (hasattr(source, "unit") and source.unit and str(source.unit).strip()) or \
		      (target.item_code and frappe.db.get_value("Item", target.item_code, "stock_uom")) or "Pcs"
		if hasattr(target, "uom"):
			target.uom = uom
		if hasattr(target, "stock_uom"):
			target.stock_uom = uom
		
		if hasattr(source, "item_group") and source.item_group and hasattr(target, "item_group"):
			target.item_group = source.item_group
		elif target.item_code:
			ig = frappe.db.get_value("Item", target.item_code, "item_group")
			if ig and hasattr(target, "item_group"):
				target.item_group = ig
		
		wh = None
		if frame_warehouse_map and hasattr(source, "frame_no") and source.frame_no:
			wh = frame_warehouse_map.get(str(source.frame_no).strip())
		if not wh and selected_warehouse:
			wh = selected_warehouse
		if wh and hasattr(target, "warehouse"):
			target.warehouse = wh
	
	item_doctype = f"{doctype} Item"
	doc = get_mapped_doc("Load Dispatch", source_name, {
		"Load Dispatch": {"doctype": doctype, "validation": {"docstatus": ["=", 1]}, "field_map": {"load_reference_no": "load_reference_no"}},
		"Load Dispatch Item": {"doctype": item_doctype, "field_map": {"item_code": "item_code", "model_variant": "item_name", "frame_no": "serial_no", "item_group": "item_group"}, "postprocess": update_item}
	}, target_doc, set_missing_values)
	
	if doctype == "Purchase Invoice" and doc and hasattr(doc, "items"):
		source_doc = frappe.get_doc("Load Dispatch", source_name)
		if source_doc and source_doc.items:
			item_to_frame = {di.item_code: str(di.frame_no).strip() for di in source_doc.items if hasattr(di, "item_code") and di.item_code and hasattr(di, "frame_no") and di.frame_no}
			for item in doc.items:
				if hasattr(item, "item_code") and item.item_code in item_to_frame:
					fn = item_to_frame[item.item_code]
					if hasattr(item, "serial_no"):
						item.serial_no = fn
					if hasattr(item, "__dict__"):
						item.__dict__["serial_no"] = fn
	
	if doc:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"name": doc.name}
	return None
	#---------------------------------------------------------

@frappe.whitelist()
def create_purchase_receipt(source_name, target_doc=None, warehouse=None, frame_no=None, frame_warehouse_mapping=None):
	"""Create Purchase Receipt from Load Dispatch"""
	return _create_purchase_document_unified(source_name, "Purchase Receipt", target_doc, warehouse, frame_warehouse_mapping)
	#---------------------------------------------------------

@frappe.whitelist()
def create_purchase_invoice(source_name, target_doc=None, warehouse=None, frame_no=None, frame_warehouse_mapping=None):
	"""Create Purchase Invoice from Load Dispatch"""
	return _create_purchase_document_unified(source_name, "Purchase Invoice", target_doc, warehouse, frame_warehouse_mapping)
	#---------------------------------------------------------


def update_load_dispatch_totals_from_document(doc, method=None):
	"""Update Load Dispatch totals (total_received_quantity and total_billed_quantity) when Purchase Receipt/Invoice is submitted or cancelled."""

	# Get custom_load_dispatch field value from the document
	load_dispatch_name = None
	
	# Try to get custom_load_dispatch from the document
	if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch:
		load_dispatch_name = doc.custom_load_dispatch
	elif frappe.db.has_column(doc.doctype, "custom_load_dispatch"):
		load_dispatch_name = frappe.db.get_value(doc.doctype, doc.name, "custom_load_dispatch")

	if not load_dispatch_name:
		return

	# STEP 1: Verify Load Dispatch document exists with this name/ID
	if not frappe.db.exists("Load Dispatch", load_dispatch_name):
		return

	# Initialize totals
	total_received_qty = 0
	total_billed_qty = 0

	# Case 1: Purchase Receipt
	if doc.doctype == "Purchase Receipt":
		if not frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
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
		
		# Sum total_qty from all submitted Purchase Receipts
		for pr in pr_list:
			pr_qty = flt(pr.get("total_qty")) or 0
			
			if pr_qty == 0:
				pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
				if hasattr(pr_doc, "items") and pr_doc.items:
					pr_qty = sum(
						flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0)
						for item in pr_doc.items
					)
			
			# From PR we only update RECEIVED quantity
			total_received_qty += pr_qty

	# Case 2: Purchase Invoice
	elif doc.doctype == "Purchase Invoice":
		if not frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
			return
		
		# First, calculate total_received_qty from ALL Purchase Receipts linked to this Load Dispatch
		pr_list = frappe.get_all(
			"Purchase Receipt",
			filters={
				"docstatus": 1,
				"custom_load_dispatch": load_dispatch_name
			},
			fields=["name", "total_qty"]
		)
		
		for pr in pr_list:
			pr_qty = flt(pr.get("total_qty")) or 0
			
			if pr_qty == 0:
				pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
				if hasattr(pr_doc, "items") and pr_doc.items:
					pr_qty = sum(
						flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0)
						for item in pr_doc.items
					)
			
			total_received_qty += pr_qty
		
		# Check if this Purchase Invoice was created from a Purchase Receipt
		# by checking if any items have purchase_receipt field set
		has_purchase_receipt_link = False
		linked_purchase_receipts = set()
		
		if hasattr(doc, "items") and doc.items:
			for item in doc.items:
				if hasattr(item, "purchase_receipt") and item.purchase_receipt:
					has_purchase_receipt_link = True
					linked_purchase_receipts.add(item.purchase_receipt)
		
		# Calculate total_billed_qty from ALL Purchase Invoices linked to this Load Dispatch
		pi_list = frappe.get_all(
			"Purchase Invoice",
			filters={
				"docstatus": 1,
				"custom_load_dispatch": load_dispatch_name
			},
			fields=["name", "total_qty"]
		)
		
		for pi in pi_list:
			pi_qty = flt(pi.get("total_qty")) or 0
			
			if pi_qty == 0:
				pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
				if hasattr(pi_doc, "items") and pi_doc.items:
					pi_qty = sum(
						flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0)
						for item in pi_doc.items
					)
			
			total_billed_qty += pi_qty
		
		# If Purchase Invoice was created from Purchase Receipt(s) that came from Load Dispatch
		# Both total_received_qty and total_billed_qty should show the same value
		if has_purchase_receipt_link and linked_purchase_receipts:
			# Check if any of the linked Purchase Receipts are linked to this Load Dispatch
			pr_from_ld = []
			for pr_name in linked_purchase_receipts:
				pr_load_dispatch = None
				if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
					pr_load_dispatch = frappe.db.get_value("Purchase Receipt", pr_name, "custom_load_dispatch")
				
				# If this Purchase Receipt is linked to the same Load Dispatch
				if pr_load_dispatch == load_dispatch_name:
					pr_from_ld.append(pr_name)
			
			# If Purchase Invoice is created from Purchase Receipt(s) that came from Load Dispatch
			if pr_from_ld:
				# When Invoice is created from Receipt, both should show the same value
				# Use the Purchase Invoice total_billed_qty for both totals
				total_received_qty = total_billed_qty

	# Get total_dispatch_quantity to determine status
	total_dispatch_qty = frappe.db.get_value("Load Dispatch", load_dispatch_name, "total_dispatch_quantity") or 0
	
	# Determine status based on received quantity
	# If total_received_quantity >= total_dispatch_quantity: status = 'Received'
	# Otherwise: status = 'In-Transit'
	if flt(total_dispatch_qty) > 0 and flt(total_received_qty) >= flt(total_dispatch_qty):
		new_status = "Received"
	else:
		new_status = "In-Transit"
	
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
	#---------------------------------------------------------


@frappe.whitelist()
def check_existing_documents(load_dispatch_name):
	"""Check if Purchase Receipt or Purchase Invoice already exists for a Load Dispatch."""
	result = {
		"has_purchase_receipt": False,
		"has_purchase_invoice": False,
		"purchase_receipt_name": None,
		"purchase_invoice_name": None
	}
	
	if not load_dispatch_name:
		return result
	
	# Check for Purchase Receipt
	if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
		pr_list = frappe.get_all(
			"Purchase Receipt",
			filters={
				"custom_load_dispatch": load_dispatch_name
			},
			fields=["name"],
			limit=1
		)
		
		if pr_list:
			result["has_purchase_receipt"] = True
			result["purchase_receipt_name"] = pr_list[0].name
	
	# Check for Purchase Invoice
	if frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
		pi_list = frappe.get_all(
			"Purchase Invoice",
			filters={
				"custom_load_dispatch": load_dispatch_name
			},
			fields=["name"],
			limit=1
		)
		
		if pi_list:
			result["has_purchase_invoice"] = True
			result["purchase_invoice_name"] = pi_list[0].name
	
	return result
	#---------------------------------------------------------


@frappe.whitelist()
def process_tabular_file(file_url, selected_load_reference_no=None):
	"""Process CSV/Excel file, create Items if they don't exist, and return tabular data with item_code populated."""
	from frappe.utils import get_site_path
	
	try:
		# Get file path from file_url
		if file_url.startswith('/files/'):
			file_path = get_site_path('public', file_url[1:])
		elif file_url.startswith('/private/files/'):
			file_path = get_site_path('private', 'files', file_url.split('/')[-1])
		else:
			file_path = get_site_path('public', 'files', file_url)
		
		# Read file based on extension
		file_ext = os.path.splitext(file_path)[1].lower()
		
		rows = []
		if file_ext == '.csv':
			# Read CSV file using Python's csv module
			with open(file_path, 'r', encoding='utf-8-sig') as f:
				reader = csv.DictReader(f)
				rows = list(reader)
		elif file_ext in ['.xlsx', '.xls']:
			# Read Excel file using pandas (if available)
			try:
				import pandas as pd
				df = pd.read_excel(file_path)
				rows = df.to_dict('records')
			except ImportError:
				frappe.throw(_("pandas library is required for Excel files. Please install it or use CSV format."))
		else:
			frappe.throw(_("Unsupported file format. Please upload CSV or Excel file."))
		
		# Normalize column names: create a mapping from various Excel column name formats to standard field names
		# This handles case-insensitive matching and common variations
		def normalize_column_name(col_name):
			"""Normalize column name to handle case-insensitive matching and variations."""
			if not col_name:
				return None
			# Convert to lowercase and strip whitespace
			normalized = str(col_name).lower().strip()
			# Remove special characters and normalize spaces
			normalized = normalized.replace('.', '').replace('_', ' ').replace('-', ' ')
			# Remove extra spaces
			normalized = ' '.join(normalized.split())
			return normalized
		
		# Helper function to check if value is empty/NaN
		def is_empty_value(value):
			"""Check if value is empty or NaN."""
			if value is None:
				return True
			if isinstance(value, float):
				try:
					import math
					return math.isnan(value)
				except:
					return False
			if isinstance(value, str):
				return not value.strip()
			return False
		
		# Create mapping from normalized column names to field names
		column_mapping = {
			'model serial no': 'model_serial_no',
			'model serial number': 'model_serial_no',
			'modelvariant': 'model_variant',
			'model variant': 'model_variant',
			'modelname': 'model_name',
			'model name': 'model_name',
			'frameno': 'frame_no',
			'frame no': 'frame_no',
			'frame number': 'frame_no',
			'engineno': 'engnie_no_motor_no',
			'engine no': 'engnie_no_motor_no',
			'engine number': 'engnie_no_motor_no',
			'motor no': 'engnie_no_motor_no',
			'motor number': 'engnie_no_motor_no',
			'colorno': 'color_code',
			'color no': 'color_code',
			'color': 'color_code',
			'colorcode': 'color_code',
			'colourno': 'color_code',
			'colour no': 'color_code',
			'colour': 'color_code',
			'colourcode': 'color_code',
			'invoiceno': 'invoice_no',
			'invoice no': 'invoice_no',
			'invoice number': 'invoice_no',
			'hsncode': 'hsn_code',
			'hsn code': 'hsn_code',
			'priceunit': 'price_unit',
			'price unit': 'price_unit',
			'price/unit': 'price_unit',
			'taxrate': 'tax_rate',
			'tax rate': 'tax_rate',
			'dispatchdate': 'dispatch_date',
			'dispatch date': 'dispatch_date',
			'dor': 'dor',
			'qty': 'qty',
			'quantity': 'qty',
			'unit': 'unit',
			'keyno': 'key_no',
			'key no': 'key_no',
			'batteryno': 'battery_no',
			'battery no': 'battery_no',
			'printname': 'print_name',
			'print name': 'print_name',
			'hmsi load reference no': 'hmsi_load_reference_no',
			'hmsi load reference number': 'hmsi_load_reference_no',
			'load reference no': 'hmsi_load_reference_no',
			'load reference number': 'hmsi_load_reference_no',
		}
		
		# Helper function to parse and format dates
		def parse_date(date_value):
			"""Parse date from various formats and return YYYY-MM-DD format."""
			if not date_value or is_empty_value(date_value):
				return None
			
			# If already a date object, format it
			if hasattr(date_value, 'strftime'):
				return date_value.strftime('%Y-%m-%d')
			
			# Convert to string
			date_str = str(date_value).strip()
			if not date_str:
				return None
			
			# Try parsing common date formats
			from frappe.utils import getdate
			try:
				# Try Frappe's getdate which handles multiple formats
				parsed_date = getdate(date_str)
				return parsed_date.strftime('%Y-%m-%d')
			except:
				# If getdate fails, try manual parsing
				try:
					# Try MM/DD/YYYY or DD/MM/YYYY format
					import re
					# Match patterns like 12/11/2025, 12-11-2025, etc.
					match = re.match(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
					if match:
						month, day, year = match.groups()
						# Assume MM/DD/YYYY format (US format)
						# If day > 12, it's likely DD/MM/YYYY
						if int(day) > 12:
							day, month = month, day  # Swap for DD/MM/YYYY
						return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
					
					# Try YYYY-MM-DD format
					match = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
					if match:
						year, month, day = match.groups()
						return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
				except:
					pass
			
			# If all parsing fails, return None
			frappe.log_error(f"Could not parse date: {date_str}", "Date Parsing Error")
			return None
		
		# Process each row: Check if Item exists, create if not, then set item_code
		processed_rows = []
		for idx, row in enumerate(rows, start=1):
			# Normalize the row data: map Excel column names to field names
			normalized_row = {}
			for excel_col, value in row.items():
				if is_empty_value(value):
					continue
				normalized_col = normalize_column_name(excel_col)
				if normalized_col and normalized_col in column_mapping:
					field_name = column_mapping[normalized_col]
					# Parse dates for date fields
					if field_name in ['dispatch_date', 'dor']:
						parsed_date = parse_date(value)
						if parsed_date:
							normalized_row[field_name] = parsed_date
					else:
						normalized_row[field_name] = value
				else:
					# Keep original column name if no mapping found
					normalized_row[excel_col] = value
			
			# Step 1: Get Model Serial No (this is the Item Code)
			# Try multiple variations
			model_serial_no = (
				normalized_row.get('model_serial_no') or
				row.get('model_serial_no') or 
				row.get('Model Serial No') or 
				row.get('MODEL_SERIAL_NO') or
				row.get('Model Serial No.') or
				row.get('MODEL_SERIAL_NO.') or
				row.get('Model Serial Number') or
				row.get('MODEL_SERIAL_NUMBER')
			)
			
			if not model_serial_no or not str(model_serial_no).strip():
				# Skip rows without Model Serial No, but still add the normalized row
				processed_rows.append(normalized_row)
				continue
			
			item_code = str(model_serial_no).strip()
			
			# Ensure model_serial_no is in the normalized row
			normalized_row['model_serial_no'] = item_code
			
			# Step 2: Check if Item exists with this Item Code (model_serial_no)
			if frappe.db.exists("Item", item_code):
				# Item exists - set item_code in the row data
				normalized_row['item_code'] = item_code
			else:
				# Item does NOT exist - create it now
				try:
					_create_item_unified(normalized_row, item_code, source_type="row_data")
					frappe.clear_cache(doctype="Item")
					if frappe.db.exists("Item", item_code):
						normalized_row['item_code'] = item_code
					else:
						frappe.log_error(f"Item '{item_code}' was not created. Row index: {idx}", "Item Creation Failed")
						normalized_row['item_code'] = None
				except Exception as e:
					# Log error but continue processing other rows
					frappe.log_error(
						f"Failed to create Item '{item_code}' for row {idx}: {str(e)}\nTraceback: {frappe.get_traceback()}",
						"Item Creation Error in process_tabular_file"
					)
					normalized_row['item_code'] = None
			
			processed_rows.append(normalized_row)
		
		return processed_rows
		
	except Exception as e:
		frappe.log_error(
			f"Error processing tabular file {file_url}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"process_tabular_file Error"
		)
		frappe.throw(_("Error processing file: {0}").format(str(e)))
	#---------------------------------------------------------


def _create_item_from_row_data(row_data, item_code):
	"""Create an Item from row data (dictionary from CSV/Excel)."""
	return _create_item_unified(row_data, item_code, source_type="row_data")


def _create_item_unified(item_data, item_code, source_type="dispatch_item", print_name=None):
	"""Unified Item creation - handles both dispatch_item and row_data."""
	if source_type == "dispatch_item":
		model_name = getattr(item_data, "model_name", None)
		model_variant = getattr(item_data, "model_variant", None) or item_code
		unit = getattr(item_data, "unit", None) or "Pcs"
		model_serial_no = getattr(item_data, "model_serial_no", None)
		
		# Get print_name - try multiple ways to access it
		# First try the parameter passed directly
		# Then try from frappe.local (set in _create_single_item_from_dispatch_item)
		if not print_name and hasattr(frappe.local, 'item_print_name_map'):
			print_name = frappe.local.item_print_name_map.get(item_code)
		
		# Try from item_data object
		if not print_name:
			try:
				print_name = getattr(item_data, "print_name", None)
			except:
				pass
		
		# Try using get() method if available
		if not print_name and hasattr(item_data, "get") and callable(getattr(item_data, "get")):
			try:
				print_name = item_data.get("print_name")
			except:
				pass
		
		# Try accessing as dictionary
		if not print_name and isinstance(item_data, dict):
			print_name = item_data.get("print_name")
		
		# Always calculate print_name if not set or empty
		if not print_name or not str(print_name).strip():
			print_name = calculate_print_name(model_serial_no, model_name)
	else:
		model_name = item_data.get('model_name') or item_data.get('Model Name') or item_data.get('MODEL_NAME')
		model_variant = item_data.get('model_variant') or item_data.get('Model Variant') or item_data.get('MODEL_VARIANT') or item_code
		unit = item_data.get('unit') or "Pcs"
		print_name = None
	
	item_group = _get_or_create_item_group_unified(model_name)
	if not item_group:
		frappe.throw(_("Could not determine Item Group for Item '{0}'. Model Name: {1}").format(item_code, model_name or 'N/A'))
	
	rkg_settings = None
	try:
		rkg_settings = frappe.get_single("RKG Settings")
	except frappe.DoesNotExistError:
		if source_type == "row_data":
			frappe.throw(_("RKG Settings not found. Please create RKG Settings and set Default HSN Code."))
	
	stock_uom = str(unit).strip() if unit else "Pcs"
	# Prepare print_name value
	print_name_value = None
	if print_name and str(print_name).strip():
		print_name_value = str(print_name).strip()
	
	item_dict = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": str(model_variant).strip() if model_variant else item_code,
		"item_group": item_group,
		"stock_uom": stock_uom,
		"is_stock_item": 1,
		"has_serial_no": 1,
	}
	# Always add print_name if available
	if print_name_value:
		item_dict["print_name"] = print_name_value
	
	item_doc = frappe.get_doc(item_dict)
	
	if rkg_settings:
		if rkg_settings.get("default_supplier") and source_type == "dispatch_item":
			if hasattr(item_doc, "supplier_items"):
				item_doc.append("supplier_items", {"supplier": rkg_settings.default_supplier, "is_default": 1})
			elif hasattr(item_doc, "supplier"):
				item_doc.supplier = rkg_settings.default_supplier
		
		hsn_code = rkg_settings.get("default_hsn_code")
		if hsn_code:
			if source_type == "row_data" and not hsn_code:
				frappe.throw(_("Default HSN Code is not set in RKG Settings."))
			if hasattr(item_doc, "gst_hsn_code"):
				item_doc.gst_hsn_code = hsn_code
			elif hasattr(item_doc, "custom_gst_hsn_code"):
				item_doc.custom_gst_hsn_code = hsn_code
	
	if source_type == "dispatch_item":
		for field in ITEM_CUSTOM_FIELDS:
			if hasattr(item_data, field):
				value = getattr(item_data, field)
				if value is not None and value != "" and hasattr(item_doc, field):
					setattr(item_doc, field, value)
	
	# Ensure print_name is set (backup in case it wasn't in initial dict)
	if print_name_value:
		if hasattr(item_doc, "print_name"):
			item_doc.print_name = print_name_value
		if frappe.db.has_column("Item", "print_name"):
			item_doc.set("print_name", print_name_value)
	
	try:
		item_doc.insert(ignore_permissions=True)
		frappe.db.commit()
		
		# Ensure print_name is set after insert using db_set (most reliable)
		if print_name_value and frappe.db.has_column("Item", "print_name"):
			try:
				frappe.db.set_value("Item", item_code, "print_name", print_name_value, update_modified=False)
				frappe.db.commit()
			except Exception as e:
				frappe.log_error(f"Failed to set print_name for Item {item_code}: {str(e)}", "Item Print Name Update Failed")
		frappe.clear_cache(doctype="Item")
		if not frappe.db.exists("Item", item_code):
			frappe.db.commit()
			if not frappe.db.exists("Item", item_code):
				frappe.log_error(f"Item {item_code} was inserted but not found", "Item Creation Verification Failed")
				raise frappe.ValidationError(_("Item '{0}' was created but not found in database.").format(item_code))
		return item_doc
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(f"Failed to insert Item {item_code}: {str(e)}", "Item Insert Failed")
		raise frappe.ValidationError(_("Failed to create Item '{0}': {1}").format(item_code, str(e)))
	#---------------------------------------------------------

def _get_or_create_item_group_unified(model_name):
	"""Unified Item Group creation - creates hierarchy: All Item Groups -> Two Wheelers Vehicle -> Model Name."""
	# Step 1: Ensure "All Item Groups" exists (top-level parent)
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
			frappe.log_error(f"Failed to create 'All Item Groups': {str(e)}", "Item Group Creation Failed")
	
	# Step 2: Ensure "Two Wheelers Vehicle" exists (intermediate parent)
	two_wheeler_vehicle = "Two Wheelers Vehicle"
	if not frappe.db.exists("Item Group", two_wheeler_vehicle):
		try:
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": two_wheeler_vehicle,
				"is_group": 1,  # Parent group - can have children
				"parent_item_group": all_groups
			}).insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"Failed to create 'Two Wheelers Vehicle': {str(e)}", "Item Group Creation Failed")
	
	# Step 3: Create Model Name as child under "Two Wheelers Vehicle" (where items go)
	if model_name and str(model_name).strip():
		model_name = str(model_name).strip()
		if frappe.db.exists("Item Group", model_name):
			return model_name
		try:
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": model_name,
				"is_group": 0,  # Leaf group - items go here
				"parent_item_group": two_wheeler_vehicle
			}).insert(ignore_permissions=True)
			frappe.db.commit()
			return model_name
		except Exception as e:
			frappe.log_error(f"Failed to create Item Group '{model_name}': {str(e)}", "Item Group Creation Failed")
	
	# Fallback: Return "Two Wheelers Vehicle" if model_name is not provided
	if frappe.db.exists("Item Group", two_wheeler_vehicle):
		return two_wheeler_vehicle
	
	# Last resort: get any available item group
	any_group = frappe.db.get_value("Item Group", {}, "name", order_by="name")
	if any_group:
		return any_group
	
	frappe.throw(_("Could not create or find an Item Group. Please create one manually."))
	#---------------------------------------------------------
