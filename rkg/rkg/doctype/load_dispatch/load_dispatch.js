frappe.ui.form.on("Load Dispatch", {
	refresh(frm) {
		calculate_total_dispatch_quantity(frm);
		if (frm.doc.load_reference_no && !frm._load_reference_no_from_csv) {
			frm._original_load_reference_no = frm.doc.load_reference_no;
		}
		
		// If warehouse is empty but Purchase Receipt exists, sync warehouse from PR
		if (!frm.doc.warehouse && frm.doc.docstatus === 1) {
			frappe.call({
				method: "rkg.rkg.doctype.load_dispatch.load_dispatch.sync_warehouse_from_existing_purchase_receipt",
				args: {
					load_dispatch_name: frm.doc.name
				},
				callback: function(r) {
					if (r.message && r.message.warehouse) {
						// Update the field value and refresh, but don't auto-save
						frm.doc.warehouse = r.message.warehouse;
						frm.refresh_field("warehouse");
					}
				},
				error: function() {
					// Silent fail - don't show error if sync fails
				}
			});
		}
		
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
		
		if (frm.fields_dict.items && frm.fields_dict.items.grid) {
			frm.fields_dict.items.grid.update_docfield_property("item_code", "hidden", false);
			apply_custom_field_styling(frm);
		}
		if (frm.doc.docstatus === 1) {
			frappe.call({
				method: "rkg.rkg.doctype.load_dispatch.load_dispatch.check_existing_documents",
				args: {
					load_dispatch_name: frm.doc.name
				},
				callback: function(r) {
					if (r.message) {
						const has_pr = r.message.has_purchase_receipt || false;
						
						// Only show Purchase Receipt button if no Purchase Receipt exists
						if (!has_pr) {
							frm.add_custom_button(__("Purchase Receipt"), function() {
								create_purchase_receipt_from_load_dispatch(frm);
							}, __("Create"));
							frm.page.set_inner_btn_group_as_primary(__("Create"));
						}
					}
				}
			});
		}
	},

	load_reference_no(frm) {
		if (frm.doc.items && frm.doc.items.length > 0) {
			const has_imported_items = frm.doc.items.some(item => item.frame_no && item.frame_no.trim() !== "");
			
			if (has_imported_items && frm._load_reference_no_from_csv) {
				if (frm.doc.load_reference_no !== frm._load_reference_no_from_csv) {
					frappe.msgprint({
						title: __("Cannot Change Load Reference Number"),
						message: __("Cannot change Load Reference Number from '{0}' to '{1}' because items are already imported from CSV. The CSV data belongs to Load Reference Number '{0}'. Please clear all items first or use a CSV file that matches the desired Load Reference Number.", 
							[frm._load_reference_no_from_csv, frm.doc.load_reference_no]),
						indicator: "red"
					});
					frm.set_value("load_reference_no", frm._load_reference_no_from_csv);
					return;
				}
			}
		}
	},

	load_dispatch_file_attach(frm) {
		if (frm.doc.load_dispatch_file_attach) {
			frappe.show_alert({
				message: __("Processing attached file..."),
				indicator: "blue"
			}, 3);

			frappe.call({
				method: "rkg.rkg.doctype.load_dispatch.load_dispatch.process_tabular_file",
				args: {
					file_url: frm.doc.load_dispatch_file_attach,
					selected_load_reference_no: frm.doc.load_reference_no || null
				},
				callback: function(r) {
					try {
						if (r && r.message) {
							let response_data = r.message;
							let rows = [];
							let has_multiple_load_ref_nos = false;
							let load_ref_nos = [];
							let valid_load_ref_nos = [];
							let invalid_load_ref_nos = [];
							
							if (response_data.rows) {
								rows = response_data.rows;
								has_multiple_load_ref_nos = response_data.has_multiple_load_ref_nos || false;
								load_ref_nos = response_data.load_ref_nos || [];
								valid_load_ref_nos = response_data.valid_load_ref_nos || [];
								invalid_load_ref_nos = response_data.invalid_load_ref_nos || [];
							} else if (Array.isArray(response_data)) {
								rows = response_data;
								const load_ref_nos_set = new Set();
								rows.forEach(row => {
									if (row.hmsi_load_reference_no) {
										load_ref_nos_set.add(row.hmsi_load_reference_no);
									}
								});
								load_ref_nos = Array.from(load_ref_nos_set);
								load_ref_nos.forEach(ref_no => {
									valid_load_ref_nos.push(ref_no);
								});
							} else {
								frappe.show_alert({
									message: __("Unexpected response format from server"),
									indicator: "orange"
								}, 5);
								return;
							}
							
							if (invalid_load_ref_nos.length > 0) {
								frappe.msgprint({
									title: __("Invalid Load Reference Numbers"),
									message: __("The following Load Reference Numbers in the file do not exist as Load Plans and will be skipped:\n{0}\n\nPlease create these Load Plans first or remove them from the file.", 
										[invalid_load_ref_nos.join(", ")]),
									indicator: "orange"
								});
								
								rows = rows.filter(row => {
									const row_load_ref_no = row.hmsi_load_reference_no;
									return !row_load_ref_no || valid_load_ref_nos.includes(row_load_ref_no);
								});
							}
							
							if (rows.length === 0) {
								frappe.msgprint({
									title: __("No Valid Data"),
									message: __("No rows with valid Load Reference Numbers found. Please ensure the Load Reference Numbers in the file exist as Load Plans."),
									indicator: "red"
								});
								return;
							}
							
							if (has_multiple_load_ref_nos && !response_data.filtered && valid_load_ref_nos.length > 1) {
								show_load_ref_no_selection_dialog(frm, valid_load_ref_nos, rows);
								return;
							}
							
							if (valid_load_ref_nos.length === 1) {
								const single_load_ref_no = valid_load_ref_nos[0];
								frappe.call({
									method: "frappe.client.get",
									args: {
										doctype: "Load Plan",
										name: single_load_ref_no
									},
									callback: function(load_plan_r) {
										if (load_plan_r.message) {
											import_rows_to_load_dispatch(frm, rows, single_load_ref_no);
										} else {
											frappe.msgprint({
												title: __("Invalid Load Reference Number"),
												message: __("Load Reference Number '{0}' does not exist as a Load Plan. Please create the Load Plan first.", [single_load_ref_no]),
												indicator: "red"
											});
										}
									}
								});
								return;
							}
							
							import_rows_to_load_dispatch(frm, rows);
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
		if (!frm.doc.load_dispatch_file_attach) {
			frappe.msgprint(__("Please attach a CSV file first"));
			return;
		}
		
		frm.trigger("load_dispatch_file_attach");
	},

});

function show_load_ref_no_selection_dialog(frm, load_ref_nos, all_rows) {
	const dialog = new frappe.ui.Dialog({
		title: __("Multiple Load Reference Numbers Found"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div style="padding: 10px; background-color: #fff3cd; border-radius: 4px; margin-bottom: 15px;">
					<p style="margin: 0;"><strong>${__("Warning")}:</strong> ${__("The file contains {0} different Load Reference Numbers. Please select which one to import.", [load_ref_nos.length])}</p>
					<p style="margin: 5px 0 0 0; font-size: 12px; color: #666;">
						<em>${__("Only rows matching the selected Load Reference Number will be imported into this Load Dispatch document.")}</em>
					</p>
					<p style="margin: 5px 0 0 0; font-size: 12px; color: #856404;">
						<strong>${__("Note")}:</strong> ${__("To import rows with other Load Reference Numbers, create separate Load Dispatch documents for each.")}
					</p>
				</div>`
			},
			{
				label: __("Load Reference Numbers in File"),
				fieldname: "load_ref_nos_info",
				fieldtype: "HTML",
				options: `<div style="padding: 10px; background-color: #f8f9fa; border-radius: 4px; margin-bottom: 15px;">
					<ul style="margin: 0; padding-left: 20px;">
						${load_ref_nos.map(ref_no => `<li><strong>${ref_no}</strong> (${all_rows.filter(r => r.hmsi_load_reference_no === ref_no).length} rows)</li>`).join('')}
					</ul>
				</div>`
			},
			{
				label: __("Select Load Reference Number"),
				fieldname: "selected_load_ref_no",
				fieldtype: "Select",
				options: load_ref_nos.join("\n"),
				reqd: 1,
				description: __("Select which Load Reference Number to import. Only rows matching this selection will be imported.")
			}
		],
		primary_action_label: __("Import Selected"),
		primary_action: function(values) {
			if (!values.selected_load_ref_no) {
				frappe.msgprint({
					title: __("Validation Error"),
					message: __("Please select a Load Reference Number."),
					indicator: "orange"
				});
				return;
			}
			
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Load Plan",
					name: values.selected_load_ref_no
				},
				callback: function(load_plan_r) {
					if (load_plan_r.message) {
						dialog.hide();
						
						const filtered_rows = all_rows.filter(function(row) {
							return row.hmsi_load_reference_no === values.selected_load_ref_no;
						});
						
						import_rows_to_load_dispatch(frm, filtered_rows, values.selected_load_ref_no);
					} else {
						frappe.msgprint({
							title: __("Invalid Load Reference Number"),
							message: __("Load Reference Number '{0}' does not exist as a Load Plan. Please create the Load Plan first or select a valid Load Reference Number.", [values.selected_load_ref_no]),
							indicator: "red"
						});
					}
				}
			});
		}
	});
	
	dialog.show();
}

function import_rows_to_load_dispatch(frm, rows, selected_load_ref_no) {
	if (!rows || rows.length === 0) {
		frappe.show_alert({
			message: __("No data found to import"),
			indicator: "orange"
		}, 5);
		return;
	}
	
	if (selected_load_ref_no && selected_load_ref_no.trim()) {
		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "Load Plan",
				name: selected_load_ref_no
			},
			callback: function(load_plan_r) {
				if (load_plan_r.message) {
					do_import_rows(frm, rows, selected_load_ref_no);
				} else {
					frappe.msgprint({
						title: __("Invalid Load Reference Number"),
						message: __("Load Reference Number '{0}' does not exist as a Load Plan. Please create the Load Plan first.", [selected_load_ref_no]),
						indicator: "red"
					});
				}
			}
		});
	} else {
		do_import_rows(frm, rows, null);
	}
}

function do_import_rows(frm, rows, selected_load_ref_no) {
	frm.clear_table("items");
	
	rows.forEach(function(row) {
		let child_row = frm.add_child("items");
		Object.keys(row).forEach(function(key) {
			if (key === 'item_code') {
				return;
			}
			child_row[key] = row[key];
		});
		if (child_row.item_code !== undefined && child_row.item_code !== null) {
			delete child_row.item_code;
		}
		if (row.price_unit) {
			const price_unit = flt(row.price_unit);
			if (price_unit > 0) {
				child_row.rate = price_unit / 1.18;
			}
		}
	});
	
	frm.refresh_field("items");
	
	setTimeout(() => apply_custom_field_styling(frm), 200);
	
	const first_row = rows[0] || {};
	const load_ref_no_to_use = selected_load_ref_no || first_row.hmsi_load_reference_no;
	
	if (load_ref_no_to_use) {
		frm._load_reference_no_from_csv = load_ref_no_to_use;
		if (frm.fields_dict.load_reference_no) {
			frm.set_value("load_reference_no", load_ref_no_to_use);
		} else {
			frm.doc.load_reference_no = load_ref_no_to_use;
		}
	}
	
	if (first_row.invoice_no) {
		if (frm.fields_dict.invoice_no) {
			frm.set_value("invoice_no", first_row.invoice_no);
		} else {
			frm.doc.invoice_no = first_row.invoice_no;
		}
	}
	
	calculate_total_dispatch_quantity(frm);
	
	frappe.show_alert({
		message: __("Successfully imported {0} rows from file", [rows.length]),
		indicator: "green"
	}, 5);
}

function calculate_total_dispatch_quantity(frm) {
	let total_dispatch_quantity = 0;
	if (frm.doc.items) {
		frm.doc.items.forEach(function(item) {
			if (item.frame_no && item.frame_no.trim() !== "") {
				total_dispatch_quantity += 1;
			}
		});
	}
	frm.set_value("total_dispatch_quantity", total_dispatch_quantity);
}

function apply_custom_field_styling(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	
	const grid = frm.fields_dict.items.grid;
	
	const ensureStyling = function() {
		$(grid.wrapper).find('[data-fieldname="print_name"]').addClass('custom-print-name');
		$(grid.wrapper).find('[data-fieldname="rate"]').addClass('custom-rate');
	};
	
	setTimeout(ensureStyling, 100);
	setTimeout(ensureStyling, 300);
	setTimeout(ensureStyling, 500);
	
	if (grid.wrapper) {
		grid.wrapper.on('render', function() {
			setTimeout(ensureStyling, 100);
		});
	}
	
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

frappe.ui.form.on("Load Dispatch Item", {
	frame_no: function(frm) {
		calculate_total_dispatch_quantity(frm);
	},
	price_unit: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.price_unit) {
			const price_unit = flt(row.price_unit);
			if (price_unit > 0) {
				row.rate = price_unit / 1.18;
				frm.refresh_field("rate", row.name, "items");
			} else {
				row.rate = 0;
				frm.refresh_field("rate", row.name, "items");
			}
		} else {
			row.rate = 0;
			frm.refresh_field("rate", row.name, "items");
		}
		setTimeout(() => apply_custom_field_styling(frm), 50);
	},
	model_serial_no: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.model_serial_no) {
			row.print_name = calculate_print_name_from_model_serial(row.model_serial_no, row.model_name);
			frm.refresh_field("print_name", row.name, "items");
		} else {
			row.print_name = "";
			frm.refresh_field("print_name", row.name, "items");
			if (row.item_code !== undefined && row.item_code !== null) {
				delete row.item_code;
				frm.refresh_field("item_code", row.name, "items");
			}
		}
		setTimeout(() => apply_custom_field_styling(frm), 50);
	},
	model_name: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.model_serial_no) {
			row.print_name = calculate_print_name_from_model_serial(row.model_serial_no, row.model_name);
			frm.refresh_field("print_name", row.name, "items");
		}
		setTimeout(() => apply_custom_field_styling(frm), 50);
	},
	items_remove: function(frm) {
		calculate_total_dispatch_quantity(frm);
		if (!frm.doc.items || frm.doc.items.length === 0) {
			frm._load_reference_no_from_csv = null;
			frm._original_load_reference_no = frm.doc.load_reference_no;
		}
	}
});

function calculate_print_name_from_model_serial(model_serial_no, model_name) {
	if (!model_serial_no) {
		return "";
	}
	
	model_serial_no = String(model_serial_no).trim();
	if (!model_serial_no) {
		return "";
	}
	
	const model_serial_upper = model_serial_no.toUpperCase();
	let id_index = model_serial_upper.indexOf("-ID");
	
	let serial_part;
	if (id_index !== -1) {
		serial_part = model_serial_no.substring(0, id_index + 3);
	} else {
		id_index = model_serial_upper.indexOf("ID");
		if (id_index !== -1) {
			serial_part = model_serial_no.substring(0, id_index) + "-ID";
		} else {
			serial_part = model_serial_no;
		}
	}
	
	if (model_name) {
		model_name = String(model_name).trim();
		if (model_name) {
			return `${model_name} (${serial_part}) (BS-VI)`;
		}
	}
	
	return `${serial_part} (BS-VI)`;
}

function create_purchase_receipt_from_load_dispatch(frm) {
	// If warehouse is not set, prompt user to select warehouse first
	if (!frm.doc.warehouse) {
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
					},
					description: __("Select warehouse for creating Purchase Receipt")
				}
			],
			primary_action_label: __("Create Purchase Receipt"),
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
				
				// Set warehouse in Load Dispatch and save, then create Purchase Receipt
				frm.set_value("warehouse", values.warehouse);
				frm.save().then(function() {
					// Reload the document to ensure warehouse is saved
					return frm.reload_doc();
				}).then(function() {
					// After warehouse is set and saved, create Purchase Receipt
					// Pass warehouse as parameter to ensure it's available
					frappe.call({
						method: "rkg.rkg.doctype.load_dispatch.load_dispatch.create_purchase_receipt_from_load_dispatch",
						args: {
							source_name: frm.doc.name,
							warehouse: values.warehouse
						},
						callback: function(r) {
							if (r.message && r.message.name) {
								frappe.set_route("Form", "Purchase Receipt", r.message.name);
							} else {
								frappe.msgprint({
									title: __("Success"),
									message: __("Purchase Receipt created successfully."),
									indicator: "green"
								});
								frm.reload_doc();
							}
						},
						error: function(r) {
							frappe.msgprint({
								title: __("Error"),
								message: r.message || __("An error occurred while creating Purchase Receipt."),
								indicator: "red"
							});
						}
					});
				});
			}
		});
		
		dialog.show();
		return;
	}
	
	// Warehouse is already set, proceed with creating Purchase Receipt
	frappe.call({
		method: "rkg.rkg.doctype.load_dispatch.load_dispatch.create_purchase_receipt_from_load_dispatch",
		args: {
			source_name: frm.doc.name
		},
		callback: function(r) {
			if (r.message && r.message.name) {
				frappe.set_route("Form", "Purchase Receipt", r.message.name);
			} else {
				frappe.msgprint({
					title: __("Success"),
					message: __("Purchase Receipt created successfully."),
					indicator: "green"
				});
				frm.reload_doc();
			}
		},
		error: function(r) {
			frappe.msgprint({
				title: __("Error"),
				message: r.message || __("An error occurred while creating Purchase Receipt."),
				indicator: "red"
			});
		}
	});
}