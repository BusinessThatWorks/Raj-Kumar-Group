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
		# Calculate totals from Purchase Receipts/Invoices if they exist
		if not self.is_new() or self.name:
			self.calculate_totals_from_purchase_documents()
		else:
			# For new documents without name, fall back to counting items
			self.calculate_total_receipt_quantity()
			self.total_billed_quantity = 0
	
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
		"""Set default values: calculate print_name and rate from price_unit."""
		if not self.items:
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
		"""Update Load Dispatch status based on received quantity from Purchase Receipts."""
		total_dispatch = flt(self.total_dispatch_quantity) or 0
		
		total_received = flt(self.total_receipt_quantity) or 0
		
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
	
	def calculate_total_receipt_quantity(self):
		"""Count the number of rows with non-empty frame_no in Load Dispatch Item child table."""
		self.total_receipt_quantity = sum(1 for item in (self.items or []) if item.frame_no and str(item.frame_no).strip())
	
	def calculate_totals_from_purchase_documents(self):
		"""Calculate total_receipt_quantity and total_billed_quantity from Purchase Receipts/Invoices linked to Load Dispatch."""
		total_received_qty = 0
		total_billed_qty = 0
		
		if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
			pr_list = frappe.get_all(
				"Purchase Receipt",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": self.name
				},
				fields=["name", "total_qty"]
			)
			
			for pr in pr_list:
				try:
					pr_qty = flt(pr.get("total_qty")) or 0
					if pr_qty == 0:
						try:
							pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
							if hasattr(pr_doc, "items") and pr_doc.items:
								pr_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pr_doc.items)
						except Exception:
							pass
					total_received_qty += pr_qty
				except Exception:
					continue
		
		if frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
			pi_list = frappe.get_all(
				"Purchase Invoice",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": self.name
				},
				fields=["name", "total_qty"]
			)
			
			for pi in pi_list:
				try:
					pi_qty = flt(pi.get("total_qty")) or 0
					if pi_qty == 0:
						try:
							pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
							if hasattr(pi_doc, "items") and pi_doc.items:
								pi_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pi_doc.items)
						except Exception:
							pass
					total_billed_qty += pi_qty
				except Exception:
					continue
			
			for pi in pi_list:
				try:
					pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
					if hasattr(pi_doc, "items") and pi_doc.items:
						linked_purchase_receipts = {item.purchase_receipt for item in pi_doc.items if hasattr(item, "purchase_receipt") and item.purchase_receipt}
						if linked_purchase_receipts:
							for pr_name in linked_purchase_receipts:
								if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
									pr_load_dispatch = frappe.db.get_value("Purchase Receipt", pr_name, "custom_load_dispatch")
									if pr_load_dispatch == self.name:
										total_received_qty = total_billed_qty
										break
				except Exception:
					continue
		
		self.total_receipt_quantity = total_received_qty
		self.total_billed_quantity = total_billed_qty
	
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
					
					# Update print_name if provided
					if hasattr(item, "print_name") and item.print_name:
						if hasattr(item_doc, "print_name"):
							item_doc.print_name = item.print_name
							updated = True
					
					# Update HSN code if provided
					if hasattr(item, "hsn_code") and item.hsn_code:
						hsn_code = item.hsn_code
						if hasattr(item_doc, "gst_hsn_code"):
							if item_doc.gst_hsn_code != hsn_code:
								item_doc.gst_hsn_code = hsn_code
								updated = True
						elif hasattr(item_doc, "custom_gst_hsn_code"):
							if item_doc.custom_gst_hsn_code != hsn_code:
								item_doc.custom_gst_hsn_code = hsn_code
								updated = True

					if updated:
						item_doc.save(ignore_permissions=True)
						frappe.db.commit()
						
						# Also update using db.set_value to ensure persistence
						if hasattr(item, "print_name") and item.print_name and frappe.db.has_column("Item", "print_name"):
							try:
								frappe.db.set_value("Item", item_code, "print_name", item.print_name, update_modified=False)
								frappe.db.commit()
							except Exception as e:
								frappe.log_error(f"Failed to update print_name for Item {item_code}: {str(e)}", "Item Print Name Update Failed")
						
						if hasattr(item, "hsn_code") and item.hsn_code:
							hsn_code = item.hsn_code
							hsn_field = None
							if frappe.db.has_column("Item", "gst_hsn_code"):
								hsn_field = "gst_hsn_code"
							elif frappe.db.has_column("Item", "custom_gst_hsn_code"):
								hsn_field = "custom_gst_hsn_code"
							
							if hsn_field:
								try:
									frappe.db.set_value("Item", item_code, hsn_field, hsn_code, update_modified=False)
									frappe.db.commit()
								except Exception as e:
									frappe.log_error(f"Failed to update HSN code for Item {item_code}: {str(e)}", "Item HSN Code Update Failed")
						
						updated_items.append(item_code)
					else:
						skipped_items.append(item_code)
					continue

				model_name = str(item.model_name).strip() if (item.model_name and str(item.model_name).strip()) else None
				item_group = _get_or_create_item_group_unified(model_name)
				
				stock_uom = str(item.unit).strip() if hasattr(item, "unit") and item.unit else "Pcs"
				
				# Get HSN code before creating item_doc
				hsn_code = None
				if hasattr(item, "hsn_code") and item.hsn_code:
					hsn_code = item.hsn_code
				
				# Build item_dict with HSN code if field exists
				item_dict = {
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item.model_variant or item_code,
					"item_group": item_group,
					"stock_uom": stock_uom,
					"is_stock_item": 1,
					"has_serial_no": 1,
				}
				
				# Add HSN code to item_dict if field exists
				if hsn_code:
					if frappe.db.has_column("Item", "gst_hsn_code"):
						item_dict["gst_hsn_code"] = hsn_code
					elif frappe.db.has_column("Item", "custom_gst_hsn_code"):
						item_dict["custom_gst_hsn_code"] = hsn_code
				
				# Add print_name to item_dict if it exists
				if hasattr(item, "print_name") and item.print_name:
					item_dict["print_name"] = item.print_name
				
				item_doc = frappe.get_doc(item_dict)
				
				if rkg_settings and rkg_settings.get("default_supplier"):
					if hasattr(item_doc, "supplier_items"):
						item_doc.append("supplier_items", {
							"supplier": rkg_settings.default_supplier,
							"is_default": 1
						})
					elif hasattr(item_doc, "supplier"):
						item_doc.supplier = rkg_settings.default_supplier
				
				# Also set HSN code on item_doc object as backup
				if hsn_code:
					if hasattr(item_doc, "gst_hsn_code"):
						item_doc.gst_hsn_code = hsn_code
					elif hasattr(item_doc, "custom_gst_hsn_code"):
						item_doc.custom_gst_hsn_code = hsn_code
				
				if hasattr(item, "print_name") and item.print_name:
					if hasattr(item_doc, "print_name"):
						item_doc.print_name = item.print_name

				item_doc.insert(ignore_permissions=True)
				frappe.db.commit()
				
				# Save HSN code using db.set_value to ensure it's persisted
				if hsn_code:
					hsn_field = None
					if frappe.db.has_column("Item", "gst_hsn_code"):
						hsn_field = "gst_hsn_code"
					elif frappe.db.has_column("Item", "custom_gst_hsn_code"):
						hsn_field = "custom_gst_hsn_code"
					
					if hsn_field:
						try:
							frappe.db.set_value("Item", item_code, hsn_field, hsn_code, update_modified=False)
							frappe.db.commit()
						except Exception as e:
							frappe.log_error(f"Failed to set HSN code for Item {item_code}: {str(e)}", "Item HSN Code Update Failed")
				
				# Save print_name using db.set_value to ensure it's persisted
				if hasattr(item, "print_name") and item.print_name and frappe.db.has_column("Item", "print_name"):
					try:
						frappe.db.set_value("Item", item_code, "print_name", item.print_name, update_modified=False)
						frappe.db.commit()
					except Exception as e:
						frappe.log_error(f"Failed to set print_name for Item {item_code}: {str(e)}", "Item Print Name Update Failed")
				
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
	"""Update Load Dispatch status based on totals when Purchase Receipt/Invoice is submitted or cancelled."""
	try:
		load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
			else (frappe.db.get_value(doc.doctype, doc.name, "custom_load_dispatch") if frappe.db.has_column(doc.doctype, "custom_load_dispatch") else None))

		if not load_dispatch_name:
			return

		if not frappe.db.exists("Load Dispatch", load_dispatch_name):
			return

		# Recalculate totals which will also update status
		load_dispatch = frappe.get_doc("Load Dispatch", load_dispatch_name)
		load_dispatch.calculate_totals_from_purchase_documents()
		load_dispatch.update_status()
		
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Error updating Load Dispatch status from {doc.doctype} {doc.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Load Dispatch Status Update Error"
		)


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
			# Try multiple encodings to handle different file formats
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
				frappe.throw(_("Unable to read the file. Please ensure it is saved as CSV with a supported encoding (UTF-8, UTF-16, or Windows-1252)."))
			
			try:
				reader = csv.DictReader(csvfile)
				rows = list(reader)
			finally:
				if csvfile:
					csvfile.close()
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
	
	# Get HSN code before creating item_dict
	hsn_code = None
	if source_type == "dispatch_item":
		if hasattr(item_data, "hsn_code") and item_data.hsn_code:
			hsn_code = item_data.hsn_code
	elif source_type == "row_data":
		hsn_code = item_data.get('hsn_code') or item_data.get('HSN Code') or item_data.get('HSN_CODE')
	
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
	
	# Add HSN code to item_dict if field exists
	if hsn_code:
		# Check which HSN field exists in Item doctype
		if frappe.db.has_column("Item", "gst_hsn_code"):
			item_dict["gst_hsn_code"] = hsn_code
		elif frappe.db.has_column("Item", "custom_gst_hsn_code"):
			item_dict["custom_gst_hsn_code"] = hsn_code
	
	item_doc = frappe.get_doc(item_dict)
	
	if rkg_settings:
		if rkg_settings.get("default_supplier") and source_type == "dispatch_item":
			if hasattr(item_doc, "supplier_items"):
				item_doc.append("supplier_items", {"supplier": rkg_settings.default_supplier, "is_default": 1})
			elif hasattr(item_doc, "supplier"):
				item_doc.supplier = rkg_settings.default_supplier
	
	# Also set HSN code on item_doc object as backup
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
		
		# Save print_name using db.set_value to ensure it's persisted
		if print_name_value and frappe.db.has_column("Item", "print_name"):
			try:
				frappe.db.set_value("Item", item_code, "print_name", print_name_value, update_modified=False)
				frappe.db.commit()
			except Exception as e:
				frappe.log_error(f"Failed to set print_name for Item {item_code}: {str(e)}", "Item Print Name Update Failed")
		
		# Save HSN code using db.set_value to ensure it's persisted
		if hsn_code:
			hsn_field = None
			if frappe.db.has_column("Item", "gst_hsn_code"):
				hsn_field = "gst_hsn_code"
			elif frappe.db.has_column("Item", "custom_gst_hsn_code"):
				hsn_field = "custom_gst_hsn_code"
			
			if hsn_field:
				try:
					frappe.db.set_value("Item", item_code, hsn_field, hsn_code, update_modified=False)
					frappe.db.commit()
				except Exception as e:
					frappe.log_error(f"Failed to set HSN code for Item {item_code}: {str(e)}", "Item HSN Code Update Failed")
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


