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
							frm.clear_table("items");
							
							if (r.message.length > 0) {
								r.message.forEach(function(row) {
									let child_row = frm.add_child("items");
									
									// Skip item_code - will be set on submit
									Object.keys(row).forEach(function(key) {
										if (key !== 'item_code') {
											child_row[key] = row[key];
										}
									});
									
									// Calculate item_name
									if (row.battery_brand && row.battery_type) {
										child_row.item_name = `${row.battery_brand} ${row.battery_type}`;
									}
								});
								
								frm.refresh_field("items");
								calculate_total_quantity(frm);
								
								frappe.show_alert({
									message: __("Successfully imported {0} rows", [r.message.length]),
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

