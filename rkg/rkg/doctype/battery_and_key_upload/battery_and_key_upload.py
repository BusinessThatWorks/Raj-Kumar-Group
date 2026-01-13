# Copyright (c) 2025, rkg and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
import os
import csv
import re
from frappe.utils import get_site_path, getdate, date_diff, now_datetime, time_diff_in_hours
from datetime import datetime as dt, timedelta


@frappe.whitelist()
def process_excel_file_for_preview(file_url):
	try:
		if not file_url:
			return {"error": "No file attached"}
		
		if file_url.startswith('/files/'):
			file_path = get_site_path('public', file_url[1:])
		elif file_url.startswith('/private/files/'):
			file_path = get_site_path('private', 'files', file_url.split('/')[-1])
		else:
			file_path = get_site_path('public', 'files', file_url)
		
		if not os.path.exists(file_path):
			return {"error": f"File not found: {file_path}"}
		
		file_ext = os.path.splitext(file_path)[1].lower()
		rows = []
		
		if file_ext == '.csv':
			with open(file_path, 'r', encoding='utf-8-sig') as f:
				reader = csv.DictReader(f)
				rows = list(reader)
		elif file_ext in ['.xlsx', '.xls']:
			try:
				import pandas as pd
				df = pd.read_excel(file_path)
				rows = df.to_dict('records')
			except ImportError:
				return {"error": "pandas library is required for Excel files. Please install it or use CSV format."}
		else:
			return {"error": "Unsupported file format. Please upload CSV or Excel file."}
		
		if not rows:
			return {"error": "No data found in the file."}
		
		doc = frappe.new_doc("Battery and Key Upload")
		doc.excel_file = file_url
		
		column_map = doc.normalize_columns([col for col in rows[0].keys()] if rows else [])
		child_table_data = []
		
		for idx, row in enumerate(rows, start=1):
			frame_no = doc.get_value(row, column_map, ['frame_no', 'frame no', 'frame number', 'serial_no', 'serial no'])
			key_no = doc.get_value(row, column_map, ['key_no', 'key no', 'key number'])
			battery_serial_no = doc.get_value(row, column_map, [
				'battery_serial_no', 'battery serial no', 'sample battery serial no',
				'battery_no', 'battery no', 'battery number'
			])
			battery_brand = doc.get_value(row, column_map, ['battery_brand', 'battery brand', 'brand'])
			battery_type = doc.get_value(row, column_map, ['battery_type', 'battery type', 'type', 'batery type'])
			sample_charging_date = doc.get_value(row, column_map, [
				'sample_charging_date', 'sample charging date', 'sample battery charging date'
			])
			charging_date_str = doc.get_value(row, column_map, ['charging_date', 'charging date'])
			if not charging_date_str and sample_charging_date:
				charging_date_str = sample_charging_date
			charging_date = doc.parse_date(charging_date_str) if charging_date_str else None
			
			if not frame_no:
				child_table_data.append({
					'frame_no': '', 'key_no': key_no or '', 'battery_serial_no': battery_serial_no or '',
					'battery_brand': battery_brand or '', 'battery_type': battery_type or '',
					'sample_charging_date': sample_charging_date or '', 'charging_date': charging_date, 'item_code': ''
				})
				continue
			
			serial_no = doc.find_serial_no(frame_no)
			item_code = frappe.db.get_value('Serial No', serial_no, 'item_code') or '' if serial_no else ''
			display_frame_no = serial_no if serial_no else frame_no
			
			child_table_data.append({
				'frame_no': display_frame_no, 'key_no': key_no or '', 'battery_serial_no': battery_serial_no or '',
				'battery_brand': battery_brand or '', 'battery_type': battery_type or '',
				'sample_charging_date': sample_charging_date or '', 'charging_date': charging_date, 'item_code': item_code
			})
		
		return {"child_table_data": child_table_data}
	except Exception as e:
		return {"error": f"Error processing file: {str(e)}"}


