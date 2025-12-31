frappe.pages['serial-batch-visual'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Serial Batch Visual',
		single_column: true
	});

	// Demo page - redirects to Frame No Dashboard
	$(page.body).html(`
		<div style="padding: 40px; text-align: center;">
			<div style="max-width: 600px; margin: 0 auto;">
				<h2 style="color: #2e7d32; margin-bottom: 20px;">
					<i class="fa fa-barcode" style="margin-right: 10px;"></i>
					Serial Batch Visual
				</h2>
				<p style="font-size: 16px; color: #666; margin-bottom: 30px;">
					This page is a demo placeholder. For serial batch visualization, please use the Frame No Dashboard.
				</p>
				<button class="btn btn-primary btn-lg" onclick="window.location.href='/app/frame-no-dashboard'" style="padding: 12px 30px; font-size: 16px;">
					<i class="fa fa-arrow-right" style="margin-right: 8px;"></i>
					Go to Frame No Dashboard
				</button>
			</div>
		</div>
	`);
}