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
	
	def _create_single_item_from_dispatch_item(self, dispatch_item, item_code):
		"""
		Create a single Item from a Load Dispatch Item.
		This method handles Item Group creation and Item creation for one item.
		"""
		# Ensure print_name is calculated
		if not hasattr(dispatch_item, "print_name") or not dispatch_item.print_name:
			model_name = getattr(dispatch_item, "model_name", None)
			dispatch_item.print_name = calculate_print_name(dispatch_item.model_serial_no, model_name)
		
		# Get or create Item Group from model_name
		item_group = self._get_or_create_item_group(dispatch_item.model_name)
		
		# Ensure item_group is set - this is critical
		if not item_group:
			frappe.throw(_("Could not determine Item Group for Item '{0}'. Model Name: {1}").format(
				item_code, getattr(dispatch_item, 'model_name', 'N/A')
			))
		
		# Fetch RKG Settings (optional)
		rkg_settings = None
		try:
			rkg_settings = frappe.get_single("RKG Settings")
		except frappe.DoesNotExistError:
			pass
		
		# Get UOM from Load Dispatch Item's unit field, default to "Pcs" if not set
		stock_uom = "Pcs"  # Default to "Pcs"
		if hasattr(dispatch_item, "unit") and dispatch_item.unit:
			stock_uom = str(dispatch_item.unit).strip()
		elif hasattr(dispatch_item, "unit") and not dispatch_item.unit:
			# If unit field exists but is empty, use default "Pcs"
			stock_uom = "Pcs"
		
		# Check if Item already exists
		if frappe.db.exists("Item", item_code):
			# Item exists, get it for update
			item_doc = frappe.get_doc("Item", item_code)
		else:
			# Create new Item
			item_doc = frappe.get_doc({
				"doctype": "Item",
				"item_code": item_code,
				"item_name": dispatch_item.model_variant or item_code,
				"item_group": item_group,
				"stock_uom": stock_uom,
				"is_stock_item": 1,
				"has_serial_no": 1,
			})
		
		# Populate Supplier from RKG Settings
		if rkg_settings and rkg_settings.get("default_supplier"):
			if hasattr(item_doc, "supplier_items"):
				item_doc.append("supplier_items", {
					"supplier": rkg_settings.default_supplier,
					"is_default": 1
				})
			elif hasattr(item_doc, "supplier"):
				item_doc.supplier = rkg_settings.default_supplier
		
		# Populate HSN Code from RKG Settings
		if rkg_settings and rkg_settings.get("default_hsn_code"):
			if hasattr(item_doc, "gst_hsn_code"):
				item_doc.gst_hsn_code = rkg_settings.default_hsn_code
			elif hasattr(item_doc, "custom_gst_hsn_code"):
				item_doc.custom_gst_hsn_code = rkg_settings.default_hsn_code
		
		# Set custom fields from Load Dispatch Item
		custom_field_map = {field: field for field in ITEM_CUSTOM_FIELDS}
		for child_field, item_field in custom_field_map.items():
			if hasattr(dispatch_item, child_field):
				child_value = getattr(dispatch_item, child_field)
				if child_value is not None and child_value != "":
					if hasattr(item_doc, item_field):
						setattr(item_doc, item_field, child_value)
		
		# Set custom_print_name
		if hasattr(dispatch_item, "print_name") and dispatch_item.print_name:
			if hasattr(item_doc, "custom_print_name"):
				item_doc.custom_print_name = dispatch_item.print_name
		
		# Save or insert Item with proper error handling
		try:
			if item_doc.is_new():
				# New Item - insert it
				item_doc.insert(ignore_permissions=True)
			else:
				# Existing Item - save updates
				item_doc.save(ignore_permissions=True)
			
			# Commit immediately after each Item creation to ensure it exists
			# Use savepoint to ensure this commit persists
			frappe.db.commit()
			
			# Force refresh cache to ensure Item is visible
			frappe.clear_cache(doctype="Item")
			
			# Verify Item exists after commit - use direct SQL query
			item_exists = frappe.db.sql("SELECT name FROM `tabItem` WHERE name = %s", (item_code,))
			if not item_exists:
				# Try one more commit and check
				frappe.db.commit()
				item_exists = frappe.db.sql("SELECT name FROM `tabItem` WHERE name = %s", (item_code,))
				if not item_exists:
					# Log this critical issue
					frappe.log_error(
						f"CRITICAL: Item {item_code} was inserted but not found in database after commit. SQL check returned: {item_exists}",
						"Item Creation Verification Failed"
					)
					raise frappe.ValidationError(
						_("Item '{0}' was created but not found in database. This may indicate a transaction issue.").format(item_code)
					)
			
			return item_doc
		except frappe.ValidationError:
			# Re-raise validation errors as-is
			raise
		except Exception as e:
			# Log detailed error
			import traceback
			error_details = traceback.format_exc()
			frappe.log_error(
				f"Failed to insert Item {item_code}: {str(e)}\n{error_details}\nItem Group: {item_group}",
				"Item Insert Failed"
			)
			# Re-raise with clear message
			raise frappe.ValidationError(_("Failed to create Item '{0}': {1}").format(item_code, str(e)))
	
	def _get_or_create_item_group(self, model_name):
		"""Get or create Item Group from model_name. Returns Item Group name."""
		# First, ensure we have a parent Item Group - create "All Item Groups" if it doesn't exist
		parent_item_group = "All Item Groups"
		if not frappe.db.exists("Item Group", parent_item_group):
			# Try to find any existing parent group
			parent_item_group = frappe.db.get_value("Item Group", {"is_group": 1}, "name", order_by="name")
			if not parent_item_group:
				# No parent group exists - create "All Item Groups"
				try:
					all_groups = frappe.get_doc({
						"doctype": "Item Group",
						"item_group_name": "All Item Groups",
						"is_group": 1
					})
					all_groups.insert(ignore_permissions=True)
					frappe.db.commit()
					parent_item_group = "All Item Groups"
				except Exception as e:
					frappe.log_error(f"Failed to create 'All Item Groups': {str(e)}", "Item Group Creation Failed")
					frappe.throw(_("No parent Item Group found and could not create 'All Item Groups'. Error: {0}").format(str(e)))
		
		# Use model_name as Item Group - create if it doesn't exist
		if model_name and str(model_name).strip():
			model_name = str(model_name).strip()
			if frappe.db.exists("Item Group", model_name):
				return model_name
			
			# Create Item Group from model_name
			try:
				new_item_group = frappe.get_doc({
					"doctype": "Item Group",
					"item_group_name": model_name,
					"is_group": 0,
					"parent_item_group": parent_item_group
				})
				new_item_group.insert(ignore_permissions=True)
				frappe.db.commit()
				return model_name
			except Exception as e:
				frappe.log_error(f"Failed to create Item Group '{model_name}': {str(e)}", "Item Group Creation Failed")
				# Fall through to default
		
		# Fall back to "Two Wheeler Vehicle"
		if frappe.db.exists("Item Group", "Two Wheeler Vehicle"):
			return "Two Wheeler Vehicle"
		
		# Create "Two Wheeler Vehicle" as default
		try:
			default_group = frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": "Two Wheeler Vehicle",
				"is_group": 0,
				"parent_item_group": parent_item_group
			})
			default_group.insert(ignore_permissions=True)
			frappe.db.commit()
			return "Two Wheeler Vehicle"
		except Exception as e:
			# Last resort: get any available item group
			any_group = frappe.db.get_value("Item Group", {}, "name", order_by="name")
			if any_group:
				return any_group
			frappe.throw(_("Could not create or find an Item Group. Please create one manually."))
	
	def _validate_links(self):
		"""
		Override _validate_links to skip validation for item_code in child table.
		item_code will be set in before_submit() when Items are created.
		This prevents LinkValidationError during draft saves.
		"""
		# Remove invalid item_codes before parent validation runs
		if self.items:
			for item in self.items:
				item_code_value = None
				try:
					item_code_value = getattr(item, 'item_code', None)
				except:
					pass
				
				if item_code_value:
					item_code_str = str(item_code_value).strip() if item_code_value else ""
					if item_code_str and not frappe.db.exists("Item", item_code_str):
						# Item doesn't exist - remove item_code before validation
						try:
							if hasattr(item, '__dict__') and 'item_code' in item.__dict__:
								del item.__dict__['item_code']
						except:
							pass
						try:
							if hasattr(item, 'item_code'):
								delattr(item, 'item_code')
						except:
							pass
		
		# Call parent's _validate_links for all other fields
		# The invalid item_codes have been removed, so validation will pass
		super()._validate_links()
	
	def before_insert(self):
		"""
		Hook called before inserting new Load Dispatch document.
		
		Note: Items are NOT created here - they are created in before_submit hook.
		This method removes any invalid item_codes to prevent LinkValidationError.
		Items will be created in before_submit() and item_code will be set then.
		"""
		if not self.items:
			return
		
		# Remove any item_codes that don't have corresponding Items
		# This prevents LinkValidationError during insert()
		# Items will be created in before_submit() hook and item_code will be set then
		for item in self.items:
			item_code_value = getattr(item, 'item_code', None)
			if item_code_value:
				item_code_str = str(item_code_value).strip() if item_code_value else ""
				if item_code_str and not frappe.db.exists("Item", item_code_str):
					# Item doesn't exist - remove item_code completely using __dict__ deletion
					# This is the most reliable way to remove a field from a Frappe child table row
					try:
						if hasattr(item, '__dict__'):
							if 'item_code' in item.__dict__:
								del item.__dict__['item_code']
							# Also try to unset using delattr
							if hasattr(item, 'item_code'):
								delattr(item, 'item_code')
					except (AttributeError, KeyError, TypeError):
						# If deletion fails, try setting to None
						try:
							setattr(item, 'item_code', None)
						except:
							pass
	
	def before_validate(self):
		"""
		Called before validate() - remove invalid item_codes as early as possible.
		This runs before any validation logic, ensuring item_code is cleaned up first.
		CRITICAL: This must remove item_code completely to prevent LinkValidationError.
		"""
		if not self.items:
			return
		
		# Remove any item_codes that don't have corresponding Items
		# This must happen as early as possible to prevent LinkValidationError
		# Use the most aggressive method: directly manipulate __dict__
		for item in self.items:
			# Check if item_code attribute exists (using getattr with None default)
			item_code_value = None
			try:
				item_code_value = getattr(item, 'item_code', None)
			except:
				pass
			
			if item_code_value:
				item_code_str = str(item_code_value).strip() if item_code_value else ""
				if item_code_str and not frappe.db.exists("Item", item_code_str):
					# Item doesn't exist - remove item_code completely
					# Try all methods to ensure it's removed
					removed = False
					
					# Method 1: Delete from __dict__ (most reliable for Frappe child tables)
					try:
						if hasattr(item, '__dict__') and 'item_code' in item.__dict__:
							del item.__dict__['item_code']
							removed = True
					except (KeyError, TypeError, AttributeError):
						pass
					
					# Method 2: Use delattr if attribute still exists
					if not removed:
						try:
							if hasattr(item, 'item_code'):
								delattr(item, 'item_code')
								removed = True
						except AttributeError:
							pass
					
					# Method 3: Set to None as fallback (Link fields may accept None)
					if not removed:
						try:
							setattr(item, 'item_code', None)
							item.item_code = None
						except:
							pass
	
	def before_save(self):
		"""
		Populate item_code from model_serial_no before saving.
		CRITICAL: Only sets item_code if Item already exists to prevent LinkValidationError.
		Items are created in before_submit() if they don't exist.
		"""
		# if not self.is_new() and self.items:
		# 	# For existing documents, set item_code only if Item exists
		# 	self.set_item_code()
		
		# Process additional operations if Load Plan exists
		if self.items and self.has_valid_load_plan():
			self.create_serial_nos()
			self.set_fields_value()
			self.update_item_pricing_fields()
			self.set_item_group()
			self.set_supplier()
	
	def on_submit(self):
		"""
		On submit, set status and update Load Plan.
		Note: Items are created in before_submit() hook, not here.
		"""
		# Set Load Dispatch status to "In-Transit" when submitted
		self.db_set("status", "In-Transit")
		self.add_dispatch_quanity_to_load_plan(docstatus=1)
	
	def validate(self):
		"""
		Validate Load Dispatch.
		CRITICAL: Items are NOT created here to allow saving documents in Draft state.
		Only set item_code if Item already exists to prevent LinkValidationError.
		Items are created in before_submit() hook before link validation runs.
		"""
		if not self.items:
			# Calculate total dispatch quantity
			self.calculate_total_dispatch_quantity()
			return
		
		# STEP 1: FIRST, remove ALL item_codes that don't have valid Items
		# This must happen FIRST to prevent LinkValidationError
		# Use multiple methods to ensure item_code is completely removed
		for item in self.items:
			item_code_value = getattr(item, 'item_code', None)
			if item_code_value:
				item_code_str = str(item_code_value).strip() if item_code_value else ""
				if item_code_str and not frappe.db.exists("Item", item_code_str):
					# Item doesn't exist - remove item_code using all possible methods
					# Method 1: Delete from __dict__
					try:
						if hasattr(item, '__dict__') and 'item_code' in item.__dict__:
							del item.__dict__['item_code']
					except (KeyError, TypeError):
						pass
					# Method 2: Use delattr
					try:
						if hasattr(item, 'item_code'):
							delattr(item, 'item_code')
					except AttributeError:
						pass
					# Method 3: Set to None (some Link fields accept this)
					try:
						item.item_code = None
					except:
						pass
					# Method 4: Use setattr with None
					try:
						setattr(item, 'item_code', None)
					except:
						pass
		
		# STEP 2: Now, only set item_code from model_serial_no if Item already exists
		# This prevents LinkValidationError when saving draft documents
		# Items will be created in before_submit() before link validation runs
		for item in self.items:
			# Skip if item_code is already set (it's valid since STEP 1 cleared invalid ones)
			if getattr(item, 'item_code', None):
				continue
			
			# If item_code is not set, try to set it from model_serial_no only if Item exists
			if item.model_serial_no and str(item.model_serial_no).strip():
				item_code = str(item.model_serial_no).strip()
				# Only set item_code if Item exists, otherwise leave it empty
				if frappe.db.exists("Item", item_code):
					item.item_code = item_code
				# else: Do not set item_code - Items will be created in before_submit()
		
		# Final safety check: Ensure no invalid item_codes remain
		# This prevents LinkValidationError by removing any item_code that doesn't have a corresponding Item
		for item in self.items:
			item_code_value = getattr(item, 'item_code', None)
			if item_code_value:
				item_code_str = str(item_code_value).strip() if item_code_value else ""
				if item_code_str and not frappe.db.exists("Item", item_code_str):
					# Item doesn't exist - remove item_code completely using __dict__ deletion
					try:
						if hasattr(item, '__dict__'):
							if 'item_code' in item.__dict__:
								del item.__dict__['item_code']
							# Also try to unset using delattr
							if hasattr(item, 'item_code'):
								delattr(item, 'item_code')
					except (AttributeError, KeyError, TypeError):
						# If deletion fails, try setting to None as last resort
						try:
							setattr(item, 'item_code', None)
						except:
							pass
		
		# For rows with item_code set, verify the Item exists (link validation will handle this)
		# For rows without item_code, they will be handled in before_submit
		# No Item creation happens here - only validation of existing item_codes
		
		# Process items if Load Plan exists (for additional operations)
		if self.items and self.has_valid_load_plan():
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
		
		# Note: Load Plan validation is done in before_submit to allow saving without Load Plan
		# This enables importing CSV data first, then creating/submitting Load Plan later
		
		# Check for duplicate frame numbers in Serial No doctype from submitted Load Dispatch documents
		# and skip those items
		self._filter_duplicate_frame_numbers()
		
		# Calculate total dispatch quantity from child table
		self.calculate_total_dispatch_quantity()
	
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
	
	def set_item_code(self):
		"""
		Populate item_code from model_serial_no for all items.
		CRITICAL: Only sets item_code if Item already exists to prevent LinkValidationError.
		Items will be created in before_submit() if they don't exist.
		If item_code is already set and valid, it will be preserved.
		"""
		
		if not self.items:
			return
		
		for item in self.items:
			# If item_code is already set and Item exists, keep it
			if item.item_code and str(item.item_code).strip():
				existing_item_code = str(item.item_code).strip()
				if frappe.db.exists("Item", existing_item_code):
					# Item exists, keep the existing item_code
					continue
				else:
					# Item doesn't exist, clear item_code
					item.item_code = None
			
			# If item_code is not set or was cleared, try to set it from model_serial_no
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

	def update_item_pricing_fields(self):
		"""
		Update Item doctypes with pricing/GST values from Load Dispatch Items.
		This runs on save/validate so existing Items get refreshed too.
		"""
		# Only update pricing if Load Plan exists
		if not self.has_valid_load_plan():
			return
		
		if not self.items:
			return

		custom_field_map = {field: field for field in ITEM_CUSTOM_FIELDS}

		for item in self.items:
			item_code = (item.model_serial_no or "").strip()
			if not item_code:
				continue
			if not frappe.db.exists("Item", item_code):
				continue
			
			# Ensure print_name is calculated before updating Item
			if not hasattr(item, "print_name") or not item.print_name:
				model_name = getattr(item, "model_name", None)
				item.print_name = calculate_print_name(item.model_serial_no, model_name)
			item_doc = frappe.get_doc("Item", item_code)
			updated = False

			for child_field, item_field in custom_field_map.items():
				if hasattr(item, child_field):
					child_value = getattr(item, child_field)
					# Allow zero/falsey numeric values to flow through; skip only if None or empty string
					if child_value is not None and child_value != "":
						if hasattr(item_doc, item_field):
							setattr(item_doc, item_field, child_value)
							updated = True
			
			# Update custom_print_name from Load Dispatch Item's print_name
			if hasattr(item, "print_name") and item.print_name:
				if hasattr(item_doc, "custom_print_name"):
					item_doc.custom_print_name = item.print_name
					updated = True

			if updated:
				item_doc.save(ignore_permissions=True)
	
	def set_item_group(self):
		"""Set item_group for Load Dispatch Items based on model_name or default."""
		# Only set item_group if Load Plan exists
		if not self.has_valid_load_plan():
			return
		
		if not self.items:
			return
		
		for item in self.items:
			# Only set item_group if the field exists on LoadDispatchItem
			if hasattr(item, 'item_group') and not item.item_group and item.model_name:
				# Check if model_name exists as an Item Group
				if frappe.db.exists("Item Group", item.model_name):
					item.item_group = item.model_name
				else:
					# Fall back to "Two Wheeler Vehicle" if model_name not found
					if frappe.db.exists("Item Group", "Two Wheeler Vehicle"):
						item.item_group = "Two Wheeler Vehicle"
	
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

	def before_submit(self):
		"""
		Validate Load Plan and create Items before submitting Load Dispatch.
		CRITICAL: Items are created here (before link validation) to prevent LinkValidationError.
		This runs before _validate_links(), ensuring all Items exist before link validation.
		"""
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
		
		# Create Items for rows that don't have item_code but have model_serial_no
		# This happens BEFORE link validation runs, so all Items will exist when validation occurs
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
	
	def _filter_duplicate_frame_numbers(self):
		"""
		Filter out Load Dispatch Items that have frame numbers already existing 
		in Serial No doctype from submitted Load Dispatch documents.
		Shows a message for each skipped item.
		"""
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
	
	def _ensure_default_item_group(self):
		"""Ensure a default Item Group exists. Creates 'Two Wheeler Vehicle' if it doesn't exist."""
		# Check if "Two Wheeler Vehicle" exists
		if frappe.db.exists("Item Group", "Two Wheeler Vehicle"):
			return "Two Wheeler Vehicle"
		
		# Check if "All Item Groups" exists (standard Frappe parent group)
		parent_group = "All Item Groups"
		if not frappe.db.exists("Item Group", parent_group):
			# Try to find any group that can be a parent
			parent_group = frappe.db.get_value("Item Group", {"is_group": 1}, "name", order_by="name")
			if not parent_group:
				# No parent group exists - can't create Item Group
				return None
		
		# Create "Two Wheeler Vehicle" Item Group
		try:
			default_group = frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": "Two Wheeler Vehicle",
				"is_group": 0,
				"parent_item_group": parent_group
			})
			default_group.insert(ignore_permissions=True)
			frappe.db.commit()
			return "Two Wheeler Vehicle"
		except Exception as e:
			# Log error but don't fail - will use fallback logic
			frappe.log_error(f"Could not create default Item Group 'Two Wheeler Vehicle': {str(e)}", "Item Group Creation Failed")
			return None
	
	def create_items_from_dispatch_items(self):
		"""
		Create Items in Item doctype for all load_dispatch_items that have model_serial_no.
		Populates Supplier and HSN Code from RKG Settings.
		Can work without Load Plan to allow saving documents before Load Plan is created.
		"""
		if not self.items:
			return
		
		# Ensure default Item Group exists if no Item Groups are found
		self._ensure_default_item_group()
		
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
			
			# Ensure item_code is set on the item ONLY if Item exists
			# This ensures item_code is always set from model_serial_no when Item exists
			if frappe.db.exists("Item", item_code):
				item.item_code = item_code
			else:
				# Item doesn't exist - don't set item_code, it will be created in before_submit()
				# Remove item_code if it was set
				if hasattr(item, '__dict__') and 'item_code' in item.__dict__:
					try:
						del item.__dict__['item_code']
					except:
						pass
			
			# Note: item_code is set from model_serial_no or existing item_code ONLY if Item exists
			
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
					
					# Update custom_print_name from Load Dispatch Item's print_name
					if hasattr(item, "print_name") and item.print_name:
						if hasattr(item_doc, "custom_print_name"):
							item_doc.custom_print_name = item.print_name
							updated = True

					if updated:
						item_doc.save(ignore_permissions=True)
						updated_items.append(item_code)
					else:
						skipped_items.append(item_code)
					continue

				# Determine item_group - use model_name as Item Group, create if it doesn't exist
				item_group = None
				
				# First, ensure we have a parent Item Group to use
				parent_item_group = "All Item Groups"
				if not frappe.db.exists("Item Group", parent_item_group):
					# Try to find any group that can be a parent
					parent_item_group = frappe.db.get_value("Item Group", {"is_group": 1}, "name", order_by="name")
					if not parent_item_group:
						# No parent group exists - this is a critical issue
						error_msg = _(
							"No parent Item Group found in the system. Items cannot be created without an Item Group structure.\n\n"
							"Please ensure 'All Item Groups' exists or create a parent Item Group first."
						)
						frappe.log_error(
							f"Item creation failed for {item_code}: No parent Item Group found",
							"Item Creation - Missing Parent Item Group"
						)
						frappe.throw(error_msg, title=_("Item Group Structure Required"))
				
				# Use model_name as Item Group - create it if it doesn't exist
				if item.model_name and str(item.model_name).strip():
					model_name = str(item.model_name).strip()
					if frappe.db.exists("Item Group", model_name):
						item_group = model_name
					else:
						# Create Item Group from model_name
						try:
							new_item_group = frappe.get_doc({
								"doctype": "Item Group",
								"item_group_name": model_name,
								"is_group": 0,
								"parent_item_group": parent_item_group
							})
							new_item_group.insert(ignore_permissions=True)
							frappe.db.commit()
							item_group = model_name
							frappe.log_error(
								f"Created Item Group '{model_name}' for Item {item_code}",
								"Item Group Auto-Creation"
							)
						except Exception as e:
							# If creation fails, log and fall back to default
							frappe.log_error(
								f"Failed to create Item Group '{model_name}': {str(e)}",
								"Item Group Creation Failed"
							)
							# Fall through to default Item Group
				
				# Fall back to "Two Wheeler Vehicle" if model_name not available or creation failed
				if not item_group:
					if frappe.db.exists("Item Group", "Two Wheeler Vehicle"):
						item_group = "Two Wheeler Vehicle"
					else:
						# Create "Two Wheeler Vehicle" as default
						try:
							default_group = frappe.get_doc({
								"doctype": "Item Group",
								"item_group_name": "Two Wheeler Vehicle",
								"is_group": 0,
								"parent_item_group": parent_item_group
							})
							default_group.insert(ignore_permissions=True)
							frappe.db.commit()
							item_group = "Two Wheeler Vehicle"
						except Exception as e:
							# Last resort: get any available item group
							any_group = frappe.db.get_value("Item Group", {}, "name", order_by="name")
							if any_group:
								item_group = any_group
							else:
								error_msg = _(
									"Could not create or find an Item Group. Items cannot be created without an Item Group.\n\n"
									"Error: {0}\n\n"
									"Please create an Item Group manually and try again."
								).format(str(e))
								frappe.log_error(
									f"Item creation failed for {item_code}: Could not create/find Item Group",
									"Item Creation - Item Group Error"
								)
								frappe.throw(error_msg, title=_("Item Group Required"))
				
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
				
				# Set custom_print_name from Load Dispatch Item's print_name
				if hasattr(item, "print_name") and item.print_name:
					if hasattr(item_doc, "custom_print_name"):
						item_doc.custom_print_name = item.print_name

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
				  "• Missing Item Group (ensure 'Two Wheeler Vehicle' Item Group exists)\n"
				  "• Validation errors in Item creation\n"
				  "• Database constraints").format(
					len(failed_items),
					failed_list
				),
				title=_("Item Creation Failed")
			)


