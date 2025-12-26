import frappe
from frappe.utils import flt, getdate, nowdate


def _build_where_clause(warehouse=None, item_code=None, status=None, from_date=None, to_date=None):
	"""Build WHERE clause for Frame No queries."""
	conditions = ["sn.docstatus < 2"]
	params = {}

	if warehouse:
		conditions.append("sn.warehouse = %(warehouse)s")
		params["warehouse"] = warehouse

	if item_code:
		conditions.append("sn.item_code = %(item_code)s")
		params["item_code"] = item_code

	if status:
		conditions.append("sn.status = %(status)s")
		params["status"] = status

	if from_date:
		conditions.append("DATE(sn.creation) >= %(from_date)s")
		params["from_date"] = getdate(from_date)

	if to_date:
		conditions.append("DATE(sn.creation) <= %(to_date)s")
		params["to_date"] = getdate(to_date)

	return " AND ".join(conditions), params


@frappe.whitelist()
def get_dashboard_data(warehouse=None, item_code=None, status=None, from_date=None, to_date=None):
	"""Return aggregated data for the Frame No Visual Dashboard."""
	where_clause, params = _build_where_clause(warehouse, item_code, status, from_date, to_date)
	
	return get_frame_no_data(where_clause, params)


def get_frame_no_data(where_clause, params):
	"""Get Frame No dashboard data."""
	# Build SELECT fields dynamically based on what columns exist
	select_fields = [
		"sn.name",
		"sn.serial_no",
		"sn.item_code",
		"sn.item_name",
		"sn.warehouse",
		"sn.status",
		"sn.creation",
		"sn.modified",
	]
	
	# Add date fields if they exist
	if frappe.db.has_column("Serial No", "purchase_date"):
		select_fields.append("sn.purchase_date")
	if frappe.db.has_column("Serial No", "delivery_date"):
		select_fields.append("sn.delivery_date")
	
	# Add custom fields if they exist
	if frappe.db.has_column("Serial No", "color_code"):
		select_fields.append("sn.color_code")
	if frappe.db.has_column("Serial No", "custom_engine_number"):
		select_fields.append("sn.custom_engine_number")
	if frappe.db.has_column("Serial No", "custom_key_no"):
		select_fields.append("sn.custom_key_no")
	if frappe.db.has_column("Serial No", "custom_battery_no"):
		select_fields.append("sn.custom_battery_no")
	
	frames = frappe.db.sql(
		f"""
		SELECT {', '.join(select_fields)}
		FROM `tabSerial No` sn
		WHERE {where_clause}
		ORDER BY sn.creation DESC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	total_frames = len(frames)
	
	# Count by status
	status_counts = {}
	for frame in frames:
		status = frame.get("status") or "Unknown"
		status_counts[status] = status_counts.get(status, 0) + 1

	# Count by warehouse
	warehouse_counts = {}
	for frame in frames:
		warehouse = frame.get("warehouse") or "Unknown"
		warehouse_counts[warehouse] = warehouse_counts.get(warehouse, 0) + 1

	# Count by item_code
	item_counts = {}
	for frame in frames:
		item_code = frame.get("item_code") or "Unknown"
		item_counts[item_code] = item_counts.get(item_code, 0) + 1

	# Status distribution chart
	status_rows = frappe.db.sql(
		f"""
		SELECT sn.status, COUNT(*) as count
		FROM `tabSerial No` sn
		WHERE {where_clause}
		GROUP BY sn.status
		ORDER BY count DESC
		""",
		params,
		as_dict=True,
	)

	status_chart = {
		"labels": [row.status or "Unknown" for row in status_rows],
		"values": [row.count for row in status_rows],
	}

	# Warehouse distribution chart
	warehouse_rows = frappe.db.sql(
		f"""
		SELECT sn.warehouse, COUNT(*) as count
		FROM `tabSerial No` sn
		WHERE {where_clause} AND sn.warehouse IS NOT NULL
		GROUP BY sn.warehouse
		ORDER BY count DESC
		LIMIT 10
		""",
		params,
		as_dict=True,
	)

	warehouse_chart = {
		"labels": [row.warehouse or "Unknown" for row in warehouse_rows],
		"values": [row.count for row in warehouse_rows],
	}

	# Item distribution chart
	item_rows = frappe.db.sql(
		f"""
		SELECT sn.item_code, COUNT(*) as count
		FROM `tabSerial No` sn
		WHERE {where_clause} AND sn.item_code IS NOT NULL
		GROUP BY sn.item_code
		ORDER BY count DESC
		LIMIT 10
		""",
		params,
		as_dict=True,
	)

	item_chart = {
		"labels": [row.item_code or "Unknown" for row in item_rows],
		"values": [row.count for row in item_rows],
	}

	# Frames by date (creation)
	date_rows = frappe.db.sql(
		f"""
		SELECT 
			DATE(sn.creation) as date,
			COUNT(*) as count
		FROM `tabSerial No` sn
		WHERE {where_clause} AND sn.creation IS NOT NULL
		GROUP BY DATE(sn.creation)
		ORDER BY DATE(sn.creation)
		""",
		params,
		as_dict=True,
	)

	date_chart = {
		"labels": [str(r.date) for r in date_rows],
		"values": [r.count for r in date_rows],
	}

	# Prepare frame cards
	frame_cards = []
	for frame in frames[:500]:  # Limit to 500 for performance
		frame_cards.append({
			"name": frame.name,
			"frame_no": frame.serial_no or frame.name,
			"item_code": frame.item_code or "-",
			"item_name": frame.item_name or "-",
			"warehouse": frame.warehouse or "-",
			"status": frame.status or "Unknown",
			"purchase_date": str(frame.get("purchase_date")) if frame.get("purchase_date") else None,
			"delivery_date": str(frame.get("delivery_date")) if frame.get("delivery_date") else None,
			"creation": str(frame.creation) if frame.creation else None,
			"color_code": frame.get("color_code") or "-",
			"custom_engine_number": frame.get("custom_engine_number") or "-",
			"custom_key_no": frame.get("custom_key_no") or "-",
			"custom_battery_no": frame.get("custom_battery_no") or "-",
		})

	return {
		"doctype": "Serial No",
		"summary": {
			"total_frames": total_frames,
			"status_counts": status_counts,
			"warehouse_counts": warehouse_counts,
			"item_counts": item_counts,
		},
		"status_chart": status_chart,
		"warehouse_chart": warehouse_chart,
		"item_chart": item_chart,
		"date_chart": date_chart,
		"frames": frame_cards,
	}


@frappe.whitelist()
def get_filter_options():
	"""Get filter options for Frame No dashboard."""
	# Get distinct warehouses
	warehouses = frappe.db.sql_list(
		"""
		SELECT DISTINCT warehouse
		FROM `tabSerial No`
		WHERE docstatus < 2 AND warehouse IS NOT NULL AND warehouse != ''
		ORDER BY warehouse
		"""
	)

	# Get distinct item codes
	item_codes = frappe.db.sql_list(
		"""
		SELECT DISTINCT item_code
		FROM `tabSerial No`
		WHERE docstatus < 2 AND item_code IS NOT NULL AND item_code != ''
		ORDER BY item_code
		"""
	)

	# Get distinct statuses
	statuses = frappe.db.sql_list(
		"""
		SELECT DISTINCT status
		FROM `tabSerial No`
		WHERE docstatus < 2 AND status IS NOT NULL AND status != ''
		ORDER BY status
		"""
	)

	return {
		"warehouses": warehouses,
		"item_codes": item_codes,
		"statuses": statuses
	}


@frappe.whitelist()
def get_frame_no_details(name):
	"""Get detailed information about a specific Frame No."""
	if not frappe.db.exists("Serial No", name):
		return {"error": f"Frame No {name} not found"}
	
	# Get Serial No document (Frame No is stored in Serial No doctype)
	frame_no = frappe.get_doc("Serial No", name)
	
	# Get all fields
	result = {
		"name": frame_no.name,
		"frame_no": frame_no.serial_no or frame_no.name,
		"item_code": frame_no.item_code,
		"item_name": frame_no.item_name,
		"warehouse": frame_no.warehouse,
		"status": frame_no.status,
		"creation": str(frame_no.creation) if frame_no.creation else None,
		"modified": str(frame_no.modified) if frame_no.modified else None,
	}
	
	# Add date fields if they exist
	if frappe.db.has_column("Serial No", "purchase_date"):
		result["purchase_date"] = str(frame_no.purchase_date) if getattr(frame_no, "purchase_date", None) else None
	if frappe.db.has_column("Serial No", "delivery_date"):
		result["delivery_date"] = str(frame_no.delivery_date) if getattr(frame_no, "delivery_date", None) else None
	
	# Add custom fields if they exist
	if frappe.db.has_column("Serial No", "color_code"):
		result["color_code"] = getattr(frame_no, "color_code", None) or "-"
	if frappe.db.has_column("Serial No", "custom_engine_number"):
		result["custom_engine_number"] = getattr(frame_no, "custom_engine_number", None) or "-"
	if frappe.db.has_column("Serial No", "custom_key_no"):
		result["custom_key_no"] = getattr(frame_no, "custom_key_no", None) or "-"
	if frappe.db.has_column("Serial No", "custom_battery_no"):
		result["custom_battery_no"] = getattr(frame_no, "custom_battery_no", None) or "-"
	
	return {"frame_no": result}

