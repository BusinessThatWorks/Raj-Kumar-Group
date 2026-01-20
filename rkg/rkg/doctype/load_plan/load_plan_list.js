frappe.listview_settings["Load Plan"] = {
	add_fields: ["date", "dispatch_plan_date", "status"],
	
	get_indicator: function (doc) {
		// Status priority:
		// 1. If Purchase Receipt exists for LD which belongs to LP: Status = "Received"
		// 2. If Load Dispatch exists for LP: Status = "In-Transit"
		// 3. If dispatch_plan_date exists (any date): Status = "Planned"
		// 4. Otherwise: Default to "Planned"

		// Check status from document (may have been updated by server-side logic)
		// Status options: Planned, Received, In-Transit, Dispatched, Partial Dispatched
		
		if (doc.status === "Received") {
			return [__("Received"), "green", "status,=,Received"];
		}

		if (doc.status === "In-Transit") {
			return [__("In-Transit"), "blue", "status,=,In-Transit"];
		}

		if (doc.status === "Dispatched") {
			return [__("Dispatched"), "green", "status,=,Dispatched"];
		}

		if (doc.status === "Partial Dispatched") {
			return [__("Partial Dispatched"), "orange", "status,=,Partial Dispatched"];
		}

		// If dispatch_plan_date exists, it should be "Planned"
		// Default: Planned (if dispatch_plan_date exists or as fallback)
		if (doc.dispatch_plan_date) {
			return [__("Planned"), "yellow", "status,=,Planned"];
		}

		// Default: Planned
		return [__("Planned"), "yellow", "status,=,Planned"];
	},
	
	onload: function(listview) {
		// Update status for all visible Load Plans based on LD and PR existence
		// This runs after the list is loaded and can update statuses asynchronously
		listview.page.add_inner_button(__("Refresh Status"), function() {
			frappe.show_progress(__("Refreshing Status"), 0, listview.data.length);
			
			const load_plan_names = listview.data.map(row => row.name || row.load_reference_no).filter(Boolean);
			
			if (load_plan_names.length === 0) {
				frappe.hide_progress();
				return;
			}
			
			frappe.call({
				method: "rkg.rkg.doctype.load_plan.load_plan.batch_update_load_plan_status",
				args: {
					load_plan_names: load_plan_names
				},
				callback: function(r) {
					frappe.hide_progress();
					if (r.message) {
						frappe.show_alert({
							message: __("Status updated for {0} Load Plans", [r.message.updated || 0]),
							indicator: "green"
						}, 3);
						listview.refresh();
					}
				},
				error: function(err) {
					frappe.hide_progress();
					console.error("Error updating Load Plan status:", err);
				}
			});
		});
	}
};