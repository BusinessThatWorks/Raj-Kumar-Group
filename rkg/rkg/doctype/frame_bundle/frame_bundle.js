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
						// Update visual indicators
						update_battery_aging_indicator(frm);
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
		// Update battery aging visual indicator
		update_battery_aging_indicator(frm);
		// Add Swap Battery button for saved documents
		if (frm.doc.name && !is_expired) {
			frm.add_custom_button(__("Swap Battery"), function() {
				show_swap_battery_dialog(frm);
			}, __("Actions"));
		}
		
		// Add visual styling to sections
		add_section_styling(frm);
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
				// Update visual indicators after battery change
				setTimeout(() => {
					update_battery_aging_indicator(frm);
				}, 500);
			});
		} else {
			frm.set_value("battery_type", "");
		}
	},
	
	battery_aging_days(frm) {
		// Update visual indicator when aging days change
		update_battery_aging_indicator(frm);
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
				fieldtype: "HTML",
				options: `<div style="margin-bottom: 15px; padding: 12px; background: #f8f9fa; border-left: 4px solid #1ab394; border-radius: 4px;">
					<h5 style="margin: 0 0 5px 0; color: #1ab394;">Current Frame</h5>
					<p style="margin: 0; color: #666; font-size: 12px;">Frame and battery information that will be swapped</p>
				</div>`
			},
			{
				fieldtype: "Data",
				fieldname: "current_frame_no",
				label: __("Frame No"),
				default: frm.doc.frame_no,
				read_only: 1,
				description: __("Current frame number")
			},
			{
				fieldtype: "Link",
				fieldname: "current_battery",
				label: __("Battery Serial No"),
				options: "Battery Information",
				default: frm.doc.battery_serial_no,
				read_only: 1,
				description: __("Current battery serial number")
			},
			{
				fieldtype: "Data",
				fieldname: "current_battery_type",
				label: __("Battery Type"),
				default: frm.doc.battery_type || __("Not Set"),
				read_only: 1,
				description: __("Current battery type")
			},
			{
				fieldtype: "Column Break"
			},
			{
				fieldtype: "HTML",
				options: `<div style="margin-bottom: 15px; padding: 12px; background: #fff3cd; border-left: 4px solid #f8ac59; border-radius: 4px;">
					<h5 style="margin: 0 0 5px 0; color: #f8ac59;">Target Frame</h5>
					<p style="margin: 0; color: #666; font-size: 12px;">Select the frame to swap batteries with</p>
				</div>`
			},
			{
				fieldtype: "Link",
				fieldname: "target_frame",
				label: __("Select Frame"),
				options: "Frame Bundle",
				get_query: function() {
					return {
						filters: {
							name: ["!=", frm.doc.name],
							docstatus: 1
						}
					};
				},
				description: __("Select the target frame to swap batteries with"),
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
									// Set battery type from response
									if (r.message.battery_type) {
										d.set_value("target_battery_type", r.message.battery_type);
									} else {
										d.set_value("target_battery_type", __("Not Set"));
									}
									// Check if types match and show visual indicator
									check_battery_types_match(frm, d);
								}
							}
						});
					} else {
						d.set_value("target_battery", "");
						d.set_value("target_battery_type", "");
					}
				},
				reqd: 1
			},
			{
				fieldtype: "Link",
				fieldname: "target_battery",
				label: __("Target Battery Serial No"),
				options: "Battery Information",
				read_only: 1,
				description: __("Target frame's current battery")
			},
			{
				fieldtype: "Data",
				fieldname: "target_battery_type",
				label: __("Battery Type"),
				read_only: 1,
				description: __("Target frame's battery type")
			},
			{
				fieldtype: "HTML",
				fieldname: "type_match_indicator",
				options: `<div id="type-match-indicator" style="margin-top: 10px; padding: 10px; border-radius: 4px; display: none;"></div>`
			}
		],
		primary_action_label: __("Swap Batteries"),
		primary_action(values) {
			if (!values.target_frame) {
				frappe.msgprint(__("Please select a frame"));
				return;
			}
			if (values.target_frame === frm.doc.name) {
				frappe.msgprint(__("Cannot swap with the same frame"));
				return;
			}
			
			// Check if battery types match
			let current_type = frm.doc.battery_type || "";
			let target_type = values.target_battery_type || "";
			
			// Validate that battery types match (required)
			if (current_type && target_type) {
				if (current_type !== target_type) {
					frappe.msgprint({
						title: __("Battery Types Do Not Match"),
						message: __("Battery types must match to perform a swap.<br><br>") +
								__("Current Frame: {0} ({1})<br>", [frm.doc.frame_no || frm.doc.name, current_type]) +
								__("Target Frame: {0} ({1})<br><br>", [values.target_frame, target_type]) +
								__("Please select a frame with the same battery type."),
						indicator: "red"
					});
					return;
				}
			} else if (!current_type || !target_type) {
				// If either battery type is missing, warn the user
				frappe.msgprint({
					title: __("Battery Type Missing"),
					message: __("Cannot swap - battery type information is missing for one or both frames. Please ensure both frames have valid battery types."),
					indicator: "red"
				});
				return;
			}
			
			// Types match - proceed with swap
			frappe.confirm(
				__("Swap batteries with the selected frame?"),
				function() {
					swap_batteries(frm, values.target_frame, false);
					d.hide();
				}
			);
		}
	});

	d.show();
	
	// Check types match on dialog open if values are already set
	setTimeout(() => {
		check_battery_types_match(frm, d);
	}, 500);
}

