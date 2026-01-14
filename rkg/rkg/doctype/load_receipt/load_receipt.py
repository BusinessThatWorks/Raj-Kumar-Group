import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import flt
from frappe.model.mapper import get_mapped_doc


class LoadReceipt(Document):
	def validate(self):
		"""Validate Load Receipt."""
		if self.docstatus == 1:
			if self.status != "Submitted":
				db_status = frappe.db.get_value("Load Receipt", self.name, "status")
				if db_status == "Submitted":
					self.status = "Submitted"
				else:
					self.status = "Submitted"
					frappe.db.set_value("Load Receipt", self.name, "status", "Submitted", update_modified=False)
		elif self.docstatus == 0:
			if not self.status:
				self.status = "Draft"
			elif self.status not in ["Draft", "Not Saved"]:
				self.status = "Draft"
		
		if self.load_dispatch:
			if not frappe.db.exists("Load Dispatch", self.load_dispatch):
				frappe.throw(_("Load Dispatch {0} does not exist").format(self.load_dispatch))
			
			load_dispatch = frappe.get_doc("Load Dispatch", self.load_dispatch)
			if load_dispatch.docstatus != 1:
				frappe.throw(_("Load Dispatch {0} must be submitted before creating Load Receipt").format(self.load_dispatch))
		
		if self.load_dispatch:
			self.calculate_totals_from_purchase_documents()
		else:
			self.calculate_total_receipt_quantity()
	
	def calculate_total_receipt_quantity(self):
		"""Count the number of rows with non-empty frame_no in Load Receipt Item child table."""
		self.total_receipt_quantity = sum(1 for item in (self.items or []) if item.frame_no and str(item.frame_no).strip())
	
	def calculate_totals_from_purchase_documents(self):
		"""Calculate total_receipt_quantity and total_billed_quantity from Purchase Receipts/Invoices linked to Load Dispatch."""
		if not self.load_dispatch:
			self.total_receipt_quantity = 0
			self.total_billed_quantity = 0
			return
		
		total_received_qty = 0
		total_billed_qty = 0
		
		if frappe.db.has_column("Purchase Receipt", "custom_load_dispatch"):
			pr_list = frappe.get_all(
				"Purchase Receipt",
				filters={
					"docstatus": 1,
					"custom_load_dispatch": self.load_dispatch
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
					"custom_load_dispatch": self.load_dispatch
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
									if pr_load_dispatch == self.load_dispatch:
										total_received_qty = total_billed_qty
										break
				except Exception:
					continue
		
		self.total_receipt_quantity = total_received_qty
		self.total_billed_quantity = total_billed_qty
	
	def on_submit(self):
		"""Set status on submit."""
		self.status = "Submitted"
		frappe.db.set_value("Load Receipt", self.name, "status", "Submitted", update_modified=False)
		self.reload()
	
	def before_cancel(self):
		"""Cancel linked Damage Assessment before cancelling Load Receipt."""
		if self.damage_assessment:
			try:
				da_name = self.damage_assessment
				
				if frappe.db.exists("Damage Assessment", da_name):
					da_docstatus = frappe.db.get_value("Damage Assessment", da_name, "docstatus")
					
					if da_docstatus == 1:
						da_doc = frappe.get_doc("Damage Assessment", da_name)
						da_doc.cancel()
				
				frappe.db.set_value("Load Receipt", self.name, {
					"damage_assessment": None,
					"frames_ok": 0,
					"frames_not_ok": 0
				}, update_modified=False)
				
				self.damage_assessment = None
				self.frames_ok = 0
				self.frames_not_ok = 0
			except Exception as e:
				frappe.log_error(
					f"Error cancelling Damage Assessment {self.damage_assessment} when cancelling Load Receipt {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
					"Load Receipt Cancel Error"
				)
	
	def on_cancel(self):
		"""Set status on cancel."""
		self.status = "Draft"
		frappe.db.set_value("Load Receipt", self.name, "status", "Draft", update_modified=False)
		self.reload()
	
	def before_trash(self):
		"""Clear damage_assessment link before deletion."""
		if self.damage_assessment:
			try:
				frappe.db.set_value("Load Receipt", self.name, {
					"damage_assessment": None,
					"frames_ok": 0,
					"frames_not_ok": 0
				}, update_modified=False)
				frappe.flags.ignore_links = True
			except Exception as e:
				frappe.log_error(
					f"Error clearing damage_assessment link when deleting Load Receipt {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
					"Load Receipt Delete Error"
				)


@frappe.whitelist()
def create_load_receipt(source_name, target_doc=None):
	"""Create Load Receipt from Load Dispatch."""
	if frappe.db.has_column("Load Receipt", "load_dispatch"):
		existing = frappe.get_all(
			"Load Receipt",
			filters={"load_dispatch": source_name},
			fields=["name"],
			limit=1
		)
		if existing:
			frappe.throw(_("Load Receipt {0} already exists for this Load Dispatch.").format(existing[0].name))
	
	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		target.load_dispatch = source_name
		target.load_reference_no = source.load_reference_no
		target.status = "Draft"
	
	def update_item(source, target, source_parent):
		pass
	
	doc = get_mapped_doc(
		"Load Dispatch",
		source_name,
		{
			"Load Dispatch": {
				"doctype": "Load Receipt",
				"validation": {"docstatus": ["=", 1]},
				"field_map": {
					"load_reference_no": "load_reference_no"
				}
			},
			"Load Dispatch Item": {
				"doctype": "Load Receipt Item",
				"field_map": {},
				"postprocess": update_item
			}
		},
		target_doc,
		set_missing_values
	)
	
	if doc:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"name": doc.name}
	return None


@frappe.whitelist()
def get_frames_status_counts(damage_assessment):
	"""Get count of OK and Not OK frames from Damage Assessment."""
	if not damage_assessment:
		return {"frames_ok": 0, "frames_not_ok": 0}
	
	load_receipt = frappe.db.get_value("Load Receipt", {"damage_assessment": damage_assessment}, "name")
	if not load_receipt:
		return {"frames_ok": 0, "frames_not_ok": 0}
	
	total_frames = frappe.db.get_value("Load Receipt", load_receipt, "total_receipt_quantity") or 0
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


def update_frames_status_counts_in_load_receipt(load_receipt_name, damage_assessment_name):
	"""Update frames OK/Not OK counts in Load Receipt from Damage Assessment."""
	if not load_receipt_name or not damage_assessment_name:
		return
	
	counts = get_frames_status_counts(damage_assessment_name)
	if isinstance(counts, dict):
		frappe.db.set_value("Load Receipt", load_receipt_name, {
			"frames_ok": counts.get("frames_ok", 0),
			"frames_not_ok": counts.get("frames_not_ok", 0)
		}, update_modified=False)
		frappe.db.commit()


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


def _create_purchase_document_unified(source_name, doctype, target_doc=None, warehouse=None, frame_warehouse_mapping=None):
	"""Unified Purchase Receipt/Invoice creation from Load Receipt"""
	from frappe.model.mapper import get_mapped_doc
	import json
	
	if frappe.db.has_column(doctype, "custom_load_dispatch"):
		load_receipt = frappe.get_doc("Load Receipt", source_name)
		if load_receipt.load_dispatch:
			existing = frappe.get_all(doctype, filters={"custom_load_dispatch": load_receipt.load_dispatch}, fields=["name"], limit=1)
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
		if hasattr(target, "custom_load_receipt"):
			target.custom_load_receipt = source_name
		elif frappe.db.has_column(doctype, "custom_load_receipt"):
			target.db_set("custom_load_receipt", source_name)
		
		if source.load_dispatch:
			target.custom_load_reference_no = source.load_reference_no
			if hasattr(target, "custom_load_dispatch"):
				target.custom_load_dispatch = source.load_dispatch
			elif frappe.db.has_column(doctype, "custom_load_dispatch"):
				target.db_set("custom_load_dispatch", source.load_dispatch)
		
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
	doc = get_mapped_doc("Load Receipt", source_name, {
		"Load Receipt": {"doctype": doctype, "validation": {"docstatus": ["=", 1]}, "field_map": {"load_reference_no": "load_reference_no"}},
		"Load Receipt Item": {"doctype": item_doctype, "field_map": {"item_code": "item_code", "model_variant": "item_name", "frame_no": "serial_no", "item_group": "item_group"}, "postprocess": update_item}
	}, target_doc, set_missing_values)
	
	if doctype == "Purchase Invoice" and doc and hasattr(doc, "items"):
		source_doc = frappe.get_doc("Load Receipt", source_name)
		if source_doc and source_doc.items:
			item_to_frame = {lri.item_code: str(lri.frame_no).strip() for lri in source_doc.items if hasattr(lri, "item_code") and lri.item_code and hasattr(lri, "frame_no") and lri.frame_no}
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
def create_purchase_receipt_from_load_receipt(source_name, target_doc=None):
	"""Create Purchase Receipt from Load Receipt."""
	load_receipt = frappe.get_doc("Load Receipt", source_name)
	load_receipt.reload()
	
	if not load_receipt.warehouse:
		frappe.throw(_("Warehouse must be set in Load Receipt before creating Purchase Receipt"))
	
	if load_receipt.docstatus != 1:
		frappe.throw(_("Load Receipt must be submitted before creating Purchase Receipt"))
	
	return _create_purchase_document_unified(source_name, "Purchase Receipt", target_doc, load_receipt.warehouse)


def update_load_receipt_totals_from_document(doc, method=None):
	"""Update Load Receipt totals (total_receipt_quantity and total_billed_quantity) when Purchase Receipt/Invoice is submitted or cancelled."""
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
			fields=["name"]
		)

		if not load_receipts:
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
							# If we can't get the document, skip it
							pass
					total_received_qty += pr_qty
				except Exception as e:
					frappe.log_error(
						f"Error processing Purchase Receipt {pr.get('name', 'Unknown')}: {str(e)}",
						"Load Receipt Totals Update Error"
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
							# If we can't get the document, skip it
							pass
					total_received_qty += pr_qty
				except Exception as e:
					frappe.log_error(
						f"Error processing Purchase Receipt {pr.get('name', 'Unknown')}: {str(e)}",
						"Load Receipt Totals Update Error"
					)
					continue
			
			linked_purchase_receipts = set()
			try:
				if doc.items:
					linked_purchase_receipts = {item.purchase_receipt for item in doc.items if hasattr(item, "purchase_receipt") and item.purchase_receipt}
			except Exception as e:
				frappe.log_error(
					f"Error getting linked purchase receipts: {str(e)}",
					"Load Receipt Totals Update Error"
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
						"Load Receipt Totals Update Error"
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

		for lr in load_receipts:
			try:
				frappe.db.set_value(
					"Load Receipt",
					lr.name,
					{
						"total_receipt_quantity": total_received_qty,
						"total_billed_quantity": total_billed_qty
					},
					update_modified=False
				)
			except Exception as e:
				frappe.log_error(
					f"Error updating Load Receipt {lr.name}: {str(e)}",
					"Load Receipt Totals Update Error"
				)
				continue

		frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Error updating Load Receipt totals from {doc.doctype} {doc.name}: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Load Receipt Totals Update Error"
		)


@frappe.whitelist()
def fix_load_receipt_statuses():
	"""Fix Load Receipt statuses that don't match docstatus."""
	try:
		load_receipts = frappe.get_all(
			"Load Receipt",
			fields=["name", "docstatus", "status"]
		)
		
		fixed_count = 0
		for lr in load_receipts:
			needs_fix = False
			correct_status = None
			
			if lr.docstatus == 1:
				if lr.status != "Submitted":
					needs_fix = True
					correct_status = "Submitted"
			elif lr.docstatus == 0:
				if lr.status not in ["Draft", "Not Saved", None]:
					needs_fix = True
					correct_status = "Draft"
			
			if needs_fix:
				frappe.db.set_value("Load Receipt", lr.name, "status", correct_status, update_modified=False)
				fixed_count += 1
				frappe.log_error(
					f"Fixed Load Receipt {lr.name}: Changed status from '{lr.status}' to '{correct_status}'",
					"Load Receipt Status Fix"
				)
		
		frappe.db.commit()
		
		return {
			"message": f"Fixed {fixed_count} Load Receipt(s) with incorrect status",
			"fixed_count": fixed_count,
			"total_checked": len(load_receipts)
		}
	except Exception as e:
		frappe.log_error(
			f"Error fixing Load Receipt statuses: {str(e)}\nTraceback: {frappe.get_traceback()}",
			"Load Receipt Status Fix Error"
		)
		raise