def calculate_print_name(model_serial_no, model_name=None):
	"""
	Calculate Print Name from Model Name and Model Serial Number.
	Logic: Model Name + (Model Serial Number up to "-ID") + (BS-VI)
	
	Example:
		model_name: "CB125 HORNET OBD2B"
		model_serial_no: "CBF125ZTIDNHB05" or "CBF125ZT-IDNHB05"
		Output: "CB125 HORNET OBD2B (CBF125ZT-ID) (BS-VI)"
	
	Args:
		model_serial_no: The Model Serial Number string
		model_name: The Model Name string (optional)
		
	Returns:
		Calculated Print Name string
	"""
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


@frappe.whitelist()
def process_tabular_file(file_url, selected_load_reference_no=None):
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
				"Model": "model_variant",  # Map to model_variant field
				"Model Variant": "model_variant",
				"Model Name": "model_name",
				"Model Serial No": "model_serial_no",
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
				"Battery No": "battery_no",
				# Legacy mappings for backward compatibility
				"HMSI/InterDealer Load Reference No": "hmsi_load_reference_no",
				"Invoice No.": "invoice_no",
				"Frame #": "frame_no",
				"Engine No/Motor No": "engnie_no_motor_no",
				"Color Code": "color_code",
			}
			
			# Required headers that MUST be present in the CSV (core), case/space-insensitive
			# Note: "Print Name" is calculated from Model Serial Number, so it's not required from CSV
			required_headers_core = [
				"HMSI Load Reference No",
				"Invoice No",
				"Dispatch Date",
				"Frame No",
				"Engine no",
				"Key No",
				"Model Name",
				"Colour",
				"Tax Rate",
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
			
			# Detect if this is a Load Plan CSV file (has Load Plan headers)
			load_plan_headers = [
				"load reference no", "dispatch plan date", "payment plan date",
				"model", "model name", "type", "variant", "color", "group color", "option", "quantity"
			]
			norm_found_headers = set(norm_csv_headers.keys())
			load_plan_header_count = sum(1 for h in load_plan_headers if h in norm_found_headers)
			
			# If most Load Plan headers are present, this is likely a Load Plan CSV
			if load_plan_header_count >= 5:
				frappe.throw(
					_("This appears to be a <b>Load Plan</b> CSV file, not a <b>Load Dispatch</b> CSV file.\n\n"
					  "Load Dispatch requires different headers including:\n"
					  "• HMSI Load Reference No\n"
					  "• Invoice No\n"
					  "• Dispatch Date\n"
					  "• Frame No\n"
					  "• Engine no\n"
					  "• Key No\n"
					  "• Model Serial No\n"
					  "• Price/Unit\n"
					  "• And other dispatch-specific fields\n\n"
					  "<b>Please use a Load Dispatch CSV file</b> with the correct headers, or create a Load Plan first using this file."),
					title=_("Wrong CSV File Type")
				)
			
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
					# Skip Print Name - it will be calculated from Model Serial Number
					if fieldname == "print_name":
						continue
					# CRITICAL: Skip item_code - it will be set on submit only if Item exists
					if fieldname == "item_code":
						continue
					
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
								if value:
									# Remove commas (thousand separators) before converting to float
									cleaned_value = str(value).replace(",", "").strip()
									row_data[fieldname] = float(cleaned_value) if cleaned_value else 0.0
								else:
									row_data[fieldname] = 0.0
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
				
				# CRITICAL: Explicitly remove item_code if it somehow got into row_data
				if "item_code" in row_data:
					del row_data["item_code"]
				
				# Calculate print_name from model_name and model_serial_no (don't read from CSV)
				if "model_serial_no" in row_data and row_data["model_serial_no"]:
					model_name = row_data.get("model_name", None)
					row_data["print_name"] = calculate_print_name(row_data["model_serial_no"], model_name)
				    
				if row_data:
					rows.append(row_data)
			
			# Validate that we have at least one hmsi_load_reference_no if we have rows
			if rows and not csv_load_reference_nos:
				frappe.throw(
					_("CSV file contains rows but no Load Reference Numbers found. Please ensure the 'HMSI Load Reference No' column has values in all rows."),
					title=_("Missing Load Reference Numbers")
				)
			
			# Validate that Load Plans exist for all hmsi_load_reference_no values from CSV
			if csv_load_reference_nos:
				missing_load_plans = []
				for load_ref_no in csv_load_reference_nos:
					if not frappe.db.exists("Load Plan", load_ref_no):
						missing_load_plans.append(load_ref_no)
				
				if missing_load_plans:
					missing_list = "\n".join([f"• {ref_no}" for ref_no in sorted(missing_load_plans)])
					frappe.throw(
						_("Load Plan Validation Failed!\n\n"
						  "The following Load Reference Numbers from the CSV do not have corresponding Load Plans:\n{0}\n\n"
						  "Please create and submit Load Plans for these Load Reference Numbers before importing the CSV.").format(missing_list),
						title=_("Load Plan Not Found")
					)
				
				# Also validate that all Load Plans are submitted
				unsubmitted_load_plans = []
				for load_ref_no in csv_load_reference_nos:
					load_plan = frappe.get_doc("Load Plan", load_ref_no)
					if load_plan.docstatus != 1:
						unsubmitted_load_plans.append(load_ref_no)
				
				if unsubmitted_load_plans:
					unsubmitted_list = "\n".join([f"• {ref_no}" for ref_no in sorted(unsubmitted_load_plans)])
					frappe.throw(
						_("Load Plan Validation Failed!\n\n"
						  "The following Load Reference Numbers have Load Plans that are not submitted:\n{0}\n\n"
						  "Please submit these Load Plans before importing the CSV.").format(unsubmitted_list),
						title=_("Load Plan Not Submitted")
					)
			
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
			
			print(rows)
			print("\n\n")
			return rows
		finally:
			if csvfile:
				csvfile.close()
			
	except Exception as e:
		frappe.log_error(f"Error processing CSV file: {str(e)}", "CSV Import Error")
		frappe.throw(f"Error processing CSV file: {str(e)}")
@frappe.whitelist()
def preserve_purchase_receipt_uom(doc, method=None):
	"""
	Preserve UOM from Load Dispatch Item's unit field when Purchase Receipt is validated.
	This ensures UOM doesn't get converted to Item's stock_uom during validation.
	"""
	preserve_uom_from_load_dispatch(doc, "Purchase Receipt")

@frappe.whitelist()
def preserve_purchase_invoice_uom(doc, method=None):
	"""
	Preserve UOM from Load Dispatch Item's unit field when Purchase Invoice is validated.
	This ensures UOM doesn't get converted to Item's stock_uom during validation.
	"""
	preserve_uom_from_load_dispatch(doc, "Purchase Invoice")

def preserve_uom_from_load_dispatch(doc, doctype_name):
	"""
	Generic function to preserve UOM from Load Dispatch Item's unit field.
	Works for Purchase Receipt and Purchase Invoice.
	"""
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
				# Set UOM if it's different from what's currently set
				if hasattr(doc_item, "uom") and doc_item.uom != uom_value:
					doc_item.uom = uom_value
				if hasattr(doc_item, "stock_uom") and doc_item.stock_uom != uom_value:
					doc_item.stock_uom = uom_value

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

@frappe.whitelist()
def create_purchase_receipt(source_name, target_doc=None, warehouse=None, frame_no=None, frame_warehouse_mapping=None):
	"""Create Purchase Receipt from Load Dispatch"""
	from frappe.model.mapper import get_mapped_doc
	import json
	
	# Check if Purchase Receipt already exists for this Load Dispatch
	if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
		existing_pr = frappe.get_all(
			"Purchase Receipt",
			filters={
				"custom_load_dispatch": source_name
			},
			fields=["name"],
			limit=1
		)
		
		if existing_pr:
			frappe.throw(
				__("Purchase Receipt {0} already exists for this Load Dispatch. Cannot create another Purchase Receipt.", [existing_pr[0].name])
			)
	
	# Build frame to warehouse mapping dictionary
	frame_warehouse_map = {}
	selected_warehouse = None
	if frame_warehouse_mapping:
		# Parse frame_warehouse_mapping if it's a JSON string
		if isinstance(frame_warehouse_mapping, str):
			try:
				frame_warehouse_mapping = json.loads(frame_warehouse_mapping)
			except (json.JSONDecodeError, ValueError):
				# Try using Frappe's parse_json as fallback
				frame_warehouse_mapping = frappe.parse_json(frame_warehouse_mapping)
		
		# frame_warehouse_mapping is a list of dicts: [{"frame_no": "xxx", "warehouse": "yyy"}, ...]
		if isinstance(frame_warehouse_mapping, list):
			for mapping in frame_warehouse_mapping:
				# Handle both dict and string cases
				if isinstance(mapping, dict):
					frame_no_key = str(mapping.get("frame_no", "")).strip()
					warehouse_value = str(mapping.get("warehouse", "")).strip()
				elif isinstance(mapping, str):
					# If mapping is a string, try to parse it
					mapping = frappe.parse_json(mapping)
					frame_no_key = str(mapping.get("frame_no", "")).strip()
					warehouse_value = str(mapping.get("warehouse", "")).strip()
				else:
					continue
				
				if frame_no_key and warehouse_value:
					frame_warehouse_map[frame_no_key] = warehouse_value
	elif warehouse:
		# Legacy support: if warehouse is provided but no mapping, use it for all
		selected_warehouse = warehouse
	
	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		# Set load_reference_no from source
		target.custom_load_reference_no = source.load_reference_no
		
		# Set custom_load_dispatch on Purchase Receipt so it can be tracked
		if hasattr(target, "custom_load_dispatch"):
			target.custom_load_dispatch = source_name
		elif frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
			target.db_set("custom_load_dispatch", source_name)
		
		# Only set update_stock to 1 if the Purchase Receipt is NOT created from a Purchase Receipt
		# If it's created from PR, stock was already updated and we shouldn't update again
		has_purchase_receipt = False
		if hasattr(target, "items") and target.items:
			for item in target.items:
				if hasattr(item, "purchase_receipt") and item.purchase_receipt:
					has_purchase_receipt = True
					break
		
		if not has_purchase_receipt and hasattr(target, "update_stock"):
			# Set update_stock to 1 only if not created from Purchase Receipt
			# This ensures serial_no field is visible when creating directly from Load Dispatch
			target.update_stock = 1
		
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
		
		# Set "Use Serial No / Batch Fields" to checked by default on child table item
		if hasattr(target, "use_serial_batch_fields"):
			target.use_serial_batch_fields = 1
		
		# Get UOM from Load Dispatch Item's unit field (prioritize this), or from Item's stock_uom, default to "Pcs"
		uom_value = "Pcs"  # Default
		if hasattr(source, "unit") and source.unit:
			# Prioritize Load Dispatch Item's unit field
			uom_value = str(source.unit).strip()
		elif target.item_code:
			# Fallback to Item's stock_uom if unit is not set in Load Dispatch Item
			item_stock_uom = frappe.db.get_value("Item", target.item_code, "stock_uom")
			if item_stock_uom:
				uom_value = item_stock_uom
		
		# Set UOM for Purchase Receipt Item - set both uom and stock_uom to ensure consistency
		if hasattr(target, "uom"):
			target.uom = uom_value
		if hasattr(target, "stock_uom"):
			target.stock_uom = uom_value
		
		# Set item_group from source if available, otherwise get from Item
		if hasattr(source, "item_group") and source.item_group:
			# If Purchase Receipt Item has item_group field, set it
			if hasattr(target, "item_group"):
				target.item_group = source.item_group
		elif target.item_code:
			# Get item_group from Item doctype
			item_group = frappe.db.get_value("Item", target.item_code, "item_group")
			if item_group and hasattr(target, "item_group"):
				target.item_group = item_group
		
		# Set warehouse based on frame mapping
		item_warehouse = None
		if frame_warehouse_map and hasattr(source, "frame_no") and source.frame_no:
			frame_no_key = str(source.frame_no).strip()
			if frame_no_key in frame_warehouse_map:
				item_warehouse = frame_warehouse_map[frame_no_key]
		
		# Fallback to selected_warehouse if no mapping found
		if not item_warehouse and selected_warehouse:
			item_warehouse = selected_warehouse
		
		if item_warehouse and hasattr(target, "warehouse"):
			target.warehouse = item_warehouse

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
				},
				"postprocess": update_item
			},
		},
		target_doc,
		set_missing_values
	)
	
	# # After document creation, ensure serial_no is set on all items
	# # This is needed because the field might not have been visible during mapping
	# if doc and hasattr(doc, "items"):
	# 	# Get the source Load Dispatch document to map frame_no to serial_no
	# 	source_doc = frappe.get_doc("Load Dispatch", source_name)
	# 	if source_doc and hasattr(source_doc, "items"):
	# 		# Create a mapping of item_code to frame_no from source
	# 		item_to_frame = {}
	# 		for dispatch_item in source_doc.items:
	# 			if (hasattr(dispatch_item, "item_code") and dispatch_item.item_code and
	# 				hasattr(dispatch_item, "frame_no") and dispatch_item.frame_no):
	# 				item_to_frame[dispatch_item.item_code] = str(dispatch_item.frame_no).strip()
			
	# 		# Set serial_no on Purchase Invoice Items
	# 		for item in doc.items:
	# 			if hasattr(item, "item_code") and item.item_code and item.item_code in item_to_frame:
	# 				frame_no_value = item_to_frame[item.item_code]
	# 				if frame_no_value:
	# 					# Set serial_no using multiple methods to ensure it works
	# 					if hasattr(item, "serial_no"):
	# 						item.serial_no = frame_no_value
	# 					# Also set directly in __dict__ as fallback
	# 					if hasattr(item, "__dict__"):
	# 						item.__dict__["serial_no"] = frame_no_value
	
	# Save the document and return it
	if doc:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"name": doc.name}
	
	return None

