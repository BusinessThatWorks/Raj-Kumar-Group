import frappe
from frappe import _
from frappe.model.document import Document


class LoadPlanUpload(Document):
	def validate(self):
		"""Validate the document before save."""
		# Check if file is attached
		if not self.excel_file:
			frappe.throw(_("Please attach an Excel file before submitting"))
		
		# Clear child table when new file is attached
		if self.has_value_changed("excel_file"):
			self.upload_items = []
			self.total_load_plans_created = 0
	
	def on_submit(self):
		"""Process the file and create Load Plans on submit."""
		if not self.excel_file:
			frappe.throw(_("No file attached"))
		
		# Reprocess the file to get latest data (file may have changed)
		# This ensures we have fresh data even if file was updated
		check_result = check_multiple_load_reference_numbers(self.excel_file)
		
		# Check if load reference numbers found
		if check_result.get("count") == 0:
			frappe.throw(_("No Load Reference Numbers found in the file. Please check the file format."))
		
		# Determine if we should create multiple Load Plans
		create_multiple = check_result.get("has_multiple", False)
		
		# Import the create function from load_plan (use EXACT same function)
		from rkg.rkg.doctype.load_plan.load_plan import create_load_plans_from_file, process_tabular_file, _create_single_load_plan
		
		# Create Load Plans (skip existing ones) - use same logic as Load Plan but skip existing
		try:
			result = create_load_plans_from_file_skip_existing(
				file_url=self.excel_file,
				create_multiple=create_multiple
			)
			
			# Prepare child table data first
			child_table_data = []
			
			# Add rows for created Load Plans
			for lp in result.get("created_load_plans", []):
				child_table_data.append({
					"load_reference_no": lp.get("load_reference_no", ""),
					"status": "Created",
					"rows_count": lp.get("rows_count", 0),
					"total_quantity": lp.get("total_quantity", 0),
					"error_message": ""
				})
			
			# Add rows for skipped Load Plans
			for skipped in result.get("skipped_load_plans", []):
				child_table_data.append({
					"load_reference_no": skipped.get("load_reference_no", ""),
					"status": "Skipped",
					"rows_count": 0,
					"total_quantity": 0,
					"error_message": skipped.get("reason", "Load Plan already exists")
				})
			
			# Add rows for errors
			for err in result.get("errors", []):
				child_table_data.append({
					"load_reference_no": err.get("load_reference_no", ""),
					"status": "Error",
					"rows_count": 0,
					"total_quantity": 0,
					"error_message": err.get("error", "")
				})
			
			# Update child table and total count together
			# CRITICAL: This happens in on_submit - Load Plans are already created above
			try:
				# Update total count
				frappe.db.set_value("Load Plan Upload", self.name, "total_load_plans_created", result.get("total_created", 0), update_modified=False)
				
				# Update child table using a helper method
				# This populates the child table with results (Created, Skipped, Error)
				if child_table_data:
					_update_upload_items_child_table(self.name, child_table_data)
				
				# Commit all changes together - ensures child table is saved before method returns
				frappe.db.commit()
				
			except Exception as table_err:
				# Error with child table - log but don't fail the whole process
				frappe.log_error(
					message=f"Error populating child table: {str(table_err)}",
					title="Load Plan Upload Child Table Error"
				)
				frappe.db.commit()
			
			# Don't show msgprint here - let the client-side handle messaging after reload
			# This prevents messages from appearing before the form reloads
			# The client will show appropriate messages after reload is complete
				
		except Exception as e:
			# Add error to child table if possible
			try:
				frappe.db.commit()  # Commit any pending changes first
				error_data = [{
					"load_reference_no": "",
					"status": "Error",
					"rows_count": 0,
					"total_quantity": 0,
					"error_message": _("Error: {0}").format(str(e))
				}]
				_update_upload_items_child_table(self.name, error_data)
			except Exception as inner_e:
				# If child table update fails, just log it
				frappe.log_error(
					message=f"Error updating child table: {str(inner_e)}",
					title="Load Plan Upload Child Table Error"
				)
				frappe.db.commit()
			frappe.log_error(
				message=f"Error creating Load Plans: {str(e)}",
				title="Load Plan Upload Error"
			)
			frappe.throw(_("Error processing file: {0}").format(str(e)))