function check_battery_types_match(frm, dialog) {
	// Check if battery types match and show visual indicator
	const current_type = frm.doc.battery_type || "";
	const target_type = dialog.get_value("target_battery_type") || "";
	const indicator = dialog.$wrapper.find("#type-match-indicator");
	
	if (!current_type || !target_type) {
		indicator.hide();
		return;
	}
	
	if (current_type === target_type) {
		indicator.css({
			'background': '#d4edda',
			'border-left': '4px solid #28a745',
			'color': '#155724'
		}).html(`
			<strong>✓ Types Match</strong><br>
			<small>Both frames have battery type: <strong>${current_type}</strong></small>
		`).show();
	} else {
		indicator.css({
			'background': '#f8d7da',
			'border-left': '4px solid #dc3545',
			'color': '#721c24'
		}).html(`
			<strong>✗ Types Do Not Match</strong><br>
			<small>Current: <strong>${current_type}</strong> | Target: <strong>${target_type}</strong></small><br>
			<small style="color: #856404;">Swap will be blocked - battery types must match.</small>
		`).show();
	}
}

function swap_batteries(frm, target_frame, force_swap = false) {
	frappe.call({
		method: "rkg.rkg.doctype.frame_bundle.frame_bundle.swap_batteries",
		args: {
			current_frame: frm.doc.name,
			target_frame: target_frame,
			force_swap: force_swap || false
		},
		freeze: true,
		freeze_message: __("Swapping batteries..."),
		callback: function(r) {
			if (r.message && r.message.error) {
				frappe.msgprint({
					title: __("Error"),
					message: __("Error: {0}", [r.message.error]),
					indicator: "red"
				});
			} else {
				frappe.show_alert({
					message: __("Batteries swapped successfully"),
					indicator: "green"
				}, 3);
				frm.reload_doc();
			}
		}
	});
}

function update_battery_aging_indicator(frm) {
	// Add visual indicator based on battery aging days
	const aging_days = frm.doc.battery_aging_days || 0;
	const aging_field = frm.fields_dict.battery_aging_days;
	
	if (!aging_field) return;
	
	// Remove existing badges/indicators
	aging_field.$wrapper.find('.battery-aging-badge').remove();
	
	// Determine color and status based on aging days
	let color_class = "default";
	let status_text = "";
	let indicator_color = "";
	
	if (aging_days <= 60) {
		color_class = "success";
		status_text = "Good";
		indicator_color = "green";
	} else if (aging_days <= 90) {
		color_class = "warning";
		status_text = "Attention";
		indicator_color = "orange";
	} else if (aging_days <= 120) {
		color_class = "danger";
		status_text = "Critical";
		indicator_color = "red";
	} else {
		color_class = "danger";
		status_text = "Expired";
		indicator_color = "red";
	}
	
	// Add visual badge/indicator (only show if not "Good" status)
	if (aging_days >= 0 && status_text !== "Good") {
		const badge = $(`
			<span class="badge badge-${color_class} battery-aging-badge" 
				  style="margin-left: 8px; font-size: 11px; padding: 4px 8px;">
				<span class="indicator ${indicator_color}" style="margin-right: 4px;"></span>
				${status_text}
			</span>
		`);
		aging_field.$wrapper.find('.control-input-wrapper').append(badge);
	}
}

function add_section_styling(frm) {
	// Add custom styling to sections for better visual hierarchy
	setTimeout(() => {
		// Style Frame Information section
		const frameSection = frm.fields_dict.section_break_frame_info;
		if (frameSection && frameSection.$wrapper) {
			frameSection.$wrapper.css({
				'border-left': '3px solid #1ab394',
				'padding-left': '10px',
				'margin-bottom': '15px'
			});
		}
		
		// Style Battery Details section
		const batterySection = frm.fields_dict.section_break_battery_details;
		if (batterySection && batterySection.$wrapper) {
			batterySection.$wrapper.css({
				'border-left': '3px solid #f8ac59',
				'padding-left': '10px',
				'margin-bottom': '15px',
				'margin-top': '20px'
			});
		}
		
		// Style Battery Actions section
		const actionsSection = frm.fields_dict.section_break_battery_actions;
		if (actionsSection && actionsSection.$wrapper) {
			actionsSection.$wrapper.css({
				'border-left': '3px solid #ed5565',
				'padding-left': '10px',
				'margin-bottom': '15px',
				'margin-top': '20px'
			});
		}
	}, 500);
}
