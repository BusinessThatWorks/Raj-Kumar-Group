import frappe
import csv
import os
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt


class LoadDispatch(Document):
	def has_valid_load_plan(self):
		"""Check if Load Dispatch has a valid Load Plan linked."""
		return bool(self.load_reference_no and frappe.db.exists("Load Plan", self.load_reference_no))
	
	def _create_single_item_from_dispatch_item(self, dispatch_item, item_code):
		"""Create a single Item from a Load Dispatch Item."""
		print_name_from_map = ((self._print_name_map.get(item_code) if hasattr(self, '_print_name_map') and self._print_name_map else None)
			or (getattr(frappe.local, 'load_dispatch_print_name_map', {}).get(item_code) if hasattr(frappe.local, 'load_dispatch_print_name_map') else None))
		
		if print_name_from_map:
			dispatch_item.print_name = print_name_from_map
			setattr(dispatch_item, 'print_name', print_name_from_map)
			if not hasattr(frappe.local, 'item_print_name_map'):
				frappe.local.item_print_name_map = {}
			frappe.local.item_print_name_map[item_code] = print_name_from_map
		
		return _create_item_unified(dispatch_item, item_code, source_type="dispatch_item", print_name=print_name_from_map)
	
	def before_insert(self):
		"""Verify item_code exists if set; Items created in before_submit hook."""
		if not self.items:
			return
		
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
	
	def before_save(self):
		"""Populate item_code from model_serial_no before saving (only if Item exists)."""
		if not self.is_new() and self.items:
			self.set_item_code()
		
		if self.items and self.has_valid_load_plan():
			self.create_serial_nos()
			self.set_fields_value()
			self.set_item_group()
			self.set_supplier()
		
		if self.items:
			self.sync_print_name_to_items()
	
	def on_submit(self):
		"""On submit, set status and update Load Plan."""
		self.db_set("status", "In-Transit")
		self.add_dispatch_quanity_to_load_plan(docstatus=1)
	
	def validate(self):
		"""Validate Load Dispatch (Items created in before_submit, not here)."""
		if not self.items:
			self.calculate_total_dispatch_quantity()
			return
		
		for item in self.items:
			if item.model_serial_no and str(item.model_serial_no).strip():
				item_code = str(item.model_serial_no).strip()
				if frappe.db.exists("Item", item_code):
					item.item_code = item_code
				else:
					item.item_code = None
		
		if self.items and self.has_valid_load_plan():
			self.create_serial_nos()
			self.set_fields_value()
			self.set_item_group()
		
		if self.items:
			self.sync_print_name_to_items()
		
		has_imported_items = any(item.frame_no and str(item.frame_no).strip() for item in (self.items or []))
		
		if has_imported_items:
			if self.is_new():
				if hasattr(self, '_load_reference_no_from_csv') and self._load_reference_no_from_csv:
					if self.load_reference_no != self._load_reference_no_from_csv:
						frappe.throw(
							_(
								"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported from CSV. The CSV data belongs to Load Reference Number '{0}'. Please clear all items first or use a CSV file that matches the desired Load Reference Number."
							).format(self._load_reference_no_from_csv, self.load_reference_no)
						)
			else:
				if self.has_value_changed("load_reference_no"):
					old_value = self.get_doc_before_save().get("load_reference_no") if self.get_doc_before_save() else None
					frappe.throw(
						_(
							"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported. Please clear all items first or create a new Load Dispatch document."
						).format(old_value or "None", self.load_reference_no)
					)
		
		self._filter_duplicate_frame_numbers()
		self.calculate_total_dispatch_quantity()
	
	def create_serial_nos(self):
		"""Create serial nos for all items on save."""
		if not self.has_valid_load_plan():
			return
		
		if self.items:
			has_purchase_date = frappe.db.has_column("Serial No", "purchase_date")
			for item in self.items:
				item_code = str(item.model_serial_no).strip() if item.model_serial_no else ""
				if item_code and item.frame_no:
					serial_no_name = str(item.frame_no).strip()

					if not frappe.db.exists("Serial No", serial_no_name):
						try:
							serial_no = frappe.get_doc({
								"doctype": "Serial No",
								"item_code": item_code,
								"serial_no": serial_no_name,
							})

							engnie_no = getattr(item, "engnie_no_motor_no", None)
							if engnie_no is not None and str(engnie_no).strip():
								if frappe.db.has_column("Serial No", "custom_engine_number"):
									serial_no.custom_engine_number = str(engnie_no).strip()

							key_no_value = getattr(item, "key_no", None)
							if key_no_value is not None and str(key_no_value).strip():
								if frappe.db.has_column("Serial No", "custom_key_no"):
									serial_no.custom_key_no = str(key_no_value).strip()

							color_code_value = getattr(item, "color_code", None)
							if color_code_value is not None and str(color_code_value).strip():
								if frappe.db.has_column("Serial No", "color_code"):
									serial_no.color_code = str(color_code_value).strip()

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
						engnie_no = getattr(item, "engnie_no_motor_no", None)
						if engnie_no is not None and str(engnie_no).strip():
							if frappe.db.has_column("Serial No", "custom_engine_number"):
								try:
									frappe.db.set_value(
										"Serial No",
										serial_no_name,
										"custom_engine_number",
										str(engnie_no).strip(),
										update_modified=False
									)
								except Exception as e:
									frappe.log_error(
										f"Error updating custom_engine_number for Serial No {serial_no_name}: {str(e)}",
										"Serial No Update Error",
									)
						
						key_no_value = getattr(item, "key_no", None)
						if key_no_value is not None and str(key_no_value).strip():
							if frappe.db.has_column("Serial No", "custom_key_no"):
								try:
									frappe.db.set_value(
										"Serial No",
										serial_no_name,
										"custom_key_no",
										str(key_no_value).strip(),
										update_modified=False
									)
								except Exception as e:
									frappe.log_error(
										f"Error updating custom_key_no for Serial No {serial_no_name}: {str(e)}",
										"Serial No Update Error",
									)

						color_code_value = getattr(item, "color_code", None)
						if color_code_value is not None and str(color_code_value).strip():
							if frappe.db.has_column("Serial No", "color_code"):
								try:
									frappe.db.set_value(
										"Serial No",
										serial_no_name,
										"color_code",
										str(color_code_value).strip(),
										update_modified=False
									)
								except Exception as e:
									frappe.log_error(
										f"Error updating color_code for Serial No {serial_no_name}: {str(e)}",
										"Serial No Update Error",
									)

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
		"""Populate item_code from model_serial_no, only if Item already exists."""
		if not self.items:
			return
		
		for item in self.items:
			if not item.model_serial_no or not str(item.model_serial_no).strip():
				continue
			
			item_code = str(item.model_serial_no).strip()
			
			if frappe.db.exists("Item", item_code):
				item.item_code = item_code
			else:
				item.item_code = None
	
	def set_fields_value(self):
		"""Set default values from RKG Settings if not already set."""
		if not self.items:
			return
		
		try:
			rkg_settings = frappe.get_single("RKG Settings")
		except frappe.DoesNotExistError:
			return
		
		for item in self.items:
			if hasattr(item, "model_serial_no") and item.model_serial_no:
				item.print_name = calculate_print_name(item.model_serial_no, getattr(item, "model_name", None))
			
			if hasattr(item, "price_unit") and item.price_unit:
				price_unit = flt(item.price_unit)
				if price_unit > 0:
					calculated_rate = price_unit / 1.18
					item.rate = calculated_rate

	def set_item_group(self):
		"""Set item_group for Load Dispatch Items based on model_name using unified function."""
		if not self.has_valid_load_plan():
			return
		
		if not self.items:
			return
		
		for item in self.items:
			if hasattr(item, 'item_group') and not item.item_group and item.model_name:
				item.item_group = _get_or_create_item_group_unified(item.model_name)
	
	def set_supplier(self):
		"""Set supplier for items from RKG Settings."""
		if not self.has_valid_load_plan():
			return
		
		if not self.items:
			return
		
		try:
			rkg_settings = frappe.get_single("RKG Settings")
			default_supplier = rkg_settings.get("default_supplier")
			
			if default_supplier:
				pass
		except frappe.DoesNotExistError:
			pass
	
	def sync_print_name_to_items(self):
		"""Sync print_name from Load Dispatch Item to Item doctype for all items with item_code."""
		if not self.items:
			return
		
		if not frappe.db.has_column("Item", "print_name"):
			return
		
		updated_items = []
		for item in self.items:
			if not item.item_code or not str(item.item_code).strip() or not frappe.db.exists("Item", (item_code := str(item.item_code).strip())):
				continue
			
			print_name = (str(item.print_name).strip() if hasattr(item, "print_name") and item.print_name else None)
			if not print_name and item.model_serial_no:
				print_name = calculate_print_name(item.model_serial_no, getattr(item, "model_name", None))
				item.print_name = print_name
			
			if print_name:
				current_print_name = frappe.db.get_value("Item", item_code, "print_name")
				if current_print_name != print_name:
					try:
						frappe.db.set_value("Item", item_code, "print_name", print_name, update_modified=False)
						updated_items.append(item_code)
					except Exception as e:
						frappe.log_error(
							f"Failed to sync print_name for Item {item_code}: {str(e)}",
							"Print Name Sync Error"
						)
		
		if updated_items:
			frappe.db.commit()
			frappe.clear_cache(doctype="Item")

	def before_submit(self):
		"""Validate Load Plan and create Items before submitting Load Dispatch."""
		if self.load_reference_no:
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
		
		if not self.items:
			return
		
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
		
		print_name_map = {}
		
		for item in self.items:
			if hasattr(item, "model_serial_no") and item.model_serial_no:
				model_serial_no = item.model_serial_no
				item_code = str(model_serial_no).strip()
				if not hasattr(item, "print_name") or not item.print_name or not str(item.print_name).strip():
					item.print_name = calculate_print_name(model_serial_no, getattr(item, "model_name", None))
				print_name_map[item_code] = item.print_name
		
		self._print_name_map = print_name_map
		
		if not hasattr(frappe.local, 'load_dispatch_print_name_map'):
			frappe.local.load_dispatch_print_name_map = {}
		frappe.local.load_dispatch_print_name_map.update(print_name_map)
		
		for item in self.items:
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
			
			if not item.model_serial_no or not str(item.model_serial_no).strip():
				continue
			
			item_code = str(item.model_serial_no).strip()
			
			if frappe.db.exists("Item", item_code):
				item.item_code = item_code
			else:
				try:
					print_name_for_item = self._print_name_map.get(item_code) if hasattr(self, '_print_name_map') and self._print_name_map else None
					if print_name_for_item:
						item.print_name = print_name_for_item
					
					self._create_single_item_from_dispatch_item(item, item_code)
					frappe.clear_cache(doctype="Item")
					frappe.db.commit()
					
					if frappe.db.exists("Item", item_code):
						item.item_code = item_code
					else:
						frappe.throw(
							_("Item '{0}' was not created for Row #{1} before submit. Please check Error Log.").format(
								item_code, getattr(item, 'idx', 'Unknown')
							),
							title=_("Item Creation Failed")
						)
				except Exception as e:
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
		"""Update Load Dispatch status based on received quantity from Load Receipt."""
		total_dispatch = flt(self.total_dispatch_quantity) or 0
		
		total_received = 0
		if frappe.db.has_column("Load Receipt", "load_dispatch"):
			load_receipts = frappe.get_all(
				"Load Receipt",
				filters={"load_dispatch": self.name},
				fields=["name", "total_receipt_quantity"],
				limit=1
			)
			if load_receipts:
				total_received = flt(load_receipts[0].get("total_receipt_quantity")) or 0
		
		if total_dispatch > 0 and total_received >= total_dispatch:
			new_status = "Received"
		else:
			new_status = "In-Transit"
		
		if self.status != new_status:
			frappe.db.set_value("Load Dispatch", self.name, "status", new_status, update_modified=False)
			self.status = new_status
	
	def add_dispatch_quanity_to_load_plan(self, docstatus):
		"""Update load_dispatch_quantity in Load Plan when Load Dispatch is submitted or cancelled."""
		if not self.load_reference_no:
			return
		
		if not self.total_dispatch_quantity:
			self.calculate_total_dispatch_quantity()
		
		current_quantity = frappe.db.get_value("Load Plan", self.load_reference_no, "load_dispatch_quantity") or 0
		
		if docstatus == 1:
			new_quantity = current_quantity + (self.total_dispatch_quantity or 0)
		elif docstatus == 2:
			new_quantity = max(0, current_quantity - (self.total_dispatch_quantity or 0))
		else:
			return
		
		status = 'In-Transit' if flt(new_quantity) > 0 else 'Submitted'
		
		frappe.db.set_value("Load Plan", self.load_reference_no, "load_dispatch_quantity", new_quantity, update_modified=False)
		frappe.db.set_value("Load Plan", self.load_reference_no, "status", status, update_modified=False)
	
	def calculate_total_dispatch_quantity(self):
		"""Count the number of rows with non-empty frame_no in Load Dispatch Item child table."""
		self.total_dispatch_quantity = sum(1 for item in (self.items or []) if item.frame_no and str(item.frame_no).strip())
	
	def _filter_duplicate_frame_numbers(self):
		"""Filter out Load Dispatch Items with frame numbers already existing in Serial No doctype."""
		if not self.items:
			return
		
		items_to_remove = []
		skipped_items = []
		
		for item in self.items:
			if not item.frame_no:
				continue
			
			frame_no = str(item.frame_no).strip()
			if not frame_no:
				continue
			
			item_code = (str(item.model_serial_no).strip() if item.model_serial_no and str(item.model_serial_no).strip() 
				else (str(item.item_code).strip() if hasattr(item, 'item_code') and item.item_code and str(item.item_code).strip() else None))
			
			if not item_code:
				continue
			
			if frappe.db.exists("Serial No", frame_no):
				if self.name:
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
					existing_doc_name = existing_load_dispatch_item[0].get('load_dispatch_name', 'Unknown')
					items_to_remove.append(item)
					skipped_items.append({
						'frame_no': frame_no,
						'item_code': item_code,
						'existing_doc': existing_doc_name
					})
		
		if items_to_remove:
			for item in items_to_remove:
				self.remove(item)
			
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
	
	def create_items_from_dispatch_items(self):
		"""Create Items from Load Dispatch Items, populating Supplier and HSN Code from RKG Settings."""
		if not self.items:
			return
		
		rkg_settings = None
		try:
			rkg_settings = frappe.get_single("RKG Settings")
		except frappe.DoesNotExistError:
			pass
		
		created_items = []
		updated_items = []
		skipped_items = []
		failed_items = []
		
		for item in self.items:
			item_code = (str(item.model_serial_no).strip() if item.model_serial_no and str(item.model_serial_no).strip()
				else (str(item.item_code).strip() if hasattr(item, 'item_code') and item.item_code and str(item.item_code).strip() else None))
			if not item_code:
				continue
			
			item.item_code = item_code
			if not hasattr(item, "print_name") or not item.print_name:
				item.print_name = calculate_print_name(item.model_serial_no, getattr(item, "model_name", None))
			
			try:
				if frappe.db.exists("Item", item_code):
					item_doc = frappe.get_doc("Item", item_code)
					updated = False
					
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

				model_name = str(item.model_name).strip() if (item.model_name and str(item.model_name).strip()) else None
				item_group = _get_or_create_item_group_unified(model_name)
				
				stock_uom = str(item.unit).strip() if hasattr(item, "unit") and item.unit else "Pcs"
				
				item_doc = frappe.get_doc({
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item.model_variant or item_code,
					"item_group": item_group,
					"stock_uom": stock_uom,
					"is_stock_item": 1,
					"has_serial_no": 1,

				})
				
				if rkg_settings and rkg_settings.get("default_supplier"):
					if hasattr(item_doc, "supplier_items"):
						item_doc.append("supplier_items", {
							"supplier": rkg_settings.default_supplier,
							"is_default": 1
						})
					elif hasattr(item_doc, "supplier"):
						item_doc.supplier = rkg_settings.default_supplier
				
				if hasattr(item, "hsn_code") and item.hsn_code:
					hsn_code = item.hsn_code
					if hasattr(item_doc, "gst_hsn_code"):
						item_doc.gst_hsn_code = hsn_code
					elif hasattr(item_doc, "custom_gst_hsn_code"):
						item_doc.custom_gst_hsn_code = hsn_code
				
				if hasattr(item, "print_name") and item.print_name:
					if hasattr(item_doc, "print_name"):
						item_doc.print_name = item.print_name

				item_doc.insert(ignore_permissions=True)
				created_items.append(item_code)
				
			except Exception as e:
				import traceback
				error_details = traceback.format_exc()
				frappe.log_error(
					f"Error creating Item {item_code}: {str(e)}\n{error_details}", 
					"Item Creation Error"
				)
				failed_items.append({
					"item_code": item_code,
					"error": str(e),
					"row": getattr(item, 'idx', 'Unknown')
				})
				continue
		
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
				_("Failed to create {0} Item(s). Please check error logs for details:\n\n{1}\n\nCommon causes:\n• Missing Item Group (ensure 'Two Wheelers Vehicle' Item Group exists)\n• Validation errors in Item creation\n• Database constraints").format(
					len(failed_items),
					failed_list
				),
				title=_("Item Creation Failed")
			)


