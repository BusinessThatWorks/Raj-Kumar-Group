frappe.ui.form.on("Battery Swapping", {
	refresh: function(frm) {
		// Set up field visibility and dependencies
		frm.toggle_display("section_break_swap_details", frm.doc.swap_battery);
		frm.toggle_display("new_frame_number", frm.doc.swap_battery);
		frm.toggle_display("new_battery_serial_no", frm.doc.swap_battery);
	},
	
	frame_number: function(frm) {
		// Auto-fetch current battery when frame is selected
		if (frm.doc.frame_number) {
			frappe.call({
				method: "rkg.rkg.doctype.battery_swapping.battery_swapping.get_current_battery",
				args: {
					frame_number: frm.doc.frame_number
				},
				callback: function(r) {
					if (r.message) {
						frm.set_value("current_battery_serial_no", r.message.battery_serial_no || "");
					}
				}
			});
		} else {
			frm.set_value("current_battery_serial_no", "");
		}
	},
	
	swap_battery: function(frm) {
		// Toggle visibility of swap details section
		frm.toggle_display("section_break_swap_details", frm.doc.swap_battery);
		frm.toggle_display("new_frame_number", frm.doc.swap_battery);
		frm.toggle_display("new_battery_serial_no", frm.doc.swap_battery);
		
		// Clear swap fields if swap is unchecked
		if (!frm.doc.swap_battery) {
			frm.set_value("new_frame_number", "");
			frm.set_value("new_battery_serial_no", "");
		}
		
		// Validate that both swap and expired cannot be selected
		if (frm.doc.swap_battery && frm.doc.is_expired) {
			frm.set_value("is_expired", 0);
			frappe.msgprint(__("Cannot swap and expire battery at the same time. Expired checkbox has been unchecked."));
		}
	},
	
	is_expired: function(frm) {
		// Validate that both swap and expired cannot be selected
		if (frm.doc.is_expired && frm.doc.swap_battery) {
			frm.set_value("swap_battery", 0);
			frm.toggle_display("section_break_swap_details", false);
			frm.toggle_display("new_frame_number", false);
			frm.toggle_display("new_battery_serial_no", false);
			frm.set_value("new_frame_number", "");
			frm.set_value("new_battery_serial_no", "");
			frappe.msgprint(__("Cannot swap and expire battery at the same time. Swap checkbox has been unchecked."));
		}
	},
	
	before_save: function(frm) {
		// Validate that at least one action is selected
		if (!frm.doc.swap_battery && !frm.doc.is_expired) {
			frappe.throw(__("Please select either 'Swap Battery' or 'Is Expired'."));
		}
		
		// Validate swap requirements
		if (frm.doc.swap_battery) {
			if (!frm.doc.new_frame_number) {
				frappe.throw(__("New Frame Number is required when Swap Battery is selected."));
			}
			if (!frm.doc.new_battery_serial_no) {
				frappe.throw(__("New Battery Serial No is required when Swap Battery is selected."));
			}
		}
		
		// Validate expired requirements
		if (frm.doc.is_expired) {
			if (!frm.doc.current_battery_serial_no) {
				frappe.throw(__("No battery found in the selected frame. Cannot mark as expired."));
			}
		}
	}
});

