// Copyright (c) 2026, beetashoke.chakraborty@clapgrow.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Battery Information", {
	refresh(frm) {
		// Add custom buttons or actions if needed
		if (frm.doc.battery_serial_no) {
			frm.set_df_property("battery_serial_no", "read_only", 1);
		}
	},

	battery_serial_no(frm) {
		// Auto-format or validate serial number if needed
		if (frm.doc.battery_serial_no) {
			frm.doc.battery_serial_no = frm.doc.battery_serial_no.trim().toUpperCase();
			frm.refresh_field("battery_serial_no");
		}
	},

	charging_date(frm) {
		// Auto-populate sample_charging_date if charging_date is set and sample_charging_date is empty
		if (frm.doc.charging_date && !frm.doc.sample_charging_date) {
			frm.set_value("sample_charging_date", frappe.datetime.str_to_user(frm.doc.charging_date));
		}
	}
});
