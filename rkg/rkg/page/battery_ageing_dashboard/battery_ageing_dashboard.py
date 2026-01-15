# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate, nowdate, date_diff


def _build_where_clause(brand=None, battery_type=None, from_date=None, to_date=None):
	"""Build WHERE clause for Battery Ageing queries."""
	conditions = ["bd.status = 'Active'"]  # Only show batteries that are active
	params = {}

	if brand:
		conditions.append("bd.battery_brand = %(brand)s")
		params["brand"] = brand

	if battery_type:
		conditions.append("bd.battery_type = %(battery_type)s")
		params["battery_type"] = battery_type

	if from_date:
		# Filter by charging_date if available, otherwise use creation date
		conditions.append("(DATE(bd.charging_date) >= %(from_date)s OR (bd.charging_date IS NULL AND DATE(bd.creation) >= %(from_date)s))")
		params["from_date"] = getdate(from_date)

	if to_date:
		# Filter by charging_date if available, otherwise use creation date
		conditions.append("(DATE(bd.charging_date) <= %(to_date)s OR (bd.charging_date IS NULL AND DATE(bd.creation) <= %(to_date)s))")
		params["to_date"] = getdate(to_date)

	return " AND ".join(conditions), params


@frappe.whitelist()
def get_dashboard_data(brand=None, battery_type=None, from_date=None, to_date=None):
	"""Return aggregated data for the Battery Ageing Dashboard."""
	where_clause, params = _build_where_clause(brand, battery_type, from_date, to_date)
	
	return get_battery_ageing_data(where_clause, params)


