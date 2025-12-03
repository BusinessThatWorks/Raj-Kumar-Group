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
		// Clear serial_no when item_code changes to avoid mismatch
		let row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "serial_no", "");
	}
});