@frappe.whitelist()
def get_totals_from_purchase_documents(load_dispatch):
	"""Get total_receipt_quantity and total_billed_quantity from Purchase Receipts/Invoices linked to Load Dispatch."""
	if not load_dispatch:
		return {"total_receipt_quantity": 0, "total_billed_quantity": 0}
	
	total_received_qty = 0
	total_billed_qty = 0
	
	if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
		pr_list = frappe.get_all(
			"Purchase Receipt",
			filters={
				"docstatus": 1,
				"custom_load_dispatch": load_dispatch
			},
			fields=["name", "total_qty"]
		)
		
		for pr in pr_list:
			try:
				pr_qty = flt(pr.get("total_qty")) or 0
				if pr_qty == 0:
					try:
						pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
						if hasattr(pr_doc, "items") and pr_doc.items:
							pr_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pr_doc.items)
					except Exception:
						pass
				total_received_qty += pr_qty
			except Exception:
				continue
	
	if frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
		pi_list = frappe.get_all(
			"Purchase Invoice",
			filters={
				"docstatus": 1,
				"custom_load_dispatch": load_dispatch
			},
			fields=["name", "total_qty"]
		)
		
		for pi in pi_list:
			try:
				pi_qty = flt(pi.get("total_qty")) or 0
				if pi_qty == 0:
					try:
						pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
						if hasattr(pi_doc, "items") and pi_doc.items:
							pi_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pi_doc.items)
					except Exception:
						pass
				total_billed_qty += pi_qty
			except Exception:
				continue
		
		for pi in pi_list:
			try:
				pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
				if hasattr(pi_doc, "items") and pi_doc.items:
					linked_purchase_receipts = {item.purchase_receipt for item in pi_doc.items if hasattr(item, "purchase_receipt") and item.purchase_receipt}
					if linked_purchase_receipts:
						for pr_name in linked_purchase_receipts:
							if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
								pr_load_dispatch = frappe.db.get_value("Purchase Receipt", pr_name, "custom_load_dispatch")
								if pr_load_dispatch == load_dispatch:
									total_received_qty = total_billed_qty
									break
			except Exception:
				continue
	
	return {
		"total_receipt_quantity": total_received_qty,
		"total_billed_quantity": total_billed_qty
	}


