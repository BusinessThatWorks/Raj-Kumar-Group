

frappe.ui.form.on("Load Plan", {
	refresh(frm) {
		// Calculate total quantity on refresh
		console.log("Load Plan: Form refreshed. Current document fields:", {
			load_reference_no: frm.doc.load_reference_no,
			dispatch_plan_date: frm.doc.dispatch_plan_date,
			payment_plan_date: frm.doc.payment_plan_date,
			total_quantity: frm.doc.total_quantity,
			child_table_rows: frm.doc.table_tezh ? frm.doc.table_tezh.length : 0
		});
		calculate_total_quantity(frm);
	},

	// Attachment handler (custom field)
	custom_attach_load_plan(frm) {
		handle_load_plan_file_import(frm, frm.doc.custom_attach_load_plan);
	},
	// Fallback handler in case the field is named "attach_load_plan"
	attach_load_plan(frm) {
		handle_load_plan_file_import(frm, frm.doc.attach_load_plan);
	},
});

// Calculate total quantity from child table
function calculate_total_quantity(frm) {
	let total_quantity = 0;
	if (frm.doc.table_tezh) {
		frm.doc.table_tezh.forEach(function(item) {
			total_quantity += flt(item.quantity) || 0;
		});
	}
	console.log("Load Plan: Calculated total_quantity =", total_quantity, "from", frm.doc.table_tezh ? frm.doc.table_tezh.length : 0, "rows");
	frm.set_value("total_quantity", total_quantity);
}

// Recalculate when quantity changes in child table
frappe.ui.form.on("Load Plan Item", {
	quantity: function(frm) {
		calculate_total_quantity(frm);
	},
	table_tezh_remove: function(frm) {
		calculate_total_quantity(frm);
	}
});

function handle_load_plan_file_import(frm, file_url) {
	if (!file_url) {
		return;
	}

	frappe.show_alert({
		message: __("Processing attached file..."),
		indicator: "blue"
	}, 3);

	// First, check if file has multiple Load Reference Numbers
	frappe.call({
		method: "rkg.rkg.doctype.load_plan.load_plan.process_tabular_file",
		args: {
			file_url: file_url
		},
		callback: function(r) {
			if (!r.message || r.message.length === 0) {
				console.log("Load Plan Import: No data returned from server");
				frappe.show_alert({
					message: __("No data found in attached file"),
					indicator: "orange"
				}, 5);
				return;
			}

			console.log("Load Plan Import: Raw data from server", r.message);
			console.log("Load Plan Import: Total rows to import", r.message.length);

			// Check for multiple Load Reference Numbers
			const unique_load_refs = new Set();
			r.message.forEach(function(row) {
				if (row.load_reference_no) {
					unique_load_refs.add(String(row.load_reference_no).trim());
				}
			});

			console.log("Load Plan Import: Unique Load Reference Numbers found", Array.from(unique_load_refs));

			// If multiple Load Reference Numbers found, ask user
			if (unique_load_refs.size > 1) {
				frappe.confirm(
					__("File contains {0} different Load Reference Numbers:<br><br>{1}<br><br>Do you want to create separate Load Plan documents for each Load Reference Number?", 
						[unique_load_refs.size, Array.from(unique_load_refs).join(", ")]),
					function() {
						// Yes - Create multiple Load Plans
						_create_load_plans_from_file(frm, file_url, true);
					},
					function() {
						// No - Use single Load Plan (current form)
						// Ask user which Load Reference Number to use
						_select_load_reference_for_single_plan(frm, r.message, Array.from(unique_load_refs));
					}
				);
			} else {
				// Single Load Reference Number - populate current form
				_populate_single_load_plan(frm, r.message);
			}
		},
		error: function(err) {
			frappe.show_alert({
				message: __("Error processing file: {0}", [err.message || "Unknown error"]),
				indicator: "red"
			}, 5);
		}
	});
}

function _create_load_plans_from_file(frm, file_url, create_multiple) {
	frappe.show_alert({
		message: __("Creating Load Plans in background..."),
		indicator: "blue"
	}, 3);

	frappe.call({
		method: "rkg.rkg.doctype.load_plan.load_plan.create_load_plans_from_file",
		args: {
			file_url: file_url,
			create_multiple: create_multiple
		},
		callback: function(r) {
			if (!r.message) {
				frappe.show_alert({
					message: __("Error creating Load Plans"),
					indicator: "red"
				}, 5);
				return;
			}

			const result = r.message;
			console.log("Load Plan Import: Creation result", result);

			// Build success message
			let message = __("Successfully created {0} Load Plan(s)", [result.total_created]);
			
			if (result.multiple_created) {
				message += "<br><br><b>Created Load Plans:</b><br>";
				result.created_load_plans.forEach(function(lp) {
					message += `• ${lp.load_reference_no} (${lp.rows_count} rows, Qty: ${lp.total_quantity})<br>`;
				});
			}

			if (result.total_errors > 0) {
				message += "<br><b>Errors:</b><br>";
				result.errors.forEach(function(err) {
					message += `• ${err.load_reference_no}: ${err.error}<br>`;
				});
			}

			frappe.msgprint({
				title: __("Load Plans Created"),
				message: message,
				indicator: result.total_errors > 0 ? "orange" : "green"
			});

			// If only one Load Plan was created, redirect to it
			if (result.total_created === 1 && result.created_load_plans.length > 0) {
				frappe.set_route("Form", "Load Plan", result.created_load_plans[0].name);
			} else if (result.total_created > 1) {
				// Multiple created - show list view
				frappe.set_route("List", "Load Plan");
			}
		},
		error: function(err) {
			frappe.show_alert({
				message: __("Error creating Load Plans: {0}", [err.message || "Unknown error"]),
				indicator: "red"
			}, 5);
		}
	});
}

