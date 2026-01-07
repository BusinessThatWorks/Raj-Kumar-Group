frappe.ui.form.on("Load Receipt", {
	load(frm) {
		// Ensure status is loaded when document first opens
		// This fixes the issue where status shows "Not Saved" in form view but "Submitted" in list view
		if (frm.doc.docstatus === 1) {
			// For submitted documents, always reload status from database
			// This is critical after PI submission when status might show "Not Saved"
			frappe.db.get_value("Load Receipt", frm.doc.name, ["status", "docstatus"], function(r) {
				if (r && r.message) {
					// Verify docstatus is still 1 (document might have been cancelled)
					if (r.message.docstatus === 1) {
						// Always set status to "Submitted" for submitted documents
						// Use direct assignment to avoid triggering "Not Saved" indicator
						if (!frm.doc.status || frm.doc.status === "Not Saved" || frm.doc.status !== "Submitted") {
							frm.doc.status = "Submitted";
							frm.refresh_field("status");
							// Clear "Not Saved" indicator
							frm.dirty = false;
						}
					}
				} else if (frm.doc.docstatus === 1) {
					// If submitted but status is missing, set it to Submitted
					if (!frm.doc.status || frm.doc.status === "Not Saved") {
						frm.doc.status = "Submitted";
						frm.refresh_field("status");
						frm.dirty = false;
					}
				}
			});
		} else if (frm.doc.docstatus === 0) {
			// For draft documents, ensure status is Draft
			if (!frm.doc.status || frm.doc.status === "Not Saved") {
				frm.set_value("status", "Draft");
				frm.refresh_field("status");
			}
		}
	},
	
	refresh(frm) {
		// Ensure status is properly synced from database
		// This fixes the issue where status shows "Not Saved" even when document is submitted
		// Always reload status from database for submitted documents to ensure accuracy
		if (frm.doc.docstatus === 1) {
			// For submitted documents, always reload status from database to ensure accuracy
			// This is critical after PI submission when status might show "Not Saved"
			frappe.db.get_value("Load Receipt", frm.doc.name, ["status", "docstatus"], function(r) {
				if (r && r.message) {
					// Verify docstatus is still 1 (document might have been cancelled)
					if (r.message.docstatus === 1) {
						// Always set status to "Submitted" for submitted documents
						// Use direct assignment to avoid triggering "Not Saved" indicator
						if (!frm.doc.status || frm.doc.status === "Not Saved" || frm.doc.status !== "Submitted") {
							frm.doc.status = "Submitted";
							frm.refresh_field("status");
							// Clear "Not Saved" indicator by marking form as not dirty
							frm.dirty = false;
						}
					}
				} else if (frm.doc.docstatus === 1) {
					// If submitted but status is missing, set it to Submitted
					if (!frm.doc.status || frm.doc.status === "Not Saved") {
						frm.doc.status = "Submitted";
						frm.refresh_field("status");
						frm.dirty = false;
					}
				}
			});
		} else if (frm.doc.docstatus === 0) {
			// For draft documents, ensure status is Draft
			if (!frm.doc.status || frm.doc.status === "Not Saved") {
				frm.set_value("status", "Draft");
				frm.refresh_field("status");
			}
		}
		
		// Calculate total receipt quantity on refresh
		calculate_total_receipt_quantity(frm);
		// Calculate total billed quantity on refresh
		calculate_total_billed_quantity(frm);
		// Update frames OK/Not OK counts from Damage Assessment
		update_frames_status_counts(frm);
		
		// All creation buttons only appear after Load Receipt is submitted
		if (frm.doc.docstatus === 1) {
			// Check if Purchase Receipt, Purchase Invoice already exists for the linked Load Dispatch
			if (frm.doc.load_dispatch) {
				frappe.call({
					method: "rkg.rkg.doctype.load_dispatch.load_dispatch.check_existing_documents",
					args: {
						load_dispatch_name: frm.doc.load_dispatch
					},
					callback: function(r) {
						if (r.message) {
							const has_pr = r.message.has_purchase_receipt || false;
							
							// Add "Create Damage Assessment" button - only if Purchase Receipt exists and Damage Assessment doesn't exist
							if (frm.doc.load_reference_no && has_pr && !frm.doc.damage_assessment) {
								frm.add_custom_button(__("Create Damage Assessment"), function() {
									create_damage_assessment(frm);
								}, __("Create"));
								frm.page.set_inner_btn_group_as_primary(__("Create"));
							}
							
							// Only show Purchase Receipt button if no Purchase Receipt exists
							if (!has_pr) {
								frm.add_custom_button(__("Purchase Receipt"), function() {
									create_purchase_receipt_from_load_receipt(frm);
								}, __("Create"));
								frm.page.set_inner_btn_group_as_primary(__("Create"));
							}
						}
					}
				});
			}
		}
	},
	
	before_save(frm) {
		// Show warehouse popup on first save if warehouse is not set
		if (frm.is_new() && !frm.doc.warehouse && frm.doc.items && frm.doc.items.length > 0) {
			// Set flag to show popup after save
			frm._show_warehouse_popup = true;
		}
	},
	
	after_save(frm) {
		// Show warehouse popup after first save if warehouse is not set
		if (frm._show_warehouse_popup && !frm.doc.warehouse) {
			frm._show_warehouse_popup = false;
			setTimeout(function() {
				show_warehouse_selection_dialog(frm);
			}, 500);
		}
	},
	
	
	load_dispatch(frm) {
		// Fetch data from Load Dispatch when load_dispatch is selected
		if (frm.doc.load_dispatch) {
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Load Dispatch",
					name: frm.doc.load_dispatch
				},
				callback: function(r) {
					if (r.message) {
						// Set load_reference_no
						frm.set_value("load_reference_no", r.message.load_reference_no);
						
						// Fetch items from Load Dispatch if items table is empty
						if (!frm.doc.items || frm.doc.items.length === 0) {
							fetch_items_from_load_dispatch(frm, r.message.name);
						}
					}
				}
			});
		}
	},
	
	damage_assessment(frm) {
		// Update frames OK/Not OK counts when Damage Assessment is linked
		update_frames_status_counts(frm);
	}
});