def _create_purchase_document_unified_from_load_dispatch(source_name, doctype, target_doc=None, warehouse=None, frame_warehouse_mapping=None):
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
		if source.load_reference_no:
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

		try:
			price_unit = flt(getattr(source, "price_unit", 0) or 0)
		except Exception:
			price_unit = 0

		if price_unit and price_unit > 0:
			if hasattr(target, "price_unit"):
				target.price_unit = price_unit
			if hasattr(target, "rate"):
				target.rate = price_unit
		
		if doctype == "Purchase Invoice" and hasattr(source, "frame_no") and source.frame_no:
			fn = str(source.frame_no).strip()
			if hasattr(target, "serial_no"):
				target.serial_no = fn
			if hasattr(target, "__dict__"):
				target.__dict__["serial_no"] = fn
		
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
		
		if hasattr(source, "hsn_code") and source.hsn_code:
			hsn_code = source.hsn_code
			if hasattr(target, "gst_hsn_code"):
				target.gst_hsn_code = hsn_code
			elif hasattr(target, "custom_gst_hsn_code"):
				target.custom_gst_hsn_code = hsn_code
		
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
			item_to_frame = {ldi.item_code: str(ldi.frame_no).strip() for ldi in source_doc.items if hasattr(ldi, "item_code") and ldi.item_code and hasattr(ldi, "frame_no") and ldi.frame_no}
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


