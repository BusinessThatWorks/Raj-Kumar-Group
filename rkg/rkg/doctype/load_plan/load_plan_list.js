frappe.listview_settings["Load Plan"] = {
	get_indicator: function (doc) {
		// Status options: Dispatched, Not Dispatched, In-Transit

		if (doc.status === "Dispatched") {
			// Dispatched → green
			return [__("Dispatched"), "green", "status,=,Dispatched"];
		}

		if (doc.status === "Not Dispatched" || doc.status === "Partial Dispatched") {
			// Not Dispatched → orange (handle both old "Partial Dispatched" and new "Not Dispatched")
			return [__("Not Dispatched"), "orange", "status,=,Not Dispatched"];
		}

		if (doc.status === "In-Transit" || doc.status === "Submitted" || !doc.status) {
			// In-Transit → blue (also handle Submitted/empty as In-Transit since nothing dispatched yet)
			return [__("In-Transit"), "blue", "status,=,In-Transit"];
		}
	},
};