@frappe.whitelist()
def create_purchase_invoice(source_name, target_doc=None, warehouse=None, frame_no=None, frame_warehouse_mapping=None):
	"""Create Purchase Invoice from Load Dispatch"""
	from frappe.model.mapper import get_mapped_doc
	import json
	
	# Check if Purchase Invoice already exists for this Load Dispatch
	if frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
		existing_pi = frappe.get_all(
			"Purchase Invoice",
			filters={
				"custom_load_dispatch": source_name
			},
			fields=["name"],
			limit=1
		)
		
		if existing_pi:
			frappe.throw(
				__("Purchase Invoice {0} already exists for this Load Dispatch. Cannot create another Purchase Invoice.", [existing_pi[0].name])
			)
	
	# Build frame to warehouse mapping dictionary
	frame_warehouse_map = {}
	selected_warehouse = None
	if frame_warehouse_mapping:
		# Parse frame_warehouse_mapping if it's a JSON string
		if isinstance(frame_warehouse_mapping, str):
			try:
				frame_warehouse_mapping = json.loads(frame_warehouse_mapping)
			except (json.JSONDecodeError, ValueError):
				# Try using Frappe's parse_json as fallback
				frame_warehouse_mapping = frappe.parse_json(frame_warehouse_mapping)
		
		# frame_warehouse_mapping is a list of dicts: [{"frame_no": "xxx", "warehouse": "yyy"}, ...]
		if isinstance(frame_warehouse_mapping, list):
			for mapping in frame_warehouse_mapping:
				# Handle both dict and string cases
				if isinstance(mapping, dict):
					frame_no_key = str(mapping.get("frame_no", "")).strip()
					warehouse_value = str(mapping.get("warehouse", "")).strip()
				elif isinstance(mapping, str):
					# If mapping is a string, try to parse it
					mapping = frappe.parse_json(mapping)
					frame_no_key = str(mapping.get("frame_no", "")).strip()
					warehouse_value = str(mapping.get("warehouse", "")).strip()
				else:
					continue
				
				if frame_no_key and warehouse_value:
					frame_warehouse_map[frame_no_key] = warehouse_value
	elif warehouse:
		# Legacy support: if warehouse is provided but no mapping, use it for all
		selected_warehouse = warehouse
	
	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		# Set load_reference_no from source
		target.custom_load_reference_no = source.load_reference_no
		
		# Set custom_load_dispatch on Purchase Invoice so it can be tracked
		if hasattr(target, "custom_load_dispatch"):
			target.custom_load_dispatch = source_name
		elif frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
			target.db_set("custom_load_dispatch", source_name)
		
		# Only set update_stock to 1 if the Purchase Invoice is NOT created from a Purchase Receipt
		# If it's created from PR, stock was already updated and we shouldn't update again
		# This prevents the validation error: "Stock cannot be updated against Purchase Receipt"
		has_purchase_receipt = False
		if hasattr(target, "items") and target.items:
			for item in target.items:
				if hasattr(item, "purchase_receipt") and item.purchase_receipt:
					has_purchase_receipt = True
					break
		
		if not has_purchase_receipt and hasattr(target, "update_stock"):
			# Set update_stock to 1 only if not created from Purchase Receipt
			# This ensures serial_no field is visible when creating directly from Load Dispatch
			target.update_stock = 1
		
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
		
		# Set warehouse on items based on frame mapping
		if (frame_warehouse_map or selected_warehouse) and hasattr(target, "items") and target.items:
			for item in target.items:
				item_warehouse = None
				# Try to find warehouse from frame mapping using serial_no
				if frame_warehouse_map and hasattr(item, "serial_no") and item.serial_no:
					serial_no_key = str(item.serial_no).strip()
					if serial_no_key in frame_warehouse_map:
						item_warehouse = frame_warehouse_map[serial_no_key]
				
				# Fallback to selected_warehouse if no mapping found
				if not item_warehouse and selected_warehouse:
					item_warehouse = selected_warehouse
				
				# Set warehouse if found
				if item_warehouse:
					if hasattr(item, "warehouse"):
						item.warehouse = item_warehouse
					if hasattr(item, "target_warehouse"):
						item.target_warehouse = item_warehouse
	
	def update_item(source, target, source_parent):
		# Map item_code from Load Dispatch Item to Purchase Invoice Item
		target.item_code = source.item_code
		# Set quantity to 1
		target.qty = 1
		
		# Set "Use Serial No / Batch Fields" to checked by default on child table item
		# This is required for the depends_on condition: doc.use_serial_batch_fields === 1
		if hasattr(target, "use_serial_batch_fields"):
			target.use_serial_batch_fields = 1
		
		# Explicitly set serial_no from frame_no after use_serial_batch_fields is set
		# This ensures the field is populated even if field_map didn't work due to visibility
		# Use setattr to ensure the value is set even if the field isn't visible yet
		if hasattr(source, "frame_no") and source.frame_no:
			frame_no_value = str(source.frame_no).strip()
			if frame_no_value:
				# Try multiple ways to set the serial_no field
				if hasattr(target, "serial_no"):
					target.serial_no = frame_no_value
				# Also try using setattr directly on the dict
				if hasattr(target, "__dict__"):
					target.__dict__["serial_no"] = frame_no_value
				# Force set using setattr as fallback
				try:
					setattr(target, "serial_no", frame_no_value)
				except:
					pass
		
		# Get UOM from Load Dispatch Item's unit field (prioritize this), or from Item's stock_uom, default to "Pcs"
		uom_value = "Pcs"  # Default
		if hasattr(source, "unit") and source.unit:
			# Prioritize Load Dispatch Item's unit field
			uom_value = str(source.unit).strip()
		elif target.item_code:
			# Fallback to Item's stock_uom if unit is not set in Load Dispatch Item
			item_stock_uom = frappe.db.get_value("Item", target.item_code, "stock_uom")
			if item_stock_uom:
				uom_value = item_stock_uom
		
		# Set UOM for Purchase Invoice Item - set both uom and stock_uom to ensure consistency
		if hasattr(target, "uom"):
			target.uom = uom_value
		if hasattr(target, "stock_uom"):
			target.stock_uom = uom_value
		
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
		
		# Set warehouse based on frame mapping
		item_warehouse = None
		if frame_warehouse_map and hasattr(source, "frame_no") and source.frame_no:
			frame_no_key = str(source.frame_no).strip()
			if frame_no_key in frame_warehouse_map:
				item_warehouse = frame_warehouse_map[frame_no_key]
		
		# Fallback to selected_warehouse if no mapping found
		if not item_warehouse and selected_warehouse:
			item_warehouse = selected_warehouse
		
		if item_warehouse and hasattr(target, "warehouse"):
			target.warehouse = item_warehouse

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
	
	# After document creation, ensure serial_no is set on all items
	# This is needed because the field might not have been visible during mapping
	if doc and hasattr(doc, "items"):
		# Get the source Load Dispatch document to map frame_no to serial_no
		source_doc = frappe.get_doc("Load Dispatch", source_name)
		if source_doc and hasattr(source_doc, "items"):
			# Create a mapping of item_code to frame_no from source
			item_to_frame = {}
			for dispatch_item in source_doc.items:
				if (hasattr(dispatch_item, "item_code") and dispatch_item.item_code and
					hasattr(dispatch_item, "frame_no") and dispatch_item.frame_no):
					item_to_frame[dispatch_item.item_code] = str(dispatch_item.frame_no).strip()
			
			# Set serial_no on Purchase Invoice Items
			for item in doc.items:
				if hasattr(item, "item_code") and item.item_code and item.item_code in item_to_frame:
					frame_no_value = item_to_frame[item.item_code]
					if frame_no_value:
						# Set serial_no using multiple methods to ensure it works
						if hasattr(item, "serial_no"):
							item.serial_no = frame_no_value
						# Also set directly in __dict__ as fallback
						if hasattr(item, "__dict__"):
							item.__dict__["serial_no"] = frame_no_value
	
	# Save the document and return it
	if doc:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"name": doc.name}
	
	return None


