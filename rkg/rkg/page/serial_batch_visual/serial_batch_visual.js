frappe.pages["serial-batch-visual"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Frame Visual Dashboard",
		single_column: true,
	});

	// Add custom styles
	$(`<style>
		.serial-batch-dashboard {
			padding: 20px;
			background: var(--bg-color);
		}
		.dashboard-header {
			margin-bottom: 30px;
		}
		.summary-cards {
			display: grid;
			grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
			gap: 20px;
			margin-bottom: 30px;
		}
		.summary-card {
			background: linear-gradient(135deg, var(--card-bg) 0%, var(--control-bg) 100%);
			border-radius: 12px;
			padding: 24px;
			box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
			border-left: 4px solid;
			transition: transform 0.2s ease, box-shadow 0.2s ease;
		}
		.summary-card:hover {
			transform: translateY(-2px);
			box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
		}
		.summary-card.items { border-left-color: #5e64ff; }
		.summary-card.serials { border-left-color: #00d4aa; }
		.summary-card.warehouses { border-left-color: #ff6b6b; }
		.summary-card .card-icon {
			font-size: 28px;
			margin-bottom: 10px;
		}
		.summary-card.items .card-icon { color: #5e64ff; }
		.summary-card.serials .card-icon { color: #00d4aa; }
		.summary-card.warehouses .card-icon { color: #ff6b6b; }
		.summary-card .card-value {
			font-size: 36px;
			font-weight: 700;
			color: var(--heading-color);
			margin-bottom: 5px;
		}
		.summary-card .card-label {
			font-size: 14px;
			color: var(--text-muted);
			text-transform: uppercase;
			letter-spacing: 1px;
		}
		.charts-section {
			display: grid;
			grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
			gap: 25px;
			margin-bottom: 30px;
			overflow-x: hidden;
		}
		.chart-container {
			background: var(--card-bg);
			border-radius: 12px;
			padding: 24px;
			box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
			min-height: 300px;
		}
		#warehouse-bar-chart {
			position: relative;
			width: 100%;
			min-height: 200px;
		}
		.warehouse-bar-chart-container {
			display: flex;
			flex-direction: column;
			gap: 12px;
			padding: 10px 0;
		}
		.warehouse-bar-item {
			display: grid;
			grid-template-columns: 200px 1fr;
			gap: 15px;
			align-items: center;
		}
		.warehouse-label {
			font-size: 13px;
			font-weight: 500;
			color: var(--heading-color);
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			min-width: 0;
		}
		.warehouse-bar-wrapper {
			position: relative;
			height: 32px;
			background: var(--bg-light-gray);
			border-radius: 6px;
			overflow: hidden;
			display: flex;
			align-items: center;
		}
		.warehouse-bar {
			height: 100%;
			background: linear-gradient(90deg, #5e64ff 0%, #7c83ff 100%);
			border-radius: 6px;
			display: flex;
			align-items: center;
			justify-content: flex-end;
			padding-right: 10px;
			min-width: 40px;
			transition: width 0.3s ease;
			position: relative;
		}
		.warehouse-bar:hover {
			background: linear-gradient(90deg, #4a52d4 0%, #6b72e6 100%);
		}
		.warehouse-value {
			color: white;
			font-weight: 600;
			font-size: 12px;
			white-space: nowrap;
		}
		@media (max-width: 768px) {
			.warehouse-bar-item {
				grid-template-columns: 150px 1fr;
			}
		}
		.chart-title {
			font-size: 16px;
			font-weight: 600;
			color: var(--heading-color);
			margin-bottom: 20px;
			display: flex;
			align-items: center;
			gap: 10px;
		}
		.chart-title i {
			color: var(--primary);
		}
		.tree-section {
			background: var(--card-bg);
			border-radius: 12px;
			padding: 24px;
			box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
		}
		.tree-header {
			font-size: 18px;
			font-weight: 600;
			color: var(--heading-color);
			margin-bottom: 20px;
			display: flex;
			align-items: center;
			justify-content: space-between;
		}
		.item-group {
			border: 1px solid var(--border-color);
			border-radius: 8px;
			margin-bottom: 10px;
			overflow: hidden;
		}
		.item-group-header {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 15px 20px;
			background: var(--control-bg);
			cursor: pointer;
			transition: background 0.2s ease;
		}
		.item-group-header:hover {
			background: var(--bg-light-gray);
		}
		.item-group-header .toggle-icon {
			transition: transform 0.3s ease;
			color: var(--text-muted);
		}
		.item-group-header.expanded .toggle-icon {
			transform: rotate(90deg);
		}
		.item-info {
			display: flex;
			align-items: center;
			gap: 15px;
		}
		.item-code {
			font-weight: 600;
			color: var(--heading-color);
		}
		.item-name {
			color: var(--text-muted);
			font-size: 13px;
		}
		.serial-count {
			background: var(--primary);
			color: white;
			padding: 4px 12px;
			border-radius: 20px;
			font-size: 12px;
			font-weight: 600;
		}
		.warehouse-badges {
			display: flex;
			gap: 5px;
		}
		.warehouse-badge {
			padding: 3px 10px;
			border-radius: 12px;
			font-size: 11px;
			font-weight: 500;
		}
		.warehouse-badge.green { background: #d4edda; color: #155724; }
		.warehouse-badge.yellow { background: #fff3cd; color: #856404; }
		.warehouse-badge.red { background: #f8d7da; color: #721c24; }
		.warehouse-badge.blue { background: #cce5ff; color: #004085; }
		.serial-list {
			display: none;
			padding: 0;
			max-height: 400px;
			overflow-y: auto;
		}
		.serial-list.expanded {
			display: block;
		}
		.serial-item {
			display: grid;
			grid-template-columns: 2fr 1.5fr 1fr 1.5fr;
			padding: 12px 20px;
			border-bottom: 1px solid var(--border-color);
			font-size: 13px;
			transition: background 0.2s ease;
		}
		.serial-item:hover {
			background: var(--bg-light-gray);
		}
		.serial-item:last-child {
			border-bottom: none;
		}
		.serial-item .serial-no {
			font-family: monospace;
			color: var(--primary);
			font-weight: 500;
		}
		.serial-item .warehouse {
			color: var(--text-muted);
		}
		.serial-item .status {
			font-weight: 500;
		}
		.serial-item .status.active { color: #28a745; }
		.serial-item .status.delivered { color: #6c757d; }
		.serial-item .document {
			color: var(--text-muted);
		}
		.filters-section {
			background: var(--card-bg);
			border-radius: 12px;
			padding: 20px;
			margin-bottom: 25px;
			box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
		}
		.filters-grid {
			display: grid;
			grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
			gap: 15px;
			align-items: end;
		}
		.filter-group label {
			display: block;
			font-size: 12px;
			font-weight: 600;
			color: var(--text-muted);
			margin-bottom: 5px;
			text-transform: uppercase;
		}
		.filter-actions {
			display: flex;
			gap: 10px;
		}
		.loading-overlay {
			position: fixed;
			top: 0;
			left: 0;
			right: 0;
			bottom: 0;
			background: rgba(255,255,255,0.8);
			display: flex;
			align-items: center;
			justify-content: center;
			z-index: 9999;
		}
		.no-data {
			text-align: center;
			padding: 60px 20px;
			color: var(--text-muted);
		}
		.no-data i {
			font-size: 48px;
			margin-bottom: 15px;
			opacity: 0.5;
		}
	</style>`).appendTo("head");

	// Store page reference
	page.serial_batch_visual = new SerialBatchVisual(page);
};

