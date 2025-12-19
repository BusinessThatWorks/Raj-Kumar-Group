frappe.ui.form.on("Damage Assessment", {
	setup(frm) {
		// Set filter for serial_no in child table based on warehouse
		frm.set_query("serial_no", "damage_assessment_item", function(doc, cdt, cdn) {
			let filters = {};
			
			// Filter by warehouse based on from_warehouse
			if (doc.from_warehouse) {
				filters["warehouse"] = doc.from_warehouse;
			}
			
			return {
				filters: filters
			};
		});
	},
	
	refresh(frm) {
		// Calculate total on refresh
		frm.trigger("calculate_total_estimated_cost");
	},
	
	calculate_total_estimated_cost(frm) {
		let total = 0;
		if (frm.doc.damage_assessment_item) {
			frm.doc.damage_assessment_item.forEach(function(item) {
				total += flt(item.estimated_cost) || 0;
			});
		}
		frm.set_value("total_estimated_cost", total);
	}
});

frappe.ui.form.on("Damage Assessment Item", {
	serial_no(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		if (row.serial_no) {
			// Auto-fetch Load Dispatch from which this frame originated
			frappe.call({
				method: "rkg.rkg.doctype.damage_assessment.damage_assessment.get_load_dispatch_from_serial_no",
				args: {
					serial_no: row.serial_no
				},
				callback: function(r) {
					if (r.message && r.message.load_dispatch) {
						frappe.model.set_value(cdt, cdn, "load_dispatch", r.message.load_dispatch);
					} else {
						frappe.model.set_value(cdt, cdn, "load_dispatch", "");
					}
				}
			});
		} else {
			frappe.model.set_value(cdt, cdn, "load_dispatch", "");
		}
	},
	
	estimated_cost(frm, cdt, cdn) {
		// Recalculate total when estimated cost changes
		frm.trigger("calculate_total_estimated_cost");
	},
	
	damage_assessment_item_remove(frm) {
		// Recalculate total when row is removed
		frm.trigger("calculate_total_estimated_cost");
	}
});
