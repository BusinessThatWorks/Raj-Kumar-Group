frappe.listview_settings["Load Plan"] = {
	get_indicator: function (doc) {
		// Status options (from doctype):
		// Submitted, In-Transit, Dispatched, Partial Dispatched

		if (doc.status === "Dispatched") {
			// Delivered → green
			return [__("Dispatched"), "green", "status,=,Dispatched"];
		}

		if (doc.status === "Not Dispatched") {
			// Partial delivered → orange
			return [__("Not Dispatched"), "orange", "status,=,Not Dispatched"];
		}

		if (doc.status === "In-Transit") {
			// In transit → blue (or any other color you prefer)
			return [__("In-Transit"), "blue", "status,=,In-Transit"];
		}

		// Default indicator for other statuses (e.g. Submitted)
		//return [__(doc.status || ""), "gray", "status,=," + (doc.status || "Submitted")];
	},
};