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
	
	
	before_save(frm) {
		// Allow saving as draft without damage details
		// Validation for damage items will be done on submit (in before_submit hook)
		// This allows creating Damage Assessment from Load Dispatch with items pre-populated but without damage details
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
	
	load_dispatch(frm) {
		// Auto-populate all frames when Load Dispatch is selected
		if (frm.doc.load_dispatch) {
			// Fetch all frames from Load Dispatch
			frappe.call({
				method: "rkg.rkg.doctype.damage_assessment.damage_assessment.get_frames_from_load_dispatch",
				args: {
					load_dispatch: frm.doc.load_dispatch
				},
				callback: function(r) {
					if (r.message && r.message.length > 0) {
						// Clear existing items
						frm.clear_table("damage_assessment_item");
						
						// Add all frames
						r.message.forEach(function(frame) {
							let row = frm.add_child("damage_assessment_item");
							row.serial_no = frame.serial_no;
							row.from_warehouse = frame.warehouse || "";  // Set warehouse from frame data
							row.load_reference_no = frame.load_reference_no || "";  // Set Load Reference Number
							row.status = "OK";  // Default to OK
							row.estimated_cost = 0;
						});
						
						frm.refresh_field("damage_assessment_item");
						frm.trigger("calculate_total_estimated_cost");
						
						frappe.show_alert({
							message: __("Auto-populated {0} frames from Load Dispatch", [r.message.length]),
							indicator: "green"
						}, 3);
					} else {
						frappe.msgprint(__("No frames found for the selected Load Dispatch"));
					}
				}
			});
		} else {
			// Clear items if Load Dispatch is cleared
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
			// Auto-fetch Warehouse and Load Reference Number from which this frame originated
			frappe.call({
				method: "rkg.rkg.doctype.damage_assessment.damage_assessment.get_load_dispatch_from_serial_no",
				args: {
					serial_no: row.serial_no
				},
				callback: function(r) {
					if (r.message) {
						// Set warehouse if available (only if not already set, to preserve existing value)
						if (r.message.warehouse && !row.from_warehouse) {
							frappe.model.set_value(cdt, cdn, "from_warehouse", r.message.warehouse);
						} else if (!r.message.warehouse && !row.from_warehouse) {
							frappe.model.set_value(cdt, cdn, "from_warehouse", "");
						}
					}
				}
			});
			
			// Fetch Load Reference Number
			frappe.call({
				method: "rkg.rkg.doctype.damage_assessment.damage_assessment.get_load_reference_no_from_serial_no",
				args: {
					serial_no: row.serial_no
				},
				callback: function(r) {
					if (r.message) {
						frappe.model.set_value(cdt, cdn, "load_reference_no", r.message);
					} else {
						frappe.model.set_value(cdt, cdn, "load_reference_no", "");
					}
				}
			});
		} else {
			frappe.model.set_value(cdt, cdn, "from_warehouse", "");
			frappe.model.set_value(cdt, cdn, "load_reference_no", "");
		}
	},
	
	status(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		// Clear estimated cost, to_warehouse, and issue fields if status is OK
		if (row.status === "OK") {
			frappe.model.set_value(cdt, cdn, "estimated_cost", 0);
			frappe.model.set_value(cdt, cdn, "to_warehouse", "");
			frappe.model.set_value(cdt, cdn, "issue_1", "");
			frappe.model.set_value(cdt, cdn, "issue_2", "");
			frappe.model.set_value(cdt, cdn, "issue_3", "");
			// Note: from_warehouse is kept as it's already fetched
		}
		
		// Refresh the row
		setTimeout(function() {
			frm.refresh_field("damage_assessment_item");
		}, 100);
		frm.trigger("calculate_total_estimated_cost");
	},
	
	from_warehouse(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		// Clear to_warehouse if status is OK
		if (row.status === "OK") {
			frappe.model.set_value(cdt, cdn, "to_warehouse", "");
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
