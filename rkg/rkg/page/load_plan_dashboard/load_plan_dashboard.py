import frappe
from frappe.utils import flt, getdate, nowdate


def _build_where_clause(doctype="Load Plan", status=None, from_date=None, to_date=None, load_reference=None):
	"""Build WHERE clause for Load Plan or Load Dispatch queries."""
	if doctype == "Load Plan":
		conditions = ["lp.docstatus < 2"]
		date_field = "lp.dispatch_plan_date"
		ref_field = "lp.load_reference_no"
	else:  # Load Dispatch
		conditions = ["ld.docstatus < 2"]
		date_field = "ld.modified"  # Load Dispatch doesn't have dispatch_plan_date
		ref_field = "ld.load_reference_no"
	
	params = {}

	if status:
		if doctype == "Load Plan":
			conditions.append("lp.status = %(status)s")
		else:
			conditions.append("ld.status = %(status)s")
		params["status"] = status

	if from_date:
		# For Load Plan: use dispatch_plan_date, fallback to payment_plan_date, then modified
		# For Load Dispatch: use modified date
		if doctype == "Load Plan":
			conditions.append(f"COALESCE({date_field}, lp.payment_plan_date, lp.modified) >= %(from_date)s")
		else:
			conditions.append(f"{date_field} >= %(from_date)s")
		params["from_date"] = getdate(from_date)

	if to_date:
		# For Load Plan: use dispatch_plan_date, fallback to payment_plan_date, then modified
		# For Load Dispatch: use modified date
		if doctype == "Load Plan":
			conditions.append(f"COALESCE({date_field}, lp.payment_plan_date, lp.modified) <= %(to_date)s")
		else:
			conditions.append(f"{date_field} <= %(to_date)s")
		params["to_date"] = getdate(to_date)

	if load_reference:
		conditions.append(f"{ref_field} LIKE %(load_reference)s")
		params["load_reference"] = f"%{load_reference}%"

	return " AND ".join(conditions), params


@frappe.whitelist()
def get_dashboard_data(status=None, from_date=None, to_date=None, load_reference=None, doctype="Load Plan"):
	"""Return aggregated data for the Load Plan and Load Dispatch Visual Dashboard."""
	where_clause, params = _build_where_clause(doctype, status, from_date, to_date, load_reference)
	
	# Get data based on doctype
	if doctype == "Load Dispatch":
		return get_load_dispatch_data(where_clause, params)
	else:
		return get_load_plan_data(where_clause, params)


