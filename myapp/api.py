"""Server-side utilities for Load Dispatch CSV imports."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Tuple

import frappe
from frappe import _
from frappe.model.meta import DocField
from frappe.utils import cint, cstr, flt, get_datetime, getdate, parse_json

CHILD_TABLE_FIELDNAME = "load_dispatch_items"
CHILD_DOCTYPE = "Load Dispatch Item"

FIELD_MAP: "OrderedDict[str, str]" = OrderedDict(
	[
		("HMSI/InterDealer Load Reference No", "load_reference_no"),
		("Invoice No.", "invoice_no"),
		("Invoice Date", "invoice_date"),
		("Model Category", "model_category"),
		("Model Name", "model_name"),
		("Model Variant", "model_variant"),
		("Color Code", "color_code"),
		("MTOC", "mtoc"),
		("Frame #", "frame_no"),
		("Engine No/Motor No", "engnie_no_motor_no"),
		("Physical Status", "physical_status"),
		("Chassis Status", "chassis_status"),
		("Location", "location"),
		("Key No", "key_no"),
		("Load Type", "load_type"),
		("Transporter Name", "transporter_name"),
		("Shipment Truck #", "shipment_truck"),
		("Dispatch Date", "dispatch_date"),
		("Planned Arrival Date", "planned_arrival_date"),
		("GR Date", "gr_date"),
		("GR No", "gr_no"),
		("Plant Code", "plant_code"),
		("Payment Amount", "payment_amount"),
		("Dealer Code", "dealer_code"),
		("Manufacturing Date", "manufacturing_date"),
		("Reference Number", "reference_number"),
		("Invoice Price", "invoice_price"),
		("SAP Sales Order No", "sap_sales_order_no"),
		("Booking Reference#", "booking_reference"),
		("Vehicle Tracking Info", "vehicle_tracking_info"),
		("Dealer Purchase Order No", "dealer_purchase_order_no"),
		("Type", "type"),
		("Capacity", "capacity"),
		("Option Code", "option_code"),
		("Transporter Code", "transporter_code"),
		("EV Battery Number", "ev_battery_number"),
		("Model Code", "model_code"),
		("HMSI Load Reference No", "reference_number"),
		("Net Dealer price", "net_dealer_price"),
		("Credit of GST", "credit_of_gst"),
		("Dealer Billing Price", "dealer_billing_price"),
		("CGST Amount", "cgst_amount"),
		("SGST Amount", "sgst_amount"),
		("IGST Amount", "igst_amount"),
		("EX-Showroom Price", "ex_showroom_price"),
		("GSTIN", "gstin"),
	]
)


@frappe.whitelist()
def import_load_dispatch_items(parent: str, rows: Iterable[Dict[str, Any]]) -> int:
	"""Append CSV rows to the Load Dispatch child table and return inserted count."""
	if not parent:
		frappe.throw(_("Parent Load Dispatch name is required."))

	rows = parse_json(rows) if rows else []
	if not isinstance(rows, list):
		frappe.throw(_("Rows must be a list of dictionaries."))

	if not rows:
		return 0

	doc = frappe.get_doc("Load Dispatch", parent)
	child_fieldname = _resolve_child_table_fieldname(doc)

	child_meta = frappe.get_meta(CHILD_DOCTYPE)
	child_fields = {df.fieldname: df for df in child_meta.fields if df.fieldname}

	inserted = 0
	for row in rows:
		if not isinstance(row, dict):
			continue

		child = doc.append(child_fieldname, {})
		for header, fieldname in FIELD_MAP.items():
			if fieldname not in child_fields:
				continue

			raw_value = row.get(header)
			value = _coerce_value(child_fields[fieldname], raw_value)
			if value is not None:
				child.set(fieldname, value)

		inserted += 1

	if inserted:
		doc.save(ignore_permissions=True)

	return inserted


def _resolve_child_table_fieldname(doc) -> str:
	"""Return the table fieldname, honoring the requested load_dispatch_items field."""
	if doc.meta.get_field(CHILD_TABLE_FIELDNAME):
		return CHILD_TABLE_FIELDNAME

	legacy_field = "items"
	if doc.meta.get_field(legacy_field):
		return legacy_field

	frappe.throw(
		_("Child table field {0} not found on Load Dispatch.").format(CHILD_TABLE_FIELDNAME)
	)


def _coerce_value(field: DocField, value: Any) -> Any:
	if value in (None, "", []):
		return None

	fieldtype = field.fieldtype
	text_value = cstr(value).strip() if isinstance(value, str) else value

	if text_value in ("", None):
		return None

	if fieldtype in {"Int", "Check"}:
		return cint(text_value)

	if fieldtype in {"Currency", "Float", "Percent"}:
		return flt(text_value)

	if fieldtype == "Date":
		return getdate(text_value)

	if fieldtype in {"Datetime", "Time"}:
		return get_datetime(text_value)

	return text_value