// Calculate total receipt quantity by counting rows with frame_no
function calculate_total_receipt_quantity(frm) {
	let total_receipt_quantity = 0;
	if (frm.doc.items) {
		frm.doc.items.forEach(function(item) {
			// Count rows that have a non-empty frame_no
			if (item.frame_no && item.frame_no.trim() !== "") {
				total_receipt_quantity += 1;
			}
		});
	}
	frm.set_value("total_receipt_quantity", total_receipt_quantity);
}

// Calculate total billed quantity from Purchase Invoices linked to Load Dispatch
function calculate_total_billed_quantity(frm) {
	if (!frm.doc.load_dispatch) {
		// For submitted documents, update directly without set_value to avoid "Not Saved"
		if (frm.doc.docstatus === 1) {
			frm.doc.total_billed_quantity = 0;
			frm.refresh_field("total_billed_quantity");
		} else {
			frm.set_value("total_billed_quantity", 0);
		}
		return;
	}
	
	// Store current status and docstatus before making the call
	const current_docstatus = frm.doc.docstatus;
	const is_submitted = current_docstatus === 1;
	
	frappe.call({
		method: "frappe.client.get",
		args: {
			doctype: "Load Dispatch",
			name: frm.doc.load_dispatch
		},
		callback: function(r) {
			if (r.message) {
				const total_billed_qty = r.message.total_billed_quantity || 0;
				
				// For submitted documents, update directly to avoid triggering "Not Saved"
				if (is_submitted) {
					frm.doc.total_billed_quantity = total_billed_qty;
					frm.refresh_field("total_billed_quantity");
					
					// CRITICAL: Always ensure status is "Submitted" for submitted documents
					// Update status directly without set_value to prevent "Not Saved" indicator
					frappe.db.get_value("Load Receipt", frm.doc.name, ["status", "docstatus"], function(status_r) {
						if (status_r && status_r.message) {
							// Verify docstatus is still 1
							if (status_r.message.docstatus === 1) {
								// Always set status to "Submitted" for submitted documents
								// Use direct assignment to avoid triggering "Not Saved"
								if (frm.doc.status !== "Submitted") {
									frm.doc.status = "Submitted";
									frm.refresh_field("status");
									// Clear any "Not Saved" indicator by refreshing the form
									frm.dirty = false;
									frm.refresh();
								}
							}
						} else if (is_submitted) {
							// If submitted but status is missing, set it to Submitted
							if (frm.doc.status !== "Submitted") {
								frm.doc.status = "Submitted";
								frm.refresh_field("status");
								frm.dirty = false;
								frm.refresh();
							}
						}
					});
				} else {
					// For draft documents, use set_value normally
					frm.set_value("total_billed_quantity", total_billed_qty);
				}
			} else {
				if (is_submitted) {
					frm.doc.total_billed_quantity = 0;
					frm.refresh_field("total_billed_quantity");
				} else {
					frm.set_value("total_billed_quantity", 0);
				}
			}
		},
		error: function() {
			if (is_submitted) {
				frm.doc.total_billed_quantity = 0;
				frm.refresh_field("total_billed_quantity");
			} else {
				frm.set_value("total_billed_quantity", 0);
			}
		}
	});
}