@frappe.whitelist()
def check_frame_age(frame_no, date):
	try:
		if not frame_no:
			return {"error": "Frame No is required"}
		
		if not date:
			return {"error": "Date is required"}
		
		frame_no = str(frame_no).strip()
		check_date = getdate(date)
		
		frame_bundle_name = None
		if frappe.db.exists("Frame Bundle", frame_no):
			frame_bundle_name = frame_no
		else:
			frame_bundle_name = frappe.db.get_value("Frame Bundle", {"frame_no": frame_no}, "name")
		
		if not frame_bundle_name:
			return {"error": f"Frame Bundle not found for frame_no: {frame_no}"}
		
		frame_bundle = frappe.get_doc("Frame Bundle", frame_bundle_name)
		battery_serial_no = frame_bundle.get("battery_serial_no")
		
		if not battery_serial_no:
			return {
				"time_difference_hours": 0,
				"default_time_hours": 0
			}
		
		if not frappe.db.exists("Battery Information", battery_serial_no):
			return {"error": f"Battery Information not found: {battery_serial_no}"}
		
		battery_info = frappe.get_doc("Battery Information", battery_serial_no)
		
		if battery_info.get("charging_date"):
			battery_date = getdate(battery_info.charging_date)
		else:
			battery_date = getdate(battery_info.creation)
		
		battery_datetime = dt.combine(battery_date, dt.min.time())
		check_datetime = dt.combine(check_date, dt.min.time())
		time_diff = check_datetime - battery_datetime
		time_diff_hours = abs(time_diff.total_seconds() / 3600)
		default_time_hours = frappe.db.get_single_value("RKG Settings", "battery_entry_default_time") or 0
		
		return {
			"time_difference_hours": time_diff_hours,
			"default_time_hours": default_time_hours
		}
	except Exception as e:
		return {"error": f"Error checking frame age: {str(e)}"}


