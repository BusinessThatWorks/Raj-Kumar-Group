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
		"""Remove OK items before submitting and validate Load Receipt is submitted."""
		# Validate that linked Load Receipt is submitted (parent-child rule)
		if self.load_receipt_number:
			if not frappe.db.exists("Load Receipt", self.load_receipt_number):
				frappe.throw(_("Load Receipt {0} does not exist").format(self.load_receipt_number))
			
			lr_docstatus = frappe.db.get_value("Load Receipt", self.load_receipt_number, "docstatus")
			if lr_docstatus != 1:
				frappe.throw(
					_("Cannot submit Damage Assessment {0} because Load Receipt {1} is not submitted. Please submit the Load Receipt first.").format(
						frappe.utils.get_link_to_form("Damage Assessment", self.name),
						frappe.utils.get_link_to_form("Load Receipt", self.load_receipt_number)
					),
					title=_("Submit Load Receipt First")
				)
		
		self.remove_ok_items()
	
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
					# Use getattr to safely get field value, works better for multi-select and other field types
					if hasattr(item, fieldname):
						value = getattr(item, fieldname, None)
						# Preserve the value even if it's an empty string or None
						item_dict[fieldname] = value
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
		
		# Link this Damage Assessment to Load Receipt if load_receipt_number is set
		if self.load_receipt_number:
			self.link_to_load_receipt()
		
		self.update_load_receipt_frames_counts()
	
	def on_cancel(self):
		"""Cancel linked Stock Entries when Damage Assessment is cancelled."""
		# Clear link in Load Receipt if it exists (no checks - parent controls cancellation)
		if self.load_receipt_number:
			try:
				if frappe.db.exists("Load Receipt", self.load_receipt_number):
					current_da = frappe.db.get_value("Load Receipt", self.load_receipt_number, "damage_assessment")
					if current_da == self.name:
						# Clear the link and reset frame counts
						frappe.db.set_value("Load Receipt", self.load_receipt_number, {
							"damage_assessment": None,
							"frames_ok": 0,
							"frames_not_ok": 0
						}, update_modified=False)
			except Exception as e:
				frappe.log_error(
					f"Error clearing damage_assessment link in Load Receipt {self.load_receipt_number} when cancelling Damage Assessment {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
					"Damage Assessment Cancel Error"
				)
		
		# Find stock entries created by this Damage Assessment
		# We find them by matching serial numbers, date, and warehouse pairs
		stock_entries = []
		if self.damage_assessment_item:
			try:
				# Get all serial numbers from damage assessment items
				serial_nos = [item.serial_no for item in self.damage_assessment_item if item.serial_no and item.status == "Not OK"]
				
				if serial_nos:
					# Find stock entries that contain these serial numbers and match the date
					# This is a best-effort approach to find related stock entries
					stock_entry_names = frappe.db.sql("""
						SELECT DISTINCT se.name
						FROM `tabStock Entry` se
						INNER JOIN `tabStock Entry Detail` sed ON se.name = sed.parent
						WHERE se.docstatus = 1
							AND se.posting_date = %s
							AND sed.serial_no IN %s
					""", (self.date or frappe.utils.today(), tuple(serial_nos)), as_dict=True)
					
					stock_entries = [se.name for se in stock_entry_names]
			except Exception as e:
				# If query fails, log error and continue without cancelling stock entries
				frappe.log_error(
					f"Error finding stock entries for Damage Assessment {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
					"Damage Assessment Cancel Error"
				)
				stock_entries = []
		
		if not stock_entries:
			return
		
		failed_entries = []
		successful_entries = []
		critical_errors = []  # Errors that should prevent Damage Assessment cancellation
		
		for se_name in stock_entries:
			try:
				result = self.cancel_stock_entry(se_name)
				if result:
					successful_entries.append(se_name)
				else:
					failed_entries.append(se_name)
			except (frappe.ValidationError, frappe.LinkExistsError) as e:
				# Critical errors - prevent Damage Assessment cancellation
				error_msg = str(e)
				critical_errors.append((se_name, error_msg))
				frappe.log_error(
					f"Critical error cancelling Stock Entry {se_name} for Damage Assessment {self.name}: {error_msg}\nTraceback: {frappe.get_traceback()}",
					"Damage Assessment Cancel Error"
				)
			except Exception as e:
				# Non-critical errors - log but allow cancellation to proceed
				error_msg = str(e)
				failed_entries.append(se_name)
				frappe.log_error(
					f"Error cancelling Stock Entry {se_name} for Damage Assessment {self.name}: {error_msg}\nTraceback: {frappe.get_traceback()}",
					"Damage Assessment Cancel Error"
				)
		
		# Handle critical errors first - these prevent cancellation
		if critical_errors:
			error_parts = []
			for se_name, error_msg in critical_errors:
				error_parts.append(_("Stock Entry {0}: {1}").format(
					frappe.utils.get_link_to_form("Stock Entry", se_name),
					error_msg
				))
			if successful_entries:
				error_parts.append(_("\n\nNote: {0} Stock Entry(s) were cancelled successfully before the error occurred.").format(
					len(successful_entries)
				))
			frappe.throw(
				_("Cannot cancel Damage Assessment because the following Stock Entry(s) have dependent documents:\n\n{0}\n\nPlease cancel the dependent documents first, then try again.").format(
					"\n".join(error_parts)
				),
				title=_("Stock Entry Cancellation Error")
			)
		
		# Provide user feedback for non-critical errors
		if failed_entries:
			error_message = _("Failed to cancel {0} Stock Entry(s): {1}").format(
				len(failed_entries),
				", ".join([frappe.utils.get_link_to_form("Stock Entry", name) for name in failed_entries])
			)
			if successful_entries:
				error_message += _("\n\nSuccessfully cancelled {0} Stock Entry(s): {1}").format(
					len(successful_entries),
					", ".join([frappe.utils.get_link_to_form("Stock Entry", name) for name in successful_entries])
				)
			# Show error but allow Damage Assessment cancellation to proceed
			frappe.msgprint(
				error_message,
				title=_("Stock Entry Cancellation Warning"),
				alert=True,
				indicator="orange"
			)
		elif successful_entries:
			if len(successful_entries) == 1:
				frappe.msgprint(
					_("Stock Entry {0} cancelled successfully").format(
						frappe.utils.get_link_to_form("Stock Entry", successful_entries[0])
					),
					alert=True,
					indicator="green"
				)
			else:
				frappe.msgprint(
					_("Successfully cancelled {0} Stock Entry(s)").format(len(successful_entries)),
					alert=True,
					indicator="green"
				)
	
	def before_trash(self):
		"""Clear damage_assessment link before deletion."""
		if self.load_receipt_number:
			try:
				if frappe.db.exists("Load Receipt", self.load_receipt_number):
					current_da = frappe.db.get_value("Load Receipt", self.load_receipt_number, "damage_assessment")
					if current_da == self.name:
						frappe.db.set_value("Load Receipt", self.load_receipt_number, {
							"damage_assessment": None,
							"frames_ok": 0,
							"frames_not_ok": 0
						}, update_modified=False)
				frappe.flags.ignore_links = True
			except Exception as e:
				frappe.log_error(
					f"Error clearing damage_assessment link when deleting Damage Assessment {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
					"Damage Assessment Delete Error"
				)
		else:
			frappe.flags.ignore_links = True
	
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
		"""Cancel a linked Stock Entry. Returns True if successful, False otherwise."""
		if not stock_entry_name:
			return False
		
		if not frappe.db.exists("Stock Entry", stock_entry_name):
			frappe.log_error(
				f"Stock Entry {stock_entry_name} does not exist for Damage Assessment {self.name}",
				"Damage Assessment Cancel Error"
			)
			return False
		
		try:
			stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
			
			# Check if already cancelled
			if stock_entry.docstatus == 2:
				return True  # Already cancelled, consider it successful
			
			# Check if draft
			if stock_entry.docstatus == 0:
				return True  # Draft entries don't need cancellation
			
			# Only cancel submitted entries
			if stock_entry.docstatus == 1:
				stock_entry.cancel()
				return True
			
			return False
		except frappe.LinkExistsError as e:
			# Stock Entry has dependent documents
			error_msg = str(e)
			frappe.log_error(
				f"Cannot cancel Stock Entry {stock_entry_name} for Damage Assessment {self.name}: {error_msg}",
				"Damage Assessment Cancel Error"
			)
			raise frappe.ValidationError(
				_("Cannot cancel Stock Entry {0}: {1}. Please cancel dependent documents first.").format(
					frappe.utils.get_link_to_form("Stock Entry", stock_entry_name),
					error_msg
				)
			)
		except frappe.PermissionError as e:
			# Permission denied
			error_msg = str(e)
			frappe.log_error(
				f"Permission denied cancelling Stock Entry {stock_entry_name} for Damage Assessment {self.name}: {error_msg}",
				"Damage Assessment Cancel Error"
			)
			raise frappe.PermissionError(
				_("Permission denied: Cannot cancel Stock Entry {0}").format(
					frappe.utils.get_link_to_form("Stock Entry", stock_entry_name)
				)
			)
		except Exception as e:
			# Other errors
			error_msg = str(e)
			frappe.log_error(
				f"Error cancelling Stock Entry {stock_entry_name} for Damage Assessment {self.name}: {error_msg}\nTraceback: {frappe.get_traceback()}",
				"Damage Assessment Cancel Error"
			)
			raise
	
	def link_to_load_receipt(self):
		"""Link this Damage Assessment to the Load Receipt specified in load_receipt_number."""
		if not self.load_receipt_number:
			return
		
		if not frappe.db.exists("Load Receipt", self.load_receipt_number):
			frappe.log_error(
				f"Load Receipt {self.load_receipt_number} does not exist for Damage Assessment {self.name}",
				"Damage Assessment Link Error"
			)
			return
		
		# Check if Load Receipt already has a different Damage Assessment linked
		existing_da = frappe.db.get_value("Load Receipt", self.load_receipt_number, "damage_assessment")
		if existing_da and existing_da != self.name:
			frappe.throw(
				_("Load Receipt {0} is already linked to Damage Assessment {1}. Please unlink it first or use a different Load Receipt.").format(
					frappe.utils.get_link_to_form("Load Receipt", self.load_receipt_number),
					frappe.utils.get_link_to_form("Damage Assessment", existing_da)
				),
				title=_("Load Receipt Already Linked")
			)
		
		# Link this Damage Assessment to the Load Receipt
		frappe.db.set_value("Load Receipt", self.load_receipt_number, "damage_assessment", self.name, update_modified=False)
		frappe.db.commit()
	
	def update_load_receipt_frames_counts(self):
		"""Update frames OK/Not OK counts in linked Load Receipt."""
		# First try to find by damage_assessment link
		load_receipt = frappe.db.get_value("Load Receipt", {"damage_assessment": self.name}, "name")
		
		# If not found by link, try using load_receipt_number
		if not load_receipt and self.load_receipt_number:
			load_receipt = self.load_receipt_number
		
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
def get_load_reference_no_from_serial_no(serial_no):
	"""Get the Load Reference Number (Load Plan) from which a Serial No (frame) originated.
	The Serial No name is the same as the frame_no in Load Dispatch Item.
	This function looks up which Load Dispatch Item has this frame_no, gets the parent Load Dispatch,
	and returns the load_reference_no from that Load Dispatch.
	
	Args:
		serial_no: The Serial No (frame_no) to look up.
	
	Returns:
		str: Load Reference Number (Load Plan name) or None if not found.
	"""
	if not serial_no:
		return None
	
	# Find Load Dispatch Item with this frame_no
	load_dispatch_item = frappe.db.get_value(
		"Load Dispatch Item",
		{"frame_no": serial_no},
		["parent"],
		as_dict=True
	)
	
	if not load_dispatch_item or not load_dispatch_item.get("parent"):
		return None
	
	load_dispatch_name = load_dispatch_item.parent
	
	# Get load_reference_no from Load Dispatch
	load_reference_no = frappe.db.get_value(
		"Load Dispatch",
		load_dispatch_name,
		"load_reference_no"
	)
	
	return load_reference_no


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
	
	# Get load_reference_no from Load Dispatch if available
	load_reference_no = None
	if load_dispatch:
		load_reference_no = frappe.db.get_value("Load Dispatch", load_dispatch, "load_reference_no")
	
	for frame in frames:
		if frame.frame_no and str(frame.frame_no).strip():
			frame_no = str(frame.frame_no).strip()
			
			serial_warehouse = frappe.db.get_value("Serial No", frame_no, "warehouse")
			warehouse = receipt_warehouse or serial_warehouse
			
			# Try to get load_reference_no from Load Dispatch Item if not already found
			frame_load_reference_no = load_reference_no
			if not frame_load_reference_no:
				# Fallback: get from Load Dispatch Item directly
				load_dispatch_item = frappe.db.get_value(
					"Load Dispatch Item",
					{"frame_no": frame_no},
					["parent"],
					as_dict=True
				)
				if load_dispatch_item and load_dispatch_item.get("parent"):
					frame_load_reference_no = frappe.db.get_value(
						"Load Dispatch",
						load_dispatch_item.parent,
						"load_reference_no"
					)
			
			result.append({
				"frame_no": frame_no,
				"serial_no": frame_no,
				"item_code": frame.item_code,
				"model_name": frame.model_name,
				"model_serial_no": frame.model_serial_no,
				"load_dispatch": load_dispatch,
				"load_reference_no": frame_load_reference_no,
				"warehouse": warehouse
			})
	
	return result


