# Copyright (c) 2025, beetashoke.chakraborty@clapgrow.com and contributors
# For license information, please see license.txt

import frappe
import csv
import os
from frappe.model.document import Document
from frappe import _


class LoadDispatch(Document):
	def validate(self):
		"""Ensure linked Load Plan exists and is submitted before creating Load Dispatch."""
		if self.load_reference_no:
			# Check if Load Plan with given Load Reference No exists
			if not frappe.db.exists("Load Plan", self.load_reference_no):
				frappe.throw(
					_(
						"Load Plan with Load Reference No {0} does not exist."
					).format(self.load_reference_no)
				)

			load_plan = frappe.get_doc("Load Plan", self.load_reference_no)
			if load_plan.docstatus != 1:
				frappe.throw(
					_(
						"Please submit Load Plan against this Load Reference No before creating Load Dispatch."
					)
				)


@frappe.whitelist()
def process_csv_file(file_url):
	"""
	Process CSV file and extract data for child table
	Maps CSV columns to Load Dispatch Item fields
	"""
	try:
		# Get file path from file_url
		# file_url format: /files/filename.csv
		if file_url.startswith("/files/"):
			file_name = file_url.split("/files/")[-1]
			file_path = frappe.get_site_path("public", "files", file_name)
		else:
			file_path = frappe.get_site_path("public", file_url.lstrip("/"))
		
		# Check if file exists
		if not os.path.exists(file_path):
			frappe.throw(f"File not found: {file_url}")
		
		# Try different encodings to handle various file formats
		encodings = ['utf-8-sig', 'utf-8', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252']
		csvfile = None
		sample = None
		
		for encoding in encodings:
			try:
				csvfile = open(file_path, 'r', encoding=encoding)
				# Try to read a sample to verify encoding works and detect delimiter
				sample = csvfile.read(1024)
				csvfile.seek(0)
				break
			except (UnicodeDecodeError, UnicodeError):
				if csvfile:
					csvfile.close()
				csvfile = None
				sample = None
				continue
		
		if not csvfile or not sample:
			frappe.throw(f"Unable to read file with supported encodings. Please ensure the file is in UTF-8, UTF-16, or Latin-1 format.")
		
		try:
			# Detect delimiter from sample
			sniffer = csv.Sniffer()
			delimiter = sniffer.sniff(sample).delimiter
			
			reader = csv.DictReader(csvfile, delimiter=delimiter)
			
			# Mapping from CSV column names to child table fieldnames
			column_mapping = {
				"HMSI/InterDealer Load Reference No": "load_reference_no",
				"Invoice No.": "invoice_no",
				"Invoice Date": "invoice_date",
				"Model Category": "model_category",
				"Model Name": "model_name",
				"Model Variant": "model_variant",
				"Color Code": "color_code",
				"MTOC": "mtoc",
				"Frame #": "frame_no",
				"Engine No/Motor No": "engnie_no_motor_no",
				"Physical Status": "physical_status",
				"Chassis Status": "chassis_status",
				"Location": "location",
				"Key No": "key_no",
				"Load Type": "load_type",
				"Transporter Name": "transporter_name",
				"Shipment Truck #": "shipment_truck",
				"Dispatch Date": "dispatch_date",
				"Planned Arrival Date": "planned_arrival_date",
				"GR Date": "gr_date",
				"GR No": "gr_no",
				"Plant Code": "plant_code",
				"Payment Amount": "payment_amount",
				"Dealer Code": "dealer_code",
				"Manufacturing Date": "manufacturing_date",
				"Reference Number": "reference_number",
				"Invoice Price": "invoice_price",
				"SAP Sales Order No": "sap_sales_order_no",
				"Booking Reference#": "booking_reference",
				"Vehicle Tracking Info": "vehicle_tracking_info",
				"Dealer Purchase Order No": "dealer_purchase_order_no",
				"Type": "type",
				"Capacity": "capacity",
				"Option Code": "option_code",
				"Transporter Code": "transporter_code",
				"EV Battery Number": "ev_battery_number",
				"Model Code": "model_code",
				"HMSI Load Reference No": "load_reference_no",  # Alternative column name
				"Net Dealer price": "net_dealer_price",
				"Credit of GST": "credit_of_gst",
				"Dealer Billing Price": "dealer_billing_price",
				"CGST Amount": "cgst_amount",
				"SGST Amount": "sgst_amount",
				"IGST Amount": "igst_amount",
				"EX-Showroom Price": "ex_showroom_price",
				"GSTIN": "gstin"
			}
			
			rows = []
			
			for csv_row in reader:
				# Skip empty rows
				if not any(csv_row.values()):
					continue
				
				row_data = {}
				for csv_col, fieldname in column_mapping.items():
					value = csv_row.get(csv_col, "").strip()
					
					if value:
						# Handle date fields
						if fieldname in ["invoice_date", "dispatch_date", "manufacturing_date"]:
							# Try to parse date (assuming format YYYY-MM-DD or similar)
							try:
								from frappe.utils import getdate
								row_data[fieldname] = getdate(value)
							except:
								row_data[fieldname] = value
						# Handle datetime fields
						elif fieldname in ["planned_arrival_date", "gr_date"]:
							try:
								from frappe.utils import get_datetime
								row_data[fieldname] = get_datetime(value)
							except:
								row_data[fieldname] = value
						# Handle integer fields
						elif fieldname in ["key_no", "gr_no"]:
							try:
								row_data[fieldname] = int(float(value)) if value else None
							except:
								row_data[fieldname] = value
						# Handle currency fields
						elif fieldname in ["payment_amount", "net_dealer_price", "credit_of_gst", 
										   "dealer_billing_price", "cgst_amount", "sgst_amount", 
										   "igst_amount", "ex_showroom_price"]:
							try:
								row_data[fieldname] = float(value) if value else 0.0
							except:
								row_data[fieldname] = 0.0
						else:
							row_data[fieldname] = value
				
				if row_data:
					rows.append(row_data)
			
			return rows
		finally:
			if csvfile:
				csvfile.close()
			
	except Exception as e:
		frappe.log_error(f"Error processing CSV file: {str(e)}", "CSV Import Error")
		frappe.throw(f"Error processing CSV file: {str(e)}")
