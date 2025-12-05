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
			
			// Filter by warehouse based on branch_warehouse or from_warehouse
			if (doc.from_warehouse) {
				filters["warehouse"] = doc.from_warehouse;
			} else if (doc.branch_warehouse) {
				filters["warehouse"] = doc.branch_warehouse;
			}
			
			return {
				filters: filters
			};
		});
	},
	
	refresh(frm) {
		// Calculate total on refresh
		frm.trigger("calculate_total_estimated_cost");
		
		// Add approval action buttons (only for draft documents)
		if (frm.doc.docstatus === 0) {
			frm.trigger("add_approval_buttons");
		}
		
		// Add workflow action buttons for submitted docs
		if (frm.doc.docstatus === 1) {
			frm.trigger("add_workflow_buttons");
		}
		
		// Show dashboard
		frm.trigger("show_status_dashboard");
	},
	
	add_approval_buttons(frm) {
		// Godown Owner Approval Button
		if (!frm.doc.godown_owner_action || frm.doc.godown_owner_action === "Sent Back for Re-estimation") {
			frm.add_custom_button(__("Approve as Godown Owner"), function() {
				frm.trigger("show_godown_owner_approval_dialog");
			}, __("Approvals"));
		}
		
		// Sales Manager Approval Button (only if Godown Owner has approved)
		if (frm.doc.godown_owner_action && 
			["Approved", "Edited & Approved"].includes(frm.doc.godown_owner_action) &&
			(!frm.doc.sales_manager_action || frm.doc.sales_manager_action === "Sent Back for Re-estimation")) {
			frm.add_custom_button(__("Approve as Sales Manager"), function() {
				frm.trigger("show_sales_manager_approval_dialog");
			}, __("Approvals"));
		}
	},
	
	add_workflow_buttons(frm) {
		// Recoupment button
		if (frm.doc.approval_status === "Approved" && frm.doc.recoupment_status === "Pending") {
			frm.add_custom_button(__("Record Recoupment"), function() {
				frm.trigger("show_recoupment_dialog");
			}, __("Actions"));
		}
		
		// Repair completion button
		if (frm.doc.recoupment_status === "Fully Deducted" && frm.doc.repair_status !== "Completed") {
			frm.add_custom_button(__("Record Repair Completion"), function() {
				frm.trigger("show_repair_dialog");
			}, __("Actions"));
		}
		
		// Settlement button
		if (frm.doc.repair_status === "Completed" && frm.doc.settlement_status === "Pending") {
			frm.add_custom_button(__("Record Settlement"), function() {
				frm.trigger("show_settlement_dialog");
			}, __("Actions"));
		}
		
		// Return to Stores button (after repair is completed)
		if (frm.doc.repair_status === "Completed" && frm.doc.return_status !== "Fully Returned") {
			frm.add_custom_button(__("Return to Stores"), function() {
				frm.trigger("show_return_dialog");
			}, __("Actions"));
			
			// Make this button primary/highlighted
			frm.page.set_inner_btn_group_as_primary(__("Actions"));
		}
	},
	
	show_status_dashboard(frm) {
		let html = `
			<div class="row" style="margin-bottom: 15px;">
				<div class="col-md-12">
					<div class="progress" style="height: 30px; margin-bottom: 10px;">
		`;
		
		// Calculate progress
		let steps = [
			{ label: "Estimated", done: frm.doc.total_estimated_cost > 0 },
			{ label: "GO Approved", done: ["Approved", "Edited & Approved"].includes(frm.doc.godown_owner_action) },
			{ label: "SM Approved", done: ["Approved", "Edited & Approved"].includes(frm.doc.sales_manager_action) },
			{ label: "Recouped", done: frm.doc.recoupment_status === "Fully Deducted" },
			{ label: "Repaired", done: frm.doc.repair_status === "Completed" },
			{ label: "Settled", done: frm.doc.settlement_status === "Settled" },
			{ label: "Returned", done: frm.doc.return_status === "Fully Returned" }
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
	
	show_godown_owner_approval_dialog(frm) {
		let d = new frappe.ui.Dialog({
			title: __("Godown Owner Approval"),
			fields: [
				{
					fieldname: "current_amount",
					fieldtype: "Currency",
					label: __("Current Estimated Amount"),
					default: frm.doc.total_estimated_cost,
					read_only: 1
				},
				{
					fieldname: "action",
					fieldtype: "Select",
					label: __("Action"),
					options: "Approved\nEdited & Approved\nRejected\nSent Back for Re-estimation",
					reqd: 1
				},
				{
					fieldname: "new_amount",
					fieldtype: "Currency",
					label: __("Revised Amount"),
					depends_on: "eval:doc.action=='Edited & Approved'"
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Remarks")
				}
			],
			primary_action_label: __("Submit"),
			primary_action: function(values) {
				frappe.call({
					method: "rkg.rkg.doctype.damage_assessment.damage_assessment.approve_as_godown_owner",
					args: {
						docname: frm.doc.name,
						action: values.action,
						amount: values.new_amount,
						remarks: values.remarks
					},
					callback: function(r) {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({
								message: r.message.message,
								indicator: "green"
							});
							frm.reload_doc();
						}
					}
				});
				d.hide();
			}
		});
		d.show();
	},
	
	show_sales_manager_approval_dialog(frm) {
		let current_amount = frm.doc.godown_owner_action === "Edited & Approved" 
			? frm.doc.godown_owner_amount 
			: frm.doc.total_estimated_cost;
		
		let d = new frappe.ui.Dialog({
			title: __("Sales Manager Approval"),
			fields: [
				{
					fieldname: "current_amount",
					fieldtype: "Currency",
					label: __("Amount from Godown Owner"),
					default: current_amount,
					read_only: 1
				},
				{
					fieldname: "action",
					fieldtype: "Select",
					label: __("Action"),
					options: "Approved\nEdited & Approved\nRejected\nSent Back for Re-estimation",
					reqd: 1
				},
				{
					fieldname: "new_amount",
					fieldtype: "Currency",
					label: __("Final Amount"),
					depends_on: "eval:doc.action=='Edited & Approved'"
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Remarks")
				}
			],
			primary_action_label: __("Submit"),
			primary_action: function(values) {
				frappe.call({
					method: "rkg.rkg.doctype.damage_assessment.damage_assessment.approve_as_sales_manager",
					args: {
						docname: frm.doc.name,
						action: values.action,
						amount: values.new_amount,
						remarks: values.remarks
					},
					callback: function(r) {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({
								message: r.message.message,
								indicator: "green"
							});
							frm.reload_doc();
						}
					}
				});
				d.hide();
			}
		});
		d.show();
	},
	
	show_recoupment_dialog(frm) {
		let d = new frappe.ui.Dialog({
			title: __("Record Recoupment"),
			fields: [
				{
					fieldname: "approved_amount",
					fieldtype: "Currency",
					label: __("Approved Amount"),
					default: frm.doc.final_approved_amount,
					read_only: 1
				},
				{
					fieldname: "amount",
					fieldtype: "Currency",
					label: __("Amount to Deduct"),
					default: frm.doc.final_approved_amount,
					reqd: 1
				},
				{
					fieldname: "method",
					fieldtype: "Select",
					label: __("Deduction Method"),
					options: "Salary Deduction\nCash Collection\nBank Transfer\nJournal Entry",
					reqd: 1
				},
				{
					fieldname: "journal_entry",
					fieldtype: "Link",
					label: __("Journal Entry"),
					options: "Journal Entry",
					depends_on: "eval:doc.method=='Journal Entry'"
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Remarks")
				}
			],
			primary_action_label: __("Record Recoupment"),
			primary_action: function(values) {
				frappe.call({
					method: "rkg.rkg.doctype.damage_assessment.damage_assessment.record_recoupment",
					args: {
						docname: frm.doc.name,
						amount: values.amount,
						method: values.method,
						journal_entry: values.journal_entry,
						remarks: values.remarks
					},
					callback: function(r) {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({
								message: r.message.message,
								indicator: "green"
							});
							frm.reload_doc();
						}
					}
				});
				d.hide();
			}
		});
		d.show();
	},
	
	show_repair_dialog(frm) {
		let d = new frappe.ui.Dialog({
			title: __("Record Repair Completion"),
			fields: [
				{
					fieldname: "estimated_amount",
					fieldtype: "Currency",
					label: __("Approved/Estimated Amount"),
					default: frm.doc.final_approved_amount,
					read_only: 1
				},
				{
					fieldname: "actual_cost",
					fieldtype: "Currency",
					label: __("Actual Repair Cost"),
					reqd: 1
				},
				{
					fieldname: "repaired_by",
					fieldtype: "Data",
					label: __("Repaired By (Technician/Vendor)")
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Repair Remarks")
				}
			],
			primary_action_label: __("Record Completion"),
			primary_action: function(values) {
				frappe.call({
					method: "rkg.rkg.doctype.damage_assessment.damage_assessment.record_repair_completion",
					args: {
						docname: frm.doc.name,
						actual_cost: values.actual_cost,
						repaired_by: values.repaired_by,
						remarks: values.remarks
					},
					callback: function(r) {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({
								message: r.message.message,
								indicator: "green"
							});
							frm.reload_doc();
						}
					}
				});
				d.hide();
			}
		});
		d.show();
	},
	
	show_settlement_dialog(frm) {
		let diff = frm.doc.difference_amount || 0;
		let default_action = diff > 0 ? "Refund to Delivery Person" : (diff < 0 ? "Charge Extra from Delivery Person" : "Absorb by Company");
		
		let d = new frappe.ui.Dialog({
			title: __("Record Settlement"),
			fields: [
				{
					fieldname: "approved_amount",
					fieldtype: "Currency",
					label: __("Approved Amount"),
					default: frm.doc.final_approved_amount,
					read_only: 1
				},
				{
					fieldname: "actual_cost",
					fieldtype: "Currency",
					label: __("Actual Repair Cost"),
					default: frm.doc.actual_repair_cost,
					read_only: 1
				},
				{
					fieldname: "difference",
					fieldtype: "Currency",
					label: __("Difference (+ = Refund, - = Charge)"),
					default: diff,
					read_only: 1
				},
				{
					fieldname: "action",
					fieldtype: "Select",
					label: __("Settlement Action"),
					options: "Refund to Delivery Person\nAbsorb by Company\nCharge Extra from Delivery Person",
					default: default_action,
					reqd: 1
				},
				{
					fieldname: "journal_entry",
					fieldtype: "Link",
					label: __("Journal Entry (if applicable)"),
					options: "Journal Entry"
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Settlement Remarks")
				}
			],
			primary_action_label: __("Record Settlement"),
			primary_action: function(values) {
				frappe.call({
					method: "rkg.rkg.doctype.damage_assessment.damage_assessment.record_settlement",
					args: {
						docname: frm.doc.name,
						action: values.action,
						journal_entry: values.journal_entry,
						remarks: values.remarks
					},
					callback: function(r) {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({
								message: r.message.message,
								indicator: "green"
							});
							frm.reload_doc();
						}
					}
				});
				d.hide();
			}
		});
		d.show();
	},
	
	show_return_dialog(frm) {
		// Build list of items to return
		let items_html = "";
		if (frm.doc.damage_assessment_item) {
			frm.doc.damage_assessment_item.forEach(function(item) {
				items_html += `<li><strong>${item.serial_no}</strong> - ${item.item_code} (${item.type_of_damage})</li>`;
			});
		}
		
		let d = new frappe.ui.Dialog({
			title: __("Return Items to Stores"),
			fields: [
				{
					fieldname: "info_html",
					fieldtype: "HTML",
					options: `
						<div class="alert alert-info">
							<strong>Items to be returned:</strong>
							<ul style="margin-top: 10px;">${items_html}</ul>
							<hr>
							<p><strong>From:</strong> ${frm.doc.to_warehouse} (Damage Godown)</p>
							<p><strong>To:</strong> ${frm.doc.from_warehouse} (Stores)</p>
						</div>
					`
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Return Remarks")
				}
			],
			primary_action_label: __("Create Return Stock Entry"),
			primary_action: function(values) {
				frappe.call({
					method: "rkg.rkg.doctype.damage_assessment.damage_assessment.return_to_stores",
					args: {
						docname: frm.doc.name,
						remarks: values.remarks
					},
					callback: function(r) {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({
								message: r.message.message,
								indicator: "green"
							});
							frm.reload_doc();
						}
					}
				});
				d.hide();
			}
		});
		d.show();
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
		
		// Clear serial_no when item_code changes to avoid mismatch
		frappe.model.set_value(cdt, cdn, "serial_no", "");
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
		} else {
			frappe.model.set_value(cdt, cdn, "damaged_qty", 0);
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