// Fetch items from Load Dispatch
function fetch_items_from_load_dispatch(frm, load_dispatch_name) {
	frappe.call({
		method: "frappe.client.get",
		args: {
			doctype: "Load Dispatch",
			name: load_dispatch_name
		},
		callback: function(r) {
			if (r.message && r.message.items) {
				// Clear existing items
				frm.clear_table("items");
				
				// Define valid fields that exist in both Load Dispatch Item and Load Receipt Item
				const valid_fields = [
					"hmsi_load_reference_no",
					"model_variant",
					"frame_no",
					"color_code",
					"hsn_code",
					"price_unit",
					"rate",
					"invoice_no",
					"model_name",
					"engnie_no_motor_no",
					"tax_rate",
					"qty",
					"key_no",
					"dispatch_date",
					"model_serial_no",
					"item_code",
					"print_name",
					"dor",
					"unit",
					"battery_no"
				];
				
				// Add items from Load Dispatch
				r.message.items.forEach(function(dispatch_item) {
					let child_row = frm.add_child("items");
					// Copy only valid fields from Load Dispatch Item
					valid_fields.forEach(function(fieldname) {
						if (dispatch_item[fieldname] !== undefined && dispatch_item[fieldname] !== null) {
							child_row[fieldname] = dispatch_item[fieldname];
						}
					});
					// Note: Status field removed from child table
				});
				
				frm.refresh_field("items");
				calculate_total_receipt_quantity(frm);
			}
		}
	});
}


// Function to show warehouse selection dialog on save
function show_warehouse_selection_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select Warehouse"),
		fields: [
			{
				label: __("Warehouse"),
				fieldname: "warehouse",
				fieldtype: "Link",
				options: "Warehouse",
				reqd: 1,
				get_query: function() {
					return {
						filters: {}
					};
				},
				description: __("Select warehouse for allocating frames in this Load Receipt")
			}
		],
		primary_action_label: __("Save"),
		primary_action: function(values) {
			if (!values.warehouse) {
				frappe.msgprint({
					title: __("Validation Error"),
					message: __("Please select a warehouse."),
					indicator: "orange"
				});
				return;
			}
			
			dialog.hide();
			
			// Set warehouse in Load Receipt
			frm.set_value("warehouse", values.warehouse);
			frm.save().then(function() {
				frappe.show_alert({
					message: __("Warehouse {0} allocated successfully", [values.warehouse]),
					indicator: "green"
				}, 3);
			});
		}
	});
	
	dialog.show();
}

