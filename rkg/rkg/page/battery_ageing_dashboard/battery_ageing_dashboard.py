# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate, nowdate, date_diff


def _build_where_clause(brand=None, battery_type=None, from_date=None, to_date=None):
	"""Build WHERE clause for Battery Ageing queries."""
	conditions = ["i.item_group = 'Batteries'"]
	params = {}

	if brand:
		conditions.append("i.custom_battery_brand = %(brand)s")
		params["brand"] = brand

	if battery_type:
		conditions.append("i.custom_battery_type = %(battery_type)s")
		params["battery_type"] = battery_type

	if from_date:
		conditions.append("DATE(i.creation) >= %(from_date)s")
		params["from_date"] = getdate(from_date)

	if to_date:
		conditions.append("DATE(i.creation) <= %(to_date)s")
		params["to_date"] = getdate(to_date)

	return " AND ".join(conditions), params


@frappe.whitelist()
def get_dashboard_data(brand=None, battery_type=None, from_date=None, to_date=None):
	"""Return aggregated data for the Battery Ageing Dashboard."""
	where_clause, params = _build_where_clause(brand, battery_type, from_date, to_date)
	
	return get_battery_ageing_data(where_clause, params)


def get_battery_ageing_data(where_clause, params):
	"""Get Battery Ageing dashboard data."""
	# Get current date for age calculation
	today = nowdate()
	
	# Build SELECT fields
	select_fields = [
		"i.name",
		"i.item_code",
		"i.item_name",
		"i.creation",
		"i.modified",
	]
	
	# Add custom fields if they exist
	if frappe.db.has_column("Item", "custom_battery_brand"):
		select_fields.append("i.custom_battery_brand")
	if frappe.db.has_column("Item", "custom_battery_type"):
		select_fields.append("i.custom_battery_type")
	if frappe.db.has_column("Item", "custom_battery_charging_code"):
		select_fields.append("i.custom_battery_charging_code")
	if frappe.db.has_column("Item", "custom_charging_date"):
		select_fields.append("i.custom_charging_date")
	
	batteries = frappe.db.sql(
		f"""
		SELECT {', '.join(select_fields)}
		FROM `tabItem` i
		WHERE {where_clause}
		ORDER BY i.creation DESC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	total_batteries = len(batteries)
	
	# Calculate age for each battery and categorize
	age_ranges = {
		"0-30 days": 0,
		"31-90 days": 0,
		"91-180 days": 0,
		"181-365 days": 0,
		"365+ days": 0,
	}
	
	# Expiry Risk Categories
	expiry_risk_counts = {
		"safe": 0,      # 0-180 days (Green)
		"warning": 0,   # 181-365 days (Orange)
		"critical": 0,  # 365+ days (Red)
	}
	
	brand_counts = {}
	battery_type_counts = {}
	
	battery_cards = []
	for battery in batteries:
		creation_date = getdate(battery.creation)
		age_days = date_diff(today, creation_date)
		
		# Categorize by age
		if age_days <= 30:
			age_ranges["0-30 days"] += 1
			age_category = "0-30 days"
		elif age_days <= 90:
			age_ranges["31-90 days"] += 1
			age_category = "31-90 days"
		elif age_days <= 180:
			age_ranges["91-180 days"] += 1
			age_category = "91-180 days"
		elif age_days <= 365:
			age_ranges["181-365 days"] += 1
			age_category = "181-365 days"
		else:
			age_ranges["365+ days"] += 1
			age_category = "365+ days"
		
		# Categorize by expiry risk
		if age_days <= 180:
			expiry_risk_counts["safe"] += 1
			risk_level = "safe"
		elif age_days <= 365:
			expiry_risk_counts["warning"] += 1
			risk_level = "warning"
		else:
			expiry_risk_counts["critical"] += 1
			risk_level = "critical"
		
		# Count by brand
		brand = battery.get("custom_battery_brand") or "Unknown"
		brand_counts[brand] = brand_counts.get(brand, 0) + 1
		
		# Count by battery type
		battery_type = battery.get("custom_battery_type") or "Unknown"
		battery_type_counts[battery_type] = battery_type_counts.get(battery_type, 0) + 1
		
		battery_cards.append({
			"name": battery.name,
			"item_code": battery.item_code or "-",
			"item_name": battery.item_name or "-",
			"brand": battery.get("custom_battery_brand") or "-",
			"battery_type": battery.get("custom_battery_type") or "-",
			"charging_code": battery.get("custom_battery_charging_code") or "-",
			"charging_date": str(battery.get("custom_charging_date")) if battery.get("custom_charging_date") else None,
			"creation_date": str(creation_date),
			"age_days": age_days,
			"age_category": age_category,
			"risk_level": risk_level,
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

	# Batteries by creation date
	date_rows = frappe.db.sql(
		f"""
		SELECT 
			DATE(i.creation) as date,
			COUNT(*) as count
		FROM `tabItem` i
		WHERE {where_clause} AND i.creation IS NOT NULL
		GROUP BY DATE(i.creation)
		ORDER BY DATE(i.creation)
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
		}
	else:
		expiry_risk_percentages = {"safe": 0, "warning": 0, "critical": 0}
	
	return {
		"doctype": "Item",
		"summary": {
			"total_batteries": total_batteries,
			"age_ranges": age_ranges,
			"expiry_risk_counts": expiry_risk_counts,
			"expiry_risk_percentages": expiry_risk_percentages,
			"brand_counts": brand_counts,
			"battery_type_counts": battery_type_counts,
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
	# Get distinct brands
	brands = frappe.db.sql_list(
		"""
		SELECT DISTINCT custom_battery_brand
		FROM `tabItem`
		WHERE item_group = 'Batteries' 
		  AND custom_battery_brand IS NOT NULL 
		  AND custom_battery_brand != ''
		ORDER BY custom_battery_brand
		"""
	)

	# Get distinct battery types
	battery_types = frappe.db.sql_list(
		"""
		SELECT DISTINCT custom_battery_type
		FROM `tabItem`
		WHERE item_group = 'Batteries' 
		  AND custom_battery_type IS NOT NULL 
		  AND custom_battery_type != ''
		ORDER BY custom_battery_type
		"""
	)

	return {
		"brands": brands,
		"battery_types": battery_types,
	}


@frappe.whitelist()
def get_battery_details(name):
	"""Get detailed information about a specific Battery Item."""
	if not frappe.db.exists("Item", name):
		return {"error": f"Battery Item {name} not found"}
	
	battery = frappe.get_doc("Item", name)
	today = nowdate()
	creation_date = getdate(battery.creation)
	age_days = date_diff(today, creation_date)
	
	result = {
		"name": battery.name,
		"item_code": battery.item_code,
		"item_name": battery.item_name,
		"creation_date": str(creation_date),
		"age_days": age_days,
		"creation": str(battery.creation) if battery.creation else None,
		"modified": str(battery.modified) if battery.modified else None,
	}
	
	# Add custom fields if they exist
	if frappe.db.has_column("Item", "custom_battery_brand"):
		result["brand"] = getattr(battery, "custom_battery_brand", None) or "-"
	if frappe.db.has_column("Item", "custom_battery_type"):
		result["battery_type"] = getattr(battery, "custom_battery_type", None) or "-"
	if frappe.db.has_column("Item", "custom_battery_charging_code"):
		result["charging_code"] = getattr(battery, "custom_battery_charging_code", None) or "-"
	if frappe.db.has_column("Item", "custom_charging_date"):
		charging_date = getattr(battery, "custom_charging_date", None)
		result["charging_date"] = str(charging_date) if charging_date else None
	
	return {"battery": result}