@frappe.whitelist()
def create_purchase_receipt_from_load_dispatch(source_name, target_doc=None, warehouse=None):
	"""Create Purchase Receipt from Load Dispatch."""
	load_dispatch = frappe.get_doc("Load Dispatch", source_name)
	load_dispatch.reload()
	
	if load_dispatch.docstatus != 1:
		frappe.throw(_("Load Dispatch must be submitted before creating Purchase Receipt"))
	
	# Use warehouse from parameter if provided, otherwise use from document
	selected_warehouse = warehouse or load_dispatch.warehouse
	
	if not selected_warehouse:
		frappe.throw(_("Warehouse must be set in Load Dispatch before creating Purchase Receipt"))
	
	# Always save warehouse to Load Dispatch if provided (even if same value, ensures it's persisted)
	if warehouse:
		frappe.db.set_value("Load Dispatch", source_name, "warehouse", warehouse, update_modified=False)
		frappe.db.commit()
		load_dispatch.reload()
	
	return _create_purchase_document_unified_from_load_dispatch(source_name, "Purchase Receipt", target_doc, selected_warehouse)


def update_load_dispatch_totals_from_document(doc, method=None):
	"""Update Load Dispatch totals (total_receipt_quantity and total_billed_quantity) when Purchase Receipt/Invoice is submitted or cancelled."""
	try:
		load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
			else (frappe.db.get_value(doc.doctype, doc.name, "custom_load_dispatch") if frappe.db.has_column(doc.doctype, "custom_load_dispatch") else None))

		if not load_dispatch_name:
			return

		if not frappe.db.exists("Load Dispatch", load_dispatch_name):
			return

		total_received_qty = 0
		total_billed_qty = 0

		if doc.doctype == "Purchase Receipt":
			if not frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
				return
			
			pr_list = frappe.get_all(
				"Purchase Receipt",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": load_dispatch_name
				},
				fields=["name", "total_qty"]
			)
			
			for pr in pr_list:
				try:
					pr_qty = flt(pr.get("total_qty")) or 0
					if pr_qty == 0:
						try:
							pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
							if hasattr(pr_doc, "items") and pr_doc.items:
								pr_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pr_doc.items)
						except Exception:
							pass
					total_received_qty += pr_qty
				except Exception as e:
					frappe.log_error(
						f"Error processing Purchase Receipt {pr.get('name', 'Unknown')}: {str(e)}",
						"Load Dispatch Totals Update Error"
					)
					continue

		elif doc.doctype == "Purchase Invoice":
			if not frappe.db.has_column("Purchase Invoice", "custom_load_dispatch"):
				return
			
			pr_list = frappe.get_all(
				"Purchase Receipt",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": load_dispatch_name
				},
				fields=["name", "total_qty"]
			)
			
			for pr in pr_list:
				try:
					pr_qty = flt(pr.get("total_qty")) or 0
					if pr_qty == 0:
						try:
							pr_doc = frappe.get_doc("Purchase Receipt", pr.name)
							if hasattr(pr_doc, "items") and pr_doc.items:
								pr_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pr_doc.items)
						except Exception:
							pass
					total_received_qty += pr_qty
				except Exception as e:
					frappe.log_error(
						f"Error processing Purchase Receipt {pr.get('name', 'Unknown')}: {str(e)}",
						"Load Dispatch Totals Update Error"
					)
					continue
			
			linked_purchase_receipts = set()
			try:
				if doc.items:
					linked_purchase_receipts = {item.purchase_receipt for item in doc.items if hasattr(item, "purchase_receipt") and item.purchase_receipt}
			except Exception as e:
				frappe.log_error(
					f"Error getting linked purchase receipts: {str(e)}",
					"Load Dispatch Totals Update Error"
				)
			has_purchase_receipt_link = bool(linked_purchase_receipts)
			
			pi_list = frappe.get_all(
				"Purchase Invoice",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": load_dispatch_name
				},
				fields=["name", "total_qty"]
			)
			
			for pi in pi_list:
				try:
					pi_qty = flt(pi.get("total_qty")) or 0
					if pi_qty == 0:
						try:
							pi_doc = frappe.get_doc("Purchase Invoice", pi.name)
							if hasattr(pi_doc, "items") and pi_doc.items:
								pi_qty = sum(flt(item.get("qty") or item.get("stock_qty") or item.get("received_qty") or 0) for item in pi_doc.items)
						except Exception:
							pass
					total_billed_qty += pi_qty
				except Exception as e:
					frappe.log_error(
						f"Error processing Purchase Invoice {pi.get('name', 'Unknown')}: {str(e)}",
						"Load Dispatch Totals Update Error"
					)
					continue
			
			if has_purchase_receipt_link and linked_purchase_receipts:
				pr_from_ld = []
				for pr_name in linked_purchase_receipts:
					pr_load_dispatch = None
					if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
						pr_load_dispatch = frappe.db.get_value("Purchase Receipt", pr_name, "custom_load_dispatch")
					
					if pr_load_dispatch == load_dispatch_name:
						pr_from_ld.append(pr_name)
				
				if pr_from_ld:
					total_received_qty = total_billed_qty

		try:
			frappe.db.set_value(
				"Load Dispatch",
				load_dispatch_name,
				{
					"total_receipt_quantity": total_received_qty,
					"total_billed_quantity": total_billed_qty
				},
				update_modified=False
			)
		except Exception as e:
			frappe.log_error(
				f"Error updating Load Dispatch {load_dispatch_name}: {str(e)}",
				"Load Dispatch Totals Update Error"
			)

		frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Error updating Load Dispatch totals from {doc.doctype} {doc.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Load Dispatch Totals Update Error"
		)


