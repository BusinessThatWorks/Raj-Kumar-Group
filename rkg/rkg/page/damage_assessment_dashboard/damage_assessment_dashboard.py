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
def get_damaged_frames_data(load_plan_reference=None, warehouse=None):
	"""Return damaged frames data with their relationships."""
	conditions = ["da.docstatus < 2"]
	params = {}

	if load_plan_reference:
		conditions.append("da.load_plan_reference_no = %(load_plan_reference)s")
		params["load_plan_reference"] = load_plan_reference

	if warehouse:
		# Filter by to_warehouse (current location after transfer)
		conditions.append("da.to_warehouse = %(warehouse)s")
		params["warehouse"] = warehouse

	where_clause = " AND ".join(conditions)

	# Get all damaged frames with their relationships
	frames = frappe.db.sql(
		f"""
		SELECT
			dai.serial_no,
			dai.type_of_damage,
			dai.estimated_cost,
			da.load_plan_reference_no,
			da.from_warehouse,
			da.to_warehouse,
			da.date as assessment_date
		FROM `tabDamage Assessment Item` dai
		INNER JOIN `tabDamage Assessment` da ON dai.parent = da.name
		LEFT JOIN `tabSerial No` sn ON dai.serial_no = sn.name
		WHERE {where_clause}
		ORDER BY da.date DESC, dai.serial_no
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)
	
	# Process frames: Current warehouse is the to_warehouse (where it was transferred to)
	for frame in frames:
		frame["current_warehouse"] = frame.get("to_warehouse") or ""

	total_frames = len(frames)

	return {
		"summary": {
			"total_frames": total_frames,
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

	warehouses = frappe.db.sql_list(
		"""
		SELECT DISTINCT sn.warehouse
		FROM `tabDamage Assessment Item` dai
		INNER JOIN `tabDamage Assessment` da ON dai.parent = da.name
		LEFT JOIN `tabSerial No` sn ON dai.serial_no = sn.name
		WHERE da.docstatus < 2 AND sn.warehouse IS NOT NULL AND sn.warehouse != ''
		ORDER BY sn.warehouse
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
	
	# Return extended format with all details
	return {
		"assessment": {
			"name": assessment.name,
			"date": str(assessment.date) if assessment.date else None,
			"load_plan_reference_no": assessment.load_plan_reference_no,
			"from_warehouse": assessment.from_warehouse,
			"to_warehouse": assessment.to_warehouse,
			"status": _docstatus_to_status(assessment.docstatus),
			"total_estimated_cost": flt(assessment.total_estimated_cost) or 0,
			"frame_count": len(items),
			"stock_entry": assessment.stock_entry,
			"modified": str(assessment.modified) if assessment.modified else None,
			"creation": str(assessment.creation) if assessment.creation else None,
		},
		"items": items,
	}