def update_load_dispatch_totals_from_document(doc, method=None):
	"""
	Update Load Dispatch totals (total_received_quantity and total_billed_quantity)
	when Purchase Receipt or Purchase Invoice is submitted or cancelled.
	
	Logic:
	1. If Purchase Receipt is created from Load Dispatch → Update Total Received Quantity
	2. If Purchase Invoice is created from Load Dispatch → Update Total Billed Quantity
	3. If Purchase Receipt is created from Load Dispatch, and then Purchase Invoice is created 
	   from that Purchase Receipt → Both Total Received Quantity and Total Billed Quantity 
	   should be calculated and should show the same value
	
	On Submit: Updates with the submitted document's total_qty
	On Cancel: Recalculates totals from all remaining submitted documents (excludes cancelled one)
	
	Args:
		doc: Purchase Receipt or Purchase Invoice document
		method: Hook method name (optional)
	"""

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


@frappe.whitelist()
def check_existing_documents(load_dispatch_name):
	"""
	Check if Purchase Receipt or Purchase Invoice already exists for a Load Dispatch.
	
	Args:
		load_dispatch_name: Name of the Load Dispatch document
		
	Returns:
		dict: {
			"has_purchase_receipt": bool,
			"has_purchase_invoice": bool,
			"purchase_receipt_name": str or None,
			"purchase_invoice_name": str or None
		}
	"""
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


