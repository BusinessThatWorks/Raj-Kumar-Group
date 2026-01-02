frappe.ui.form.on("Battery Details", {
	battery_swapping(frm) {
		if (!frm.doc.battery_swapping) {
			frm.set_value("new_frame_number", "");
		}
	},

	charging_date(frm) {
		if (frm.doc.charging_date) {
			frappe.call({
				method: "rkg.rkg.doctype.battery_details.battery_details.calculate_expiry_date",
				args: {
					charging_date: frm.doc.charging_date
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value("battery_expiry_date", r.message);
					}
				}
			});
		} else {
			frm.set_value("battery_expiry_date", "");
		}
	},

	new_frame_number(frm) {
		if (frm.doc.new_frame_number) {
			frm.set_value("frame_no", frm.doc.new_frame_number);
			
			if (frm.doc.battery_swapping && frm.doc.battery_serial_no) {
				frappe.call({
					method: "rkg.rkg.doctype.battery_details.battery_details.update_serial_no_battery_no",
					args: {
						serial_no: frm.doc.new_frame_number,
						battery_serial_no: frm.doc.battery_serial_no
					},
					callback: function(r) {
						if (r.exc) {
							frappe.show_alert({
								message: __("Failed to update Serial No"),
								indicator: "red"
							}, 3);
						}
					}
				});
			}
		}
	}
});

