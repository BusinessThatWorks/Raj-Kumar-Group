// Copyright (c) 2026, beetashoke.chakraborty@clapgrow.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Frame Bundle", {
	refresh(frm) {
		// Refresh battery aging for submitted documents to show current value
		// Check discard_history to determine if battery is expired (is_battery_expired is a Button field)
		const is_expired = frm.doc.discard_history && frm.doc.discard_history.length > 0;
		if (frm.doc.name && frm.doc.docstatus === 1 && !is_expired) {
			frappe.call({
				method: "rkg.rkg.doctype.frame_bundle.frame_bundle.refresh_battery_aging",
				args: {
					frame_name: frm.doc.name
				},
				callback: function(r) {
					if (r.message && r.message.success) {
						// Update the field value in the form
						frm.set_value("battery_aging_days", r.message.battery_aging_days);
					}
				},
				error: function() {
					// Silently fail - aging will show last calculated value
				}
			});
		}
		
		// Update battery_serial_no read-only state
		update_battery_serial_no_readonly(frm);
		// Show/hide discarded history section
		update_discarded_history_visibility(frm);
		// Make Swap History child table read-only and system-controlled
		make_swap_history_readonly(frm);
		// Make Discard History child table read-only and system-controlled
		make_discard_history_readonly(frm);
		// Handle is_battery_expired button visibility and action
		setup_battery_expired_button(frm);
		// Add Swap Battery button for saved documents
		if (frm.doc.name) {
			frm.add_custom_button(__("Swap Battery"), function() {
				show_swap_battery_dialog(frm);
			});
		}
	},

	onload(frm) {
		// Battery aging is calculated by backend - no client-side calculation needed
		// Update battery_serial_no read-only state
		update_battery_serial_no_readonly(frm);
		// Show/hide discarded history section
		update_discarded_history_visibility(frm);
		// Make Swap History child table read-only and system-controlled
		make_swap_history_readonly(frm);
		// Make Discard History child table read-only and system-controlled
		make_discard_history_readonly(frm);
		// Handle is_battery_expired button visibility and action
		setup_battery_expired_button(frm);
	},

	swap_history(frm) {
		// Ensure Swap History remains read-only when rows are added
		make_swap_history_readonly(frm);
	},

	discard_history(frm) {
		// Ensure Discard History remains read-only when rows are added
		make_discard_history_readonly(frm);
	},

	battery_serial_no(frm) {
		// Update battery_type when battery_serial_no changes
		if (frm.doc.battery_serial_no) {
			frappe.db.get_value("Battery Information", frm.doc.battery_serial_no, "battery_type", (r) => {
				if (r && r.battery_type) {
					frm.set_value("battery_type", r.battery_type);
				} else {
					frm.set_value("battery_type", "");
				}
			});
		} else {
			frm.set_value("battery_type", "");
		}
	},

	frame_no(frm) {
		// Update warehouse when frame_no changes
		if (frm.doc.frame_no) {
			// First try to find Serial No by serial_no field
			frappe.db.get_value("Serial No", {"serial_no": frm.doc.frame_no}, "warehouse", (r) => {
				if (r && r.warehouse) {
					frm.set_value("warehouse", r.warehouse);
				} else {
					// Try checking if frame_no exists as Serial No name
					frappe.db.get_value("Serial No", frm.doc.frame_no, "warehouse", (r2) => {
						if (r2 && r2.warehouse) {
							frm.set_value("warehouse", r2.warehouse);
						} else {
							frm.set_value("warehouse", "");
						}
					});
				}
			});
		} else {
			frm.set_value("warehouse", "");
		}
	}
});

// Battery aging calculation removed - backend is now the single source of truth
// The calculate_battery_aging() function in frame_bundle.py handles all aging calculations
// based on battery_installed_on field, not document creation date

function update_battery_serial_no_readonly(frm) {
	// Make battery_serial_no read-only when battery is expired
	// Check discard_history since is_battery_expired is a Button field (doesn't store values)
	const is_expired = frm.doc.discard_history && frm.doc.discard_history.length > 0;
	if (is_expired) {
		frm.set_df_property("battery_serial_no", "read_only", 1);
	} else {
		frm.set_df_property("battery_serial_no", "read_only", 0);
	}
}