@frappe.whitelist()
def get_frames_status_counts(damage_assessment):
	"""Get count of OK and Not OK frames from Damage Assessment."""
	if not damage_assessment:
		return {"frames_ok": 0, "frames_not_ok": 0}
	
	load_dispatch = frappe.db.get_value("Load Dispatch", {"damage_assessment": damage_assessment}, "name")
	if not load_dispatch:
		return {"frames_ok": 0, "frames_not_ok": 0}
	
	total_frames = frappe.db.get_value("Load Dispatch", load_dispatch, "total_receipt_quantity") or 0
	damage_assessment_doc = frappe.get_doc("Damage Assessment", damage_assessment)
	
	if damage_assessment_doc.docstatus == 1:
		not_ok_count = frappe.db.count("Damage Assessment Item", {
			"parent": damage_assessment,
			"status": "Not OK"
		})
		ok_count = max(0, total_frames - not_ok_count)
	else:
		ok_count = frappe.db.count("Damage Assessment Item", {
			"parent": damage_assessment,
			"status": "OK"
		})
		not_ok_count = frappe.db.count("Damage Assessment Item", {
			"parent": damage_assessment,
			"status": "Not OK"
		})
	
	return {
		"frames_ok": ok_count,
		"frames_not_ok": not_ok_count
	}


