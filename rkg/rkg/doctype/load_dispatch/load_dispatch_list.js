frappe.listview_settings["Load Dispatch"] = {
	get_indicator: function (doc) {
		// Status options (from doctype):
		// In-Transit, Received

		if (doc.status === "Received") {
			// Received → green
			return [__("Received"), "green", "status,=,Received"];
		}

		if (doc.status === "In-Transit") {
			// In transit → blue
			return [__("In-Transit"), "blue", "status,=,In-Transit"];
		}

		// Default indicator for other / empty statuses
		//return [__(doc.status || ""), "gray", "status,=," + (doc.status || "")];
	},
};


