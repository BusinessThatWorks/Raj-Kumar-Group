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
		
		// Set filter for original_damage_assessment - only show submitted Damage Transfers
		frm.set_query("original_damage_assessment", function() {
			return {
				filters: {
					"transfer_direction": "Damage Transfer",
					"docstatus": 1,
					"return_status": ["in", ["Not Returned", "Partially Returned"]]
				}
			};
		});
	},
	
	refresh(frm) {
		// Update field labels based on transfer direction
		frm.trigger("update_warehouse_labels");
	},
	
	transfer_direction(frm) {
		// Clear original_damage_assessment when switching to Damage Transfer
		if (frm.doc.transfer_direction === "Damage Transfer") {
			frm.set_value("original_damage_assessment", "");
		}
		
		// Auto-swap warehouses when transfer direction changes (only if both are set)
		if (frm.doc.from_warehouse && frm.doc.to_warehouse && !frm.doc.original_damage_assessment) {
			let temp = frm.doc.from_warehouse;
			frm.set_value("from_warehouse", frm.doc.to_warehouse);
			frm.set_value("to_warehouse", temp);
		}
		
		// Update labels
		frm.trigger("update_warehouse_labels");
		
		// Clear child table items if switching direction and items exist
		if (frm.doc.damage_assessment_item && frm.doc.damage_assessment_item.length > 0) {
			frappe.confirm(
				__("Changing transfer direction will clear the items table. Continue?"),
				function() {
					frm.clear_table("damage_assessment_item");
					frm.refresh_field("damage_assessment_item");
				},
				function() {
					// Revert direction change
					let current = frm.doc.transfer_direction;
					let revert = current === "Damage Transfer" ? "Return Transfer" : "Damage Transfer";
					frm.set_value("transfer_direction", revert);
					// Swap back warehouses
					if (!frm.doc.original_damage_assessment) {
						let temp = frm.doc.from_warehouse;
						frm.set_value("from_warehouse", frm.doc.to_warehouse);
						frm.set_value("to_warehouse", temp);
					}
				}
			);
		}
	},
	
	original_damage_assessment(frm) {
		// When original damage assessment is selected, populate child table
		if (frm.doc.original_damage_assessment && frm.doc.transfer_direction === "Return Transfer") {
			frappe.call({
				method: "rkg.rkg.doctype.damage_assessment.damage_assessment.get_damage_assessment_items",
				args: {
					damage_assessment: frm.doc.original_damage_assessment
				},
				callback: function(r) {
					if (r.message) {
						// Set warehouses (reversed from original)
						frm.set_value("from_warehouse", r.message.to_warehouse);
						frm.set_value("to_warehouse", r.message.from_warehouse);
						frm.set_value("stock_entry_type", r.message.stock_entry_type);
						
						// Clear existing items and add from original
						frm.clear_table("damage_assessment_item");
						
						r.message.items.forEach(function(item) {
							let row = frm.add_child("damage_assessment_item");
							row.item_code = item.item_code;
							row.serial_no = item.serial_no;
							row.total_qty_received = item.total_qty_received;
							row.type_of_damage = item.type_of_damage;
							row.damaged_qty = item.damaged_qty;
							row.item_remarks = item.item_remarks;
						});
						
						frm.refresh_field("damage_assessment_item");
						
						frappe.show_alert({
							message: __("Items populated from {0}", [frm.doc.original_damage_assessment]),
							indicator: "green"
						});
					}
				}
			});
		} else if (!frm.doc.original_damage_assessment) {
			// Clear items if original is cleared
			frm.clear_table("damage_assessment_item");
			frm.refresh_field("damage_assessment_item");
		}
	},
	
	update_warehouse_labels(frm) {
		// Update field descriptions based on transfer direction
		if (frm.doc.transfer_direction === "Damage Transfer") {
			frm.set_df_property("from_warehouse", "description", "Source warehouse (e.g., Stores)");
			frm.set_df_property("to_warehouse", "description", "Damage warehouse (e.g., Damage Godown)");
		} else {
			frm.set_df_property("from_warehouse", "description", "Damage warehouse (e.g., Damage Godown)");
			frm.set_df_property("to_warehouse", "description", "Return warehouse (e.g., Stores)");
		}
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