def get_load_plan_data(where_clause, params):
	"""Get Load Plan dashboard data."""

	plans = frappe.db.sql(
		f"""
		SELECT
			lp.name,
			lp.load_reference_no,
			lp.dispatch_plan_date,
			lp.payment_plan_date,
			lp.status,
			lp.total_quantity,
			lp.load_dispatch_quantity,
			lp.modified,
			(SELECT COUNT(*) FROM `tabLoad Plan Item` lpi WHERE lpi.parent = lp.name) as item_count,
			(SELECT COALESCE(SUM(lpi.quantity), 0) FROM `tabLoad Plan Item` lpi WHERE lpi.parent = lp.name) as calculated_qty
		FROM `tabLoad Plan` lp
		WHERE {where_clause}
		ORDER BY COALESCE(lp.dispatch_plan_date, lp.payment_plan_date, lp.modified) DESC, lp.modified DESC
		LIMIT 500
		""",
		params,
		as_dict=True,
	)
	
	# Fix Load Plans where total_quantity doesn't match calculated quantity
	for plan in plans:
		calculated_qty = flt(plan.get("calculated_qty")) or 0
		stored_qty = flt(plan.get("total_quantity")) or 0
		
		# If calculated quantity differs from stored, update it
		if calculated_qty != stored_qty and plan.get("name"):
			frappe.db.set_value("Load Plan", plan.name, "total_quantity", calculated_qty, update_modified=False)
			plan["total_quantity"] = calculated_qty
			print(f"DEBUG: Fixed Load Plan {plan.name} - updated total_quantity from {stored_qty} to {calculated_qty}")

	total_plans = len(plans)
	total_planned_qty = sum(flt(p.total_quantity) for p in plans)
	total_dispatched_qty = sum(flt(p.load_dispatch_quantity) for p in plans)
	dispatch_completion = flt((total_dispatched_qty / total_planned_qty) * 100) if total_planned_qty else 0

	# Status distribution
	status_rows = frappe.db.sql(
		f"""
		SELECT lp.status, COUNT(*) as count
		FROM `tabLoad Plan` lp
		WHERE {where_clause}
		GROUP BY lp.status
		ORDER BY count DESC
		""",
		params,
		as_dict=True,
	)

	status_chart = {
		"labels": [row.status or "Unknown" for row in status_rows],
		"values": [row.count for row in status_rows],
	}

	# Plan vs dispatch by date
	plan_rows = frappe.db.sql(
		f"""
		SELECT lp.dispatch_plan_date as date, SUM(lp.total_quantity) as planned_qty, SUM(lp.load_dispatch_quantity) as dispatched_qty
		FROM `tabLoad Plan` lp
		WHERE {where_clause} AND lp.dispatch_plan_date IS NOT NULL
		GROUP BY lp.dispatch_plan_date
		ORDER BY lp.dispatch_plan_date
		""",
		params,
		as_dict=True,
	)

	plan_vs_dispatch = {
		"labels": [str(r.date) for r in plan_rows],
		"planned": [flt(r.planned_qty) for r in plan_rows],
		"dispatched": [flt(r.dispatched_qty) for r in plan_rows],
	}

	# Top planned models
	model_rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(lpi.model_name, lpi.model_variant, lpi.model) as label,
			SUM(lpi.quantity) as qty
		FROM `tabLoad Plan Item` lpi
		JOIN `tabLoad Plan` lp ON lpi.parent = lp.name
		WHERE {where_clause} AND COALESCE(lpi.model_name, lpi.model_variant, lpi.model) IS NOT NULL
		GROUP BY label
		ORDER BY qty DESC
		LIMIT 8
		""",
		params,
		as_dict=True,
	)

	top_models = {
		"labels": [m.label for m in model_rows],
		"values": [flt(m.qty) for m in model_rows],
	}

	today = getdate(nowdate())
	plan_cards = []
	for plan in plans:
		planned = flt(plan.total_quantity)
		dispatched = flt(plan.load_dispatch_quantity)
		progress = flt((dispatched / planned) * 100) if planned else 0
		progress = min(progress, 100)
		remaining = max(0, planned - dispatched)
		dispatch_date = plan.dispatch_plan_date
		is_overdue = bool(dispatch_date and getdate(dispatch_date) < today and remaining > 0)

		plan_cards.append(
			{
				"load_reference_no": plan.load_reference_no,
				"status": plan.status or "Submitted",
				"dispatch_plan_date": str(dispatch_date) if dispatch_date else None,
				"payment_plan_date": str(plan.payment_plan_date) if plan.payment_plan_date else None,
				"total_quantity": planned,
				"load_dispatch_quantity": dispatched,
				"remaining": remaining,
				"progress": round(progress, 1),
				"is_overdue": is_overdue,
			}
		)

	return {
		"doctype": "Load Plan",
		"summary": {
			"total_plans": total_plans,
			"total_planned_qty": total_planned_qty,
			"total_dispatched_qty": total_dispatched_qty,
			"dispatch_completion": round(dispatch_completion, 1),
		},
		"status_chart": status_chart,
		"plan_vs_dispatch": plan_vs_dispatch,
		"top_models": top_models,
		"plans": plan_cards,
	}


def get_load_dispatch_data(where_clause, params):
	"""Get Load Dispatch dashboard data."""
	dispatches = frappe.db.sql(
		f"""
		SELECT
			ld.name,
			ld.dispatch_no,
			ld.load_reference_no,
			ld.invoice_no,
			ld.status,
			ld.total_dispatch_quantity,
			ld.total_load_quantity,
			ld.total_received_quantity,
			ld.total_billed_quantity,
			ld.modified
		FROM `tabLoad Dispatch` ld
		WHERE {where_clause}
		ORDER BY ld.modified DESC
		LIMIT 500
		""",
		params,
		as_dict=True,
	)

	total_dispatches = len(dispatches)
	total_dispatch_qty = sum(flt(d.total_dispatch_quantity) for d in dispatches)
	total_received_qty = sum(flt(d.total_received_quantity) for d in dispatches)
	total_billed_qty = sum(flt(d.total_billed_quantity) for d in dispatches)
	receive_completion = flt((total_received_qty / total_dispatch_qty) * 100) if total_dispatch_qty else 0
	bill_completion = flt((total_billed_qty / total_dispatch_qty) * 100) if total_dispatch_qty else 0

	# Status distribution
	status_rows = frappe.db.sql(
		f"""
		SELECT ld.status, COUNT(*) as count
		FROM `tabLoad Dispatch` ld
		WHERE {where_clause}
		GROUP BY ld.status
		ORDER BY count DESC
		""",
		params,
		as_dict=True,
	)

	status_chart = {
		"labels": [row.status or "Unknown" for row in status_rows],
		"values": [row.count for row in status_rows],
	}

	# Dispatch vs Received vs Billed by date
	date_rows = frappe.db.sql(
		f"""
		SELECT 
			DATE(ld.modified) as date,
			SUM(ld.total_dispatch_quantity) as dispatch_qty,
			SUM(ld.total_received_quantity) as received_qty,
			SUM(ld.total_billed_quantity) as billed_qty
		FROM `tabLoad Dispatch` ld
		WHERE {where_clause} AND ld.modified IS NOT NULL
		GROUP BY DATE(ld.modified)
		ORDER BY DATE(ld.modified)
		""",
		params,
		as_dict=True,
	)

	dispatch_vs_received = {
		"labels": [str(r.date) for r in date_rows],
		"dispatched": [flt(r.dispatch_qty) for r in date_rows],
		"received": [flt(r.received_qty) for r in date_rows],
		"billed": [flt(r.billed_qty) for r in date_rows],
	}

	# Top dispatched models
	model_rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(ldi.model_name, ldi.model_variant) as label,
			SUM(ldi.qty) as qty
		FROM `tabLoad Dispatch Item` ldi
		JOIN `tabLoad Dispatch` ld ON ldi.parent = ld.name
		WHERE {where_clause} AND COALESCE(ldi.model_name, ldi.model_variant) IS NOT NULL
		GROUP BY label
		ORDER BY qty DESC
		LIMIT 8
		""",
		params,
		as_dict=True,
	)

	top_models = {
		"labels": [m.label for m in model_rows],
		"values": [flt(m.qty) for m in model_rows],
	}

	dispatch_cards = []
	for dispatch in dispatches:
		dispatched = flt(dispatch.total_dispatch_quantity)
		received = flt(dispatch.total_received_quantity)
		billed = flt(dispatch.total_billed_quantity)
		receive_progress = flt((received / dispatched) * 100) if dispatched else 0
		bill_progress = flt((billed / dispatched) * 100) if dispatched else 0
		receive_progress = min(receive_progress, 100)
		bill_progress = min(bill_progress, 100)

		dispatch_cards.append(
			{
				"name": dispatch.name,
				"dispatch_no": dispatch.dispatch_no,
				"load_reference_no": dispatch.load_reference_no,
				"invoice_no": dispatch.invoice_no,
				"status": dispatch.status or "In-Transit",
				"total_dispatch_quantity": dispatched,
				"total_received_quantity": received,
				"total_billed_quantity": billed,
				"receive_progress": round(receive_progress, 1),
				"bill_progress": round(bill_progress, 1),
			}
		)

	return {
		"doctype": "Load Dispatch",
		"summary": {
			"total_dispatches": total_dispatches,
			"total_dispatch_qty": total_dispatch_qty,
			"total_received_qty": total_received_qty,
			"total_billed_qty": total_billed_qty,
			"receive_completion": round(receive_completion, 1),
			"bill_completion": round(bill_completion, 1),
		},
		"status_chart": status_chart,
		"dispatch_vs_received": dispatch_vs_received,
		"top_models": top_models,
		"dispatches": dispatch_cards,
	}


