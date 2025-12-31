// Serial Batch Visual Page
frappe.pages["serial-batch-visual"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Serial Batch Visual",
		single_column: true,
	});

	// Simple placeholder content
	$(page.body).html(`
		<div style="padding: 20px; text-align: center;">
			<h2>Serial Batch Visual</h2>
			<p>This page is under construction.</p>
			<p>You can access the <a href="/app/frame-no-dashboard">Frame No Dashboard</a> for frame-related information.</p>
		</div>
	`);
};

