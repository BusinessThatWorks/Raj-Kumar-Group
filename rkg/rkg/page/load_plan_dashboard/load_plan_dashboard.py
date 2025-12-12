import frappe
from frappe.utils import flt, getdate, nowdate


def _build_where_clause(status=None, from_date=None, to_date=None, load_reference=None):
	conditions = ["lp.docstatus < 2"]
	params = {}

	if status:
		conditions.append("lp.status = %(status)s")
		params["status"] = status

	if from_date:
		conditions.append("lp.dispatch_plan_date >= %(from_date)s")
		params["from_date"] = getdate(from_date)

	if to_date:
		conditions.append("lp.dispatch_plan_date <= %(to_date)s")
		params["to_date"] = getdate(to_date)

	if load_reference:
		conditions.append("lp.load_reference_no LIKE %(load_reference)s")
		params["load_reference"] = f"%{load_reference}%"

	return " AND ".join(conditions), params


@frappe.whitelist()
def get_dashboard_data(status=None, from_date=None, to_date=None, load_reference=None):
	"""Return aggregated data for the Load Plan Visual Dashboard."""
	where_clause, params = _build_where_clause(status, from_date, to_date, load_reference)

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
			lp.modified
		FROM `tabLoad Plan` lp
		WHERE {where_clause}
		ORDER BY COALESCE(lp.dispatch_plan_date, lp.payment_plan_date, lp.modified) DESC, lp.modified DESC
		LIMIT 500
		""",
		params,
		as_dict=True,
	)

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


@frappe.whitelist()
def get_filter_options():
	statuses = frappe.db.sql_list(
		"""
		SELECT DISTINCT status
		FROM `tabLoad Plan`
		WHERE status IS NOT NULL AND status != ''
		ORDER BY status
		"""
	)

	return {"statuses": statuses}