@frappe.whitelist()
def process_tabular_file(file_url, selected_load_reference_no=None):
	"""
	Process CSV/Excel file and return tabular data.
	
	For each row:
	1. Read Model Serial No (this is the Item Code)
	2. Check if Item exists with that Item Code (model_serial_no)
	3. If not, create the Item
	4. Then set item_code in the row data
	
	Args:
		file_url: URL of the attached file
		selected_load_reference_no: Optional Load Reference No from form
	
	Returns:
		List of dictionaries, each representing a row with item_code populated
	"""
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
		
		# Process each row: Only set item_code if Item already exists
		# Items will be created in before_submit() hook, not during CSV import
		processed_rows = []
		for idx, row in enumerate(rows, start=1):
			# Normalize the row data: map Excel column names to field names
			normalized_row = {}
			for excel_col, value in row.items():
				if is_empty_value(value):
					continue
				normalized_col = normalize_column_name(excel_col)
				
				# CRITICAL: Skip item_code column from CSV - it will be set from model_serial_no on submit
				# This prevents invalid item_code values from being imported
				# Check both normalized and original column names
				if normalized_col and normalized_col == 'item code':
					continue
				if excel_col and excel_col.lower().strip() in ['item_code', 'item code']:
					continue
				
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
					# Keep original column name if no mapping found, but skip item_code
					if excel_col.lower().strip() not in ['item_code', 'item code']:
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
			
			# Step 2: CRITICAL - NEVER set item_code in CSV import data
			# Items will be created in before_submit() and item_code will be set then
			# Explicitly remove item_code if it somehow got into normalized_row
			if 'item_code' in normalized_row:
				del normalized_row['item_code']
			
			# DO NOT set item_code here at all - it will be set in before_submit() when Items are created
			# This prevents LinkValidationError during draft saves
			
			processed_rows.append(normalized_row)
		
		return processed_rows
		
	except Exception as e:
		frappe.log_error(
			f"Error processing tabular file {file_url}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"process_tabular_file Error"
		)
		frappe.throw(_("Error processing file: {0}").format(str(e)))