def get_battery_ageing_data(where_clause, params):
	"""Get Battery Ageing dashboard data with Frame Bundle information."""
	# Get current date for age calculation
	today = nowdate()
	
	# Build SELECT fields from Battery Information with Frame Bundle join
	select_fields = [
		"bd.name",
		"bd.battery_serial_no",
		"bd.battery_brand",
		"bd.battery_type",
		"bd.charging_date",
		"bd.status",
		"bd.creation",
		"bd.modified",
		"fb.name as frame_bundle_name",
		"fb.frame_no",
		"fb.battery_aging_days",
		"fb.battery_installed_on",
		"fb.warehouse",
		"(SELECT COUNT(*) FROM `tabFrame Bundle Discard History` WHERE parent = fb.name) as discard_count",
	]
	
	batteries = frappe.db.sql(
		f"""
		SELECT {', '.join(select_fields)}
		FROM `tabBattery Information` bd
		LEFT JOIN `tabFrame Bundle` fb ON fb.battery_serial_no = bd.name AND fb.docstatus = 1
		WHERE {where_clause}
		ORDER BY bd.charging_date DESC, bd.creation DESC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	total_batteries = len(batteries)
	
	# Calculate age for each battery and categorize
	age_ranges = {
		"0-60 days": 0,
		"60-90 days": 0,
		"90-120 days": 0,
		"120+ days": 0,
	}
	
	# Expiry Risk Categories
	expiry_risk_counts = {
		"safe": 0,      # 0-60 days (Green)
		"warning": 0,   # 60-90 days (Orange)
		"critical": 0,  # 90-120 days (Red)
		"very_critical": 0,  # 120+ days (Dark Red)
	}
	
	# 60-day count (batteries that are around 60 days old)
	batteries_60_days = 0
	
	brand_counts = {}
	battery_type_counts = {}
	
	battery_cards = []
	for battery in batteries:
		# Calculate age - prefer battery_aging_days from Frame Bundle (most accurate)
		# If not installed on a frame, use charging_date from Battery Information
		if battery.get("battery_aging_days") is not None:
			# Battery is installed on a frame - use Frame Bundle aging days
			age_days = battery.battery_aging_days
			charging_date = battery.get("battery_installed_on")
		elif battery.get("charging_date"):
			# Battery not on frame - use charging_date from Battery Information
			charging_date = getdate(battery.charging_date)
			age_days = date_diff(today, charging_date)
		else:
			# Fallback to creation date only if charging_date is not available
			creation_date = getdate(battery.creation)
			charging_date = creation_date
			age_days = date_diff(today, creation_date)
		
		# Count batteries that are around 60 days old (55-65 days range)
		if 55 <= age_days <= 65:
			batteries_60_days += 1
		
		# Categorize by age
		if age_days <= 60:
			age_ranges["0-60 days"] += 1
			age_category = "0-60 days"
		elif age_days <= 90:
			age_ranges["60-90 days"] += 1
			age_category = "60-90 days"
		elif age_days <= 120:
			age_ranges["90-120 days"] += 1
			age_category = "90-120 days"
		else:
			age_ranges["120+ days"] += 1
			age_category = "120+ days"
		
		# Categorize by expiry risk
		if age_days <= 60:
			expiry_risk_counts["safe"] += 1
			risk_level = "safe"
		elif age_days <= 90:
			expiry_risk_counts["warning"] += 1
			risk_level = "warning"
		elif age_days <= 120:
			expiry_risk_counts["critical"] += 1
			risk_level = "critical"
		else:
			expiry_risk_counts["very_critical"] += 1
			risk_level = "very_critical"
		
		# Count by brand
		brand = battery.get("battery_brand") or "Unknown"
		brand_counts[brand] = brand_counts.get(brand, 0) + 1
		
		# Count by battery type
		battery_type = battery.get("battery_type") or "Unknown"
		battery_type_counts[battery_type] = battery_type_counts.get(battery_type, 0) + 1
		
		# Note: battery_expiry_date field is not available in Battery Information doctype
		days_until_expiry = None
		
		# Get swap history count for this battery
		swap_count = 0
		if battery.get("frame_bundle_name"):
			swap_count = frappe.db.count("Frame Bundle Swap History", {
				"parent": battery.frame_bundle_name
			}) or 0
		
		is_discarded = (battery.get("discard_count") or 0) > 0
		
		battery_cards.append({
			"name": battery.name,
			"battery_serial_no": battery.battery_serial_no or "-",
			"brand": battery.get("battery_brand") or "-",
			"battery_type": battery.get("battery_type") or "-",
			"frame_no": battery.get("frame_no") or None,
			"frame_bundle_name": battery.get("frame_bundle_name") or None,
			"warehouse": battery.get("warehouse") or None,
			"battery_aging_days": battery.get("battery_aging_days"),
			"battery_installed_on": str(battery.get("battery_installed_on")) if battery.get("battery_installed_on") else None,
			"charging_date": str(battery.charging_date) if battery.charging_date else None,
			"creation_date": str(getdate(battery.creation)) if battery.creation else None,
			"age_days": age_days,
			"age_category": age_category,
			"risk_level": risk_level,
			"status": battery.get("status") or "Active",
			"is_discarded": 1 if is_discarded else 0,
			"swap_count": swap_count,
			"is_installed": 1 if battery.get("frame_bundle_name") else 0,
			"creation": str(battery.creation) if battery.creation else None,
			"modified": str(battery.modified) if battery.modified else None,
		})

	# Age distribution chart
	age_chart = {
		"labels": list(age_ranges.keys()),
		"values": list(age_ranges.values()),
	}

	# Brand distribution chart (top 10)
	brand_chart_rows = sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)[:10]
	brand_chart = {
		"labels": [row[0] for row in brand_chart_rows],
		"values": [row[1] for row in brand_chart_rows],
	}

	# Battery type distribution chart (top 10)
	battery_type_chart_rows = sorted(battery_type_counts.items(), key=lambda x: x[1], reverse=True)[:10]
	battery_type_chart = {
		"labels": [row[0] for row in battery_type_chart_rows],
		"values": [row[1] for row in battery_type_chart_rows],
	}

	# Batteries by charging date
	date_rows = frappe.db.sql(
		f"""
		SELECT 
			DATE(bd.charging_date) as date,
			COUNT(*) as count
		FROM `tabBattery Information` bd
		WHERE {where_clause} AND bd.charging_date IS NOT NULL
		GROUP BY DATE(bd.charging_date)
		ORDER BY DATE(bd.charging_date)
		""",
		params,
		as_dict=True,
	)

	date_chart = {
		"labels": [str(r.date) for r in date_rows],
		"values": [r.count for r in date_rows],
	}

	# Calculate expiry risk percentages
	expiry_risk_percentages = {}
	if total_batteries > 0:
		expiry_risk_percentages = {
			"safe": round((expiry_risk_counts["safe"] / total_batteries) * 100, 1),
			"warning": round((expiry_risk_counts["warning"] / total_batteries) * 100, 1),
			"critical": round((expiry_risk_counts["critical"] / total_batteries) * 100, 1),
			"very_critical": round((expiry_risk_counts["very_critical"] / total_batteries) * 100, 1),
		}
	else:
		expiry_risk_percentages = {"safe": 0, "warning": 0, "critical": 0, "very_critical": 0}
	
	return {
		"doctype": "Battery Information",
		"summary": {
			"total_batteries": total_batteries,
			"age_ranges": age_ranges,
			"expiry_risk_counts": expiry_risk_counts,
			"expiry_risk_percentages": expiry_risk_percentages,
			"brand_counts": brand_counts,
			"battery_type_counts": battery_type_counts,
			"batteries_60_days": batteries_60_days,  # Count of batteries around 60 days old
		},
		"age_chart": age_chart,
		"brand_chart": brand_chart,
		"battery_type_chart": battery_type_chart,
		"date_chart": date_chart,
		"batteries": battery_cards,
	}


@frappe.whitelist()
def get_filter_options():
	"""Get filter options for Battery Ageing dashboard."""
	# Get distinct brands from Battery Information (only Active)
	brands = frappe.db.sql_list(
		"""
		SELECT DISTINCT battery_brand
		FROM `tabBattery Information`
		WHERE status = 'Active'
		  AND battery_brand IS NOT NULL 
		  AND battery_brand != ''
		ORDER BY battery_brand
		"""
	)

	# Get distinct battery types from Battery Information (only Active)
	battery_types = frappe.db.sql_list(
		"""
		SELECT DISTINCT battery_type
		FROM `tabBattery Information`
		WHERE status = 'Active'
		  AND battery_type IS NOT NULL 
		  AND battery_type != ''
		ORDER BY battery_type
		"""
	)

	return {
		"brands": brands,
		"battery_types": battery_types,
	}


@frappe.whitelist()
def get_battery_details(name):
	"""Get detailed information about a specific Battery Information record with Frame Bundle data."""
	if not frappe.db.exists("Battery Information", name):
		return {"error": f"Battery Information {name} not found"}
	
	battery = frappe.get_doc("Battery Information", name)
	today = nowdate()
	
	# Get Frame Bundle information if battery is installed
	frame_bundle = frappe.db.get_value(
		"Frame Bundle",
		{"battery_serial_no": name, "docstatus": 1},
		["name", "frame_no", "battery_aging_days", "battery_installed_on", "warehouse"],
		as_dict=True
	)
	
	# Check if battery is discarded
	is_discarded = False
	swap_history = []
	discard_history = []
	
	if frame_bundle:
		# Check discard history
		discard_count = frappe.db.count("Frame Bundle Discard History", {
			"parent": frame_bundle.name
		}) or 0
		is_discarded = discard_count > 0
		
		# Get swap history
		swap_history = frappe.get_all(
			"Frame Bundle Swap History",
			filters={"parent": frame_bundle.name},
			fields=["swap_date", "swapped_with_frame", "swapped_by", "old_battery_serial_no", "new_battery_serial_no"],
			order_by="swap_date desc"
		)
		
		# Get discard history
		if is_discarded:
			discard_history = frappe.get_all(
				"Frame Bundle Discard History",
				filters={"parent": frame_bundle.name},
				fields=["discarded_date", "discarded_by", "discarded_battery_serial_no"],
				order_by="discarded_date desc"
			)
	
	# Calculate age - prefer battery_aging_days from Frame Bundle
	if frame_bundle and frame_bundle.get("battery_aging_days") is not None:
		age_days = frame_bundle.battery_aging_days
		charging_date = frame_bundle.get("battery_installed_on")
	elif battery.charging_date:
		charging_date = getdate(battery.charging_date)
		age_days = date_diff(today, charging_date)
	else:
		creation_date = getdate(battery.creation)
		charging_date = creation_date
		age_days = date_diff(today, creation_date)
	
	result = {
		"name": battery.name,
		"battery_serial_no": battery.battery_serial_no or "-",
		"brand": battery.battery_brand or "-",
		"battery_type": battery.battery_type or "-",
		"frame_no": frame_bundle.frame_no if frame_bundle else None,
		"frame_bundle_name": frame_bundle.name if frame_bundle else None,
		"warehouse": frame_bundle.warehouse if frame_bundle else None,
		"battery_aging_days": frame_bundle.battery_aging_days if frame_bundle else None,
		"battery_installed_on": str(frame_bundle.battery_installed_on) if frame_bundle and frame_bundle.battery_installed_on else None,
		"charging_date": str(battery.charging_date) if battery.charging_date else None,
		"creation_date": str(getdate(battery.creation)) if battery.creation else None,
		"age_days": age_days,
		"status": battery.status or "Active",
		"is_discarded": is_discarded,
		"is_installed": 1 if frame_bundle else 0,
		"swap_history": swap_history,
		"discard_history": discard_history,
		"swap_count": len(swap_history),
		"creation": str(battery.creation) if battery.creation else None,
		"modified": str(battery.modified) if battery.modified else None,
	}
	
	return {"battery": result}