// Create Purchase Receipt from Load Receipt
function create_purchase_receipt_from_load_receipt(frm) {
	// If warehouse is not set, prompt user to select warehouse first
	if (!frm.doc.warehouse) {
		const dialog = new frappe.ui.Dialog({
			title: __("Select Warehouse"),
			fields: [
				{
					label: __("Warehouse"),
					fieldname: "warehouse",
					fieldtype: "Link",
					options: "Warehouse",
					reqd: 1,
					get_query: function() {
						return {
							filters: {}
						};
					},
					description: __("Select warehouse for creating Purchase Receipt")
				}
			],
			primary_action_label: __("Create Purchase Receipt"),
			primary_action: function(values) {
				if (!values.warehouse) {
					frappe.msgprint({
						title: __("Validation Error"),
						message: __("Please select a warehouse."),
						indicator: "orange"
					});
					return;
				}
				
				dialog.hide();
				
				// Set warehouse in Load Receipt and save, then create Purchase Receipt
				frm.set_value("warehouse", values.warehouse);
				frm.save().then(function() {
					// After warehouse is set and saved, create Purchase Receipt
					frappe.call({
						method: "rkg.rkg.doctype.load_receipt.load_receipt.create_purchase_receipt_from_load_receipt",
						args: {
							source_name: frm.doc.name
						},
						callback: function(r) {
							if (r.message && r.message.name) {
								frappe.set_route("Form", "Purchase Receipt", r.message.name);
								calculate_total_billed_quantity(frm);
							} else {
								frappe.msgprint({
									title: __("Success"),
									message: __("Purchase Receipt created successfully."),
									indicator: "green"
								});
								frm.reload_doc();
								calculate_total_billed_quantity(frm);
							}
						},
						error: function(r) {
							frappe.msgprint({
								title: __("Error"),
								message: r.message || __("An error occurred while creating Purchase Receipt."),
								indicator: "red"
							});
						}
					});
				});
			}
		});
		
		dialog.show();
		return;
	}
	
	// Warehouse is already set, proceed with creating Purchase Receipt
	frappe.call({
		method: "rkg.rkg.doctype.load_receipt.load_receipt.create_purchase_receipt_from_load_receipt",
		args: {
			source_name: frm.doc.name
		},
		callback: function(r) {
			if (r.message && r.message.name) {
				frappe.set_route("Form", "Purchase Receipt", r.message.name);
				calculate_total_billed_quantity(frm);
			} else {
				frappe.msgprint({
					title: __("Success"),
					message: __("Purchase Receipt created successfully."),
					indicator: "green"
				});
				frm.reload_doc();
				calculate_total_billed_quantity(frm);
			}
		},
		error: function(r) {
			frappe.msgprint({
				title: __("Error"),
				message: r.message || __("An error occurred while creating Purchase Receipt."),
				indicator: "red"
			});
		}
	});
}


// Update frames OK/Not OK counts from Damage Assessment
function update_frames_status_counts(frm) {
	if (!frm.doc.damage_assessment) {
		frm.set_value("frames_ok", 0);
		frm.set_value("frames_not_ok", 0);
		return;
	}
	
	frappe.call({
		method: "rkg.rkg.doctype.load_receipt.load_receipt.get_frames_status_counts",
		args: {
			damage_assessment: frm.doc.damage_assessment
		},
		callback: function(r) {
			if (r.message) {
				frm.set_value("frames_ok", r.message.frames_ok || 0);
				frm.set_value("frames_not_ok", r.message.frames_not_ok || 0);
			}
		}
	});
}

// Create Damage Assessment from Load Receipt
function create_damage_assessment(frm) {
	if (!frm.doc.load_reference_no) {
		frappe.msgprint({
			title: __("Error"),
			message: __("Load Reference No is required to create Damage Assessment."),
			indicator: "red"
		});
		return;
	}
	
	if (!frm.doc.items || frm.doc.items.length === 0) {
		frappe.msgprint({
			title: __("Error"),
			message: __("Please add items with Frame Numbers before creating Damage Assessment."),
			indicator: "red"
		});
		return;
	}
	
	frappe.call({
		method: "rkg.rkg.doctype.load_receipt.load_receipt.create_damage_assessment",
		args: {
			source_name: frm.doc.name
		},
		callback: function(r) {
			if (r.message && r.message.name) {
				// Set the damage_assessment field
				frm.set_value("damage_assessment", r.message.name);
				// Refresh to show the field
				frm.refresh();
				// Open the created Damage Assessment
				frappe.set_route("Form", "Damage Assessment", r.message.name);
				frappe.show_alert({
					message: __("Damage Assessment {0} created successfully", [r.message.name]),
					indicator: "green"
				}, 5);
			}
		},
		error: function(r) {
			frappe.msgprint({
				title: __("Error"),
				message: r.message || __("An error occurred while creating Damage Assessment."),
				indicator: "red"
			});
		}
	});
}

// Recalculate when frame_no changes in child table
frappe.ui.form.on("Load Receipt Item", {
	frame_no: function(frm) {
		calculate_total_receipt_quantity(frm);
	},
	items_remove: function(frm) {
		calculate_total_receipt_quantity(frm);
	},
	items_add: function(frm) {
		calculate_total_receipt_quantity(frm);
	}
});