function update_discarded_history_visibility(frm) {
	// Show/hide discarded history section based on discard_history table
	if (frm.doc.discard_history && frm.doc.discard_history.length > 0) {
		frm.set_df_property("section_break_discarded_history", "hidden", 0);
	} else {
		frm.set_df_property("section_break_discarded_history", "hidden", 1);
	}
}

function setup_battery_expired_button(frm) {
	// Hide button if already discarded (action already performed)
	// Check discard_history table instead of discarded_date field
	if (frm.doc.discard_history && frm.doc.discard_history.length > 0) {
		frm.set_df_property("is_battery_expired", "hidden", 1);
		return;
	}
	
	// Show button if not discarded and document is saved
	if (!frm.doc.name) {
		frm.set_df_property("is_battery_expired", "hidden", 1);
		return;
	}
	
	frm.set_df_property("is_battery_expired", "hidden", 0);
	
	// Add click handler for the button field
	// In Frappe, Button fields are rendered as buttons and we handle clicks on the wrapper
	let button_wrapper = frm.fields_dict.is_battery_expired.$wrapper;
	if (button_wrapper) {
		// Remove any existing handlers to avoid duplicates
		button_wrapper.off("click");
		
		// Add click handler
		button_wrapper.on("click", function(e) {
			e.preventDefault();
			e.stopPropagation();
			
			// UI safety: Check if already discarded (additional UI safety)
			// Check discard_history table instead of discarded_date field
			if (frm.doc.discard_history && frm.doc.discard_history.length > 0) {
				frappe.msgprint(__("Battery has already been marked as discarded."));
				return;
			}
			
			// Find the button element
			let button = button_wrapper.find("button, .btn, [type='button']").first();
			
			// Check if button is disabled (already processing)
			if (button.prop("disabled")) {
				return;
			}
			
			// Confirm action
			frappe.confirm(
				__("Are you sure you want to mark this battery as discarded? This action cannot be undone."),
				function() {
					// Disable button to prevent double-click
					button.prop("disabled", true);
					
					// Call server method
					frappe.call({
						method: "rkg.rkg.doctype.frame_bundle.frame_bundle.mark_battery_expired",
						args: {
							frame_name: frm.doc.name
						},
						freeze: true,
						freeze_message: __("Marking battery as discarded..."),
						callback: function(r) {
							if (r.message && r.message.error) {
								// Re-enable button on error
								button.prop("disabled", false);
								frappe.msgprint(__("Error: {0}", [r.message.error]));
							} else {
								// Success - reload document to show updated state
								frappe.show_alert({
									message: __("Battery marked as discarded successfully"),
									indicator: "green"
								}, 3);
								frm.reload_doc();
							}
						},
						error: function(r) {
							// Re-enable button on error
							button.prop("disabled", false);
						}
					});
				}
			);
		});
	}
}

function make_swap_history_readonly(frm) {
	// Make Swap History child table read-only and system-controlled
	frm.set_df_property("swap_history", "read_only", 1);
	
	// Get the grid and disable add/delete/edit
	let grid = frm.get_field("swap_history").grid;
	if (grid) {
		grid.cannot_add_rows = true;
		grid.cannot_delete_rows = true;
		// Make all existing rows non-editable
		if (grid.grid_rows) {
			grid.grid_rows.forEach(function(row) {
				row.toggle_editable(false);
			});
		}
		// Prevent new rows from being added
		grid.wrapper.find(".grid-add-row").hide();
	}
}

function make_discard_history_readonly(frm) {
	// Make Discard History child table read-only and system-controlled
	frm.set_df_property("discard_history", "read_only", 1);
	
	// Get the grid and disable add/delete/edit
	let grid = frm.get_field("discard_history").grid;
	if (grid) {
		grid.cannot_add_rows = true;
		grid.cannot_delete_rows = true;
		// Make all existing rows non-editable
		if (grid.grid_rows) {
			grid.grid_rows.forEach(function(row) {
				row.toggle_editable(false);
			});
		}
		// Prevent new rows from being added
		grid.wrapper.find(".grid-add-row").hide();
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
