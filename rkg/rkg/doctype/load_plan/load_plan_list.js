frappe.listview_settings["Load Plan"] = {
	add_fields: ["date", "dispatch_plan_date", "status"],

	get_indicator: function (doc) {
		// FINAL STATUS PRIORITY
		// 1. Received      → PR exists
		// 2. In-Transit    → LD exists
		// 3. Planned       → dispatch_plan_date > today
		// 4. Submit        → default

		// Normalize legacy statuses
		const legacy_received = ["Dispatched", "Partial Dispatched"];

		if (doc.status === "Received" || legacy_received.includes(doc.status)) {
			return [__("Received"), "green", "status,=,Received"];
		}

		if (doc.status === "In-Transit") {
			return [__("In-Transit"), "blue", "status,=,In-Transit"];
		}

		// Planned only when dispatch_plan_date is in future
		if (doc.dispatch_plan_date) {
			const today = frappe.datetime.get_today();
			if (doc.dispatch_plan_date > today) {
				return [__("Planned"), "yellow", "status,=,Planned"];
			}
		}

		if (doc.status === "Submit") {
			return [__("Submit"), "", "status,=,Submit"];
		}

		// Default fallback
	},

	onload: function (listview) {

		// Manual refresh button
		listview.page.add_inner_button(__("Refresh Status"), function () {
			const load_plan_names = (listview.data || [])
				.map(row => row.name)
				.filter(Boolean);

			if (!load_plan_names.length) return;

			frappe.call({
				method: "rkg.rkg.doctype.load_plan.load_plan.batch_update_load_plan_status",
				args: { load_plan_names },
				callback: function (r) {
					if (r.message?.updated) {
						frappe.show_alert(
							__("Status updated for {0} Load Plans", [r.message.updated]),
							3
						);
						listview.refresh();
					}
				}
			});
		});

		// Auto-fix legacy statuses silently
		const legacy_rows = (listview.data || []).filter(row =>
			["Dispatched", "Partial Dispatched"].includes(row.status)
		);

		if (legacy_rows.length) {
			const names = legacy_rows.map(row => row.name).filter(Boolean);

			frappe.call({
				method: "rkg.rkg.doctype.load_plan.load_plan.batch_update_load_plan_status",
				args: { load_plan_names: names },
				callback: function (r) {
					if (r.message?.updated) {
						listview.refresh();
					}
				}
			});
		}
	}
};
