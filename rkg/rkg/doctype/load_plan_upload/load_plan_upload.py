import frappe
from frappe import _
from frappe.model.document import Document


class LoadPlanUpload(Document):
	def validate(self):
		if not self.excel_file:
			frappe.throw(_("Please attach an Excel file before submitting"))
		
		if self.has_value_changed("excel_file"):
			self.upload_items = []
			self.total_load_plans_created = 0
	
	def before_submit(self):
		if not self.excel_file:
			frappe.throw(_("No file attached"))
		
		self.upload_items = []
		
		try:
			check_result = check_multiple_load_reference_numbers(self.excel_file)
			
			if check_result.get("count") == 0:
				frappe.throw(_("No Load Reference Numbers found in the file. Please check the file format."))
			
			create_multiple = check_result.get("has_multiple", False)
			analysis_result = _analyze_load_plans_for_upload(
				file_url=self.excel_file,
				create_multiple=create_multiple
			)
			
			for lp in analysis_result.get("will_create", []):
				row = self.append("upload_items", {})
				row.load_reference_no = lp.get("load_reference_no", "")
				row.status = "Created"
				row.rows_count = lp.get("rows_count", 0)
				row.total_quantity = lp.get("estimated_quantity", 0)
				row.error_message = ""
			
			for skipped in analysis_result.get("will_skip", []):
				row = self.append("upload_items", {})
				row.load_reference_no = skipped.get("load_reference_no", "")
				row.status = "Skipped"
				row.rows_count = 0
				row.total_quantity = 0
				row.error_message = skipped.get("reason", "Load Plan already exists")
			
			self.total_load_plans_created = analysis_result.get("total_will_create", 0)
			
		except Exception as e:
			row = self.append("upload_items", {})
			row.load_reference_no = ""
			row.status = "Error"
			row.rows_count = 0
			row.total_quantity = 0
			row.error_message = _("Error: {0}").format(str(e))
			
			self.total_load_plans_created = 0
			
			frappe.log_error(
				message=f"Error analyzing file in before_submit: {str(e)}",
				title="Load Plan Upload Analysis Error"
			)
			
			frappe.throw(_("Error analyzing file: {0}").format(str(e)))
	
	def on_submit(self):
		if not self.excel_file:
			frappe.throw(_("No file attached"))
		
		check_result = check_multiple_load_reference_numbers(self.excel_file)
		
		if check_result.get("count") == 0:
			frappe.throw(_("No Load Reference Numbers found in the file. Please check the file format."))
		
		create_multiple = check_result.get("has_multiple", False)
		
		try:
			create_load_plans_from_file_skip_existing(
				file_url=self.excel_file,
				create_multiple=create_multiple
			)
		except Exception as e:
			frappe.log_error(
				message=f"Error creating Load Plans: {str(e)}",
				title="Load Plan Upload Error"
			)
			frappe.throw(_("Error processing file: {0}").format(str(e)))


def _analyze_load_plans_for_upload(file_url, create_multiple=True):
	"""Analyze file to determine which Load Plans will be created/skipped."""
	if not file_url:
		return {"will_create": [], "will_skip": [], "total_will_create": 0}
	
	from rkg.rkg.doctype.load_plan.load_plan import process_tabular_file
	
	all_rows = process_tabular_file(file_url)
	
	if not all_rows:
		return {"will_create": [], "will_skip": [], "total_will_create": 0}
	
	grouped_data = {}
	for row in all_rows:
		load_ref = row.get("load_reference_no")
		if not load_ref:
			continue
		
		load_ref = str(load_ref).strip()
		if load_ref not in grouped_data:
			grouped_data[load_ref] = {
				"load_reference_no": load_ref,
				"rows": []
			}
		
		grouped_data[load_ref]["rows"].append(row)
	
	if not grouped_data:
		return {"will_create": [], "will_skip": [], "total_will_create": 0}
	
	unique_load_refs = list(grouped_data.keys())
	existing_load_plans = []
	new_load_refs = []
	
	for load_ref in unique_load_refs:
		if frappe.db.exists("Load Plan", load_ref):
			existing_load_plans.append(load_ref)
		else:
			new_load_refs.append(load_ref)
	
	should_create_multiple = create_multiple and len(new_load_refs) > 1
	
	will_create = []
	load_refs_to_process = new_load_refs if should_create_multiple else (new_load_refs[:1] if new_load_refs else [])
	
	for load_ref in load_refs_to_process:
		data = grouped_data[load_ref]
		rows_count = len(data.get("rows", []))
		estimated_quantity = sum(int(row.get("quantity", 0) or 0) for row in data.get("rows", []))
		
		will_create.append({
			"load_reference_no": load_ref,
			"rows_count": rows_count,
			"estimated_quantity": estimated_quantity
		})
	
	will_skip = []
	for load_ref in existing_load_plans:
		will_skip.append({
			"load_reference_no": load_ref,
			"reason": "Load Plan already exists"
		})
	
	return {
		"will_create": will_create,
		"will_skip": will_skip,
		"total_will_create": len(will_create)
	}


