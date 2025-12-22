frappe.ui.form.on("Load Dispatch", {
	refresh(frm) {
		// Calculate total dispatch quantity on refresh
		calculate_total_dispatch_quantity(frm);
		// Store original load_reference_no for change detection (only if not already set from CSV)
		if (frm.doc.load_reference_no && !frm._load_reference_no_from_csv) {
			frm._original_load_reference_no = frm.doc.load_reference_no;
		}
		
		// Add custom CSS stylesheet if not already added
		if (!$('#load-dispatch-custom-styles').length) {
			$('<style id="load-dispatch-custom-styles">')
				.text(`
					/* Custom styling for Load Dispatch Item fields */
					[data-fieldname="print_name"] input,
					[data-fieldname="print_name"] .control-value,
					[data-fieldname="print_name"] .grid-value,
					td[data-fieldname="print_name"] input,
					td[data-fieldname="print_name"] .control-value {
						font-size: 14px !important;
						color: #2e7d32 !important;
					}
					
					[data-fieldname="rate"] input,
					[data-fieldname="rate"] .control-value,
					[data-fieldname="rate"] .grid-value,
					td[data-fieldname="rate"] input,
					td[data-fieldname="rate"] .control-value {
						font-size: 14px !important;
						color: #2e7d32 !important;
					}
				`)
				.appendTo('head');
		}
		
		// Show item_code field - it will be populated on save
		if (frm.fields_dict.items && frm.fields_dict.items.grid) {
			// Always show the field (it will be populated from model_serial_no on save)
			frm.fields_dict.items.grid.update_docfield_property("item_code", "hidden", false);
			
			// Apply custom styling to print_name and rate fields in child table
			apply_custom_field_styling(frm);
		}
		if(frm.doc.docstatus==1){
			// Check if Purchase Receipt or Purchase Invoice already exists
			frappe.call({
				method: "rkg.rkg.doctype.load_dispatch.load_dispatch.check_existing_documents",
				args: {
					load_dispatch_name: frm.doc.name
				},
				callback: function(r) {
					if (r.message) {
						const has_pr = r.message.has_purchase_receipt || false;
						const has_pi = r.message.has_purchase_invoice || false;
						
						// Only show Purchase Receipt button if no Purchase Receipt exists
						if (!has_pr) {
							frm.add_custom_button(__("Purchase Receipt"),frm.cscript["Create Purchase Receipt"], __("Create"));
							frm.page.set_inner_btn_group_as_primary(__("Create"));
						}
						
						// Only show Purchase Invoice button if no Purchase Invoice exists
						if (!has_pi) {
							frm.add_custom_button(__("Purchase Invoice"),frm.cscript["Create Purchase Invoice"], __("Create"));
							frm.page.set_inner_btn_group_as_primary(__("Create"));
						}
						
						// Show message if documents already exist
						if (has_pr || has_pi) {
							let message = __("Cannot create additional documents. ");
							if (has_pr && has_pi) {
								message += __("Purchase Receipt and Purchase Invoice already exist for this Load Dispatch.");
							} else if (has_pr) {
								message += __("Purchase Receipt already exists for this Load Dispatch.");
							} else if (has_pi) {
								message += __("Purchase Invoice already exists for this Load Dispatch.");
							}
							
							frappe.show_alert({
								message: message,
								indicator: "orange"
							}, 5);
						}
					}
				}
			});
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
		// Event listener for when spreadsheet/CSV file is attached
		if (frm.doc.load_dispatch_file_attach) {
			frappe.show_alert({
				message: __("Processing attached file..."),
				indicator: "blue"
			}, 3);

			// Call server method to extract tabular data row-wise
			frappe.call({
				method: "rkg.rkg.doctype.load_dispatch.load_dispatch.process_tabular_file",
				args: {
					file_url: frm.doc.load_dispatch_file_attach,
					selected_load_reference_no: frm.doc.load_reference_no || null
				},
				callback: function(r) {
					try {
						if (r && r.message) {
							// Clear existing items
							frm.clear_table("items");
							
							// Add rows from imported data
							if (r.message.length > 0) {
								r.message.forEach(function(row) {
									let child_row = frm.add_child("items");
									Object.keys(row).forEach(function(key) {
										child_row[key] = row[key];
									});
									// Set item_code from model_serial_no if available
									// Item will be created on save if it doesn't exist
									if (row.model_serial_no && row.model_serial_no.trim()) {
										child_row.item_code = row.model_serial_no.trim();
									}
									// Calculate rate from price_unit (excluding 18% GST)
									if (row.price_unit) {
										const price_unit = flt(row.price_unit);
										if (price_unit > 0) {
											child_row.rate = price_unit / 1.18;
										}
									}
								});
								
								frm.refresh_field("items");
								
								// Apply custom styling to print_name and rate fields after import
								setTimeout(() => apply_custom_field_styling(frm), 200);
								
								// Map values from first imported row to parent fields
								const first_row = r.message[0] || {};
								if (first_row.hmsi_load_reference_no) {
									// Store the load_reference_no from the file to prevent changes
									frm._load_reference_no_from_csv = first_row.hmsi_load_reference_no;
									// Check if field exists before setting
									if (frm.fields_dict.load_reference_no) {
										frm.set_value("load_reference_no", first_row.hmsi_load_reference_no);
									} else {
										// Fallback: set directly on doc if field not yet available
										frm.doc.load_reference_no = first_row.hmsi_load_reference_no;
									}
								}
								if (first_row.invoice_no) {
									// Check if field exists before setting
									if (frm.fields_dict.invoice_no) {
										frm.set_value("invoice_no", first_row.invoice_no);
									} else {
										// Fallback: set directly on doc if field not yet available
										frm.doc.invoice_no = first_row.invoice_no;
									}
								}
								
								// Recalculate total dispatch quantity after import
								calculate_total_dispatch_quantity(frm);
								
								frappe.show_alert({
									message: __("Successfully imported {0} rows from file", [r.message.length]),
									indicator: "green"
								}, 5);
							} else {
								frappe.show_alert({
									message: __("No data found in attached file"),
									indicator: "orange"
								}, 5);
							}
						} else {
							frappe.show_alert({
								message: __("Unexpected response format from server"),
								indicator: "orange"
							}, 5);
						}
					} catch (error) {
						console.error("Error processing CSV import:", error);
						frappe.show_alert({
							message: __("Error processing imported data: {0}", [error.message || "Unknown error"]),
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

// Apply custom CSS styling to print_name and rate fields in child table
// Note: CSS stylesheet is added in refresh() function, this function ensures styling is applied after grid renders
function apply_custom_field_styling(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	
	const grid = frm.fields_dict.items.grid;
	
	// Function to force re-application of styles (CSS should handle most of it, but this ensures it works)
	const ensureStyling = function() {
		// The CSS stylesheet should handle styling, but we can add classes or force style if needed
		$(grid.wrapper).find('[data-fieldname="print_name"]').addClass('custom-print-name');
		$(grid.wrapper).find('[data-fieldname="rate"]').addClass('custom-rate');
	};
	
	// Apply with delays to catch grid rendering at different stages
	setTimeout(ensureStyling, 100);
	setTimeout(ensureStyling, 300);
	setTimeout(ensureStyling, 500);
	
	// Apply styling when grid is refreshed/re-rendered
	if (grid.wrapper) {
		grid.wrapper.on('render', function() {
			setTimeout(ensureStyling, 100);
		});
	}
	
	// Use MutationObserver to watch for DOM changes in the grid
	if (typeof MutationObserver !== 'undefined' && grid.wrapper && grid.wrapper[0]) {
		const observer = new MutationObserver(function(mutations) {
			ensureStyling();
		});
		
		observer.observe(grid.wrapper[0], {
			childList: true,
			subtree: true,
			attributes: true,
			attributeFilter: ['class', 'data-fieldname']
		});
	}
}

// Recalculate when frame_no changes in child table
frappe.ui.form.on("Load Dispatch Item", {
	frame_no: function(frm) {
		calculate_total_dispatch_quantity(frm);
	},
	price_unit: function(frm, cdt, cdn) {
		// Calculate rate from price_unit (excluding 18% GST)
		// rate = price_unit / 1.18 (standard GST exclusion formula)
		// Note: price_unit remains unchanged, only rate is calculated
		let row = locals[cdt][cdn];
		if (row.price_unit) {
			const price_unit = flt(row.price_unit);
			if (price_unit > 0) {
				// Always calculate rate by excluding 18% GST from price_unit
				// price_unit value is preserved as-is from Excel
				row.rate = price_unit / 1.18;
				frm.refresh_field("rate", row.name, "items");
			} else {
				// Clear rate if price_unit is 0 or negative
				row.rate = 0;
				frm.refresh_field("rate", row.name, "items");
			}
		} else {
			// Clear rate if price_unit is empty
			row.rate = 0;
			frm.refresh_field("rate", row.name, "items");
		}
		// Reapply styling after rate field refresh
		setTimeout(() => apply_custom_field_styling(frm), 50);
	},
	model_serial_no: function(frm, cdt, cdn) {
		// Set item_code from model_serial_no and calculate print_name when model_serial_no changes
		let row = locals[cdt][cdn];
		if (row.model_serial_no) {
			// Set item_code from model_serial_no (Item will be created on save if it doesn't exist)
			const item_code = row.model_serial_no.trim();
			row.item_code = item_code;
			frm.refresh_field("item_code", row.name, "items");
			
			// Calculate print_name from model_name and model_serial_no
			row.print_name = calculate_print_name_from_model_serial(row.model_serial_no, row.model_name);
			frm.refresh_field("print_name", row.name, "items");
		} else {
			// Clear item_code if model_serial_no is cleared
			row.item_code = "";
			frm.refresh_field("item_code", row.name, "items");
		}
		// Reapply styling after field refresh
		setTimeout(() => apply_custom_field_styling(frm), 50);
	},
	model_name: function(frm, cdt, cdn) {
		// Recalculate print_name when model_name changes
		let row = locals[cdt][cdn];
		if (row.model_serial_no) {
			row.print_name = calculate_print_name_from_model_serial(row.model_serial_no, row.model_name);
			frm.refresh_field("print_name", row.name, "items");
		}
		// Reapply styling after field refresh
		setTimeout(() => apply_custom_field_styling(frm), 50);
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

// Helper function to calculate print_name from model_name and model_serial_no (client-side)
function calculate_print_name_from_model_serial(model_serial_no, model_name) {
	if (!model_serial_no) {
		return "";
	}
	
	model_serial_no = String(model_serial_no).trim();
	if (!model_serial_no) {
		return "";
	}
	
	// Extract Model Serial Number part up to "-ID" (including "-ID")
	// Search for "-ID" pattern (case-insensitive)
	const model_serial_upper = model_serial_no.toUpperCase();
	let id_index = model_serial_upper.indexOf("-ID");
	
	let serial_part;
	if (id_index !== -1) {
		// Take everything up to and including "-ID"
		// Add 3 to include "-ID" (3 characters)
		serial_part = model_serial_no.substring(0, id_index + 3);
	} else {
		// If "-ID" not found, try to find "ID" (without dash) and take up to it
		id_index = model_serial_upper.indexOf("ID");
		if (id_index !== -1) {
			// Take everything up to "ID" and add "-ID"
			serial_part = model_serial_no.substring(0, id_index) + "-ID";
		} else {
			// If "ID" not found at all, use the whole model_serial_no
			serial_part = model_serial_no;
		}
	}
	
	// Build the result: Model Name + (Serial Part) + (BS-VI)
	if (model_name) {
		model_name = String(model_name).trim();
		if (model_name) {
			return `${model_name} (${serial_part}) (BS-VI)`;
		}
	}
	
	// If no model_name, just use serial_part
	return `${serial_part} (BS-VI)`;
}

cur_frm.cscript["Create Purchase Receipt"] = function(){
	show_frame_warehouse_dialog(cur_frm, "Purchase Receipt");
}

cur_frm.cscript["Create Purchase Invoice"] = function(){
	show_frame_warehouse_dialog(cur_frm, "Purchase Invoice");
}

// Function to show dialog for selecting Warehouse
function show_frame_warehouse_dialog(frm, doc_type) {
	// Get all frame numbers from items
	const frame_numbers = [];
	if (frm.doc.items && frm.doc.items.length > 0) {
		frm.doc.items.forEach(function(item) {
			if (item.frame_no && item.frame_no.trim() !== "") {
				// Avoid duplicates
				if (frame_numbers.indexOf(item.frame_no.trim()) === -1) {
					frame_numbers.push(item.frame_no.trim());
				}
			}
		});
	}
	
	// Check if there are any frame numbers
	if (frame_numbers.length === 0) {
		frappe.msgprint({
			title: __("No Frame Numbers Found"),
			message: __("Please add items with Frame Numbers before creating {0}.", [doc_type]),
			indicator: "orange"
		});
		return;
	}
	
	// Show simple dialog with just warehouse selection
	const dialog = new frappe.ui.Dialog({
		title: __("Select Warehouse"),
		fields: [
			{
				label: __("Warehouse"),
				fieldname: "warehouse",
				fieldtype: "Link",
				options: "Warehouse",
				reqd: 1,
				get_query: function() {
					return {
						filters: {}
					};
				}
			},
			{
				fieldtype: "Section Break",
				label: __("Frames Information")
			},
			{
				fieldname: "frames_info",
				fieldtype: "HTML",
				options: `<div style="padding: 10px; background-color: #f8f9fa; border-radius: 4px;">
					<p style="margin: 0;"><strong>${__("Total Frames")}:</strong> ${frame_numbers.length}</p>
					<p style="margin: 5px 0 0 0; font-size: 12px; color: #666;">
						<em>${__("All frames will be assigned to the selected warehouse.")}</em>
					</p>
				</div>`
			}
		],
		primary_action_label: __("Create"),
		primary_action: function(values) {
			if (!values.warehouse) {
				frappe.msgprint({
					title: __("Validation Error"),
					message: __("Please select a warehouse."),
					indicator: "orange"
				});
				return;
			}
			
			dialog.hide();
			
			// Create mapping for all frames with the selected warehouse
			const mapping = frame_numbers.map(function(frame_no) {
				return {
					frame_no: frame_no,
					warehouse: values.warehouse
				};
			});
			
			// Call the appropriate creation method with mapping
			const method_name = doc_type === "Purchase Receipt" 
				? "rkg.rkg.doctype.load_dispatch.load_dispatch.create_purchase_receipt"
				: "rkg.rkg.doctype.load_dispatch.load_dispatch.create_purchase_invoice";
			
			frappe.call({
				method: method_name,
				args: {
					source_name: frm.doc.name,
					frame_warehouse_mapping: mapping
				},
				callback: function(r) {
					if (r.message && r.message.name) {
						// Open the created document
						frappe.set_route("Form", doc_type, r.message.name);
					} else if (r.message) {
						// If response is the doc object, try to get name
						const doc_name = r.message.name || (r.message.doc && r.message.doc.name);
						if (doc_name) {
							frappe.set_route("Form", doc_type, doc_name);
						} else {
							frappe.msgprint({
								title: __("Success"),
								message: __("{0} created successfully.", [doc_type]),
								indicator: "green"
							});
							frm.reload_doc();
						}
					}
				},
				error: function(r) {
					frappe.msgprint({
						title: __("Error"),
						message: r.message || __("An error occurred while creating {0}.", [doc_type]),
						indicator: "red"
					});
				}
			});
		}
	});
	
	dialog.show();
}