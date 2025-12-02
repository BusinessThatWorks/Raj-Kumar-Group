// Copyright (c) 2025, beetashoke.chakraborty@clapgrow.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Load Dispatch", {
	refresh(frm) {
		// Calculate total dispatch quantity on refresh
		calculate_total_dispatch_quantity(frm);
		// Store original load_reference_no for change detection (only if not already set from CSV)
		if (frm.doc.load_reference_no && !frm._load_reference_no_from_csv) {
			frm._original_load_reference_no = frm.doc.load_reference_no;
		}
		
		// Show item_code field - it will be populated on save
		if (frm.fields_dict.items && frm.fields_dict.items.grid) {
			// Always show the field (it will be populated from mtoc on save)
			frm.fields_dict.items.grid.update_docfield_property("item_code", "hidden", false);
		}
		if(frm.doc.docstatus==1){
			frm.add_custom_button(__("Purchase Order"),frm.cscript["Create Purchase Order"], __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));
			frm.add_custom_button(__("Purchase Receipt"),frm.cscript["Create Purchase Receipt"], __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));
			frm.add_custom_button(__("Purchase Invoice"),frm.cscript["Create Purchase Invoice"], __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));						
		}
	},

	load_reference_no(frm) {
		// Prevent changing load_reference_no if items are already imported from CSV
		if (frm.doc.items && frm.doc.items.length > 0) {
			// Check if any item has frame_no (imported data)
			const has_imported_items = frm.doc.items.some(item => item.frame_no && item.frame_no.trim() !== "");
			
			if (has_imported_items && frm._load_reference_no_from_csv) {
				// If user tries to change from the CSV value, block it
				if (frm.doc.load_reference_no !== frm._load_reference_no_from_csv) {
					frappe.msgprint({
						title: __("Cannot Change Load Reference Number"),
						message: __("Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported from CSV. The CSV data belongs to Load Reference Number '{0}'. Please clear all items first or use a CSV file that matches the desired Load Reference Number.", 
							[frm._load_reference_no_from_csv, frm.doc.load_reference_no]),
						indicator: "red"
					});
					// Revert to the CSV value
					frm.set_value("load_reference_no", frm._load_reference_no_from_csv);
					return;
				}
			}
		}
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
					file_url: frm.doc.load_dispatch_file_attach,
					selected_load_reference_no: frm.doc.load_reference_no || null
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
								// Note: item_code will be populated from mtoc on save
							});
							
							frm.refresh_field("items");
							
							// Map values from first imported row to parent fields
							const first_row = r.message[0] || {};
							if (first_row.load_reference_no) {
								// Store the load_reference_no from CSV to prevent changes (set before updating field)
								frm._load_reference_no_from_csv = first_row.load_reference_no;
								frm.set_value("load_reference_no", first_row.load_reference_no);
							}
							if (first_row.invoice_no) {
								frm.set_value("invoice_no", first_row.invoice_no);
							}
							
							// Recalculate total dispatch quantity after import
							calculate_total_dispatch_quantity(frm);
							
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
	},

});

// Calculate total dispatch quantity by counting rows with frame_no
function calculate_total_dispatch_quantity(frm) {
	let total_dispatch_quantity = 0;
	if (frm.doc.items) {
		frm.doc.items.forEach(function(item) {
			// Count rows that have a non-empty frame_no
			if (item.frame_no && item.frame_no.trim() !== "") {
				total_dispatch_quantity += 1;
			}
		});
	}
	frm.set_value("total_dispatch_quantity", total_dispatch_quantity);
}

// Recalculate when frame_no changes in child table
frappe.ui.form.on("Load Dispatch Item", {
	frame_no: function(frm) {
		calculate_total_dispatch_quantity(frm);
	},
	items_remove: function(frm) {
		calculate_total_dispatch_quantity(frm);
		// Reset CSV load_reference_no flag if all items are cleared
		// This allows user to change load_reference_no after clearing items
		if (!frm.doc.items || frm.doc.items.length === 0) {
			frm._load_reference_no_from_csv = null;
			frm._original_load_reference_no = frm.doc.load_reference_no;
		}
	}
});
cur_frm.cscript["Create Purchase Order"] = function(){
	frappe.model.open_mapped_doc({
		method: "rkg.rkg.doctype.load_dispatch.load_dispatch.create_purchase_order",
		frm: cur_frm
	});
}

cur_frm.cscript["Create Purchase Receipt"] = function(){
	frappe.model.open_mapped_doc({
		method: "rkg.rkg.doctype.load_dispatch.load_dispatch.create_purchase_receipt",
		frm: cur_frm
	});
}

cur_frm.cscript["Create Purchase Invoice"] = function(){
	frappe.model.open_mapped_doc({
		method: "rkg.rkg.doctype.load_dispatch.load_dispatch.create_purchase_invoice",
		frm: cur_frm
	});
}