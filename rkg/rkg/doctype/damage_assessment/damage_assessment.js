frappe.ui.form.on("Damage Assessment", {
	setup(frm) {
		// Set filter for serial_no in child table based on selected item_code and warehouse
		frm.set_query("serial_no", "damage_assessment_item", function(doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			
			let filters = {};
			
			// Filter by item_code if selected
			if (row.item_code) {
				filters["item_code"] = row.item_code;
			}
			
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
		
		// Show dashboard
		frm.trigger("show_status_dashboard");
	},
	
	show_status_dashboard(frm) {
		let html = `
			<div class="row" style="margin-bottom: 15px;">
				<div class="col-md-12">
					<div class="progress" style="height: 30px; margin-bottom: 10px;">
		`;
		
		// Calculate progress - Simplified steps
		let steps = [
			{ label: "Estimated", done: frm.doc.total_estimated_cost > 0 },
			{ label: "Submitted", done: frm.doc.docstatus === 1 }
		];
		
		let completed = steps.filter(s => s.done).length;
		let percentage = (completed / steps.length) * 100;
		
		html += `
						<div class="progress-bar bg-success" role="progressbar" 
							style="width: ${percentage}%;" 
							aria-valuenow="${completed}" aria-valuemin="0" aria-valuemax="${steps.length}">
							${completed}/${steps.length} Steps
						</div>
					</div>
					<div class="row text-center" style="font-size: 11px;">
		`;
		
		steps.forEach(function(step) {
			let icon = step.done ? '✅' : '⏳';
			let color = step.done ? 'green' : 'gray';
			html += `<div class="col" style="color: ${color}; padding: 2px;">${icon} ${step.label}</div>`;
		});
		
		html += `
					</div>
				</div>
			</div>
		`;
		
		frm.set_df_property("basic_info_section", "description", html);
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
	item_code(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		// Clear serial_no and load_dispatch when item_code changes to avoid mismatch
		frappe.model.set_value(cdt, cdn, "serial_no", "");
		frappe.model.set_value(cdt, cdn, "load_dispatch", "");
		frappe.model.set_value(cdt, cdn, "estimated_cost", 0);
		
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
			frappe.model.set_value(cdt, cdn, "damaged_qty", 1);
			
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
			frappe.model.set_value(cdt, cdn, "damaged_qty", 0);
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