def _update_upload_items_child_table(parent_name, child_table_data):
	"""
	Helper function to update child table after document submission.
	Uses direct SQL insert to ensure immediate visibility without refresh.
	"""
	try:
		# Delete existing child table rows
		frappe.db.sql("""
			DELETE FROM `tabLoad Plan Upload Item`
			WHERE parent = %s
		""", (parent_name,))
		
		# Insert new rows directly
		for idx, row_data in enumerate(child_table_data, start=1):
			frappe.db.sql("""
				INSERT INTO `tabLoad Plan Upload Item`
				(name, creation, modified, modified_by, owner, docstatus, parent, parentfield, parenttype, idx,
				 load_reference_no, status, rows_count, total_quantity, error_message)
				VALUES
				(%s, NOW(), NOW(), %s, %s, 0, %s, 'upload_items', 'Load Plan Upload', %s,
				 %s, %s, %s, %s, %s)
			""", (
				frappe.generate_hash(length=10),
				frappe.session.user,
				frappe.session.user,
				parent_name,
				idx,
				row_data.get("load_reference_no", ""),
				row_data.get("status", ""),
				row_data.get("rows_count", 0),
				row_data.get("total_quantity", 0),
				row_data.get("error_message", "")
			))
		frappe.db.commit()
	except Exception as sql_err:
		frappe.log_error(
			message=f"Error inserting child table rows via SQL: {str(sql_err)}",
			title="Load Plan Upload Child Table SQL Error"
		)
		raise


@frappe.whitelist()
def check_multiple_load_reference_numbers(file_url):
	"""
	Read the Excel file and check if multiple load reference numbers exist.
	ONLY reads the file - does NOT create any Load Plans.
	Uses the EXACT same logic as Load Plan's create_load_plans_from_file.
	
	Args:
		file_url: URL of the attached file
		
	Returns:
		dict with unique_load_refs list, count, load_ref_details (with row counts), and message
	"""
	if not file_url:
		frappe.throw(_("No file provided"))
	
	# Import the process_tabular_file function from load_plan (same as Load Plan uses)
	from rkg.rkg.doctype.load_plan.load_plan import process_tabular_file
	
	# Process the file to get all rows (same as Load Plan does)
	all_rows = process_tabular_file(file_url)
	
	if not all_rows:
		frappe.throw(_("No data found in the file"))
	
	# Group rows by load_reference_no (EXACT same logic as Load Plan)
	grouped_data = {}
	for idx, row in enumerate(all_rows):
		load_ref = row.get("load_reference_no")
		if not load_ref:
			# Skip rows without load_reference_no
			continue
		
		load_ref = str(load_ref).strip()
		if load_ref not in grouped_data:
			grouped_data[load_ref] = {
				"load_reference_no": load_ref,
				"dispatch_plan_date": row.get("dispatch_plan_date"),
				"payment_plan_date": row.get("payment_plan_date"),
				"rows": []
			}
		
		# Count rows per load reference
		grouped_data[load_ref]["rows"].append(row)
	
	if not grouped_data:
		frappe.throw(_("No valid Load Reference Numbers found in the file"))
	
	# Get unique load reference numbers (same as Load Plan)
	unique_load_refs = list(grouped_data.keys())
	unique_load_refs_list = sorted(unique_load_refs)
	count = len(unique_load_refs_list)
	
	# Build detailed info for each load reference (row count, etc.)
	load_ref_details = []
	for load_ref in unique_load_refs_list:
		data = grouped_data[load_ref]
		row_count = len(data.get("rows", []))
		# Calculate total quantity from rows
		total_qty = sum(int(row.get("quantity", 0) or 0) for row in data.get("rows", []))
		
		load_ref_details.append({
			"load_reference_no": load_ref,
			"rows_count": row_count,
			"total_quantity": total_qty,
			"dispatch_plan_date": data.get("dispatch_plan_date"),
			"payment_plan_date": data.get("payment_plan_date")
		})
	
	# Build message
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
		"load_ref_details": load_ref_details  # New: detailed info per load ref
	}