def update_frames_status_counts_in_load_dispatch(load_dispatch_name, damage_assessment_name):
	"""Update frames OK/Not OK counts in Load Dispatch from Damage Assessment."""
	if not load_dispatch_name or not damage_assessment_name:
		return
	
	counts = get_frames_status_counts(damage_assessment_name)
	if isinstance(counts, dict):
		frappe.db.set_value("Load Dispatch", load_dispatch_name, {
			"frames_ok": counts.get("frames_ok", 0),
			"frames_not_ok": counts.get("frames_not_ok", 0)
		}, update_modified=False)
		frappe.db.commit()


def set_purchase_receipt_serial_batch_fields_readonly(doc, method=None):
	"""Set "Use Serial No / Batch Fields" to checked on child table items for Purchase Receipts created from Load Dispatch."""
	load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
		else (frappe.db.get_value("Purchase Receipt", doc.name, "custom_load_dispatch") if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch") else None))
	
	if load_dispatch_name and doc.items:
		for item in doc.items:
			if hasattr(item, "use_serial_batch_fields"):
				if not item.use_serial_batch_fields:
					item.use_serial_batch_fields = 1


@frappe.whitelist()
def preserve_purchase_receipt_uom(doc, method=None):
	"""Preserve UOM from Load Dispatch Item's unit field when Purchase Receipt is validated."""
	preserve_uom_from_load_dispatch(doc, "Purchase Receipt")

@frappe.whitelist()
def preserve_purchase_invoice_uom(doc, method=None):
	"""Preserve UOM from Load Dispatch Item's unit field when Purchase Invoice is validated."""
	preserve_uom_from_load_dispatch(doc, "Purchase Invoice")

def preserve_uom_from_load_dispatch(doc, doctype_name):
	"""Preserve UOM from Load Dispatch Item's unit field for Purchase Receipt and Purchase Invoice."""
	if not doc.items:
		return
	
	load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
		else (frappe.db.get_value(doctype_name, doc.name, "custom_load_dispatch") if frappe.db.has_column(doctype_name, "custom_load_dispatch") else None))
	
	if not load_dispatch_name:
		return
	
	try:
		load_dispatch = frappe.get_doc("Load Dispatch", load_dispatch_name)
	except frappe.DoesNotExistError:
		return
	
	item_uom_map = {}
	if load_dispatch.items:
		for ld_item in load_dispatch.items:
			if ld_item.item_code and hasattr(ld_item, "unit") and ld_item.unit:
				item_uom_map[ld_item.item_code] = str(ld_item.unit).strip()
	
	if item_uom_map:
		for doc_item in doc.items:
			if doc_item.item_code and doc_item.item_code in item_uom_map:
				uom_value = item_uom_map[doc_item.item_code]
				if hasattr(doc_item, "uom") and doc_item.uom != uom_value:
					doc_item.uom = uom_value
				if hasattr(doc_item, "stock_uom") and doc_item.stock_uom != uom_value:
					doc_item.stock_uom = uom_value