def _create_item_from_row_data(row_data, item_code):
	"""
	Create an Item from row data (dictionary from CSV/Excel).
	
	Args:
		row_data: Dictionary containing row data from CSV/Excel
		item_code: Item Code (from Model Serial No)
	"""
	# Get Model Variant (for item_name)
	model_variant = (
		row_data.get('model_variant') or 
		row_data.get('Model Variant') or 
		row_data.get('MODEL_VARIANT') or 
		item_code
	)
	
	# Get Model Name (for item_group)
	model_name = (
		row_data.get('model_name') or 
		row_data.get('Model Name') or 
		row_data.get('MODEL_NAME')
	)
	
	# Get or create Item Group from Model Name
	item_group = _get_or_create_item_group_from_name(model_name)
	
	# Fetch HSN Code from RKG Settings (REQUIRED)
	rkg_settings = None
	try:
		rkg_settings = frappe.get_single("RKG Settings")
	except frappe.DoesNotExistError:
		frappe.throw(_("RKG Settings not found. Please create RKG Settings and set Default HSN Code."))
	
	hsn_code = rkg_settings.get("default_hsn_code")
	if not hsn_code:
		frappe.throw(_("Default HSN Code is not set in RKG Settings. Please set it before creating Items."))
	
	# Get UOM from row data's unit field, default to "Pcs" if not set
	stock_uom = "Pcs"  # Default to "Pcs"
	if row_data.get('unit'):
		stock_uom = str(row_data.get('unit')).strip()
	
	# Create Item document
	item_doc = frappe.get_doc({
		"doctype": "Item",
		"item_code": item_code,
		"item_name": str(model_variant).strip() if model_variant else item_code,
		"item_group": item_group,
		"stock_uom": stock_uom,
		"is_stock_item": 1,
		"has_serial_no": 1,
	})
	
	# Set HSN Code - try standard field first, then custom field
	if hasattr(item_doc, "gst_hsn_code"):
		item_doc.gst_hsn_code = hsn_code
	elif hasattr(item_doc, "custom_gst_hsn_code"):
		item_doc.custom_gst_hsn_code = hsn_code
	else:
		# If neither field exists, log warning but continue
		frappe.log_error(f"HSN Code field not found in Item doctype. Tried: gst_hsn_code, custom_gst_hsn_code", "HSN Code Field Missing")
	
	# Insert Item (ignoring permissions as per requirement)
	item_doc.insert(ignore_permissions=True)
	
	# Commit immediately to ensure Item exists
	frappe.db.commit()
	
	# Verify Item was created
	if not frappe.db.exists("Item", item_code):
		raise frappe.ValidationError(_("Item '{0}' was not created. Please check Error Log.").format(item_code))
	
	return item_doc


