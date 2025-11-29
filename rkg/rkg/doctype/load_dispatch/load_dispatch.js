// Copyright (c) 2025, beetashoke.chakraborty@clapgrow.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Load Dispatch", {
	refresh(frm) {

	},

	load_dispatch_file_attach(frm) {
		// Event listener for when CSV file is attached
		if (frm.doc.load_dispatch_file_attach) {
			frappe.show_alert({
				message: __("Processing CSV file..."),
				indicator: "blue"
			}, 3);

			// Call server method to extract CSV data
			frappe.call({
				method: "rkg.rkg.doctype.load_dispatch.load_dispatch.process_csv_file",
				args: {
					file_url: frm.doc.load_dispatch_file_attach
				},
				callback: function(r) {
					if (r.message) {
						// Clear existing items
						frm.clear_table("items");
						
						// Add rows from CSV data
						if (r.message.length > 0) {
							r.message.forEach(function(row) {
								let child_row = frm.add_child("items");
								// Set values directly on the child row object
								Object.keys(row).forEach(function(key) {
									child_row[key] = row[key];
								});
							});
							
							frm.refresh_field("items");
							
							// Map values from first imported row to parent fields
							const first_row = r.message[0] || {};
							if (first_row.load_reference_no) {
								frm.set_value("load_reference_no", first_row.load_reference_no);
							}
							if (first_row.invoice_no) {
								frm.set_value("invoice_no", first_row.invoice_no);
							}
							
							frappe.show_alert({
								message: __("Successfully imported {0} rows from CSV", [r.message.length]),
								indicator: "green"
							}, 5);
						} else {
							frappe.show_alert({
								message: __("No data found in CSV file"),
								indicator: "orange"
							}, 5);
						}
					}
				},
				error: function(r) {
					frappe.show_alert({
						message: __("Error processing CSV file: {0}", [r.message || "Unknown error"]),
						indicator: "red"
					}, 5);
				}
			});
		}
	},

	import_data_from_file(frm) {
		// Button click handler for manual import
		if (!frm.doc.load_dispatch_file_attach) {
			frappe.msgprint(__("Please attach a CSV file first"));
			return;
		}
		
		// Trigger the same logic as file attachment
		frm.trigger("load_dispatch_file_attach");
	}
});
