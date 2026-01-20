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

		// Any other status (including Submit/Submitted) should show as Planned
		return [__("Planned"), "yellow", "status,=,Planned"];
	},

	onload: function (listview) {

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
