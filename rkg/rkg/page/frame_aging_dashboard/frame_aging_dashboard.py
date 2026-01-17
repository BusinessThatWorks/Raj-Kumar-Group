# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate, nowdate, date_diff


def _build_where_clause(warehouse=None, item_code=None, status=None, from_date=None, to_date=None):
	"""Build WHERE clause for Frame Aging queries."""
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
	"""Return aggregated data for the Frame Aging Dashboard."""
	where_clause, params = _build_where_clause(warehouse, item_code, status, from_date, to_date)
	
	return get_frame_aging_data(where_clause, params)


def get_frame_aging_data(where_clause, params):
	"""Get Frame Aging dashboard data."""
	# Get current date for age calculation
	today = nowdate()
	
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
	
	# Add custom fields if they exist
	if frappe.db.has_column("Serial No", "color_code"):
		select_fields.append("sn.color_code")
	if frappe.db.has_column("Serial No", "custom_engine_number"):
		select_fields.append("sn.custom_engine_number")
	if frappe.db.has_column("Serial No", "custom_key_no"):
		select_fields.append("sn.custom_key_no")
	if frappe.db.has_column("Serial No", "custom_battery_no"):
		select_fields.append("sn.custom_battery_no")
	
	# Get frames with Purchase Receipt creation date
	frames = frappe.db.sql(
		f"""
		SELECT {', '.join(select_fields)},
			(SELECT DATE(MIN(pr.creation))
			 FROM `tabPurchase Receipt` pr
			 INNER JOIN `tabPurchase Receipt Item` pri ON pr.name = pri.parent
			 WHERE (pri.serial_no = sn.name OR FIND_IN_SET(sn.name, pri.serial_no) > 0) 
			   AND pr.docstatus = 1
			 LIMIT 1) as purchase_receipt_date,
			fb.name as frame_bundle_name,
			fb.battery_serial_no,
			fb.battery_type,
			fb.battery_aging_days,
			fb.battery_installed_on,
			(SELECT COUNT(*) FROM `tabFrame Bundle Discard History` WHERE parent = fb.name) as discard_count,
			(SELECT COUNT(*) FROM `tabFrame Bundle Swap History` WHERE parent = fb.name) as swap_count
		FROM `tabSerial No` sn
		LEFT JOIN `tabFrame Bundle` fb ON fb.frame_no = sn.serial_no AND fb.docstatus = 1
		WHERE {where_clause}
		ORDER BY sn.creation DESC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	total_frames = len(frames)
	
	# Calculate age for each frame and categorize
	age_ranges = {
		"0-30 days": 0,
		"30-60 days": 0,
		"60-90 days": 0,
		"90-180 days": 0,
		"180+ days": 0,
	}
	
	# Age category counts
	age_category_counts = {
		"new": 0,       # 0-30 days (Green)
		"recent": 0,    # 30-60 days (Light Green)
		"moderate": 0,  # 60-90 days (Yellow)
		"old": 0,       # 90-180 days (Orange)
		"very_old": 0,  # 180+ days (Red)
	}
	
	# Count by status
	status_counts = {}
	
	# Count by warehouse
	warehouse_counts = {}
	
	# Count by item_code
	item_counts = {}

	frame_cards = []
	for frame in frames:
		# Get Purchase Receipt creation date (start date)
		purchase_receipt_date = frame.get("purchase_receipt_date")
		
		# Calculate frame age: Today - Purchase Receipt creation date
		if purchase_receipt_date:
			pr_date = getdate(purchase_receipt_date)
			age_days = date_diff(today, pr_date)
			# Format purchase date
			if isinstance(purchase_receipt_date, str):
				purchase_date = purchase_receipt_date.split(' ')[0] if ' ' in purchase_receipt_date else purchase_receipt_date
			else:
				purchase_date = str(purchase_receipt_date).split(' ')[0]
		else:
			# If no Purchase Receipt, use creation date as fallback
			creation_date = getdate(frame.creation)
			age_days = date_diff(today, creation_date)
			purchase_date = None
		
		# Categorize by age
		if age_days <= 30:
			age_ranges["0-30 days"] += 1
			age_category = "0-30 days"
			age_category_counts["new"] += 1
			risk_level = "new"
		elif age_days <= 60:
			age_ranges["30-60 days"] += 1
			age_category = "30-60 days"
			age_category_counts["recent"] += 1
			risk_level = "recent"
		elif age_days <= 90:
			age_ranges["60-90 days"] += 1
			age_category = "60-90 days"
			age_category_counts["moderate"] += 1
			risk_level = "moderate"
		elif age_days <= 180:
			age_ranges["90-180 days"] += 1
			age_category = "90-180 days"
			age_category_counts["old"] += 1
			risk_level = "old"
		else:
			age_ranges["180+ days"] += 1
			age_category = "180+ days"
			age_category_counts["very_old"] += 1
			risk_level = "very_old"
		
		# Count by status
		status = frame.get("status") or "Unknown"
		status_counts[status] = status_counts.get(status, 0) + 1
		
		# Count by warehouse
		warehouse = frame.get("warehouse") or "Unknown"
		warehouse_counts[warehouse] = warehouse_counts.get(warehouse, 0) + 1
		
		# Count by item_code
		item_code = frame.get("item_code") or "Unknown"
		item_counts[item_code] = item_counts.get(item_code, 0) + 1
		
		# Get battery information
		battery_serial_no = frame.get("battery_serial_no")
		battery_type = frame.get("battery_type")
		battery_aging_days = frame.get("battery_aging_days")
		battery_installed_on = frame.get("battery_installed_on")
		is_discarded = (frame.get("discard_count") or 0) > 0
		swap_count = frame.get("swap_count") or 0
		
		# Get battery serial number from Battery Information if available
		battery_serial_no_display = None
		if battery_serial_no:
			battery_info = frappe.db.get_value("Battery Information", battery_serial_no, "battery_serial_no", as_dict=False)
			if battery_info:
				battery_serial_no_display = battery_info
		
		frame_cards.append({
			"name": frame.name,
			"frame_no": frame.serial_no or frame.name,
			"item_code": frame.item_code or "-",
			"item_name": frame.item_name or "-",
			"warehouse": frame.warehouse or "-",
			"status": frame.status or "Unknown",
			"purchase_date": purchase_date,
			"age_days": age_days,
			"age_category": age_category,
			"risk_level": risk_level,
			"creation": str(frame.creation) if frame.creation else None,
			"modified": str(frame.modified) if frame.modified else None,
			"color_code": frame.get("color_code") or "-",
			"custom_engine_number": frame.get("custom_engine_number") or "-",
			"custom_key_no": frame.get("custom_key_no") or "-",
			"custom_battery_no": frame.get("custom_battery_no") or "-",
			"frame_bundle_name": frame.get("frame_bundle_name"),
			"battery_serial_no": battery_serial_no_display or battery_serial_no,
			"battery_type": battery_type,
			"battery_aging_days": battery_aging_days,
			"battery_installed_on": str(battery_installed_on) if battery_installed_on else None,
			"is_discarded": 1 if is_discarded else 0,
			"swap_count": swap_count,
			"has_battery": 1 if battery_serial_no else 0,
			"today_date": str(today),  # Include today's date for display
		})

	# Age distribution chart
	age_chart = {
		"labels": list(age_ranges.keys()),
		"values": list(age_ranges.values()),
	}

	# Status distribution chart
	status_chart_rows = sorted(status_counts.items(), key=lambda x: x[1], reverse=True)[:10]
	status_chart = {
		"labels": [row[0] for row in status_chart_rows],
		"values": [row[1] for row in status_chart_rows],
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

	# Frames by age range (for line chart)
	age_range_chart = {
		"labels": list(age_ranges.keys()),
		"values": list(age_ranges.values()),
	}

	return {
		"doctype": "Serial No",
		"summary": {
			"total_frames": total_frames,
			"age_ranges": age_ranges,
			"age_category_counts": age_category_counts,
			"status_counts": status_counts,
			"warehouse_counts": warehouse_counts,
			"item_counts": item_counts,
			"today_date": str(today),  # Include today's date
		},
		"age_chart": age_chart,
		"status_chart": status_chart,
		"warehouse_chart": warehouse_chart,
		"item_chart": item_chart,
		"age_range_chart": age_range_chart,
		"frames": frame_cards,
	}


@frappe.whitelist()
def get_filter_options():
	"""Get filter options for Frame Aging dashboard."""
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
def get_frame_aging_details(name):
	"""Get detailed information about a specific Frame with aging information."""
	if not frappe.db.exists("Serial No", name):
		return {"error": f"Frame No {name} not found"}
	
	# Get Serial No document (Frame No is stored in Serial No doctype)
	frame_no = frappe.get_doc("Serial No", name)
	frame_no_value = frame_no.serial_no or frame_no.name
	today = nowdate()
	
	# Get Frame Bundle information
	frame_bundle = frappe.db.get_value(
		"Frame Bundle",
		{"frame_no": frame_no_value, "docstatus": 1},
		["name", "battery_serial_no", "battery_type", "battery_aging_days", "battery_installed_on"],
		as_dict=True
	)
	
	# Get Purchase Receipt creation date (start date)
	purchase_receipt_date = frappe.db.sql(
		"""
		SELECT DATE(MIN(pr.creation))
		FROM `tabPurchase Receipt` pr
		INNER JOIN `tabPurchase Receipt Item` pri ON pr.name = pri.parent
		WHERE (pri.serial_no = %s OR FIND_IN_SET(%s, pri.serial_no) > 0)
		  AND pr.docstatus = 1
		LIMIT 1
		""",
		(name, name),
		as_list=True,
	)
	
	# Calculate frame age
	if purchase_receipt_date and purchase_receipt_date[0] and purchase_receipt_date[0][0]:
		pr_date = getdate(purchase_receipt_date[0][0])
		age_days = date_diff(today, pr_date)
		if isinstance(purchase_receipt_date[0][0], str):
			purchase_date = purchase_receipt_date[0][0].split(' ')[0] if ' ' in purchase_receipt_date[0][0] else purchase_receipt_date[0][0]
		else:
			purchase_date = str(purchase_receipt_date[0][0]).split(' ')[0]
	else:
		# Fallback to creation date
		creation_date = getdate(frame_no.creation)
		age_days = date_diff(today, creation_date)
		purchase_date = None
	
	# Categorize age
	if age_days <= 30:
		age_category = "0-30 days"
		risk_level = "new"
	elif age_days <= 60:
		age_category = "30-60 days"
		risk_level = "recent"
	elif age_days <= 90:
		age_category = "60-90 days"
		risk_level = "moderate"
	elif age_days <= 180:
		age_category = "90-180 days"
		risk_level = "old"
	else:
		age_category = "180+ days"
		risk_level = "very_old"
	
	# Get all fields
	result = {
		"name": frame_no.name,
		"frame_no": frame_no_value,
		"item_code": frame_no.item_code,
		"item_name": frame_no.item_name,
		"warehouse": frame_no.warehouse,
		"status": frame_no.status,
		"purchase_date": purchase_date,
		"age_days": age_days,
		"age_category": age_category,
		"risk_level": risk_level,
		"start_date": purchase_date,  # Purchase Receipt creation date
		"end_date": str(today),  # Today's date
		"creation": str(frame_no.creation) if frame_no.creation else None,
		"modified": str(frame_no.modified) if frame_no.modified else None,
	}
	
	# Add Frame Bundle and Battery information
	if frame_bundle:
		result["frame_bundle_name"] = frame_bundle.name
		result["battery_serial_no"] = frame_bundle.battery_serial_no
		result["battery_type"] = frame_bundle.battery_type
		result["battery_aging_days"] = frame_bundle.battery_aging_days
		result["battery_installed_on"] = str(frame_bundle.battery_installed_on) if frame_bundle.battery_installed_on else None
		result["has_battery"] = 1 if frame_bundle.battery_serial_no else 0
		
		# Get battery serial number display value
		if frame_bundle.battery_serial_no:
			battery_info = frappe.db.get_value("Battery Information", frame_bundle.battery_serial_no, "battery_serial_no", as_dict=False)
			if battery_info:
				result["battery_serial_no_display"] = battery_info
		
		# Check if battery is discarded
		discard_count = frappe.db.count("Frame Bundle Discard History", {
			"parent": frame_bundle.name
		}) or 0
		result["is_discarded"] = discard_count > 0
		
		# Get swap history
		swap_history = frappe.get_all(
			"Frame Bundle Swap History",
			filters={"parent": frame_bundle.name},
			fields=["swap_date", "swapped_with_frame", "swapped_by", "old_battery_serial_no", "new_battery_serial_no"],
			order_by="swap_date desc"
		)
		result["swap_history"] = swap_history
		result["swap_count"] = len(swap_history)
	else:
		result["frame_bundle_name"] = None
		result["battery_serial_no"] = None
		result["battery_type"] = None
		result["battery_aging_days"] = None
		result["battery_installed_on"] = None
		result["has_battery"] = 0
		result["is_discarded"] = False
		result["swap_history"] = []
		result["swap_count"] = 0
	
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