@frappe.whitelist()
def create_load_plans_from_file_skip_existing(file_url, create_multiple=True):
	"""
	Process file and create Load Plan documents, but skip Load Plans that already exist.
	Uses EXACT same logic as Load Plan's create_load_plans_from_file, but skips existing ones.
	
	Args:
		file_url: URL of the attached file
		create_multiple: If True, create separate Load Plans for each load_reference_no
		
	Returns:
		dict with created_load_plans list, skipped_load_plans list, and summary
	"""
	if not file_url:
		frappe.throw(_("No file provided"))
	
	# Import functions from load_plan (use EXACT same functions)
	from rkg.rkg.doctype.load_plan.load_plan import process_tabular_file, _create_single_load_plan
	
	# Process the file to get all rows (EXACT same as Load Plan)
	all_rows = process_tabular_file(file_url)
	
	if not all_rows:
		frappe.throw(_("No data found in the file"))
	
	# Group rows by load_reference_no (EXACT same logic as Load Plan)
	grouped_data = {}
	for idx, row in enumerate(all_rows):
		load_ref = row.get("load_reference_no")
		if not load_ref:
			# Skip rows without load_reference_no
			continue
		
		load_ref = str(load_ref).strip()
		if load_ref not in grouped_data:
			grouped_data[load_ref] = {
				"load_reference_no": load_ref,
				"dispatch_plan_date": row.get("dispatch_plan_date"),
				"payment_plan_date": row.get("payment_plan_date"),
				"rows": []
			}
		
		# Add child table row (exclude parent fields) - EXACT same as Load Plan
		child_fields = ["model", "model_name", "model_type", "model_variant", 
		               "model_color", "group_color", "option", "quantity"]
		child_row = {}
		for field in child_fields:
			# Always include field - use value from row if exists, otherwise None
			child_row[field] = row.get(field)
		
		# ALWAYS append child_row for every row with load_reference_no
		grouped_data[load_ref]["rows"].append(child_row)
	
	if not grouped_data:
		frappe.throw(_("No valid Load Reference Numbers found in the file"))
	
	# Check which Load Plans already exist (NEW: skip existing)
	unique_load_refs = list(grouped_data.keys())
	existing_load_plans = []
	new_load_refs = []
	
	for load_ref in unique_load_refs:
		if frappe.db.exists("Load Plan", load_ref):
			existing_load_plans.append(load_ref)
		else:
			new_load_refs.append(load_ref)
	
	# Determine if we should create multiple Load Plans (same logic as Load Plan)
	should_create_multiple = create_multiple and len(new_load_refs) > 1
	
	created_load_plans = []
	errors = []
	skipped_load_plans = []
	
	if should_create_multiple:
		# Create multiple Load Plans (only for new load_reference_no that don't exist)
		for load_ref in new_load_refs:
			data = grouped_data[load_ref]
			try:
				load_plan = _create_single_load_plan(
					load_ref,
					data.get("dispatch_plan_date"),
					data.get("payment_plan_date"),
					data.get("rows", []),
					file_url
				)
				created_load_plans.append({
					"name": load_plan.name,
					"load_reference_no": load_ref,
					"rows_count": len(data.get("rows", [])),
					"total_quantity": load_plan.total_quantity
				})
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
		
		# Add skipped Load Plans to the list
		for load_ref in existing_load_plans:
			skipped_load_plans.append({
				"load_reference_no": load_ref,
				"reason": "Load Plan already exists"
			})
	else:
		# Create single Load Plan (only if it doesn't exist)
		if new_load_refs:
			first_load_ref = new_load_refs[0]
			data = grouped_data[first_load_ref]
			try:
				load_plan = _create_single_load_plan(
					first_load_ref,
					data.get("dispatch_plan_date"),
					data.get("payment_plan_date"),
					data.get("rows", []),
					file_url
				)
				created_load_plans.append({
					"name": load_plan.name,
					"load_reference_no": first_load_ref,
					"rows_count": len(data.get("rows", [])),
					"total_quantity": load_plan.total_quantity
				})
			except Exception as e:
				error_msg = str(e)
				errors.append({
					"load_reference_no": first_load_ref,
					"error": error_msg
				})
				frappe.log_error(
					message=f"Error creating Load Plan {first_load_ref}: {error_msg}",
					title="Load Plan Creation Error"
				)
		
		# Add skipped Load Plans to the list
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