frappe.pages["serial-batch-visual"].on_page_show = function (wrapper) {
	// Refresh data when page is shown
	if (wrapper.page.serial_batch_visual) {
		wrapper.page.serial_batch_visual.refresh();
	}
};

class SerialBatchVisual {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.filters = {};
		this.charts = {};
		
		this.init();
	}

	init() {
		this.render_layout();
		this.setup_filters();
		this.load_filter_options();
		this.refresh();
	}

	render_layout() {
		this.wrapper.html(`
			<div class="serial-batch-dashboard">
				<!-- Filters Section -->
				<div class="filters-section">
					<div class="filters-grid">
						<div class="filter-group">
							<label>Company</label>
							<select class="form-control filter-company"></select>
						</div>
						<div class="filter-group">
							<label>Warehouse</label>
							<select class="form-control filter-warehouse">
								<option value="">All Warehouses</option>
							</select>
						</div>
						<div class="filter-group">
							<label>Status</label>
							<select class="form-control filter-status">
								<option value="">All Statuses</option>
							</select>
						</div>
						<div class="filter-group">
							<label>From Date</label>
							<input type="date" class="form-control filter-from-date">
						</div>
						<div class="filter-group">
							<label>To Date</label>
							<input type="date" class="form-control filter-to-date">
						</div>
						<div class="filter-group filter-actions">
							<button class="btn btn-primary btn-refresh">
								<i class="fa fa-refresh"></i> Refresh
							</button>
							<button class="btn btn-default btn-clear">
								<i class="fa fa-times"></i> Clear
							</button>
						</div>
					</div>
				</div>

				<!-- Summary Cards -->
				<div class="summary-cards">
					<div class="summary-card items">
						<div class="card-icon"><i class="fa fa-cube"></i></div>
						<div class="card-value" id="total-items">0</div>
						<div class="card-label">Total Items</div>
					</div>
					<div class="summary-card serials">
						<div class="card-icon"><i class="fa fa-barcode"></i></div>
						<div class="card-value" id="total-serials">0</div>
						<div class="card-label">Frame Number</div>
					</div>
					<div class="summary-card warehouses">
						<div class="card-icon"><i class="fa fa-warehouse"></i></div>
						<div class="card-value" id="total-warehouses">0</div>
						<div class="card-label">Warehouses</div>
					</div>
				</div>

				<!-- Charts Section -->
				<div class="charts-section">
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-bar-chart"></i> Frame Count by Item Code
						</div>
						<div id="item-bar-chart"></div>
					</div>
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-bar-chart"></i> Distribution by Warehouse
						</div>
						<div id="warehouse-bar-chart"></div>
					</div>
				</div>

				<!-- Frame Aging Table -->
				<div class="tree-section">
					<div class="tree-header">
						<span><i class="fa fa-table"></i> Aging Summary</span>
					</div>
					<div id="aging-summary-table"></div>
				</div>

				<div class="tree-section">
					<div class="tree-header">
						<span><i class="fa fa-list"></i> Frame Aging</span>
					</div>
					<div id="frame-aging-table"></div>
				</div>

				<!-- Tree View Section -->
				<div class="tree-section">
					<div class="tree-header">
						<span><i class="fa fa-sitemap"></i> Frame Numbers By Item Code</span>
						<button class="btn btn-xs btn-default btn-expand-all">
							<i class="fa fa-expand"></i> Expand All
						</button>
					</div>
					<div id="item-tree-container"></div>
				</div>
			</div>
		`);
	}

	setup_filters() {
		const me = this;

		// Set default dates (last 30 days)
		const today = frappe.datetime.get_today();
		const thirtyDaysAgo = frappe.datetime.add_days(today, -30);
		
		this.wrapper.find(".filter-from-date").val(thirtyDaysAgo);
		this.wrapper.find(".filter-to-date").val(today);

		// Refresh button
		this.wrapper.find(".btn-refresh").on("click", function () {
			me.refresh();
		});

		// Clear button
		this.wrapper.find(".btn-clear").on("click", function () {
			me.wrapper.find(".filter-warehouse").val("");
			me.wrapper.find(".filter-status").val("");
			me.wrapper.find(".filter-from-date").val(thirtyDaysAgo);
			me.wrapper.find(".filter-to-date").val(today);
			me.refresh();
		});

		// Expand all button
		this.wrapper.find(".btn-expand-all").on("click", function () {
			const isExpanded = $(this).hasClass("expanded");
			if (isExpanded) {
				me.wrapper.find(".item-group-header").removeClass("expanded");
				me.wrapper.find(".serial-list").removeClass("expanded");
				$(this).removeClass("expanded").html('<i class="fa fa-expand"></i> Expand All');
			} else {
				me.wrapper.find(".item-group-header").addClass("expanded");
				me.wrapper.find(".serial-list").addClass("expanded");
				$(this).addClass("expanded").html('<i class="fa fa-compress"></i> Collapse All');
			}
		});
	}

	load_filter_options() {
		const me = this;

		frappe.call({
			method: "rkg.rkg.page.serial_batch_visual.serial_batch_visual.get_filter_options",
			callback: function (r) {
				if (r.message) {
					// Populate company dropdown
					const companySelect = me.wrapper.find(".filter-company");
					companySelect.html('<option value="">All Companies</option>');
					r.message.companies.forEach(function (company) {
						companySelect.append(`<option value="${company}">${company}</option>`);
					});

					// Populate warehouse dropdown
					const warehouseSelect = me.wrapper.find(".filter-warehouse");
					warehouseSelect.html('<option value="">All Warehouses</option>');
					r.message.warehouses.forEach(function (warehouse) {
						warehouseSelect.append(`<option value="${warehouse}">${warehouse}</option>`);
					});

					// Populate status dropdown
					const statusSelect = me.wrapper.find(".filter-status");
					statusSelect.html('<option value="">All Statuses</option>');
					if (r.message.statuses) {
						r.message.statuses.forEach(function (status) {
							statusSelect.append(`<option value="${status}">${status}</option>`);
						});
					}
				}
			},
		});
	}

	refresh() {
		const me = this;

		// Get filter values
		const filters = {
			company: this.wrapper.find(".filter-company").val(),
			warehouse: this.wrapper.find(".filter-warehouse").val(),
			status: this.wrapper.find(".filter-status").val(),
			from_date: this.wrapper.find(".filter-from-date").val(),
			to_date: this.wrapper.find(".filter-to-date").val(),
		};

		// Show loading
		frappe.show_progress("Loading", 30, 100, "Fetching data...");

		// Fetch main data
		frappe.call({
			method: "rkg.rkg.page.serial_batch_visual.serial_batch_visual.get_serial_batch_data",
			args: filters,
			callback: function (r) {
				frappe.show_progress("Loading", 60, 100, "Rendering charts...");
				
				if (r.message) {
					me.render_summary(r.message.summary);
					me.render_item_chart(r.message.by_item);
					me.render_warehouse_chart(r.message.by_warehouse);
					me.render_aging_summary(r.message.by_age_bucket);
					me.render_frame_table(r.message.raw_data);
				}

				// Fetch grouped data for tree view
				me.load_tree_data(filters);
			},
			error: function () {
				frappe.hide_progress();
				frappe.msgprint(__("Error loading data. Please try again."));
			},
		});
	}

	load_tree_data(filters) {
		const me = this;

		frappe.call({
			method: "rkg.rkg.page.serial_batch_visual.serial_batch_visual.get_grouped_serial_data",
			args: {
				company: filters.company,
				warehouse: filters.warehouse,
				status: filters.status,
				from_date: filters.from_date,
				to_date: filters.to_date,
			},
			callback: function (r) {
				frappe.show_progress("Loading", 100, 100, "Complete!");
				setTimeout(() => frappe.hide_progress(), 500);

				if (r.message) {
					me.render_tree_view(r.message);
				}
			},
		});
	}

	render_summary(summary) {
		this.wrapper.find("#total-items").text(summary.total_items || 0);
		this.wrapper.find("#total-serials").text(summary.total_serials || 0);
		this.wrapper.find("#total-warehouses").text(summary.total_warehouses || 0);
	}

	render_item_chart(data) {
		const container = this.wrapper.find("#item-bar-chart")[0];
		
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html('<div class="no-data"><i class="fa fa-bar-chart"></i><p>No data available</p></div>');
			return;
		}

		// Clear previous chart
		$(container).empty();

		// Create bar chart using Frappe Charts
		this.charts.itemChart = new frappe.Chart(container, {
			title: "",
			data: {
				labels: data.labels,
				datasets: [
					{
						name: "Serial Count",
						values: data.values,
					},
				],
			},
			type: "bar",
			height: 300,
			colors: ["#5e64ff"],
			barOptions: {
				spaceRatio: 0.4,
			},
			axisOptions: {
				xAxisMode: "tick",
				xIsSeries: true,
			},
		});
	}

	render_warehouse_chart(data) {
		const container = this.wrapper.find("#warehouse-bar-chart");
		
		if (!container.length) {
			console.error("Warehouse chart container not found");
			return;
		}
		
		if (!data || !data.labels || data.labels.length === 0) {
			container.html('<div class="no-data"><i class="fa fa-bar-chart"></i><p>No data available</p></div>');
			return;
		}

		// Validate data integrity
		if (!data.values || data.values.length !== data.labels.length) {
			console.error("Warehouse chart data mismatch: labels and values length don't match");
			container.html('<div class="no-data"><i class="fa fa-bar-chart"></i><p>Data format error</p></div>');
			return;
		}

		// Clear previous chart - destroy existing chart if it exists
		if (this.charts.warehouseChart) {
			try {
				this.charts.warehouseChart.destroy();
			} catch (e) {
				// Ignore errors if chart doesn't have destroy method
			}
		}
		container.empty();

		// Use full warehouse names
		const labels = data.labels || [];
		const values = data.values || [];
		
		// Find max value for percentage calculation
		const maxValue = Math.max(...values, 1);
		
		// Create custom horizontal bar chart HTML
		let chartHTML = '<div class="warehouse-bar-chart-container">';
		
		labels.forEach((label, index) => {
			const value = values[index];
			const percentage = (value / maxValue) * 100;
			
			chartHTML += `
				<div class="warehouse-bar-item">
					<div class="warehouse-label" title="${label}">${label}</div>
					<div class="warehouse-bar-wrapper">
						<div class="warehouse-bar" style="width: ${percentage}%">
							<span class="warehouse-value">${value}</span>
						</div>
					</div>
				</div>
			`;
		});
		
		chartHTML += '</div>';
		container.html(chartHTML);
	}

	render_frame_table(data) {
		const container = this.wrapper.find("#frame-aging-table");
		container.empty();

		if (!data || data.length === 0) {
			container.html('<div class="no-data"><i class="fa fa-list"></i><p>No serial numbers found</p></div>');
			return;
		}

		// Limit rows to 200 to keep UI light
		const rows = data.slice(0, 200);
		const table = $(`
			<div class="serial-list" style="display:block; max-height:400px; overflow:auto; padding:0;">
				<div class="serial-item" style="font-weight:600; background: var(--bg-light-gray); grid-template-columns: 1.5fr 1fr 1fr 1fr 0.8fr;">
					<div>Frame No</div>
					<div>Item Code</div>
					<div>Warehouse</div>
					<div>Age Bucket</div>
					<div>Age (days)</div>
				</div>
				${rows
					.map(
						(r) => `
						<div class="serial-item" style="grid-template-columns: 1.5fr 1fr 1fr 1fr 0.8fr;">
							<div class="serial-no">${r.serial_no || ""}</div>
							<div>${r.item_code || "-"}</div>
							<div class="warehouse">${r.warehouse || "-"}</div>
							<div>${r.age_bucket || "-"}</div>
							<div>${typeof r.age_days === "number" ? r.age_days : "-"}</div>
						</div>
					`
					)
					.join("")}
				${data.length > 200 ? `<div class="serial-item" style="justify-content:center; color: var(--text-muted);">
					<em>... and ${data.length - 200} more</em>
				</div>` : ""}
			</div>
		`);

		container.append(table);
	}

	render_aging_summary(data) {
		const container = this.wrapper.find("#aging-summary-table");
		container.empty();

		if (!data || !data.labels || data.labels.length === 0) {
			container.html('<div class="no-data"><i class="fa fa-table"></i><p>No data available</p></div>');
			return;
		}

		const rows = data.labels.map((label, idx) => {
			const value = Array.isArray(data.values) ? data.values[idx] : 0;
			return `
				<div class="serial-item" style="grid-template-columns: 1fr 0.5fr;">
					<div>${label}</div>
					<div>${value}</div>
				</div>
			`;
		}).join("");

		const table = $(`
			<div class="serial-list" style="display:block; max-height:240px; overflow:auto; padding:0;">
				<div class="serial-item" style="font-weight:600; background: var(--bg-light-gray); grid-template-columns: 1fr 0.5fr;">
					<div>Period (days)</div>
					<div>No. of Frames</div>
				</div>
				${rows}
			</div>
		`);

		container.append(table);
	}

	render_tree_view(data) {
		const container = this.wrapper.find("#item-tree-container");
		container.empty();

		if (!data || data.length === 0) {
			container.html('<div class="no-data"><i class="fa fa-sitemap"></i><p>No serial numbers found</p></div>');
			return;
		}

		const me = this;

		data.forEach(function (item) {
			const warehouseBadges = me.get_warehouse_badges(item.warehouses);
			
			const itemGroup = $(`
				<div class="item-group">
					<div class="item-group-header">
						<div class="item-info">
							<i class="fa fa-chevron-right toggle-icon"></i>
							<div>
								<div class="item-code">${item.item_code}</div>
								<div class="item-name">${item.item_name || ""}</div>
							</div>
						</div>
						<div style="display: flex; align-items: center; gap: 15px;">
							<div class="warehouse-badges">${warehouseBadges}</div>
							<span class="serial-count">${item.count} serials</span>
						</div>
					</div>
					<div class="serial-list">
						<div class="serial-item" style="font-weight: 600; background: var(--bg-light-gray);">
							<div>Serial No</div>
							<div>Warehouse</div>
							<div>Status</div>
							<div>Age (days)</div>
						</div>
						${me.render_serial_items(item.serials)}
					</div>
				</div>
			`);

			// Toggle expand/collapse
			itemGroup.find(".item-group-header").on("click", function () {
				$(this).toggleClass("expanded");
				$(this).siblings(".serial-list").toggleClass("expanded");
			});

			container.append(itemGroup);
		});
	}

	render_serial_items(serials) {
		if (!serials || serials.length === 0) return "";

		// Limit to first 50 to avoid performance issues
		const displaySerials = serials.slice(0, 50);
		const hasMore = serials.length > 50;

		let html = displaySerials
			.map(
				(s) => `
			<div class="serial-item">
				<div class="serial-no">${s.serial_no || ""}</div>
				<div class="warehouse">${s.warehouse || "-"}</div>
				<div class="status ${(s.status || "").toLowerCase()}">${s.status || "-"}</div>
				<div class="document">${typeof s.age_days === "number" ? s.age_days : "-"}</div>
			</div>
		`
			)
			.join("");

		if (hasMore) {
			html += `<div class="serial-item" style="justify-content: center; color: var(--text-muted);">
				<em>... and ${serials.length - 50} more serial numbers</em>
			</div>`;
		}

		return html;
	}

	get_warehouse_badges(warehouses) {
		if (!warehouses || warehouses.length === 0) return "";

		const colorMap = {
			"stores": "green",
			"damage": "red",
			"work in progress": "yellow",
			"wip": "yellow",
		};

		return warehouses
			.map((w) => {
				let color = "blue";
				const lowerW = w.toLowerCase();
				for (const [key, val] of Object.entries(colorMap)) {
					if (lowerW.includes(key)) {
						color = val;
						break;
					}
				}
				// Shorten warehouse name
				const shortName = w.length > 15 ? w.substring(0, 15) + "..." : w;
				return `<span class="warehouse-badge ${color}" title="${w}">${shortName}</span>`;
			})
			.join("");
	}
}

