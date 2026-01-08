// Copyright (c) 2026, beetashoke.chakraborty@clapgrow.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Frame Bundle", {
	refresh(frm) {
		// Calculate battery aging days from creation date
		calculate_battery_aging(frm);
		// Update battery_serial_no read-only state
		update_battery_serial_no_readonly(frm);
		// Show/hide discarded history section
		update_discarded_history_visibility(frm);
		// Add Swap Battery button for saved documents
		if (frm.doc.name) {
			frm.add_custom_button(__("Swap Battery"), function() {
				show_swap_battery_dialog(frm);
			});
		}
	},

	onload(frm) {
		// Calculate aging when form loads
		calculate_battery_aging(frm);
		// Update battery_serial_no read-only state
		update_battery_serial_no_readonly(frm);
		// Show/hide discarded history section
		update_discarded_history_visibility(frm);
	},

	is_battery_expired(frm) {
		// Make battery_serial_no read-only when is_battery_expired is checked
		update_battery_serial_no_readonly(frm);
		// Show/hide discarded history section
		update_discarded_history_visibility(frm);
		// Update discarded history when checked
		if (frm.doc.is_battery_expired && !frm.is_new()) {
			update_discarded_history(frm);
		}
	}
});

function calculate_battery_aging(frm) {
	if (frm.doc.creation) {
		// Extract date part from creation datetime (format: YYYY-MM-DD HH:mm:ss.ssssss)
		const creation_date = frm.doc.creation.split(' ')[0];
		const today = frappe.datetime.get_today();
		
		// Calculate difference in days using moment.js
		const diff_days = moment(today).diff(moment(creation_date), 'days');
		
		// Update the field (ensure non-negative)
		frm.set_value("battery_aging_days", diff_days >= 0 ? diff_days : 0);
	} else if (frm.is_new()) {
		// For new documents, set to 0
		frm.set_value("battery_aging_days", 0);
	}
}

function update_battery_serial_no_readonly(frm) {
	// Make battery_serial_no read-only when is_battery_expired is checked
	if (frm.doc.is_battery_expired) {
		frm.set_df_property("battery_serial_no", "read_only", 1);
	} else {
		frm.set_df_property("battery_serial_no", "read_only", 0);
	}
}

function update_discarded_history_visibility(frm) {
	// Show/hide discarded history section based on checkbox
	if (frm.doc.is_battery_expired) {
		frm.set_df_property("section_break_discarded_history", "hidden", 0);
	} else {
		frm.set_df_property("section_break_discarded_history", "hidden", 1);
	}
}

function update_discarded_history(frm) {
	// Update discarded history fields when battery is marked as discarded
	if (frm.doc.is_battery_expired && !frm.doc.discarded_date) {
		frm.set_value("discarded_date", frappe.datetime.now_datetime());
		frm.set_value("discarded_by", frappe.user.name);
		frm.set_value("discarded_battery_serial_no", frm.doc.battery_serial_no || "");
	}
}

function show_swap_battery_dialog(frm) {
	let d = new frappe.ui.Dialog({
		title: __("Swap Battery"),
		fields: [
			{
				fieldtype: "Section Break",
				label: __("Current Frame")
			},
			{
				fieldtype: "Data",
				fieldname: "current_frame_no",
				label: __("Frame No"),
				default: frm.doc.frame_no,
				read_only: 1
			},
			{
				fieldtype: "Link",
				fieldname: "current_battery",
				label: __("Battery Serial No"),
				options: "Battery Information",
				default: frm.doc.battery_serial_no,
				read_only: 1
			},
			{
				fieldtype: "Section Break",
				label: __("Target Frame")
			},
			{
				fieldtype: "Link",
				fieldname: "target_frame",
				label: __("Select Frame"),
				options: "Frame Bundle",
				get_query: function() {
					return {
						filters: {
							name: ["!=", frm.doc.name]
						}
					};
				},
				onchange: function() {
					let target_frame = d.get_value("target_frame");
					if (target_frame) {
						frappe.call({
							method: "rkg.rkg.doctype.frame_bundle.frame_bundle.get_frame_battery",
							args: {
								frame_name: target_frame
							},
							callback: function(r) {
								if (r.message) {
									d.set_value("target_battery", r.message.battery_serial_no || "");
								}
							}
						});
					} else {
						d.set_value("target_battery", "");
					}
				},
				reqd: 1
			},
			{
				fieldtype: "Link",
				fieldname: "target_battery",
				label: __("Target Battery Serial No"),
				options: "Battery Information",
				read_only: 1
			}
		],
		primary_action_label: __("Swap"),
		primary_action(values) {
			if (!values.target_frame) {
				frappe.msgprint(__("Please select a frame"));
				return;
			}
			if (values.target_frame === frm.doc.name) {
				frappe.msgprint(__("Cannot swap with the same frame"));
				return;
			}
			frappe.confirm(
				__("Swap batteries with the selected frame?"),
				function() {
					swap_batteries(frm, values.target_frame);
					d.hide();
				}
			);
		}
	});

	d.show();
}

function swap_batteries(frm, target_frame) {
	frappe.call({
		method: "rkg.rkg.doctype.frame_bundle.frame_bundle.swap_batteries",
		args: {
			current_frame: frm.doc.name,
			target_frame: target_frame
		},
		freeze: true,
		freeze_message: __("Swapping batteries..."),
		callback: function(r) {
			if (r.message && r.message.error) {
				frappe.msgprint(__("Error: {0}", [r.message.error]));
			} else {
				frappe.msgprint(__("Batteries swapped successfully"));
				frm.reload_doc();
			}
		}
	});
}
