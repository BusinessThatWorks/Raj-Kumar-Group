

frappe.ui.form.on("Load Plan", {
	refresh(frm) {
		// Calculate total quantity on refresh
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

	frappe.call({
		method: "rkg.rkg.doctype.load_plan.load_plan.process_tabular_file",
		args: {
			file_url: file_url
		},
		callback: function(r) {
			if (!r.message) {
				return;
			}

			// Clear existing rows
			frm.clear_table("table_tezh");

			if (r.message.length > 0) {
				r.message.forEach(function(row) {
					const child = frm.add_child("table_tezh");
					Object.keys(row).forEach(function(key) {
						if (key in child) {
							child[key] = row[key];
						}
					});
				});

				frm.refresh_field("table_tezh");

				// Map parent fields from first row
				const first_row = r.message[0] || {};
				if (first_row.load_reference_no) {
					frm.set_value("load_reference_no", first_row.load_reference_no);
				}
				if (first_row.dispatch_plan_date) {
					frm.set_value("dispatch_plan_date", first_row.dispatch_plan_date);
				}
				if (first_row.payment_plan_date) {
					frm.set_value("payment_plan_date", first_row.payment_plan_date);
				}

				// Recalculate totals
				calculate_total_quantity(frm);

				frappe.show_alert({
					message: __("Imported {0} rows from file", [r.message.length]),
					indicator: "green"
				}, 5);
			} else {
				frappe.show_alert({
					message: __("No data found in attached file"),
					indicator: "orange"
				}, 5);
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