def calculate_print_name(model_serial_no, model_name=None):
	"""Calculate Print Name: Model Name + (Model Serial Number up to "-ID") + (BS-VI)"""
	if not model_serial_no:
		return ""
	
	model_serial_no = str(model_serial_no).strip()
	if not model_serial_no:
		return ""
	
	model_serial_upper = model_serial_no.upper()
	id_index = model_serial_upper.find("-ID")
	
	if id_index != -1:
		serial_part = model_serial_no[:id_index + 3]
	else:
		id_index = model_serial_upper.find("ID")
		if id_index != -1:
			serial_part = model_serial_no[:id_index] + "-ID"
		else:
			serial_part = model_serial_no
	
	if model_name:
		model_name = str(model_name).strip()
		if model_name:
			return f"{model_name} ({serial_part}) (BS-VI)"
	
	# If no model_name, just use serial_part
	return f"{serial_part} (BS-VI)"
def update_load_dispatch_status_from_totals(doc, method=None):
	"""Update Load Dispatch status based on totals from Load Receipts when Purchase Receipt/Invoice is submitted or cancelled."""
	try:
		load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
			else (frappe.db.get_value(doc.doctype, doc.name, "custom_load_dispatch") if frappe.db.has_column(doc.doctype, "custom_load_dispatch") else None))

		if not load_dispatch_name:
			return

		if not frappe.db.exists("Load Dispatch", load_dispatch_name):
			return

		if not frappe.db.has_column("Load Receipt", "load_dispatch"):
			return

		load_receipts = frappe.get_all(
			"Load Receipt",
			filters={"load_dispatch": load_dispatch_name},
			fields=["name", "total_receipt_quantity"],
			limit=1
		)

		if not load_receipts:
			return

		total_received_qty = flt(load_receipts[0].get("total_receipt_quantity")) or 0
		total_dispatch_qty = frappe.db.get_value("Load Dispatch", load_dispatch_name, "total_dispatch_quantity") or 0
		
		if flt(total_dispatch_qty) > 0 and flt(total_received_qty) >= flt(total_dispatch_qty):
			new_status = "Received"
		else:
			new_status = "In-Transit"
		
		frappe.db.set_value(
			"Load Dispatch",
			load_dispatch_name,
			{
				"status": new_status
			},
			update_modified=False
		)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Error updating Load Dispatch status from {doc.doctype} {doc.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Load Dispatch Status Update Error"
		)

