# Copyright (c) 2025, beetashoke.chakraborty@clapgrow.com and contributors
# For license information, please see license.txt

import frappe
import csv
import os
from frappe.model.document import Document
from frappe import _


class LoadDispatch(Document):
	def before_save(self):
		"""Populate item_code from mtoc before saving."""
		# Populate item_code from mtoc for all items on save
		if self.items:
			for item in self.items:
				if item.mtoc:
					# Always set item_code from mtoc on save
					item.item_code = str(item.mtoc).strip()
	
	def validate(self):
		"""Ensure linked Load Plan exists and is submitted before creating Load Dispatch."""
		# Also populate item_code in validate as backup
		if self.items:
			for item in self.items:
				if item.mtoc and not item.item_code:
					# Set item_code from mtoc if not already set
					item.item_code = str(item.mtoc).strip()
		
		# Prevent changing load_reference_no if document has imported items (works for both new and existing documents)
		has_imported_items = False
		if self.items:
			for item in self.items:
				if item.frame_no and str(item.frame_no).strip():
					has_imported_items = True
					break
		
		# Check if load_reference_no is being changed
		if has_imported_items:
			if self.is_new():
				# For new documents with imported items, check if load_reference_no was set from CSV
				# We track this via a custom property set during CSV import
				if hasattr(self, '_load_reference_no_from_csv') and self._load_reference_no_from_csv:
					if self.load_reference_no != self._load_reference_no_from_csv:
						frappe.throw(
							_(
								"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported from CSV. The CSV data belongs to Load Reference Number '{0}'. Please clear all items first or use a CSV file that matches the desired Load Reference Number."
							).format(self._load_reference_no_from_csv, self.load_reference_no)
						)
				# If no flag is set but items exist, it means items were imported
				# In this case, we need to prevent changes - but we can't know the original value
				# So we'll rely on client-side validation for new documents
			else:
				# For existing documents, check if value changed
				if self.has_value_changed("load_reference_no"):
					old_value = self.get_doc_before_save().get("load_reference_no") if self.get_doc_before_save() else None
					frappe.throw(
						_(
							"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported. Please clear all items first or create a new Load Dispatch document."
						).format(old_value or "None", self.load_reference_no)
					)
		
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
		
		# Calculate total dispatch quantity from child table
		self.calculate_total_dispatch_quantity()
	
	def on_submit(self):
		self.add_dispatch_quanity_to_load_plan(docstatus=1)
	
	def on_cancel(self):
		self.add_dispatch_quanity_to_load_plan(docstatus=2)
	
	def add_dispatch_quanity_to_load_plan(self, docstatus):
		"""
		Update load_dispatch_quantity in Load Plan when Load Dispatch is submitted or cancelled.
		
		Args:
			docstatus: 1 for submit (add quantity), 2 for cancel (subtract quantity)
		"""
		if not self.load_reference_no:
			return
		
		# Ensure total_dispatch_quantity is calculated
		if not self.total_dispatch_quantity:
			self.calculate_total_dispatch_quantity()
		
		# Get current load_dispatch_quantity from database (works for submitted documents)
		current_quantity = frappe.db.get_value("Load Plan", self.load_reference_no, "load_dispatch_quantity") or 0
		
		# Calculate new quantity based on docstatus
		if docstatus == 1:  # Submit - add quantity
			new_quantity = current_quantity + (self.total_dispatch_quantity or 0)
		elif docstatus == 2:  # Cancel - subtract quantity
			new_quantity = max(0, current_quantity - (self.total_dispatch_quantity or 0))
		else:
			return
		
		# Update directly in database using db_set (works for submitted documents)
		frappe.db.set_value("Load Plan", self.load_reference_no, "load_dispatch_quantity", new_quantity, update_modified=False)
	
	def validate(self):
		"""Ensure linked Load Plan exists and is submitted before creating Load Dispatch."""
		# Prevent changing load_reference_no if document has imported items (works for both new and existing documents)
		has_imported_items = False
		if self.items:
			for item in self.items:
				if item.frame_no and str(item.frame_no).strip():
					has_imported_items = True
					break
		
		# Check if load_reference_no is being changed
		if has_imported_items:
			if self.is_new():
				# For new documents with imported items, check if load_reference_no was set from CSV
				# We track this via a custom property set during CSV import
				if hasattr(self, '_load_reference_no_from_csv') and self._load_reference_no_from_csv:
					if self.load_reference_no != self._load_reference_no_from_csv:
						frappe.throw(
							_(
								"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported from CSV. The CSV data belongs to Load Reference Number '{0}'. Please clear all items first or use a CSV file that matches the desired Load Reference Number."
							).format(self._load_reference_no_from_csv, self.load_reference_no)
						)
				# If no flag is set but items exist, it means items were imported
				# In this case, we need to prevent changes - but we can't know the original value
				# So we'll rely on client-side validation for new documents
			else:
				# For existing documents, check if value changed
				if self.has_value_changed("load_reference_no"):
					old_value = self.get_doc_before_save().get("load_reference_no") if self.get_doc_before_save() else None
					frappe.throw(
						_(
							"Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported. Please clear all items first or create a new Load Dispatch document."
						).format(old_value or "None", self.load_reference_no)
					)
		
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
		
		# Calculate total dispatch quantity from child table
		self.calculate_total_dispatch_quantity()
	
	def calculate_total_dispatch_quantity(self):
		"""Count the number of rows with non-empty frame_no in Load Dispatch Item child table."""
		total_dispatch_quantity = 0
		if self.items:
			for item in self.items:
				# Count rows that have a non-empty frame_no
				if item.frame_no and str(item.frame_no).strip():
					total_dispatch_quantity += 1
		self.total_dispatch_quantity = total_dispatch_quantity


@frappe.whitelist()
def process_csv_file(file_url, selected_load_reference_no=None):
	"""
	Process CSV file and extract data for child table
	Maps CSV columns to Load Dispatch Item fields
	
	Args:
		file_url: Path to the CSV file
		selected_load_reference_no: The manually selected Load Reference No to validate against
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
			csv_load_reference_nos = set()  # Track all load_reference_no values from CSV
			
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
					
					# Track load_reference_no from CSV
					if fieldname == "load_reference_no" and value:
						csv_load_reference_nos.add(value)
				
				if row_data:
					rows.append(row_data)
			
			# Validate load_reference_no match if manually selected
			if selected_load_reference_no:
				if len(csv_load_reference_nos) == 0:
					frappe.throw(_("CSV file does not contain any Load Reference Number. Please ensure the CSV has 'HMSI/InterDealer Load Reference No' or 'HMSI Load Reference No' column."))
				elif len(csv_load_reference_nos) > 1:
					frappe.throw(_("CSV file contains multiple different Load Reference Numbers: {0}. All rows must have the same Load Reference Number.").format(", ".join(sorted(csv_load_reference_nos))))
				else:
					csv_load_ref = list(csv_load_reference_nos)[0]
					if csv_load_ref != selected_load_reference_no:
						frappe.throw(_("Load Reference Number mismatch! You have selected '{0}', but the CSV file contains '{1}'. Please ensure the CSV file matches the selected Load Reference Number.").format(selected_load_reference_no, csv_load_ref))
			
			return rows
		finally:
			if csvfile:
				csvfile.close()
			
	except Exception as e:
		frappe.log_error(f"Error processing CSV file: {str(e)}", "CSV Import Error")
		frappe.throw(f"Error processing CSV file: {str(e)}")
