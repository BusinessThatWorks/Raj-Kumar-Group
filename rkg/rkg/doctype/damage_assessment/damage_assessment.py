import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt


class DamageAssessment(Document):
	def validate(self):
		"""Validate and calculate totals."""
		self.set_stock_entry_type()
		self.calculate_total_estimated_cost()
	
	def before_submit(self):
		"""Validate damage items and remove OK items before submitting."""
		self.remove_ok_items()
		self.validate_damage_items()
	
	def set_stock_entry_type(self):
		"""Set Stock Entry Type to Material Transfer if not already set."""
		material_transfer = "Material Transfer"
		
		if not frappe.db.exists("Stock Entry Type", material_transfer):
			alternative = "Material Transfer (for Manufacture)"
			if frappe.db.exists("Stock Entry Type", alternative):
				material_transfer = alternative
			else:
				frappe.throw(_("Stock Entry Type 'Material Transfer' not found. Please create it in Stock Entry Type master."))
		
		if not self.stock_entry_type:
			self.stock_entry_type = material_transfer
		elif self.stock_entry_type != material_transfer:
			self.stock_entry_type = material_transfer
	
	def remove_ok_items(self):
		"""Remove child table rows where Status is 'OK', keeping only 'Not OK' items."""
		if not self.damage_assessment_item:
			return
		
		ok_count = sum(1 for item in self.damage_assessment_item if item.status == "OK")
		
		if ok_count == 0:
			return
		
		child_meta = frappe.get_meta("Damage Assessment Item")
		fieldnames = [df.fieldname for df in child_meta.fields if df.fieldtype not in ['Section Break', 'Column Break', 'Tab Break']]
		
		not_ok_items_data = []
		for item in self.damage_assessment_item:
			if item.status == "Not OK":
				item_dict = {}
				for fieldname in fieldnames:
					if hasattr(item, fieldname):
						item_dict[fieldname] = item.get(fieldname)
				not_ok_items_data.append(item_dict)
		
		self.damage_assessment_item = []
		for item_data in not_ok_items_data:
			self.append("damage_assessment_item", item_data)
		
		if ok_count > 0:
			frappe.msgprint(
				_("Removed {0} item(s) with Status 'OK' from the child table. Only 'Not OK' items will be saved.").format(ok_count),
				alert=True,
				indicator="blue"
			)
	
	def validate_damage_items(self):
		"""Validate that Not OK items have at least one damage/issue (type_of_damage_1 is mandatory), estimated cost, and warehouses.
		This method is called from before_submit, so it only runs when submitting, not when saving as draft."""
		if self.damage_assessment_item:
			for item in self.damage_assessment_item:
				if item.status == "Not OK":
					if not item.type_of_damage_1:
						frappe.throw(_("Damage/Issue 1 is required for frame {0} marked as Not OK").format(item.serial_no or ""))
					if not item.estimated_cost:
						frappe.throw(_("Estimated Amount is required for frame {0} marked as Not OK").format(item.serial_no or ""))
					if not item.from_warehouse:
						frappe.throw(_("From Warehouse is required for frame {0} marked as Not OK").format(item.serial_no or ""))
					if not item.to_warehouse:
						frappe.throw(_("To Warehouse (Damage Godown) is required for frame {0} marked as Not OK").format(item.serial_no or ""))
	
	def calculate_total_estimated_cost(self):
		"""Calculate total estimated cost from child table items."""
		total = 0
		if self.damage_assessment_item:
			for item in self.damage_assessment_item:
				total += flt(item.estimated_cost) or 0
		self.total_estimated_cost = total
	
	def on_submit(self):
		"""Actions on submit."""
		if self.stock_entry_type:
			self.create_stock_entries()
		
		self.update_load_receipt_frames_counts()
	
	def on_cancel(self):
		"""Cancel linked Stock Entries when Damage Assessment is cancelled."""
		try:
			stock_entries = frappe.get_all(
				"Stock Entry",
				filters={
					"custom_damage_assessment": self.name,
					"docstatus": 1
				},
				fields=["name"]
			)
			
			for se in stock_entries:
				self.cancel_stock_entry(se.name)
		except Exception:
			frappe.log_error(
				f"Error cancelling stock entries for Damage Assessment {self.name}",
				"Damage Assessment Cancel Error"
			)
	
	def create_stock_entries(self):
		"""Create Stock Entries to move damaged items to Damage Godowns. Groups items by warehouse pairs (from_warehouse, to_warehouse) and creates separate stock entries for each unique warehouse combination. Handles multiple damages per frame by deduplicating serial_no entries."""
		if not self.damage_assessment_item:
			return
		
		if not self.stock_entry_type:
			frappe.throw(_("Stock Entry Type is required to create Stock Entries"))
		
		warehouse_groups = {}
		damaged_items = [item for item in self.damage_assessment_item if item.status == "Not OK"]
		
		if not damaged_items:
			return
		
		for item in damaged_items:
			if not item.serial_no or not item.from_warehouse or not item.to_warehouse:
				continue
			
			warehouse_key = (item.from_warehouse, item.to_warehouse)
			
			if warehouse_key not in warehouse_groups:
				warehouse_groups[warehouse_key] = {}
			
			if item.serial_no not in warehouse_groups[warehouse_key]:
				warehouse_groups[warehouse_key][item.serial_no] = item
		
		if not warehouse_groups:
			return
		
		created_stock_entries = []
		for (from_wh, to_wh), serial_no_items in warehouse_groups.items():
			stock_entry = frappe.new_doc("Stock Entry")
			stock_entry.stock_entry_type = self.stock_entry_type
			stock_entry.posting_date = self.date or frappe.utils.today()
			
			try:
				stock_entry.custom_damage_assessment = self.name
			except AttributeError:
				pass
			
			for serial_no, item in serial_no_items.items():
				item_code = frappe.db.get_value("Serial No", serial_no, "item_code")
				if not item_code:
					frappe.throw(_("Item Code not found for Serial No: {0}").format(serial_no))
				
				if not frappe.db.exists("Serial No", serial_no):
					frappe.throw(_("Serial No {0} does not exist").format(serial_no))
				
				actual_warehouse = frappe.db.get_value("Serial No", serial_no, "warehouse")
				
				if not actual_warehouse:
					stock_ledger = frappe.db.sql("""
						SELECT warehouse
						FROM `tabStock Ledger Entry`
						WHERE serial_no = %s
						ORDER BY posting_date DESC, posting_time DESC, creation DESC
						LIMIT 1
					""", (serial_no,), as_dict=True)
					if stock_ledger:
						actual_warehouse = stock_ledger[0].warehouse
				
				if not actual_warehouse and self.load_receipt_number:
					actual_warehouse = frappe.db.get_value(
						"Load Receipt",
						self.load_receipt_number,
						"warehouse"
					)
				
				source_warehouse = actual_warehouse or from_wh
				
				serial_warehouse = frappe.db.get_value("Serial No", serial_no, "warehouse")
				if not serial_warehouse and source_warehouse:
					try:
						frappe.db.set_value("Serial No", serial_no, "warehouse", source_warehouse, update_modified=False)
						frappe.db.commit()
					except Exception as e:
						frappe.log_error(
							f"Error updating Serial No {serial_no} warehouse: {str(e)}",
							"Serial No Warehouse Update Error"
						)
				
				if not source_warehouse:
					frappe.throw(_("Cannot determine source warehouse for Serial No {0}. Please ensure Serial No warehouse is set or item is in stock.").format(serial_no))
				
				stock_entry_item = stock_entry.append("items", {
					"item_code": item_code,
					"qty": 1,
					"s_warehouse": source_warehouse,
					"t_warehouse": to_wh,
				})
				
				stock_entry_item.serial_no = serial_no
			
			if stock_entry.items:
				stock_entry.insert(ignore_permissions=True)
				try:
					stock_entry.submit()
					created_stock_entries.append(stock_entry.name)
				except Exception as e:
					error_msg = str(e)
					if "needed in Warehouse" in error_msg or "not present" in error_msg.lower() or "insufficient stock" in error_msg.lower():
						frappe.log_error(
							f"Stock Entry {stock_entry.name} saved as draft. Submit PR first, then submit this Stock Entry.",
							"SE Draft - Stock Not Available"
						)
						created_stock_entries.append(stock_entry.name)
						frappe.msgprint(
							_("Stock Entry {0} created as draft because items are not in stock yet. Please create and submit Purchase Receipt first, then submit this Stock Entry.").format(
								frappe.utils.get_link_to_form("Stock Entry", stock_entry.name)
							),
							alert=True,
							indicator="orange"
						)
					else:
						raise
		
		if created_stock_entries:
			submitted_entries = []
			draft_entries = []
			for se_name in created_stock_entries:
				docstatus = frappe.db.get_value("Stock Entry", se_name, "docstatus")
				if docstatus == 1:
					submitted_entries.append(se_name)
				else:
					draft_entries.append(se_name)
			
			if len(created_stock_entries) == 1:
				se_name = created_stock_entries[0]
				docstatus = frappe.db.get_value("Stock Entry", se_name, "docstatus")
				if docstatus == 1:
					frappe.msgprint(
						_("Stock Entry {0} created and submitted - Items moved to Damage Godown").format(
							frappe.utils.get_link_to_form("Stock Entry", se_name)
						),
						alert=True,
						indicator="green"
					)
				else:
					frappe.msgprint(
						_("Stock Entry {0} created as draft - Submit after Purchase Receipt").format(
							frappe.utils.get_link_to_form("Stock Entry", se_name)
						),
						alert=True,
						indicator="orange"
					)
			else:
				submitted_links = ", ".join([
					frappe.utils.get_link_to_form("Stock Entry", se_name)
					for se_name in submitted_entries
				]) if submitted_entries else None
				
				draft_links = ", ".join([
					frappe.utils.get_link_to_form("Stock Entry", se_name)
					for se_name in draft_entries
				]) if draft_entries else None
				
				message_parts = []
				if submitted_links:
					message_parts.append(_("Submitted: {0}").format(submitted_links))
				if draft_links:
					message_parts.append(_("Draft (submit after PR): {0}").format(draft_links))
				
				frappe.msgprint(
					_("Created {0} Stock Entries. {1}").format(len(created_stock_entries), " | ".join(message_parts)),
					alert=True,
					indicator="green" if not draft_entries else "orange"
				)
	
	def cancel_stock_entry(self, stock_entry_name):
		"""Cancel a linked Stock Entry."""
		if not stock_entry_name:
			return
		
		if not frappe.db.exists("Stock Entry", stock_entry_name):
			return
		
		stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
		if stock_entry.docstatus != 1:
			return
		
		stock_entry.cancel()
		frappe.msgprint(
			_("Stock Entry {0} cancelled").format(stock_entry_name),
			alert=True,
			indicator="orange"
		)
	
	def update_load_receipt_frames_counts(self):
		"""Update frames OK/Not OK counts in linked Load Receipt."""
		load_receipt = frappe.db.get_value("Load Receipt", {"damage_assessment": self.name}, "name")
		if not load_receipt:
			return
		
		total_frames = frappe.db.get_value("Load Receipt", load_receipt, "total_receipt_quantity") or 0
		
		not_ok_count = len([item for item in (self.damage_assessment_item or []) if item.status == "Not OK"])
		
		ok_count = max(0, total_frames - not_ok_count)
		
		frappe.db.set_value("Load Receipt", load_receipt, {
			"frames_ok": ok_count,
			"frames_not_ok": not_ok_count
		}, update_modified=False)
		frappe.db.commit()