def sync_warehouse_from_purchase_receipt_to_load_dispatch(doc, method=None):
	"""Sync warehouse from Purchase Receipt back to Load Dispatch when PR is created."""
	try:
		load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
			else (frappe.db.get_value("Purchase Receipt", doc.name, "custom_load_dispatch") if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch") else None))
		
		if not load_dispatch_name:
			return
		
		if not frappe.db.exists("Load Dispatch", load_dispatch_name):
			return
		
		# Get warehouse from Purchase Receipt items (use the first non-empty warehouse)
		warehouse = None
		if doc.items:
			for item in doc.items:
				if hasattr(item, "warehouse") and item.warehouse:
					warehouse = item.warehouse
					break
		
		# If warehouse found and Load Dispatch doesn't have it, set it
		if warehouse:
			current_warehouse = frappe.db.get_value("Load Dispatch", load_dispatch_name, "warehouse")
			if not current_warehouse or current_warehouse != warehouse:
				frappe.db.set_value("Load Dispatch", load_dispatch_name, "warehouse", warehouse, update_modified=False)
				frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Error syncing warehouse from Purchase Receipt {doc.name} to Load Dispatch: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Warehouse Sync Error"
		)


@frappe.whitelist()
def sync_warehouse_from_existing_purchase_receipt(load_dispatch_name):
	"""Sync warehouse from existing Purchase Receipt to Load Dispatch. Used when Load Dispatch warehouse is empty but PR exists."""
	if not load_dispatch_name:
		return {"warehouse": None}
	
	if not frappe.db.exists("Load Dispatch", load_dispatch_name):
		return {"warehouse": None}
	
	# Check if Purchase Receipt exists for this Load Dispatch
	if not frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
		return {"warehouse": None}
	
	pr_list = frappe.get_all(
		"Purchase Receipt",
		filters={
			"custom_load_dispatch": load_dispatch_name
		},
		fields=["name"],
		limit=1
	)
	
	if not pr_list:
		return {"warehouse": None}
	
	# Get warehouse from Purchase Receipt items
	try:
		pr = frappe.get_doc("Purchase Receipt", pr_list[0].name)
		if pr.items:
			for item in pr.items:
				if hasattr(item, "warehouse") and item.warehouse:
					warehouse = item.warehouse
					# Save warehouse to Load Dispatch if it's empty
					current_warehouse = frappe.db.get_value("Load Dispatch", load_dispatch_name, "warehouse")
					if not current_warehouse:
						frappe.db.set_value("Load Dispatch", load_dispatch_name, "warehouse", warehouse, update_modified=False)
						frappe.db.commit()
					return {"warehouse": warehouse}
	except Exception as e:
		frappe.log_error(
			f"Error syncing warehouse from Purchase Receipt to Load Dispatch {load_dispatch_name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Warehouse Sync Error"
		)
	
	return {"warehouse": None}