@frappe.whitelist()
def break_circular_dependency(damage_assessment_name=None, load_receipt_name=None):
	"""Utility function to manually break circular dependency between Damage Assessment and Load Receipt.
	This can be called before deletion if automatic link clearing doesn't work.
	
	Args:
		damage_assessment_name: Name of Damage Assessment document
		load_receipt_name: Name of Load Receipt document
	"""
	if damage_assessment_name:
		try:
			da = frappe.get_doc("Damage Assessment", damage_assessment_name)
			if da.load_receipt_number:
				if frappe.db.exists("Load Receipt", da.load_receipt_number):
					current_da = frappe.db.get_value("Load Receipt", da.load_receipt_number, "damage_assessment")
					if current_da == damage_assessment_name:
						frappe.db.set_value("Load Receipt", da.load_receipt_number, {
							"damage_assessment": None,
							"frames_ok": 0,
							"frames_not_ok": 0
						}, update_modified=False)
						frappe.db.commit()
						return {"message": f"Cleared damage_assessment link in Load Receipt {da.load_receipt_number}"}
		except Exception as e:
			frappe.log_error(
				f"Error breaking circular dependency for Damage Assessment {damage_assessment_name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
				"Break Circular Dependency Error"
			)
			raise
	
	if load_receipt_name:
		try:
			lr = frappe.get_doc("Load Receipt", load_receipt_name)
			if lr.damage_assessment:
				frappe.db.set_value("Load Receipt", load_receipt_name, {
					"damage_assessment": None,
					"frames_ok": 0,
					"frames_not_ok": 0
				}, update_modified=False)
				frappe.db.commit()
				return {"message": f"Cleared damage_assessment link in Load Receipt {load_receipt_name}"}
		except Exception as e:
			frappe.log_error(
				f"Error breaking circular dependency for Load Receipt {load_receipt_name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
				"Break Circular Dependency Error"
			)
			raise
	
	return {"message": "No action taken. Provide either damage_assessment_name or load_receipt_name."}
