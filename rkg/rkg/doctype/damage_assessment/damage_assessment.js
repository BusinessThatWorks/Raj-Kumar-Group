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
		// Always set Stock Entry Type to Material Transfer
		if (!frm.doc.stock_entry_type || frm.doc.stock_entry_type !== "Material Transfer") {
			frm.set_value("stock_entry_type", "Material Transfer");
		}
		
		// Make Stock Entry Type field read-only
		if (frm.fields_dict.stock_entry_type) {
			frm.set_df_property("stock_entry_type", "read_only", 1);
		}
		
		// Calculate total on refresh
		frm.trigger("calculate_total_estimated_cost");
	},
	
	stock_entry_type(frm) {
		// Prevent changing Stock Entry Type - always keep it as Material Transfer
		if (frm.doc.stock_entry_type && frm.doc.stock_entry_type !== "Material Transfer") {
			frappe.show_alert({
				message: __("Stock Entry Type must always be 'Material Transfer'"),
				indicator: "orange"
			}, 3);
			frm.set_value("stock_entry_type", "Material Transfer");
		}
	},
	
	load_plan_reference_no(frm) {
		// Auto-populate all frames when Load Plan Reference No is selected
		if (frm.doc.load_plan_reference_no) {
			// Fetch all frames from all Load Dispatches linked to this Load Plan
			frappe.call({
				method: "rkg.rkg.doctype.damage_assessment.damage_assessment.get_frames_from_load_plan",
				args: {
					load_plan_reference_no: frm.doc.load_plan_reference_no
				},
				callback: function(r) {
					if (r.message && r.message.length > 0) {
						// Clear existing items
						frm.clear_table("damage_assessment_item");
						
						// Add all frames
						r.message.forEach(function(frame) {
							let row = frm.add_child("damage_assessment_item");
							row.serial_no = frame.serial_no;
							row.load_dispatch = frame.load_dispatch || "";  // Set from frame data
							row.status = "OK";  // Default to OK
							row.type_of_damage = "";
							row.estimated_cost = 0;
						});
						
						frm.refresh_field("damage_assessment_item");
						frm.trigger("calculate_total_estimated_cost");
						
						frappe.show_alert({
							message: __("Auto-populated {0} frames from Load Reference No", [r.message.length]),
							indicator: "green"
						}, 3);
					} else {
						frappe.msgprint(__("No frames found for the selected Load Reference No"));
					}
				}
			});
		} else {
			// Clear items if Load Plan Reference No is cleared
			frm.clear_table("damage_assessment_item");
			frm.refresh_field("damage_assessment_item");
		}
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
	
	status(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		// Clear damage/issue, estimated cost, and warehouses if status is OK
		if (row.status === "OK") {
			frappe.model.set_value(cdt, cdn, "type_of_damage", "");
			frappe.model.set_value(cdt, cdn, "estimated_cost", 0);
			frappe.model.set_value(cdt, cdn, "from_warehouse", "");
			frappe.model.set_value(cdt, cdn, "to_warehouse", "");
		}
		
		// Refresh the row to show/hide fields based on status
		frm.refresh_field("damage_assessment_item");
		frm.trigger("calculate_total_estimated_cost");
	},
	
	type_of_damage(frm, cdt, cdn) {
		// Recalculate total when damage/issue changes (in case it affects cost)
		frm.trigger("calculate_total_estimated_cost");
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
