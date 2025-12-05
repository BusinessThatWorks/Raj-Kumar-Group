# Copyright (c) 2025, RKG and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_days


@frappe.whitelist()
def get_serial_batch_data(company=None, from_date=None, to_date=None, item_code=None, warehouse=None):
	"""
	Get Serial and Batch Summary data for visual dashboard.
	Returns aggregated data for charts and detailed data for tree view.
	"""
	filters = {}
	conditions = ["1=1"]
	
	# Build conditions for Serial No table
	if company:
		conditions.append("sn.company = %(company)s")
		filters["company"] = company
	
	if warehouse:
		conditions.append("sn.warehouse = %(warehouse)s")
		filters["warehouse"] = warehouse
	
	if item_code:
		conditions.append("sn.item_code = %(item_code)s")
		filters["item_code"] = item_code
	
	where_clause = " AND ".join(conditions)
	
	# Query Serial No table directly for accurate counts
	query = f"""
		SELECT 
			sn.name as serial_no,
			sn.item_code,
			sn.warehouse,
			sn.status,
			sn.item_group,
			item.item_name
		FROM `tabSerial No` sn
		LEFT JOIN `tabItem` item ON sn.item_code = item.name
		WHERE {where_clause}
		ORDER BY sn.item_code, sn.name
		LIMIT 2000
	"""
	
	data = frappe.db.sql(query, filters, as_dict=True)
	
	# Process data for visualization
	result = {
		"raw_data": data,
		"summary": get_summary_stats_from_serials(data),
		"by_item": get_data_by_item_from_serials(data),
		"by_warehouse": get_data_by_warehouse_from_serials(data),
		"by_voucher_type": get_data_by_voucher_type_from_serials(data),
	}
	
	return result


def get_summary_stats_from_serials(data):
	"""Get summary statistics from Serial No data for number cards."""
	items = set()
	serials = set()
	warehouses = set()
	statuses = set()
	
	for row in data:
		if row.get("item_code"):
			items.add(row.item_code)
		if row.get("serial_no"):
			serials.add(row.serial_no)
		if row.get("warehouse"):
			warehouses.add(row.warehouse)
		if row.get("status"):
			statuses.add(row.status)
	
	return {
		"total_items": len(items),
		"total_serials": len(serials),
		"total_warehouses": len(warehouses),
		"total_voucher_types": len(statuses)
	}


def get_data_by_item_from_serials(data):
	"""Group Serial No data by item code for bar chart."""
	item_counts = {}
	item_names = {}
	
	for row in data:
		item_code = row.get("item_code")
		if not item_code:
			continue
		
		if item_code not in item_counts:
			item_counts[item_code] = 0
			item_names[item_code] = row.get("item_name") or item_code
		
		item_counts[item_code] += 1
	
	# Sort by count descending and take top 10
	sorted_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:10]
	
	return {
		"labels": [item_names.get(item[0], item[0])[:20] for item in sorted_items],
		"values": [item[1] for item in sorted_items],
		"item_codes": [item[0] for item in sorted_items]
	}


def get_data_by_warehouse_from_serials(data):
	"""Group Serial No data by warehouse for pie chart."""
	warehouse_counts = {}
	
	for row in data:
		warehouse = row.get("warehouse")
		if not warehouse:
			continue
		
		if warehouse not in warehouse_counts:
			warehouse_counts[warehouse] = 0
		
		warehouse_counts[warehouse] += 1
	
	# Sort by count descending
	sorted_warehouses = sorted(warehouse_counts.items(), key=lambda x: x[1], reverse=True)
	
	return {
		"labels": [w[0] for w in sorted_warehouses],
		"values": [w[1] for w in sorted_warehouses]
	}


def get_data_by_voucher_type_from_serials(data):
	"""Group Serial No data by status for donut chart."""
	status_counts = {}
	
	for row in data:
		status = row.get("status")
		if not status:
			status = "Unknown"
		
		if status not in status_counts:
			status_counts[status] = 0
		
		status_counts[status] += 1
	
	# Sort by count descending
	sorted_statuses = sorted(status_counts.items(), key=lambda x: x[1], reverse=True)
	
	return {
		"labels": [s[0] for s in sorted_statuses],
		"values": [s[1] for s in sorted_statuses]
	}


@frappe.whitelist()
def get_serials_by_item(item_code, company=None, warehouse=None):
	"""Get all serial numbers for a specific item code."""
	filters = {"item_code": item_code}
	
	if company:
		filters["company"] = company
	if warehouse:
		filters["warehouse"] = warehouse
	
	# Get from Serial No doctype
	serials = frappe.get_all(
		"Serial No",
		filters=filters,
		fields=["name", "item_code", "warehouse", "status", "purchase_document_no", "creation"],
		order_by="creation desc",
		limit=500
	)
	
	return serials


@frappe.whitelist()
def get_grouped_serial_data(company=None, from_date=None, to_date=None, warehouse=None):
	"""
	Get serial numbers grouped by item code for tree view.
	"""
	filters = {}
	conditions = ["1=1"]
	
	if company:
		conditions.append("sn.company = %(company)s")
		filters["company"] = company
	
	if warehouse:
		conditions.append("sn.warehouse = %(warehouse)s")
		filters["warehouse"] = warehouse
	
	where_clause = " AND ".join(conditions)
	
	# Get serial numbers with their item details
	query = f"""
		SELECT 
			sn.name as serial_no,
			sn.item_code,
			sn.warehouse,
			sn.status,
			sn.purchase_document_no,
			sn.creation,
			item.item_name
		FROM `tabSerial No` sn
		LEFT JOIN `tabItem` item ON sn.item_code = item.name
		WHERE {where_clause}
		ORDER BY sn.item_code, sn.name
		LIMIT 2000
	"""
	
	data = frappe.db.sql(query, filters, as_dict=True)
	
	# Group by item code
	grouped = {}
	for row in data:
		item_code = row.get("item_code")
		if not item_code:
			continue
		
		if item_code not in grouped:
			grouped[item_code] = {
				"item_code": item_code,
				"item_name": row.get("item_name") or item_code,
				"serials": [],
				"count": 0,
				"warehouses": set()
			}
		
		grouped[item_code]["serials"].append({
			"serial_no": row.get("serial_no"),
			"warehouse": row.get("warehouse"),
			"status": row.get("status"),
			"purchase_document_no": row.get("purchase_document_no"),
			"creation": row.get("creation")
		})
		grouped[item_code]["count"] += 1
		if row.get("warehouse"):
			grouped[item_code]["warehouses"].add(row.get("warehouse"))
	
	# Convert sets to lists for JSON serialization
	result = []
	for item_code, item_data in grouped.items():
		item_data["warehouses"] = list(item_data["warehouses"])
		result.append(item_data)
	
	# Sort by count descending
	result.sort(key=lambda x: x["count"], reverse=True)
	
	return result


@frappe.whitelist()
def get_filter_options():
	"""Get options for filter dropdowns."""
	companies = frappe.get_all("Company", fields=["name"], order_by="name")
	warehouses = frappe.get_all("Warehouse", fields=["name"], order_by="name")
	items = frappe.get_all(
		"Item", 
		filters={"has_serial_no": 1},
		fields=["name", "item_name"],
		order_by="name",
		limit=500
	)
	
	return {
		"companies": [c.name for c in companies],
		"warehouses": [w.name for w in warehouses],
		"items": items
	}

