frappe.ui.form.on("Battery", {
	refresh(frm) {
		calculate_total_quantity(frm);
	},

	battery_file_attach(frm) {
		if (frm.doc.battery_file_attach) {
			frappe.show_alert({
				message: __("Processing file..."),
				indicator: "blue"
			}, 3);

			frappe.call({
				method: "rkg.rkg.doctype.battery.battery.process_battery_file",
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
									
									// Set all fields except internal flags
									Object.keys(row).forEach(function(key) {
										if (key !== 'item_exists' && key !== 'item_code') {
											child_row[key] = row[key];
										}
									});
									
									// Set item_code if item already exists
									if (row.item_exists && row.item_code) {
										child_row.item_code = row.item_code;
									}
									
									// Calculate item_name
									if (row.battery_brand && row.battery_type) {
										child_row.item_name = `${row.battery_brand} ${row.battery_type}`;
									}
								});
								
								frm.refresh_field("items");
								calculate_total_quantity(frm);
								
								// Show summary message
								const existing_count = response.existing_count || 0;
								const new_count = response.new_count || rows.length;
								const total_count = rows.length;
								
								let message = __("Successfully imported {0} row(s)", [total_count]);
								let indicator = "green";
								
								if (existing_count > 0) {
									const existing_items = response.existing_items || [];
									let existing_msg = existing_items.slice(0, 10).join(", ");
									if (existing_count > 10) {
										existing_msg += __(" and {0} more", [existing_count - 10]);
									}
									
									message += "\n\n";
									message += __("{0} item(s) already exist and will be skipped on submit: {1}", 
										[existing_count, existing_msg]);
									indicator = "orange";
								}
								
								if (new_count > 0 && existing_count > 0) {
									message += "\n";
									message += __("{0} new item(s) will be created on submit.", [new_count]);
								}
								
								frappe.msgprint({
									message: message,
									title: __("File Import Summary"),
									indicator: indicator,
									alert: true
								});
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
	battery_serial_no: function(frm) {
		calculate_total_quantity(frm);
	},
	
	battery_brand: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.battery_brand && row.battery_type) {
			row.item_name = `${row.battery_brand} ${row.battery_type}`;
			frm.refresh_field("item_name", row.name, "items");
		}
	},
	
	battery_type: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.battery_brand && row.battery_type) {
			row.item_name = `${row.battery_brand} ${row.battery_type}`;
			frm.refresh_field("item_name", row.name, "items");
		}
	},
	
	items_remove: function(frm) {
		calculate_total_quantity(frm);
	}
});