def update_load_receipt_status_from_document(doc, method=None):
	"""Update Load Receipt status when Purchase Invoice/Receipt is submitted, cancelled or deleted."""
	try:
		load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
			else (frappe.db.get_value(doc.doctype, doc.name, "custom_load_dispatch") if frappe.db.has_column(doc.doctype, "custom_load_dispatch") else None))

		if not load_dispatch_name:
			return

		if not frappe.db.has_column("Load Receipt", "load_dispatch"):
			return

		load_receipts = frappe.get_all(
			"Load Receipt",
			filters={"load_dispatch": load_dispatch_name},
			fields=["name", "docstatus"]
		)

		for lr in load_receipts:
			current_docstatus = frappe.db.get_value("Load Receipt", lr.name, "docstatus")
			
			if current_docstatus == 1:
				frappe.db.set_value("Load Receipt", lr.name, "status", "Submitted", update_modified=False)
			elif current_docstatus == 0:
				current_status = frappe.db.get_value("Load Receipt", lr.name, "status")
				if current_status not in ["Draft", "Not Saved", None]:
					frappe.db.set_value("Load Receipt", lr.name, "status", "Draft", update_modified=False)

		frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Error updating Load Receipt status from {doc.doctype} {doc.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Load Receipt Status Update Error"
		)