def _get_or_create_item_group_from_name(model_name):
	"""
	Get or create Item Group from Model Name.
	
	Args:
		model_name: Model Name from row data
	
	Returns:
		Item Group name (string)
	"""
	# First, ensure we have a parent Item Group
	parent_item_group = "All Item Groups"
	if not frappe.db.exists("Item Group", parent_item_group):
		# Try to find any existing parent group
		parent_item_group = frappe.db.get_value("Item Group", {"is_group": 1}, "name", order_by="name")
		if not parent_item_group:
			# Create "All Item Groups" if it doesn't exist
			try:
				all_groups = frappe.get_doc({
					"doctype": "Item Group",
					"item_group_name": "All Item Groups",
					"is_group": 1
				})
				all_groups.insert(ignore_permissions=True)
				frappe.db.commit()
				parent_item_group = "All Item Groups"
			except Exception as e:
				frappe.log_error(f"Failed to create 'All Item Groups': {str(e)}", "Item Group Creation Failed")
	
	# Use model_name as Item Group - create if it doesn't exist
	if model_name and str(model_name).strip():
		model_name = str(model_name).strip()
		if frappe.db.exists("Item Group", model_name):
			return model_name
		
		# Create Item Group from model_name
		try:
			new_item_group = frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": model_name,
				"is_group": 0,
				"parent_item_group": parent_item_group
			})
			new_item_group.insert(ignore_permissions=True)
			frappe.db.commit()
			return model_name
		except Exception as e:
			frappe.log_error(f"Failed to create Item Group '{model_name}': {str(e)}", "Item Group Creation Failed")
			# Fall through to default
	
	# Fall back to "Two Wheeler Vehicle"
	if frappe.db.exists("Item Group", "Two Wheeler Vehicle"):
		return "Two Wheeler Vehicle"
	
	# Create "Two Wheeler Vehicle" as default
	try:
		default_group = frappe.get_doc({
			"doctype": "Item Group",
			"item_group_name": "Two Wheeler Vehicle",
			"is_group": 0,
			"parent_item_group": parent_item_group
		})
		default_group.insert(ignore_permissions=True)
		frappe.db.commit()
		return "Two Wheeler Vehicle"
	except Exception as e:
		# Last resort: get any available item group
		any_group = frappe.db.get_value("Item Group", {}, "name", order_by="name")
		if any_group:
			return any_group
		frappe.throw(_("Could not create or find an Item Group. Please create one manually."))
