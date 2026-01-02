frappe.ui.form.on("Battery Transaction", {
	refresh(frm) {
		// Show/hide fields based on transaction type
		if (frm.doc.transaction_type === "In") {
			frm.set_df_property("battery_file_attach", "reqd", 0);
			frm.set_df_property("items", "hidden", 0);
			frm.set_df_property("battery_serial_no", "hidden", 1);
			if (frm.doc.items) {
				calculate_total_quantity(frm);
			}
		} else if (frm.doc.transaction_type === "Out") {
			frm.set_df_property("battery_file_attach", "hidden", 1);
			frm.set_df_property("items", "hidden", 1);
			frm.set_df_property("battery_serial_no", "hidden", 0);
			
			// Set query filter for battery_serial_no to show only "In Stock" Battery Details
			if (frm.fields_dict.battery_serial_no) {
				frm.set_query("battery_serial_no", function() {
					return {
						filters: {
							status: "In Stock"
						}
					};
				});
			}
		}
	},

	transaction_type(frm) {
		// Reset fields when transaction type changes
		if (frm.doc.transaction_type === "In") {
			frm.set_value("battery_serial_no", "");
			frm.set_value("battery_brand_out", "");
			frm.set_value("battery_type_out", "");
			frm.set_value("frame_no_out", "");
			frm.set_value("battery_charging_code_out", "");
			frm.set_value("charging_date_out", "");
		} else if (frm.doc.transaction_type === "Out") {
			frm.clear_table("items");
			frm.set_value("battery_file_attach", "");
		}
		frm.refresh();
	},

	battery_serial_no(frm) {
		// For Out transactions, fetch and populate Battery Details
		if (frm.doc.transaction_type === "Out" && frm.doc.battery_serial_no) {
			frappe.call({
				method: "rkg.rkg.doctype.battery_transaction.battery_transaction.get_battery_details_for_out",
				args: {
					battery_details_name: frm.doc.battery_serial_no
				},
				callback: function(r) {
					if (r && r.message) {
						const details = r.message;
						
						// Check for errors
						if (details.error) {
							frappe.msgprint({
								title: __("Error"),
								message: details.error,
								indicator: "red"
							});
							// Clear fields on error
							frm.set_value("battery_brand_out", "");
							frm.set_value("battery_type_out", "");
							frm.set_value("frame_no_out", "");
							frm.set_value("battery_charging_code_out", "");
							frm.set_value("charging_date_out", "");
							return;
						}
						
						// Auto-populate fields
						frm.set_value("battery_brand_out", details.battery_brand || "");
						frm.set_value("battery_type_out", details.battery_type || "");
						frm.set_value("frame_no_out", details.frame_no || "");
						frm.set_value("battery_charging_code_out", details.battery_charging_code || "");
						frm.set_value("charging_date_out", details.charging_date || "");
						
						frappe.show_alert({
							message: __("Battery Details loaded successfully"),
							indicator: "green"
						}, 3);
					} else {
						frappe.msgprint({
							title: __("Not Found"),
							message: __("No Battery Details found."),
							indicator: "orange"
						});
						// Clear fields if not found
						frm.set_value("battery_brand_out", "");
						frm.set_value("battery_type_out", "");
						frm.set_value("frame_no_out", "");
						frm.set_value("battery_charging_code_out", "");
						frm.set_value("charging_date_out", "");
					}
				}
			});
		} else if (frm.doc.transaction_type === "Out") {
			// Clear fields if battery_serial_no is cleared
			frm.set_value("battery_brand_out", "");
			frm.set_value("battery_type_out", "");
			frm.set_value("frame_no_out", "");
			frm.set_value("battery_charging_code_out", "");
			frm.set_value("charging_date_out", "");
		}
	},

	battery_file_attach(frm) {
		// Only process file for In transactions
		if (frm.doc.transaction_type !== "In") {
			return;
		}
		if (frm.doc.battery_file_attach) {
			frappe.show_alert({
				message: __("Processing file..."),
				indicator: "blue"
			}, 3);

			frappe.call({
				method: "rkg.rkg.doctype.battery_transaction.battery_transaction.process_battery_file",
				args: {
					file_url: frm.doc.battery_file_attach
				},
				callback: function(r) {
					try {
						if (r && r.message) {
							const response = r.message;
							const rows = response.rows || (Array.isArray(response) ? response : []);
							
							frm.clear_table("items");
							
							if (rows.length > 0) {
								rows.forEach(function(row) {
									let child_row = frm.add_child("items");
									
									// Set all fields from the row
									Object.keys(row).forEach(function(key) {
										child_row[key] = row[key];
									});
								});
								
								frm.refresh_field("items");
								calculate_total_quantity(frm);
								
								frappe.show_alert({
									message: __("Successfully imported {0} row(s)", [rows.length]),
									indicator: "green"
								}, 5);
							} else {
								frappe.show_alert({
									message: __("No data found in file"),
									indicator: "orange"
								}, 5);
							}
						}
					} catch (error) {
						console.error("Error processing file:", error);
						frappe.show_alert({
							message: __("Error processing file: {0}", [error.message || "Unknown error"]),
							indicator: "red"
						}, 5);
					}
				},
				error: function(r) {
					frappe.show_alert({
						message: __("Error processing file: {0}", [r.message || "Unknown error"]),
						indicator: "red"
					}, 5);
				}
			});
		}
	}
});

function calculate_total_quantity(frm) {
	let total = 0;
	if (frm.doc.items) {
		frm.doc.items.forEach(function(item) {
			if (item.battery_serial_no && item.battery_serial_no.trim() !== "") {
				total += 1;
			}
		});
	}
	frm.set_value("total_battery_quantity", total);
}

frappe.ui.form.on("Battery Item", {
	battery_serial_no: function(frm, cdt, cdn) {
		calculate_total_quantity(frm);
		
		// Auto-populate fields from Battery Details when selected
		let row = locals[cdt][cdn];
		if (row.battery_serial_no && frm.doc.transaction_type === "In") {
			frappe.call({
				method: "rkg.rkg.doctype.battery_transaction.battery_transaction.get_battery_details_for_out",
				args: {
					battery_details_name: row.battery_serial_no
				},
				callback: function(r) {
					if (r && r.message && !r.message.error) {
						const details = r.message;
						// Update child row fields
						frappe.model.set_value(cdt, cdn, "battery_brand", details.battery_brand || "");
						frappe.model.set_value(cdt, cdn, "battery_type", details.battery_type || "");
						frappe.model.set_value(cdt, cdn, "battery_charging_code", details.battery_charging_code || "");
						frappe.model.set_value(cdt, cdn, "charging_date", details.charging_date || "");
						frm.refresh_field("items");
					}
				}
			});
		}
	},
	
	items_remove: function(frm) {
		calculate_total_quantity(frm);
	}
});

// Add get_query for battery_serial_no in Battery Item child table
frappe.ui.form.on("Battery Transaction", {
	refresh: function(frm) {
		// Set query filter for battery_serial_no in child table to show only "In Stock" Battery Details
		if (frm.doc.transaction_type === "In") {
			frm.set_query("battery_serial_no", "items", function() {
				return {
					filters: {
						"status": "In Stock"
					}
				};
			});
		}
	}
});