function _select_load_reference_for_single_plan(frm, rows, load_reference_list) {
	// Show dialog to select which Load Reference Number to use
	const dialog = new frappe.ui.Dialog({
		title: __("Select Load Reference Number"),
		fields: [
			{
				label: __("Load Reference Number"),
				fieldname: "selected_load_ref",
				fieldtype: "Select",
				options: load_reference_list.join("\n"),
				reqd: 1,
				default: load_reference_list[0] // Default to first one
			}
		],
		primary_action_label: __("Import"),
		primary_action(values) {
			const selected_load_ref = values.selected_load_ref;
			// Filter rows to only include the selected Load Reference Number
			const filtered_rows = rows.filter(function(row) {
				return row.load_reference_no && String(row.load_reference_no).trim() === String(selected_load_ref).trim();
			});
			
			console.log("Load Plan Import: Selected Load Reference Number =", selected_load_ref);
			console.log("Load Plan Import: Filtered rows count =", filtered_rows.length, "out of", rows.length);
			
			if (filtered_rows.length === 0) {
				frappe.msgprint({
					title: __("No Data Found"),
					message: __("No rows found for Load Reference Number: {0}", [selected_load_ref]),
					indicator: "orange"
				});
				dialog.hide();
				return;
			}
			
			dialog.hide();
			_populate_single_load_plan(frm, filtered_rows);
		}
	});
	
	dialog.show();
}

function _populate_single_load_plan(frm, rows) {
	// Clear existing rows
	frm.clear_table("table_tezh");

	if (rows.length > 0) {
		// Define valid child table fields (from Load Plan Item doctype)
		const child_table_fields = [
			'model',
			'model_name',
			'model_type',
			'model_variant',
			'model_color',
			'group_color',
			'option',
			'quantity'
		];
		
		// Define parent fields (from Load Plan doctype)
		const parent_fields = [
			'load_reference_no',
			'dispatch_plan_date',
			'payment_plan_date'
		];
		
		// Get first row for parent field mapping
		const first_row = rows[0] || {};
		console.log("Load Plan Import: First row data for parent fields", first_row);
		
		// Map parent fields from first row
		const parent_fields_populated = {};
		if (first_row.load_reference_no) {
			frm.set_value("load_reference_no", first_row.load_reference_no);
			parent_fields_populated.load_reference_no = first_row.load_reference_no;
			console.log("Load Plan Import: Set load_reference_no =", first_row.load_reference_no);
		}
		if (first_row.dispatch_plan_date) {
			frm.set_value("dispatch_plan_date", first_row.dispatch_plan_date);
			parent_fields_populated.dispatch_plan_date = first_row.dispatch_plan_date;
			console.log("Load Plan Import: Set dispatch_plan_date =", first_row.dispatch_plan_date);
		}
		if (first_row.payment_plan_date) {
			frm.set_value("payment_plan_date", first_row.payment_plan_date);
			parent_fields_populated.payment_plan_date = first_row.payment_plan_date;
			console.log("Load Plan Import: Set payment_plan_date =", first_row.payment_plan_date);
		}
		console.log("Load Plan Import: All parent fields populated", parent_fields_populated);
		
		// Process each row for child table
		rows.forEach(function(row, index) {
			console.log(`Load Plan Import: Processing row ${index + 1}`, row);
			const child = frm.add_child("table_tezh");
			const populated_fields = {};
			const skipped_fields = {};
			
			Object.keys(row).forEach(function(key) {
				// Skip parent fields - they're already handled above
				if (parent_fields.includes(key)) {
					skipped_fields[key] = row[key];
					return;
				}
				
				// Only populate valid child table fields
				if (child_table_fields.includes(key)) {
					child[key] = row[key];
					populated_fields[key] = row[key];
				} else {
					skipped_fields[key] = row[key];
					console.log(`Load Plan Import: Row ${index + 1} - Field '${key}' is not a valid child table field, skipping`);
				}
			});
			
			console.log(`Load Plan Import: Row ${index + 1} - Populated child table fields:`, populated_fields);
			if (Object.keys(skipped_fields).length > 0) {
				console.log(`Load Plan Import: Row ${index + 1} - Skipped fields (parent or invalid):`, skipped_fields);
			}
		});

		frm.refresh_field("table_tezh");

		// Recalculate totals
		calculate_total_quantity(frm);
		
		// Log final state
		console.log("Load Plan Import: Final document state", {
			load_reference_no: frm.doc.load_reference_no,
			dispatch_plan_date: frm.doc.dispatch_plan_date,
			payment_plan_date: frm.doc.payment_plan_date,
			total_quantity: frm.doc.total_quantity,
			child_table_rows: frm.doc.table_tezh ? frm.doc.table_tezh.length : 0,
			child_table_data: frm.doc.table_tezh
		});

		frappe.show_alert({
			message: __("Imported {0} rows from file", [rows.length]),
			indicator: "green"
		}, 5);
	} else {
		console.log("Load Plan Import: No data found in attached file");
		frappe.show_alert({
			message: __("No data found in attached file"),
			indicator: "orange"
		}, 5);
	}
}