@frappe.whitelist()
def get_load_dispatch_from_serial_no(serial_no):
	"""Get the Load Dispatch document from which a Serial No (frame) originated, and also get the warehouse where the Serial No is currently located. The Serial No name is the same as the frame_no in Load Dispatch Item. This function looks up which Load Dispatch Item has this frame_no and returns the parent Load Dispatch name and the warehouse. Args: serial_no: The Serial No (frame_no) to look up. Returns: dict with load_dispatch name and warehouse, or None if not found."""
	if not serial_no:
		return {"load_dispatch": None, "warehouse": None}
	
	warehouse = frappe.db.get_value("Serial No", serial_no, "warehouse")
	
	load_dispatch_item = frappe.db.get_value(
		"Load Dispatch Item",
		{"frame_no": serial_no},
		["parent"],
		as_dict=True
	)
	
	result = {"load_dispatch": None, "warehouse": warehouse}
	if load_dispatch_item and load_dispatch_item.get("parent"):
		result["load_dispatch"] = load_dispatch_item.parent
	
	return result


@frappe.whitelist()
def get_frames_from_load_receipt(load_receipt_number):
	"""Get all frames (frame_no) from Load Receipt items. Also includes the warehouse where each frame is currently located. Args: load_receipt_number: The Load Receipt Number (Load Receipt name). Returns: list of dicts with frame_no, warehouse, and related information."""
	if not load_receipt_number:
		return []
	
	if not frappe.db.exists("Load Receipt", load_receipt_number):
		return []
	
	load_receipt = frappe.get_doc("Load Receipt", load_receipt_number)
	
	receipt_warehouse = load_receipt.warehouse
	
	load_dispatch = load_receipt.load_dispatch or ""
	
	frames = frappe.db.get_all(
		"Load Receipt Item",
		filters={
			"parent": load_receipt_number,
			"frame_no": ["!=", ""]
		},
		fields=["frame_no", "item_code", "model_name", "model_serial_no"],
		order_by="idx"
	)
	
	result = []
	for frame in frames:
		if frame.frame_no and str(frame.frame_no).strip():
			frame_no = str(frame.frame_no).strip()
			
			serial_warehouse = frappe.db.get_value("Serial No", frame_no, "warehouse")
			warehouse = receipt_warehouse or serial_warehouse
			
			result.append({
				"frame_no": frame_no,
				"serial_no": frame_no,
				"item_code": frame.item_code,
				"model_name": frame.model_name,
				"model_serial_no": frame.model_serial_no,
				"load_dispatch": load_dispatch,
				"warehouse": warehouse
			})
	
	return result
