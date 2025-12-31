// Serial No Dashboard Page
frappe.pages["serial-no-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Serial No Dashboard",
		single_column: true,
	});

	// Simple placeholder content
	$(page.body).html(`
		<div style="padding: 20px; text-align: center;">
			<h2>Serial No Dashboard</h2>
			<p>This page is under construction.</p>
			<p>You can access the <a href="/app/frame-no-dashboard">Frame No Dashboard</a> for frame-related information.</p>
		</div>
	`);
};