@frappe.whitelist()
def get_filter_options(doctype="Load Plan"):
	"""Get filter options for Load Plan or Load Dispatch."""
	if doctype == "Load Dispatch":
		statuses = frappe.db.sql_list(
			"""
			SELECT DISTINCT status
			FROM `tabLoad Dispatch`
			WHERE docstatus < 2 AND status IS NOT NULL AND status != ''
			ORDER BY status
			"""
		)
	else:
		statuses = frappe.db.sql_list(
			"""
			SELECT DISTINCT status
			FROM `tabLoad Plan`
			WHERE docstatus < 2 AND status IS NOT NULL AND status != ''
			ORDER BY status
			"""
		)

	return {"statuses": statuses}


@frappe.whitelist()
def get_combined_dashboard_data(status=None, from_date=None, to_date=None, load_reference=None):
	"""Get combined data for both Load Plan and Load Dispatch."""
	load_plan_data = get_dashboard_data(status, from_date, to_date, load_reference, "Load Plan")
	load_dispatch_data = get_dashboard_data(status, from_date, to_date, load_reference, "Load Dispatch")
	
	return {
		"load_plan": load_plan_data,
		"load_dispatch": load_dispatch_data,
	}


@frappe.whitelist()
def get_load_plan_details(load_reference_no):
	"""Get detailed information about a specific Load Plan including child table items."""
	if not frappe.db.exists("Load Plan", load_reference_no):
		return {"error": f"Load Plan {load_reference_no} not found"}
	
	# Get Load Plan document
	load_plan = frappe.get_doc("Load Plan", load_reference_no)
	
	# Get child table items
	items = frappe.get_all(
		"Load Plan Item",
		filters={"parent": load_reference_no},
		fields=["model", "model_name", "model_type", "model_variant", "model_color", "group_color", "option", "quantity"],
		order_by="idx"
	)
	
	return {
		"plan": {
			"load_reference_no": load_plan.load_reference_no,
			"dispatch_plan_date": str(load_plan.dispatch_plan_date) if load_plan.dispatch_plan_date else None,
			"payment_plan_date": str(load_plan.payment_plan_date) if load_plan.payment_plan_date else None,
			"status": load_plan.status,
			"total_quantity": flt(load_plan.total_quantity) or 0,
			"load_dispatch_quantity": flt(load_plan.load_dispatch_quantity) or 0,
		},
		"items": items
	}


