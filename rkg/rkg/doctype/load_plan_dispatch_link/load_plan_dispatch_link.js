frappe.ui.form.on("Load Plan Dispatch Link", {
	load_dispatch(frm, cdt, cdn) {
		// Make the load_dispatch field clickable to open the dispatch document
		const row = locals[cdt][cdn];
		if (row.load_dispatch) {
			// This will be handled by Frappe's default link behavior
			// But we can add custom behavior if needed
		}
	}
});