@frappe.whitelist()
def check_multiple_load_reference_numbers(file_url):
	"""Check if multiple load reference numbers exist in the file."""
	if not file_url:
		frappe.throw(_("No file provided"))
	
	from rkg.rkg.doctype.load_plan.load_plan import process_tabular_file
	
	all_rows = process_tabular_file(file_url)
	
	if not all_rows:
		frappe.throw(_("No data found in the file"))
	
	grouped_data = {}
	for idx, row in enumerate(all_rows):
		load_ref = row.get("load_reference_no")
		if not load_ref:
			continue
		
		load_ref = str(load_ref).strip()
		if load_ref not in grouped_data:
			grouped_data[load_ref] = {
				"load_reference_no": load_ref,
				"dispatch_plan_date": row.get("dispatch_plan_date"),
				"payment_plan_date": row.get("payment_plan_date"),
				"rows": []
			}
		
		grouped_data[load_ref]["rows"].append(row)
	
	if not grouped_data:
		frappe.throw(_("No valid Load Reference Numbers found in the file"))
	
	unique_load_refs = list(grouped_data.keys())
	unique_load_refs_list = sorted(unique_load_refs)
	count = len(unique_load_refs_list)
	
	load_ref_details = []
	for load_ref in unique_load_refs_list:
		data = grouped_data[load_ref]
		row_count = len(data.get("rows", []))
		total_qty = sum(int(row.get("quantity", 0) or 0) for row in data.get("rows", []))
		
		load_ref_details.append({
			"load_reference_no": load_ref,
			"rows_count": row_count,
			"total_quantity": total_qty,
			"dispatch_plan_date": data.get("dispatch_plan_date"),
			"payment_plan_date": data.get("payment_plan_date")
		})
	
	if count == 0:
		message = _("No Load Reference Numbers found in the file")
	elif count == 1:
		message = _("Single Load Reference Number found: {0}").format(unique_load_refs_list[0])
	else:
		message = _("Multiple Load Reference Numbers found ({0}): {1}").format(
			count, ", ".join(unique_load_refs_list)
		)
	
	return {
		"unique_load_refs": unique_load_refs_list,
		"count": count,
		"has_multiple": count > 1,
		"message": message,
		"total_rows": len(all_rows),
		"load_ref_details": load_ref_details
	}


@frappe.whitelist()
def create_load_plans_from_file_skip_existing(file_url, create_multiple=True):
	"""Create Load Plan documents, skipping existing ones."""
	if not file_url:
		frappe.throw(_("No file provided"))
	
	from rkg.rkg.doctype.load_plan.load_plan import process_tabular_file, _create_single_load_plan
	
	all_rows = process_tabular_file(file_url)
	
	if not all_rows:
		frappe.throw(_("No data found in the file"))
	
	grouped_data = {}
	for idx, row in enumerate(all_rows):
		load_ref = row.get("load_reference_no")
		if not load_ref:
			continue
		
		load_ref = str(load_ref).strip()
		if load_ref not in grouped_data:
			grouped_data[load_ref] = {
				"load_reference_no": load_ref,
				"dispatch_plan_date": row.get("dispatch_plan_date"),
				"payment_plan_date": row.get("payment_plan_date"),
				"rows": []
			}
		
		child_fields = ["model", "model_name", "model_type", "model_variant", 
		               "model_color", "group_color", "option", "quantity"]
		child_row = {}
		for field in child_fields:
			child_row[field] = row.get(field)
		
		grouped_data[load_ref]["rows"].append(child_row)
	
	if not grouped_data:
		frappe.throw(_("No valid Load Reference Numbers found in the file"))
	
	unique_load_refs = list(grouped_data.keys())
	existing_load_plans = []
	new_load_refs = []
	
	for load_ref in unique_load_refs:
		if frappe.db.exists("Load Plan", load_ref):
			existing_load_plans.append(load_ref)
		else:
			new_load_refs.append(load_ref)
	
	should_create_multiple = create_multiple and len(new_load_refs) > 1
	
	created_load_plans = []
	errors = []
	skipped_load_plans = []
	
	def _create_load_plan_with_error_handling(load_ref):
		data = grouped_data[load_ref]
		try:
			load_plan = _create_single_load_plan(
				load_ref,
				data.get("dispatch_plan_date"),
				data.get("payment_plan_date"),
				data.get("rows", []),
				file_url
			)
			return {
				"name": load_plan.name,
				"load_reference_no": load_ref,
				"rows_count": len(data.get("rows", [])),
				"total_quantity": load_plan.total_quantity
			}
		except Exception as e:
			error_msg = str(e)
			errors.append({
				"load_reference_no": load_ref,
				"error": error_msg
			})
			frappe.log_error(
				message=f"Error creating Load Plan {load_ref}: {error_msg}",
				title="Load Plan Creation Error"
			)
			return None
	
	load_refs_to_process = new_load_refs if should_create_multiple else (new_load_refs[:1] if new_load_refs else [])
	
	for load_ref in load_refs_to_process:
		result = _create_load_plan_with_error_handling(load_ref)
		if result:
			created_load_plans.append(result)
	
	for load_ref in existing_load_plans:
		skipped_load_plans.append({
			"load_reference_no": load_ref,
			"reason": "Load Plan already exists"
		})
	
	return {
		"created_load_plans": created_load_plans,
		"skipped_load_plans": skipped_load_plans,
		"errors": errors,
		"total_created": len(created_load_plans),
		"total_skipped": len(skipped_load_plans),
		"total_errors": len(errors),
		"unique_load_refs": unique_load_refs,
		"multiple_created": should_create_multiple
	}