@frappe.whitelist()
def check_existing_documents(load_dispatch_name):
	"""Check if Purchase Receipt, Purchase Invoice, or Load Receipt already exists for a Load Dispatch."""
	result = {
		"has_purchase_receipt": False,
		"has_purchase_invoice": False,
		"has_load_receipt": False,
		"purchase_receipt_name": None,
		"purchase_invoice_name": None,
		"load_receipt_name": None
	}
	
	if not load_dispatch_name:
		return result
	
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
	
	if frappe.db.has_column("Load Receipt", "load_dispatch"):
		lr_list = frappe.get_all(
			"Load Receipt",
			filters={
				"load_dispatch": load_dispatch_name
			},
			fields=["name"],
			limit=1
		)
		
		if lr_list:
			result["has_load_receipt"] = True
			result["load_receipt_name"] = lr_list[0].name
	
	return result


@frappe.whitelist()
def process_tabular_file(file_url, selected_load_reference_no=None):
	"""Process CSV/Excel file, create Items if they don't exist, and return tabular data with item_code populated."""
	from frappe.utils import get_site_path
	
	try:
		if file_url.startswith('/files/'):
			file_path = get_site_path('public', file_url[1:])
		elif file_url.startswith('/private/files/'):
			file_path = get_site_path('private', 'files', file_url.split('/')[-1])
		else:
			file_path = get_site_path('public', 'files', file_url)
		
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
				frappe.throw(_("pandas library is required for Excel files. Please install it or use CSV format."))
		else:
			frappe.throw(_("Unsupported file format. Please upload CSV or Excel file."))
		
		def normalize_column_name(col_name):
			"""Normalize column name to handle case-insensitive matching and variations."""
			if not col_name:
				return None
			normalized = str(col_name).lower().strip()
			normalized = normalized.replace('.', '').replace('_', ' ').replace('-', ' ')
			normalized = ' '.join(normalized.split())
			return normalized
		
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
		
		def parse_date(date_value):
			"""Parse date from various formats and return YYYY-MM-DD format."""
			if not date_value or is_empty_value(date_value):
				return None
			
			if hasattr(date_value, 'strftime'):
				return date_value.strftime('%Y-%m-%d')
			
			date_str = str(date_value).strip()
			if not date_str:
				return None
			
			from frappe.utils import getdate
			try:
				parsed_date = getdate(date_str)
				return parsed_date.strftime('%Y-%m-%d')
			except:
				try:
					import re
					match = re.match(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
					if match:
						month, day, year = match.groups()
						if int(day) > 12:
							day, month = month, day
						return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
					
					match = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
					if match:
						year, month, day = match.groups()
						return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
				except:
					pass
			
			frappe.log_error(f"Could not parse date: {date_str}", "Date Parsing Error")
			return None
		
		processed_rows = []
		load_ref_nos = set()
		
		for idx, row in enumerate(rows, start=1):
			normalized_row = {}
			for excel_col, value in row.items():
				if is_empty_value(value):
					continue
				normalized_col = normalize_column_name(excel_col)
				if normalized_col and normalized_col in column_mapping:
					field_name = column_mapping[normalized_col]
					if field_name in ['dispatch_date', 'dor']:
						parsed_date = parse_date(value)
						if parsed_date:
							normalized_row[field_name] = parsed_date
					else:
						normalized_row[field_name] = value
				else:
					normalized_row[excel_col] = value
			
			hmsi_load_ref_no = (
				normalized_row.get('hmsi_load_reference_no') or
				row.get('hmsi_load_reference_no') or
				row.get('HMSI Load Reference No') or
				row.get('HMSI_LOAD_REFERENCE_NO') or
				row.get('Load Reference No') or
				row.get('LOAD_REFERENCE_NO')
			)
			
			if hmsi_load_ref_no and str(hmsi_load_ref_no).strip():
				load_ref_nos.add(str(hmsi_load_ref_no).strip())
				normalized_row['hmsi_load_reference_no'] = str(hmsi_load_ref_no).strip()
			
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
				processed_rows.append(normalized_row)
				continue
			
			item_code = str(model_serial_no).strip()
			
			normalized_row['model_serial_no'] = item_code
			
			if frappe.db.exists("Item", item_code):
				normalized_row['item_code'] = item_code
			else:
				try:
					_create_item_unified(normalized_row, item_code, source_type="row_data")
					frappe.clear_cache(doctype="Item")
					if frappe.db.exists("Item", item_code):
						normalized_row['item_code'] = item_code
					else:
						frappe.log_error(f"Item '{item_code}' was not created. Row index: {idx}", "Item Creation Failed")
						normalized_row['item_code'] = None
				except Exception as e:
					frappe.log_error(
						f"Failed to create Item '{item_code}' for row {idx}: {str(e)}\nTraceback: {frappe.get_traceback()}",
						"Item Creation Error in process_tabular_file"
					)
					normalized_row['item_code'] = None
			
			processed_rows.append(normalized_row)
		
		load_ref_nos_list = sorted(list(load_ref_nos))
		
		invalid_load_ref_nos = []
		valid_load_ref_nos = []
		for load_ref_no in load_ref_nos_list:
			if frappe.db.exists("Load Plan", load_ref_no):
				valid_load_ref_nos.append(load_ref_no)
			else:
				invalid_load_ref_nos.append(load_ref_no)
		
		if selected_load_reference_no and selected_load_reference_no.strip():
			selected_load_ref_no = str(selected_load_reference_no).strip()
			
			if not frappe.db.exists("Load Plan", selected_load_ref_no):
				frappe.throw(
					_("Load Reference Number '{0}' does not exist as a Load Plan. Please create the Load Plan first or select a valid Load Reference Number.").format(selected_load_ref_no),
					title=_("Invalid Load Reference Number")
				)
			
			filtered_rows = []
			for row in processed_rows:
				row_load_ref_no = row.get('hmsi_load_reference_no')
				if row_load_ref_no and str(row_load_ref_no).strip() == selected_load_ref_no:
					filtered_rows.append(row)
				elif not row_load_ref_no:
					filtered_rows.append(row)
			
			return {
				'rows': filtered_rows,
				'has_multiple_load_ref_nos': len(load_ref_nos_list) > 1,
				'load_ref_nos': load_ref_nos_list,
				'valid_load_ref_nos': valid_load_ref_nos,
				'invalid_load_ref_nos': invalid_load_ref_nos,
				'selected_load_ref_no': selected_load_ref_no,
				'filtered': True
			}
		
		# Return all rows with metadata about Load Ref Nos
		return {
			'rows': processed_rows,
			'has_multiple_load_ref_nos': len(load_ref_nos_list) > 1,
			'load_ref_nos': load_ref_nos_list,
			'valid_load_ref_nos': valid_load_ref_nos,
			'invalid_load_ref_nos': invalid_load_ref_nos,
			'selected_load_ref_no': None,
			'filtered': False
		}
		
	except Exception as e:
		frappe.log_error(
			f"Error processing tabular file {file_url}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"process_tabular_file Error"
		)
		frappe.throw(_("Error processing file: {0}").format(str(e)))


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
		if not print_name:
			print_name = (getattr(frappe.local, 'item_print_name_map', {}).get(item_code) if hasattr(frappe.local, 'item_print_name_map') else None
				or (getattr(item_data, "print_name", None) if hasattr(item_data, "print_name") else None)
				or (item_data.get("print_name") if isinstance(item_data, dict) else None))
		
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
		pass
	
	stock_uom = str(unit).strip() if unit else "Pcs"
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
	if print_name_value:
		item_dict["print_name"] = print_name_value
	
	item_doc = frappe.get_doc(item_dict)
	
	if rkg_settings:
		if rkg_settings.get("default_supplier") and source_type == "dispatch_item":
			if hasattr(item_doc, "supplier_items"):
				item_doc.append("supplier_items", {"supplier": rkg_settings.default_supplier, "is_default": 1})
			elif hasattr(item_doc, "supplier"):
				item_doc.supplier = rkg_settings.default_supplier
	
	hsn_code = None
	if source_type == "dispatch_item":
		if hasattr(item_data, "hsn_code") and item_data.hsn_code:
			hsn_code = item_data.hsn_code
	elif source_type == "row_data":
		hsn_code = item_data.get('hsn_code') or item_data.get('HSN Code') or item_data.get('HSN_CODE')
	
	if hsn_code:
		if hasattr(item_doc, "gst_hsn_code"):
			item_doc.gst_hsn_code = hsn_code
		elif hasattr(item_doc, "custom_gst_hsn_code"):
			item_doc.custom_gst_hsn_code = hsn_code
	
	if print_name_value and hasattr(item_doc, "print_name"):
		item_doc.print_name = print_name_value
	
	try:
		item_doc.insert(ignore_permissions=True)
		frappe.db.commit()
		
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

def _get_or_create_item_group_unified(model_name):
	"""Unified Item Group creation - creates hierarchy: All Item Groups -> Two Wheelers Vehicle -> Model Name."""
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
	
	two_wheeler_vehicle = "Two Wheelers Vehicle"
	if not frappe.db.exists("Item Group", two_wheeler_vehicle):
		try:
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": two_wheeler_vehicle,
				"is_group": 1,
				"parent_item_group": all_groups
			}).insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"Failed to create 'Two Wheelers Vehicle': {str(e)}", "Item Group Creation Failed")
	
	if model_name and str(model_name).strip():
		model_name = str(model_name).strip()
		if frappe.db.exists("Item Group", model_name):
			return model_name
		try:
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": model_name,
				"is_group": 0,
				"parent_item_group": two_wheeler_vehicle
			}).insert(ignore_permissions=True)
			frappe.db.commit()
			return model_name
		except Exception as e:
			frappe.log_error(f"Failed to create Item Group '{model_name}': {str(e)}", "Item Group Creation Failed")
	
	if frappe.db.exists("Item Group", two_wheeler_vehicle):
		return two_wheeler_vehicle
	
	any_group = frappe.db.get_value("Item Group", {}, "name", order_by="name")
	if any_group:
		return any_group
	
	frappe.throw(_("Could not create or find an Item Group. Please create one manually."))