def preserve_purchase_invoice_serial_no_from_receipt(doc, method=None):
	"""Preserve serial_no from Purchase Receipt Item when creating Purchase Invoice from Purchase Receipt."""
	if not doc.items:
		return
	
	purchase_receipts = {item.purchase_receipt for item in doc.items if hasattr(item, "purchase_receipt") and item.purchase_receipt}
	
	if not purchase_receipts:
		return
	
	receipt_item_map = {}
	
	for pr_name in purchase_receipts:
		try:
			purchase_receipt = frappe.get_doc("Purchase Receipt", pr_name)
			if not purchase_receipt.items:
				continue
			
			for pr_item in purchase_receipt.items:
				if pr_item.item_code and hasattr(pr_item, "serial_no") and pr_item.serial_no:
					key = (pr_name, pr_item.item_code, pr_item.idx)
					receipt_item_map[key] = pr_item.serial_no
		except frappe.DoesNotExistError:
			continue
	
	if receipt_item_map:
		for pi_item in doc.items:
			if pi_item.item_code and hasattr(pi_item, "purchase_receipt") and pi_item.purchase_receipt:
				pr_name = pi_item.purchase_receipt
				key = (pr_name, pi_item.item_code, pi_item.idx)
				if key in receipt_item_map:
					serial_no_value = receipt_item_map[key]
				else:
					serial_no_value = next((v for (pr_key, item_code, idx), v in receipt_item_map.items() if pr_key == pr_name and item_code == pi_item.item_code), None)
				
				if serial_no_value:
					if hasattr(pi_item, "use_serial_batch_fields") and not pi_item.use_serial_batch_fields:
						pi_item.use_serial_batch_fields = 1
					if hasattr(pi_item, "serial_no"):
						pi_item.serial_no = serial_no_value
	
	has_purchase_receipt = any(hasattr(item, "purchase_receipt") and item.purchase_receipt for item in (doc.items or []))
	
	if not has_purchase_receipt and hasattr(doc, "update_stock") and not doc.update_stock:
		doc.update_stock = 1


def validate_purchase_invoice_requires_receipt(doc, method=None):
	"""Validate that Purchase Invoice must be linked to a Purchase Receipt."""
	if not doc.items:
		return
	
	has_purchase_receipt = any(
		hasattr(item, "purchase_receipt") and item.purchase_receipt 
		for item in doc.items
	)
	
	if has_purchase_receipt:
		return
	
	load_dispatch_name = (doc.custom_load_dispatch if hasattr(doc, "custom_load_dispatch") and doc.custom_load_dispatch
		else (frappe.db.get_value("Purchase Invoice", doc.name, "custom_load_dispatch") if frappe.db.has_column("Purchase Invoice", "custom_load_dispatch") else None))
	
	if load_dispatch_name:
		pr_list = frappe.get_all(
			"Purchase Receipt",
			filters={
				"custom_load_dispatch": load_dispatch_name,
				"docstatus": 1
			},
			fields=["name"],
			limit=1
		)
		
		if pr_list:
			pr_name = pr_list[0].name
			for item in doc.items:
				if hasattr(item, "purchase_receipt") and not item.purchase_receipt:
					item.purchase_receipt = pr_name
			return
	
	frappe.throw(_("Create Purchase Receipt First to create Purchase Invoice"))