@frappe.whitelist()
def recalculate_load_plan_quantities(load_reference_no=None):
	"""
	Recalculate total_quantity for Load Plans by summing quantities from child table items.
	If load_reference_no is provided, only recalculate that specific Load Plan.
	Otherwise, recalculate all Load Plans.
	"""
	from frappe.utils import flt
	
	if load_reference_no:
		# Recalculate specific Load Plan
		if not frappe.db.exists("Load Plan", load_reference_no):
			return {"success": False, "message": f"Load Plan {load_reference_no} not found"}
		
		# Calculate from child table
		items = frappe.get_all(
			"Load Plan Item",
			filters={"parent": load_reference_no},
			fields=["quantity"]
		)
		
		total_qty = sum(flt(item.quantity) or 0 for item in items)
		
		# Update Load Plan
		frappe.db.set_value("Load Plan", load_reference_no, "total_quantity", total_qty, update_modified=False)
		frappe.db.commit()
		
		return {
			"success": True,
			"message": f"Recalculated Load Plan {load_reference_no}: {total_qty} (from {len(items)} items)"
		}
	else:
		# Recalculate all Load Plans
		load_plans = frappe.get_all("Load Plan", filters={"docstatus": ["<", 2]}, fields=["name"])
		
		updated_count = 0
		for lp in load_plans:
			# Calculate from child table
			items = frappe.get_all(
				"Load Plan Item",
				filters={"parent": lp.name},
				fields=["quantity"]
			)
			
			total_qty = sum(flt(item.quantity) or 0 for item in items)
			current_qty = flt(frappe.db.get_value("Load Plan", lp.name, "total_quantity")) or 0
			
			# Only update if different
			if total_qty != current_qty:
				frappe.db.set_value("Load Plan", lp.name, "total_quantity", total_qty, update_modified=False)
				updated_count += 1
		
		frappe.db.commit()
		
		return {
			"success": True,
			"message": f"Recalculated {updated_count} Load Plan(s) out of {len(load_plans)} total"
		}

