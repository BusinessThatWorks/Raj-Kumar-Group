

frappe.ui.form.on("Load Plan", {
	refresh(frm) {
		// Calculate total quantity on refresh
		calculate_total_quantity(frm);
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