class BatteryandKeyUpload(Document):
    def before_insert(self):
        if self.upload_items:
            self.check_48_hour_limit_and_block()
    
    def validate(self):
        if self.has_value_changed("excel_file"):
            self.upload_items = []
        if self.upload_items:
            self.check_48_hour_limit_and_block()

    def before_submit(self):
        if self.upload_items:
            self.check_48_hour_limit_and_block()
        if not self.excel_file:
            frappe.throw(_("No file attached"))

    def on_submit(self):
        try:
            self.process_excel_file()
            self.check_and_send_notification()
        except Exception as e:
            frappe.throw(_("Error processing file: {0}").format(str(e)))

    def on_cancel(self):
        if self.upload_items:
            for item in self.upload_items:
                if item.frame_no:
                    frappe.db.set_value("Battery Key Upload Item", item.name, "frame_no", None, update_modified=False)
            frappe.db.commit()

    def process_excel_file(self):
        file_path = self.get_file_path()
        if not os.path.exists(file_path):
            frappe.throw(_("File not found: {0}").format(file_path))

        file_ext = os.path.splitext(file_path)[1].lower()
        rows = []

        if file_ext == '.csv':
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        elif file_ext in ['.xlsx', '.xls']:
            try:
                import pandas as pd
                df = pd.read_excel(file_path)
                rows = df.to_dict('records')
            except ImportError:
                frappe.throw(_("pandas library is required for Excel files. Please install it or use CSV format."))
        else:
            frappe.throw(_("Unsupported file format. Please upload CSV or Excel file."))

        if not rows:
            frappe.throw(_("No data found in the file."))

        column_map = self.normalize_columns([col for col in rows[0].keys()] if rows else [])

        child_table_data = []
        total_errors = 0

        for idx, row in enumerate(rows, start=1):
            frame_no = self.get_value(row, column_map, ['frame_no', 'frame no', 'frame number', 'serial_no', 'serial no'])
            key_no = self.get_value(row, column_map, ['key_no', 'key no', 'key number'])
            battery_serial_no = self.get_value(row, column_map, [
                'battery_serial_no', 'battery serial no', 'sample battery serial no',
                'battery_no', 'battery no', 'battery number'
            ])
            battery_brand = self.get_value(row, column_map, ['battery_brand', 'battery brand', 'brand'])
            battery_type = self.get_value(row, column_map, ['battery_type', 'battery type', 'type', 'batery type'])
            sample_charging_date = self.get_value(row, column_map, [
                'sample_charging_date', 'sample charging date', 'sample battery charging date'
            ])
            charging_date_str = self.get_value(row, column_map, ['charging_date', 'charging date'])
            if not charging_date_str and sample_charging_date:
                charging_date_str = sample_charging_date
            charging_date = self.parse_date(charging_date_str) if charging_date_str else None

            if not frame_no:
                total_errors += 1
                child_table_data.append({
                    'frame_no': '', 'key_no': '', 'battery_serial_no': '', 'battery_brand': '',
                    'battery_type': '', 'sample_charging_date': '', 'charging_date': None, 'item_code': ''
                })
                continue

            serial_no = self.find_serial_no(frame_no)

            if not serial_no:
                total_errors += 1
                child_table_data.append({
                    'frame_no': frame_no, 'key_no': key_no or '', 'battery_serial_no': battery_serial_no or '',
                    'battery_brand': battery_brand or '', 'battery_type': battery_type or '',
                    'sample_charging_date': sample_charging_date or '', 'charging_date': charging_date, 'item_code': ''
                })
                continue

            try:
                battery_info_name = None
                if battery_serial_no:
                    battery_info_name = self.create_or_update_battery_information(
                        battery_serial_no=battery_serial_no,
                        battery_brand=battery_brand,
                        battery_type=battery_type,
                        sample_charging_date=sample_charging_date,
                        charging_date=charging_date
                    )

                actual_frame_no = frappe.db.get_value('Serial No', serial_no, 'serial_no') or serial_no
                item_code = frappe.db.get_value('Serial No', serial_no, 'item_code') or ''
                self.create_frame_bundle(
                    frame_no=actual_frame_no,
                    item_code=item_code,
                    battery_serial_no=battery_info_name,
                    key_number=key_no
                )

                child_table_data.append({
                    'frame_no': serial_no, 'key_no': key_no or '', 'battery_serial_no': battery_serial_no or '',
                    'battery_brand': battery_brand or '', 'battery_type': battery_type or '',
                    'sample_charging_date': sample_charging_date or '', 'charging_date': charging_date, 'item_code': item_code
                })
            except Exception as e:
                total_errors += 1
                child_table_data.append({
                    'frame_no': serial_no, 'key_no': key_no or '', 'battery_serial_no': battery_serial_no or '',
                    'battery_brand': battery_brand or '', 'battery_type': battery_type or '',
                    'sample_charging_date': sample_charging_date or '', 'charging_date': charging_date, 'item_code': ''
                })

        self.upload_items = []
        for row_data in child_table_data:
            child_row = self.append("upload_items", {})
            child_row.frame_no = row_data.get("frame_no") or ""
            child_row.key_no = row_data.get("key_no") or ""
            child_row.battery_serial_no = row_data.get("battery_serial_no") or ""
            child_row.battery_brand = row_data.get("battery_brand") or ""
            child_row.battery_type = row_data.get("battery_type") or ""
            child_row.sample_charging_date = row_data.get("sample_charging_date") or ""
            child_row.charging_date = row_data.get("charging_date")
            child_row.item_code = row_data.get("item_code") or ""

        frappe.db.commit()

    def get_file_path(self):
        file_url = self.excel_file
        if file_url.startswith('/files/'):
            return get_site_path('public', file_url[1:])
        elif file_url.startswith('/private/files/'):
            return get_site_path('private', 'files', file_url.split('/')[-1])
        else:
            return get_site_path('public', 'files', file_url)

    def normalize_columns(self, columns):
        column_map = {}
        for col in columns:
            if not col:
                continue
            normalized = str(col).lower().strip().replace('.', '').replace('_', ' ').replace('-', ' ')
            normalized = ' '.join(normalized.split())
            column_map[normalized] = col
        return column_map

    def get_value(self, row, column_map, possible_names):
        for name in possible_names:
            normalized = name.lower().strip().replace('.', '').replace('_', ' ').replace('-', ' ')
            normalized = ' '.join(normalized.split())
            if normalized in column_map:
                original_col = column_map[normalized]
                value = row.get(original_col)
                if value is not None:
                    if isinstance(value, float):
                        import math
                        if math.isnan(value):
                            continue
                    value_str = str(value).strip()
                    if value_str:
                        return value_str
        return None

    def parse_date(self, date_value):
        if not date_value:
            return None
        if hasattr(date_value, 'strftime'):
            return date_value
        date_str = str(date_value).strip()
        if not date_str:
            return None
        try:
            return getdate(date_str)
        except:
            try:
                match = re.match(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
                if match:
                    part1, part2, year = match.groups()
                    if int(part1) > 12:
                        day, month = part1, part2
                    else:
                        month, day = part1, part2
                    return getdate(f"{year}-{month.zfill(2)}-{day.zfill(2)}")
                match = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
                if match:
                    year, month, day = match.groups()
                    return getdate(f"{year}-{month.zfill(2)}-{day.zfill(2)}")
            except:
                pass
        return None

    def find_serial_no(self, frame_no):
        if not frame_no:
            return None
        frame_no = str(frame_no).strip()
        serial_no = frappe.db.get_value("Serial No", {"serial_no": frame_no}, "name")
        if serial_no:
            return str(serial_no).strip()
        if frappe.db.exists("Serial No", frame_no):
            return str(frame_no).strip()
        return None

    def create_or_update_battery_information(self, battery_serial_no=None, battery_brand=None, 
                                             battery_type=None, sample_charging_date=None, charging_date=None):
        if not battery_serial_no or not str(battery_serial_no).strip():
            return None
        battery_serial_no = str(battery_serial_no).strip()
        parsed_charging_date = charging_date if hasattr(charging_date, 'strftime') else getdate(charging_date) if charging_date else None

        existing = frappe.db.get_value("Battery Information", {"battery_serial_no": battery_serial_no}, "name")
        if existing:
            update_fields = {}
            if battery_brand: update_fields["battery_brand"] = str(battery_brand).strip()
            if battery_type: update_fields["battery_type"] = str(battery_type).strip()
            if sample_charging_date: update_fields["sample_charging_date"] = str(sample_charging_date).strip()
            if parsed_charging_date: update_fields["charging_date"] = parsed_charging_date
            if update_fields:
                frappe.db.set_value("Battery Information", existing, update_fields, update_modified=False)
                frappe.db.commit()
            return existing
        else:
            try:
                doc = frappe.get_doc({
                    "doctype": "Battery Information",
                    "battery_serial_no": battery_serial_no,
                    "battery_brand": str(battery_brand).strip() if battery_brand else "",
                    "battery_type": str(battery_type).strip() if battery_type else "",
                    "sample_charging_date": str(sample_charging_date).strip() if sample_charging_date else "",
                    "charging_date": parsed_charging_date
                })
                doc.insert(ignore_permissions=True)
                doc.submit()
                frappe.db.commit()
                return doc.name
            except Exception as e:
                return None

    def create_frame_bundle(self, frame_no=None, item_code=None, battery_serial_no=None, key_number=None):
        if not frame_no:
            return None
        actual_frame_no = str(frame_no).strip()
        
        if frappe.db.exists("Frame Bundle", actual_frame_no):
            return actual_frame_no
        
        existing_by_field = frappe.db.get_value("Frame Bundle", {"frame_no": actual_frame_no}, "name")
        if existing_by_field:
            return existing_by_field
        
        try:
            doc = frappe.get_doc({
                "doctype": "Frame Bundle",
                "frame_no": actual_frame_no,
                "item_code": str(item_code).strip() if item_code else "",
                "battery_serial_no": battery_serial_no if (battery_serial_no and frappe.db.exists("Battery Information", battery_serial_no)) else None,
                "key_number": str(key_number).strip() if key_number else None
            })
            
            doc.insert(ignore_permissions=True)
            
            if not doc.name or doc.name != actual_frame_no:
                existing = frappe.db.get_value("Frame Bundle", {"frame_no": actual_frame_no}, "name")
                if existing:
                    return existing
                return None
            
            doc.submit()
            frappe.db.commit()
            
            if not frappe.db.exists("Frame Bundle", doc.name):
                existing = frappe.db.get_value("Frame Bundle", {"frame_no": actual_frame_no}, "name")
                if existing:
                    return existing
                return None
            
            return doc.name
        except frappe.DuplicateEntryError:
            existing = frappe.db.get_value("Frame Bundle", {"frame_no": actual_frame_no}, "name")
            if existing:
                return existing
            return None
        except Exception as e:
            existing = frappe.db.get_value("Frame Bundle", {"frame_no": actual_frame_no}, "name")
            if existing:
                return existing
            return None

    def check_and_send_notification(self):
        if not self.upload_items:
            return
        
        notification_email = frappe.db.get_single_value("RKG Settings", "notification_email")
        if not notification_email:
            return
        
        frame_count = 0
        for item in self.upload_items:
            if item.frame_no:
                frame_count += 1
        
        if frame_count > 0:
            self.send_notification_email(notification_email, frame_count)

    def send_notification_email(self, notification_email, frame_count):
        try:
            email_list = [email.strip() for email in notification_email.split(',') if email.strip()]
            if not email_list:
                return
            
            subject = "Battery & Key Upload Notification"
            message = f"Battery and Key Upload is being done against {frame_count} frames"
            
            frappe.sendmail(
                recipients=email_list,
                subject=subject,
                message=message,
                now=True
            )
        except Exception as e:
            pass

    def check_48_hour_limit_and_block(self):
        if not self.upload_items:
            return
        
        overdue_frames = []
        
        for item in self.upload_items:
            if not item.frame_no:
                continue
            
            frame_no = str(item.frame_no).strip()
            
            purchase_receipt_info = frappe.db.sql("""
                SELECT 
                    pr.name as purchase_receipt_name,
                    pr.creation as pr_creation_date
                FROM `tabPurchase Receipt` pr
                INNER JOIN `tabPurchase Receipt Item` pri ON pr.name = pri.parent
                WHERE (pri.serial_no = %s OR FIND_IN_SET(%s, pri.serial_no) > 0)
                    AND pr.docstatus = 1
                ORDER BY pr.creation DESC
                LIMIT 1
            """, (frame_no, frame_no), as_dict=True)
            
            if not purchase_receipt_info:
                continue
            
            pr_info = purchase_receipt_info[0]
            pr_creation = pr_info['pr_creation_date']
            hours_passed = time_diff_in_hours(now_datetime(), pr_creation)
            
            if hours_passed > 48:
                overdue_frames.append({
                    'frame_no': frame_no,
                    'purchase_receipt': pr_info['purchase_receipt_name'],
                    'hours_passed': round(hours_passed, 2),
                    'pr_creation_date': pr_creation
                })
        
        if overdue_frames:
            self.send_48_hour_limit_exceeded_notification(overdue_frames)
            
            frame_count = len(overdue_frames)
            if frame_count == 1:
                error_message = _("Cannot upload battery numbers. Frame {frame_no} exceeds 48-hour limit from Purchase Receipt creation. Email notification sent to supervisor.").format(
                    frame_no=overdue_frames[0]['frame_no']
                )
            else:
                error_message = _("Cannot upload battery numbers. {count} frame(s) exceed the 48-hour limit from Purchase Receipt creation. Email notification sent to supervisor.").format(
                    count=frame_count
                )
            
            frappe.throw(error_message, title=_("48-Hour Upload Limit Exceeded"))

    def send_48_hour_limit_exceeded_notification(self, overdue_frames):
        try:
            notification_email = frappe.db.get_single_value("RKG Settings", "notification_email")
            if not notification_email:
                return
            
            email_list = [email.strip() for email in notification_email.split(',') if email.strip()]
            if not email_list:
                return
            
            subject = "Battery & Key Upload Blocked - 48 Hour Limit Exceeded"
            message = f"Battery and Key Upload was blocked because the following frames exceed the 48-hour limit from Purchase Receipt creation:\n\n"
            
            for idx, frame_info in enumerate(overdue_frames[:20], 1):
                message += f"{idx}. Frame No: {frame_info['frame_no']}\n"
                message += f"   Purchase Receipt: {frame_info['purchase_receipt']}\n"
                message += f"   PR Created: {frame_info['pr_creation_date']}\n"
                message += f"   Hours Passed: {frame_info['hours_passed']} hours\n\n"
            
            if len(overdue_frames) > 20:
                message += f"... and {len(overdue_frames) - 20} more frame(s).\n\n"
            
            message += "Please review and take appropriate action."
            
            frappe.sendmail(
                recipients=email_list,
                subject=subject,
                message=message,
                now=True
            )
        except Exception as e:
            pass
