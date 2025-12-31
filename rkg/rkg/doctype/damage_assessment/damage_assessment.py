import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt


class DamageAssessment(Document):
	def validate(self):
		"""Validate and calculate totals."""
		self.set_stock_entry_type()
		self.remove_ok_items()  # Remove items with Status "OK" before validation
		self.validate_damage_items()
		self.calculate_total_estimated_cost()
	
	def set_stock_entry_type(self):
		"""Set Stock Entry Type to Material Transfer if not already set."""
		# Check if Material Transfer exists, if not use Material Transfer (for Manufacture) as fallback
		material_transfer = "Material Transfer"
		
		if not frappe.db.exists("Stock Entry Type", material_transfer):
			# Try alternative name
			alternative = "Material Transfer (for Manufacture)"
			if frappe.db.exists("Stock Entry Type", alternative):
				material_transfer = alternative
			else:
				# If neither exists, throw error
				frappe.throw(_("Stock Entry Type 'Material Transfer' not found. Please create it in Stock Entry Type master."))
		
		if not self.stock_entry_type:
			self.stock_entry_type = material_transfer
		elif self.stock_entry_type != material_transfer:
			# Force it to Material Transfer
			self.stock_entry_type = material_transfer
	
	def remove_ok_items(self):
		"""Remove child table rows where Status is 'OK', keeping only 'Not OK' items."""
		if not self.damage_assessment_item:
			return
		
		# Count OK items before removal for message
		ok_count = sum(1 for item in self.damage_assessment_item if item.status == "OK")
		
		if ok_count == 0:
			return  # No OK items to remove
		
		# Get child table meta to know which fields to copy
		child_meta = frappe.get_meta("Damage Assessment Item")
		fieldnames = [df.fieldname for df in child_meta.fields if df.fieldtype not in ['Section Break', 'Column Break', 'Tab Break']]
		
		# Filter to keep only "Not OK" items and convert to dict
		not_ok_items_data = []
		for item in self.damage_assessment_item:
			if item.status == "Not OK":
				# Convert child table row to dictionary
				item_dict = {}
				for fieldname in fieldnames:
					if hasattr(item, fieldname):
						item_dict[fieldname] = item.get(fieldname)
				not_ok_items_data.append(item_dict)
		
		# Clear the child table and add back only "Not OK" items
		self.damage_assessment_item = []
		for item_data in not_ok_items_data:
			self.append("damage_assessment_item", item_data)
		
		# Show message if items were removed
		if ok_count > 0:
			frappe.msgprint(
				_("Removed {0} item(s) with Status 'OK' from the child table. Only 'Not OK' items will be saved.").format(ok_count),
				alert=True,
				indicator="blue"
			)
	
	def validate_damage_items(self):
		"""Validate that Not OK items have at least one damage/issue (type_of_damage_1 is mandatory), estimated cost, and warehouses."""
		if self.damage_assessment_item:
			for item in self.damage_assessment_item:
				if item.status == "Not OK":
					# At least one damage/issue is required (type_of_damage_1 is mandatory)
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
		# Create stock entries for damaged frames (grouped by warehouse pairs)
		if self.stock_entry_type:
			self.create_stock_entries()
	
	def on_cancel(self):
		"""Cancel linked Stock Entries when Damage Assessment is cancelled."""
		# Try to get stock entries linked to this Damage Assessment via custom field. If custom field doesn't exist, this will return empty list
		try:
			stock_entries = frappe.get_all(
				"Stock Entry",
				filters={
					"custom_damage_assessment": self.name,
					"docstatus": 1  # Only cancel submitted entries
				},
				fields=["name"]
			)
			
			for se in stock_entries:
				self.cancel_stock_entry(se.name)
		except Exception:
			# Custom field may not exist, or there might be other issues. Log the error but don't fail the cancel operation
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
		
		# Group damaged items by warehouse pairs
		warehouse_groups = {}
		damaged_items = [item for item in self.damage_assessment_item if item.status == "Not OK"]
		
		if not damaged_items:
			return  # No damaged items, no stock entries needed
		
		for item in damaged_items:
			if not item.serial_no or not item.from_warehouse or not item.to_warehouse:
				continue
			
			# Create a key for grouping by warehouse pair
			warehouse_key = (item.from_warehouse, item.to_warehouse)
			
			if warehouse_key not in warehouse_groups:
				warehouse_groups[warehouse_key] = {}
			
			# Use serial_no as key to deduplicate - if same frame has multiple damages, we only need one stock entry item per frame
			if item.serial_no not in warehouse_groups[warehouse_key]:
				warehouse_groups[warehouse_key][item.serial_no] = item
		
		if not warehouse_groups:
			return
		
		# Create a stock entry for each warehouse pair
		created_stock_entries = []
		for (from_wh, to_wh), serial_no_items in warehouse_groups.items():
			stock_entry = frappe.new_doc("Stock Entry")
			stock_entry.stock_entry_type = self.stock_entry_type
			stock_entry.posting_date = self.date or frappe.utils.today()
			
			# Add custom field to link back to Damage Assessment. Note: This assumes you have a custom field 'custom_damage_assessment' in Stock Entry. If not, you may need to add it or use a different method to track
			try:
				stock_entry.custom_damage_assessment = self.name
			except AttributeError:
				pass  # Custom field may not exist, continue without it
			
			# Add one stock entry item per unique serial_no (frame)
			for serial_no, item in serial_no_items.items():
				# Get item_code from Serial No
				item_code = frappe.db.get_value("Serial No", serial_no, "item_code")
				if not item_code:
					frappe.throw(_("Item Code not found for Serial No: {0}").format(serial_no))
				
				stock_entry.append("items", {
					"item_code": item_code,
					"custom_serial_no": serial_no,
					"qty": 1,
					"s_warehouse": from_wh,
					"t_warehouse": to_wh,
				})
			
			if stock_entry.items:
				stock_entry.insert(ignore_permissions=True)
				stock_entry.submit()
				created_stock_entries.append(stock_entry.name)
		
		if created_stock_entries:
			# Show message with links to created stock entries
			if len(created_stock_entries) == 1:
				frappe.msgprint(
					_("Stock Entry {0} created - Items moved to Damage Godown").format(
						frappe.utils.get_link_to_form("Stock Entry", created_stock_entries[0])
					),
					alert=True,
					indicator="green"
				)
			else:
				links = ", ".join([
					frappe.utils.get_link_to_form("Stock Entry", se_name)
					for se_name in created_stock_entries
				])
				frappe.msgprint(
					_("Created {0} Stock Entries: {1}").format(len(created_stock_entries), links),
					alert=True,
					indicator="green"
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


@frappe.whitelist()
def get_load_dispatch_from_serial_no(serial_no):
	"""Get the Load Dispatch document from which a Serial No (frame) originated, and also get the warehouse where the Serial No is currently located. The Serial No name is the same as the frame_no in Load Dispatch Item. This function looks up which Load Dispatch Item has this frame_no and returns the parent Load Dispatch name and the warehouse. Args: serial_no: The Serial No (frame_no) to look up. Returns: dict with load_dispatch name and warehouse, or None if not found."""
	if not serial_no:
		return {"load_dispatch": None, "warehouse": None}
	
	# Get warehouse from Serial No
	warehouse = frappe.db.get_value("Serial No", serial_no, "warehouse")
	
	# Look up Load Dispatch Item where frame_no matches the serial_no
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
def get_frames_from_load_plan(load_plan_reference_no):
	"""Get all frames (frame_no) from all Load Dispatch documents linked to a Load Plan. Also includes the warehouse where each frame is currently located. Args: load_plan_reference_no: The Load Plan Reference No (Load Plan name). Returns: list of dicts with frame_no, warehouse, and related information."""
	if not load_plan_reference_no:
		return []
	
	if not frappe.db.exists("Load Plan", load_plan_reference_no):
		return []
	
	# Get all Load Dispatch documents linked to this Load Plan
	load_dispatches = frappe.db.get_all(
		"Load Dispatch",
		filters={
			"load_reference_no": load_plan_reference_no
		},
		fields=["name"],
		order_by="name"
	)
	
	if not load_dispatches:
		return []
	
	# Get all Load Dispatch Item names from all Load Dispatches
	load_dispatch_names = [ld.name for ld in load_dispatches]
	
	# Get all Load Dispatch Items with frame_no from all these Load Dispatches
	frames = frappe.db.get_all(
		"Load Dispatch Item",
		filters={
			"parent": ["in", load_dispatch_names],
			"frame_no": ["!=", ""]
		},
		fields=["frame_no", "item_code", "model_name", "model_serial_no", "parent"],
		order_by="parent, idx"
	)
	
	# Return list of frame information with warehouse
	result = []
	seen_frames = set()  # To avoid duplicates if same frame appears in multiple dispatches
	for frame in frames:
		if frame.frame_no and str(frame.frame_no).strip():
			frame_no = str(frame.frame_no).strip()
			# Only add if we haven't seen this frame_no before
			if frame_no not in seen_frames:
				seen_frames.add(frame_no)
				
				# Get warehouse from Serial No
				warehouse = frappe.db.get_value("Serial No", frame_no, "warehouse")
				
				result.append({
					"frame_no": frame_no,
					"serial_no": frame_no,  # frame_no is the serial_no name
					"item_code": frame.item_code,
					"model_name": frame.model_name,
					"model_serial_no": frame.model_serial_no,
					"load_dispatch": frame.parent,
					"warehouse": warehouse  # Add warehouse
				})
	
	return result
