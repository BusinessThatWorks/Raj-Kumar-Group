import frappe
from frappe.utils import flt, getdate, nowdate


def _docstatus_to_status(docstatus):
	"""Map docstatus to status string."""
	status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
	return status_map.get(docstatus, "Unknown")


def _status_to_docstatus(status):
	"""Map status string to docstatus."""
	status_map = {"Draft": 0, "Submitted": 1, "Cancelled": 2}
	return status_map.get(status)


def _build_where_clause(status=None, from_date=None, to_date=None, load_plan_reference=None):
	"""Build WHERE clause for Damage Assessment queries."""
	conditions = ["da.docstatus < 2"]
	params = {}

	if status:
		docstatus = _status_to_docstatus(status)
		if docstatus is not None:
			conditions.append("da.docstatus = %(docstatus)s")
			params["docstatus"] = docstatus

	if from_date:
		conditions.append("da.date >= %(from_date)s")
		params["from_date"] = getdate(from_date)

	if to_date:
		conditions.append("da.date <= %(to_date)s")
		params["to_date"] = getdate(to_date)

	if load_plan_reference:
		conditions.append("da.load_plan_reference_no = %(load_plan_reference)s")
		params["load_plan_reference"] = load_plan_reference

	return " AND ".join(conditions), params


@frappe.whitelist()
def get_damaged_frames_data(load_plan_reference=None, warehouse=None, status=None):
	"""Return damaged frames data with their relationships from child table."""
	conditions = ["da.docstatus < 2"]
	params = {}

	if load_plan_reference:
		conditions.append("da.load_plan_reference_no = %(load_plan_reference)s")
		params["load_plan_reference"] = load_plan_reference

	if warehouse:
		# Filter by to_warehouse or from_warehouse in child table
		conditions.append("(dai.to_warehouse = %(warehouse)s OR dai.from_warehouse = %(warehouse)s)")
		params["warehouse"] = warehouse

	if status:
		# Filter by status (OK or Not OK)
		conditions.append("dai.status = %(status)s")
		params["status"] = status

	where_clause = " AND ".join(conditions)

	# Get all frames with their relationships from child table
	frames = frappe.db.sql(
		f"""
		SELECT
			dai.serial_no,
			dai.load_dispatch,
			dai.status,
			dai.type_of_damage,
			dai.estimated_cost,
			dai.from_warehouse,
			dai.to_warehouse,
			da.load_plan_reference_no,
			da.name as assessment_name,
			da.date as assessment_date,
			da.total_estimated_cost,
			sn.warehouse as current_warehouse
		FROM `tabDamage Assessment Item` dai
		INNER JOIN `tabDamage Assessment` da ON dai.parent = da.name
		LEFT JOIN `tabSerial No` sn ON dai.serial_no = sn.name
		WHERE {where_clause}
		ORDER BY da.date DESC, dai.status DESC, dai.serial_no
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)
	
	# Calculate summary statistics
	total_frames = len(frames)
	ok_frames = len([f for f in frames if f.get("status") == "OK"])
	not_ok_frames = len([f for f in frames if f.get("status") == "Not OK"])
	total_cost = sum([flt(f.get("estimated_cost") or 0) for f in frames])

	return {
		"summary": {
			"total_frames": total_frames,
			"ok_frames": ok_frames,
			"not_ok_frames": not_ok_frames,
			"total_cost": total_cost,
		},
		"frames": frames,
	}


@frappe.whitelist()
def get_filter_options():
	"""Get filter options for Damage Assessment dashboard."""
	load_plan_references = frappe.db.sql_list(
		"""
		SELECT DISTINCT da.load_plan_reference_no
		FROM `tabDamage Assessment` da
		WHERE da.docstatus < 2 AND da.load_plan_reference_no IS NOT NULL AND da.load_plan_reference_no != ''
		ORDER BY da.load_plan_reference_no
		"""
	)

	# Get warehouses from child table (both from_warehouse and to_warehouse)
	warehouses = frappe.db.sql_list(
		"""
		SELECT DISTINCT warehouse
		FROM (
			SELECT dai.from_warehouse as warehouse
			FROM `tabDamage Assessment Item` dai
			INNER JOIN `tabDamage Assessment` da ON dai.parent = da.name
			WHERE da.docstatus < 2 AND dai.from_warehouse IS NOT NULL AND dai.from_warehouse != ''
			UNION
			SELECT dai.to_warehouse as warehouse
			FROM `tabDamage Assessment Item` dai
			INNER JOIN `tabDamage Assessment` da ON dai.parent = da.name
			WHERE da.docstatus < 2 AND dai.to_warehouse IS NOT NULL AND dai.to_warehouse != ''
		) as wh
		WHERE warehouse IS NOT NULL AND warehouse != ''
		ORDER BY warehouse
		"""
	)

	return {
		"load_plan_references": load_plan_references,
		"warehouses": warehouses
	}


@frappe.whitelist()
def get_assessment_details(name):
	"""Get detailed information about a specific Damage Assessment including child table items."""
	if not frappe.db.exists("Damage Assessment", name):
		return {"error": f"Damage Assessment {name} not found"}
	
	# Get Damage Assessment document
	assessment = frappe.get_doc("Damage Assessment", name)
	
	# Get child table items
	items = frappe.get_all(
		"Damage Assessment Item",
		filters={"parent": name},
		fields=[
			"serial_no",
			"load_dispatch",
			"type_of_damage",
			"date_of_arrival_of_frame",
			"damage_description",
			"estimated_cost",
			"item_remarks"
		],
		order_by="idx"
	)
	
	# Get items with all fields including status and warehouses
	items = frappe.get_all(
		"Damage Assessment Item",
		filters={"parent": name},
		fields=[
			"serial_no",
			"load_dispatch",
			"status",
			"type_of_damage",
			"date_of_arrival_of_frame",
			"damage_description",
			"estimated_cost",
			"from_warehouse",
			"to_warehouse",
			"item_remarks"
		],
		order_by="idx"
	)
	
	# Return extended format with all details
	return {
		"assessment": {
			"name": assessment.name,
			"date": str(assessment.date) if assessment.date else None,
			"load_plan_reference_no": assessment.load_plan_reference_no,
			"stock_entry_type": assessment.stock_entry_type,
			"status": _docstatus_to_status(assessment.docstatus),
			"total_estimated_cost": flt(assessment.total_estimated_cost) or 0,
			"frame_count": len(items),
			"ok_count": len([i for i in items if i.get("status") == "OK"]),
			"not_ok_count": len([i for i in items if i.get("status") == "Not OK"]),
			"modified": str(assessment.modified) if assessment.modified else None,
			"creation": str(assessment.creation) if assessment.creation else None,
		},
		"items": items,
	}

