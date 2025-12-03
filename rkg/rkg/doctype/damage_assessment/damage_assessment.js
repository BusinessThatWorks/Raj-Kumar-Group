frappe.ui.form.on("Damage Assessment", {
	setup(frm) {
		// Set filter for serial_no in child table based on selected item_code
		frm.set_query("serial_no", "damage_assessment_item", function(doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			
			let filters = {};
			
			// Filter by item_code if selected
			if (row.item_code) {
				filters["item_code"] = row.item_code;
			}
			
			return {
				filters: filters
			};
		});
	}
});

frappe.ui.form.on("Damage Assessment Item", {
	item_code(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		// Clear serial_no when item_code changes to avoid mismatch
		frappe.model.set_value(cdt, cdn, "serial_no", "");
		frappe.model.set_value(cdt, cdn, "damaged_qty", 0);
		
		if (row.item_code) {
			// Fetch total_qty_received from Serial No doctype
			frappe.call({
				method: "rkg.rkg.doctype.damage_assessment.damage_assessment.get_serial_no_count",
				args: {
					item_code: row.item_code
				},
				callback: function(r) {
					if (r.message !== undefined) {
						frappe.model.set_value(cdt, cdn, "total_qty_received", r.message);
					}
				}
			});
		} else {
			frappe.model.set_value(cdt, cdn, "total_qty_received", 0);
		}
	},
	
	serial_no(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		if (row.serial_no) {
			// When serial_no is selected, set damaged_qty = 1
			// (each serial no represents 1 unit being marked as damaged)
			frappe.model.set_value(cdt, cdn, "damaged_qty", 1);
		} else {
			frappe.model.set_value(cdt, cdn, "damaged_qty", 0);
		}
	}
});
