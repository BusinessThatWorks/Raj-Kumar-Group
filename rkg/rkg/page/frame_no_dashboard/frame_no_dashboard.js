// Helper function to format numbers
function format_number(value, precision) {
	const num = parseFloat(value) || 0;
	if (precision === 0) {
		return Math.round(num).toString();
	}
	return num.toFixed(precision);
}

frappe.pages["frame-no-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Frame No Dashboard",
		single_column: true,
	});

	add_styles();
	page.frame_no_dashboard = new FrameNoDashboard(page);
};

frappe.pages["frame-no-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.page.frame_no_dashboard) {
		wrapper.page.frame_no_dashboard.refresh();
	}
};

class FrameNoDashboard {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
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
			<div class="frame-no-dashboard">
				<div class="filters-section">
					<div class="filters-grid">
						<div class="filter-group">
							<label>Warehouse</label>
							<select class="form-control filter-warehouse">
								<option value="">All Warehouses</option>
							</select>
						</div>
						<div class="filter-group">
							<label>Item Code</label>
							<select class="form-control filter-item-code">
								<option value="">All Items</option>
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
							<input type="date" class="form-control filter-from-date" />
						</div>
						<div class="filter-group">
							<label>To Date</label>
							<input type="date" class="form-control filter-to-date" />
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

				<div class="summary-cards">
					<div class="summary-card total">
						<div class="card-icon"><i class="fa fa-barcode"></i></div>
						<div class="card-value" id="total-frames">0</div>
						<div class="card-label">Total Frames</div>
					</div>
					<div class="summary-card active">
						<div class="card-icon"><i class="fa fa-check-circle"></i></div>
						<div class="card-value" id="active-frames">0</div>
						<div class="card-label">Active</div>
					</div>
					<div class="summary-card delivered">
						<div class="card-icon"><i class="fa fa-truck"></i></div>
						<div class="card-value" id="delivered-frames">0</div>
						<div class="card-label">Delivered</div>
					</div>
					<div class="summary-card warehouses">
						<div class="card-icon"><i class="fa fa-warehouse"></i></div>
						<div class="card-value" id="total-warehouses">0</div>
						<div class="card-label">Warehouses</div>
					</div>
				</div>

				<div class="charts-section">
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-pie-chart"></i> Status Distribution
						</div>
						<div id="status-chart"></div>
					</div>
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-bar-chart"></i> Warehouse Distribution
						</div>
						<div id="warehouse-chart"></div>
					</div>
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-bar-chart"></i> Item Distribution
						</div>
						<div id="item-chart"></div>
					</div>
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-line-chart"></i> Frames by Date
						</div>
						<div id="date-chart"></div>
					</div>
				</div>

				<div class="frames-section">
					<div class="section-header">
						<span><i class="fa fa-list"></i> Frames</span>
					</div>
					<div id="frames-list"></div>
				</div>

				<!-- Frame No Details Section -->
				<div class="frame-no-details-section" id="frame-no-details-section" style="display: none;">
					<div class="section-header">
						<button class="btn btn-sm btn-default btn-back-to-list" style="margin-right: 10px;">
							<i class="fa fa-arrow-left"></i> Back to List
						</button>
						<span><i class="fa fa-info-circle"></i> Frame No Details</span>
					</div>
					<div id="frame-no-details"></div>
				</div>
			</div>
		`);
	}

	setup_filters() {
		this.wrapper.find(".btn-refresh").on("click", () => this.refresh());
		this.wrapper.find(".btn-clear").on("click", () => {
			this.wrapper.find(".filter-warehouse").val("");
			this.wrapper.find(".filter-item-code").val("");
			this.wrapper.find(".filter-status").val("");
			this.wrapper.find(".filter-from-date").val("");
			this.wrapper.find(".filter-to-date").val("");
			this.refresh();
		});

		// Back to list button
		this.wrapper.find(".btn-back-to-list").on("click", () => {
			this.hide_frame_no_details();
		});
	}

	load_filter_options() {
		frappe.call({
			method: "rkg.rkg.page.frame_no_dashboard.frame_no_dashboard.get_filter_options",
			callback: (r) => {
				if (r.message) {
					// Load warehouses
					if (r.message.warehouses) {
						const select = this.wrapper.find(".filter-warehouse");
						select.empty().append(`<option value="">All Warehouses</option>`);
						r.message.warehouses.forEach((wh) => {
							select.append(`<option value="${wh}">${wh}</option>`);
						});
					}
					// Load item codes
					if (r.message.item_codes) {
						const select = this.wrapper.find(".filter-item-code");
						select.empty().append(`<option value="">All Items</option>`);
						r.message.item_codes.forEach((item) => {
							select.append(`<option value="${item}">${item}</option>`);
						});
					}
					// Load statuses
					if (r.message.statuses) {
						const select = this.wrapper.find(".filter-status");
						select.empty().append(`<option value="">All Statuses</option>`);
						r.message.statuses.forEach((st) => {
							select.append(`<option value="${st}">${st}</option>`);
						});
					}
				}
			},
		});
	}

	refresh() {
		const from_date_val = this.wrapper.find(".filter-from-date").val();
		const to_date_val = this.wrapper.find(".filter-to-date").val();
		
		const filters = {
			warehouse: this.wrapper.find(".filter-warehouse").val() || null,
			item_code: this.wrapper.find(".filter-item-code").val() || null,
			status: this.wrapper.find(".filter-status").val() || null,
			from_date: from_date_val && from_date_val.trim() ? from_date_val : null,
			to_date: to_date_val && to_date_val.trim() ? to_date_val : null,
		};

		frappe.call({
			method: "rkg.rkg.page.frame_no_dashboard.frame_no_dashboard.get_dashboard_data",
			args: filters,
			callback: (r) => {
				if (r.message) {
					this.render_summary(r.message.summary || {});
					this.render_status_chart(r.message.status_chart || {});
					this.render_warehouse_chart(r.message.warehouse_chart || {});
					this.render_item_chart(r.message.item_chart || {});
					this.render_date_chart(r.message.date_chart || {});
					this.render_frames_list(r.message.frames || []);
				} else {
					this.render_summary({});
					this.render_status_chart({});
					this.render_warehouse_chart({});
					this.render_item_chart({});
					this.render_date_chart({});
					this.render_frames_list([]);
				}
			},
			error: (r) => {
				console.error("Error loading dashboard data:", r);
				frappe.msgprint(__("Unable to load dashboard data right now."));
				this.render_summary({});
				this.render_frames_list([]);
			},
		});
	}

	render_summary(summary) {
		const total = summary.total_frames || 0;
		const status_counts = summary.status_counts || {};
		const warehouse_counts = summary.warehouse_counts || {};
		
		// Count active (status = "Active" or "In Stock")
		const active = (status_counts["Active"] || 0) + (status_counts["In Stock"] || 0);
		const delivered = status_counts["Delivered"] || 0;
		const total_warehouses = Object.keys(warehouse_counts).length;

		this.wrapper.find("#total-frames").text(format_number(total, 0));
		this.wrapper.find("#active-frames").text(format_number(active, 0));
		this.wrapper.find("#delivered-frames").text(format_number(delivered, 0));
		this.wrapper.find("#total-warehouses").text(format_number(total_warehouses, 0));
	}

	render_status_chart(data) {
		const container = this.wrapper.find("#status-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No status data"));
			return;
		}
		// Destroy existing chart if it exists
		if (this.charts.statusChart && typeof this.charts.statusChart.destroy === "function") {
			this.charts.statusChart.destroy();
		}
		$(container).empty();
		this.charts.statusChart = new frappe.Chart(container, {
			data: { labels: data.labels, datasets: [{ name: "Frames", values: data.values }] },
			type: "pie",
			height: 260,
			colors: ["#5e64ff", "#00d4aa", "#ffa726", "#ff6b6b", "#26c6da", "#9ccc65", "#ab47bc"],
		});
	}

	render_warehouse_chart(data) {
		const container = this.wrapper.find("#warehouse-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No warehouse data"));
			return;
		}
		if (this.charts.warehouseChart && typeof this.charts.warehouseChart.destroy === "function") {
			this.charts.warehouseChart.destroy();
		}
		$(container).empty();
		this.charts.warehouseChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [{ name: "Frames", values: data.values }],
			},
			type: "bar",
			height: 260,
			colors: ["#5e64ff"],
			barOptions: { spaceRatio: 0.5 },
		});
	}

	render_item_chart(data) {
		const container = this.wrapper.find("#item-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No item data"));
			return;
		}
		if (this.charts.itemChart && typeof this.charts.itemChart.destroy === "function") {
			this.charts.itemChart.destroy();
		}
		$(container).empty();
		this.charts.itemChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [{ name: "Frames", values: data.values }],
			},
			type: "bar",
			height: 260,
			colors: ["#00d4aa"],
			barOptions: { spaceRatio: 0.5 },
		});
	}

	render_date_chart(data) {
		const container = this.wrapper.find("#date-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No date data"));
			return;
		}
		if (this.charts.dateChart && typeof this.charts.dateChart.destroy === "function") {
			this.charts.dateChart.destroy();
		}
		$(container).empty();
		this.charts.dateChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [{ name: "Frames", values: data.values }],
			},
			type: "line",
			height: 260,
			colors: ["#ffa726"],
			axisOptions: { xAxisMode: "tick", xIsSeries: true },
		});
	}

	render_frames_list(frames) {
		const container = this.wrapper.find("#frames-list");
		container.empty();

		if (!frames || frames.length === 0) {
			container.html(no_data("No Frames found for filters."));
			return;
		}

		const cards = frames.slice(0, 200).map((frame) => this.build_frame_card(frame)).join("");
		container.html(cards);
		
		// Add click handlers
		const self = this;
		container.find(".frame-card").on("click", (e) => {
			const card = $(e.currentTarget);
			const name = card.data("name");
			if (name) {
				self.show_frame_no_details(name);
			}
		});
	}

	build_frame_card(frame) {
		const statusClass = (frame.status || "Unknown").toLowerCase().replace(/\s+/g, "-");
		
		return `
			<div class="frame-card" data-doctype="Serial No" data-name="${frame.name || ''}" style="cursor: pointer;">
				<div class="frame-card__header">
					<div>
						<div class="frame-ref">${frame.frame_no || frame.name || "-"}</div>
						<div class="frame-item">${frame.item_code || "-"} ${frame.item_name ? `(${frame.item_name})` : ""}</div>
					</div>
					<div class="frame-status ${statusClass}">
						${frame.status || "Unknown"}
					</div>
				</div>
				<div class="frame-card__body">
					<div class="frame-metrics">
						<div><span class="muted">Warehouse</span><div class="metric-value">${frame.warehouse || "-"}</div></div>
						<div><span class="muted">Color</span><div class="metric-value">${frame.color_code || "-"}</div></div>
						<div><span class="muted">Engine No</span><div class="metric-value">${frame.custom_engine_number || "-"}</div></div>
					</div>
					${frame.purchase_date ? `<div class="frame-date"><i class="fa fa-calendar"></i> Purchase: ${frame.purchase_date}</div>` : ""}
					${frame.delivery_date ? `<div class="frame-date"><i class="fa fa-truck"></i> Delivery: ${frame.delivery_date}</div>` : ""}
				</div>
			</div>
		`;
	}

	show_frame_no_details(name) {
		// Hide list, show details
		this.wrapper.find(".frames-section").hide();
		this.wrapper.find("#frame-no-details-section").show();

		// Fetch Frame No details
		frappe.call({
			method: "rkg.rkg.page.frame_no_dashboard.frame_no_dashboard.get_frame_no_details",
			args: { name: name },
			callback: (r) => {
				if (r.message) {
					this.render_frame_no_details(r.message);
				}
			},
			error: () => {
				frappe.msgprint(__("Unable to load Frame No details."));
			},
		});
	}

	hide_frame_no_details() {
		this.wrapper.find("#frame-no-details-section").hide();
		this.wrapper.find(".frames-section").show();
	}

	render_frame_no_details(data) {
		const container = this.wrapper.find("#frame-no-details");
		const frame = data.frame_no || {};

		container.html(`
			<div class="frame-no-details-card">
				<div class="details-header">
					<h3>${frame.frame_no || frame.name || "-"}</h3>
					<span class="badge badge-info">${frame.status || "Unknown"}</span>
				</div>
				<div class="details-body">
					<div class="details-row">
						<div class="detail-item">
							<label>Item Code:</label>
							<span>${frame.item_code || "-"}</span>
						</div>
						<div class="detail-item">
							<label>Item Name:</label>
							<span>${frame.item_name || "-"}</span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Warehouse:</label>
							<span><strong>${frame.warehouse || "-"}</strong></span>
						</div>
						<div class="detail-item">
							<label>Status:</label>
							<span><strong>${frame.status || "-"}</strong></span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Purchase Date:</label>
							<span>${frame.purchase_date || "-"}</span>
						</div>
						<div class="detail-item">
							<label>Delivery Date:</label>
							<span>${frame.delivery_date || "-"}</span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Color Code:</label>
							<span>${frame.color_code || "-"}</span>
						</div>
						<div class="detail-item">
							<label>Engine Number:</label>
							<span>${frame.custom_engine_number || "-"}</span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Key No:</label>
							<span>${frame.custom_key_no || "-"}</span>
						</div>
						<div class="detail-item">
							<label>Battery No:</label>
							<span>${frame.custom_battery_no || "-"}</span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Created:</label>
							<span>${frame.creation ? frappe.datetime.str_to_user(frame.creation) : "-"}</span>
						</div>
						<div class="detail-item">
							<label>Modified:</label>
							<span>${frame.modified ? frappe.datetime.str_to_user(frame.modified) : "-"}</span>
						</div>
					</div>
				</div>
			</div>
		`);
	}
}

function no_data(message) {
	return `<div class="no-data"><i class="fa fa-info-circle"></i><p>${message}</p></div>`;
}

function add_styles() {
	$(`<style>
		.frame-no-dashboard { padding: 18px; background: var(--bg-color); }
		.filters-section { background: var(--card-bg); padding: 16px; border-radius: 12px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); margin-bottom: 18px; }
		.filters-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; align-items: end; }
		.filter-group label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; }
		.filter-actions { display: flex; gap: 10px; }

		.summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 14px; margin-bottom: 18px; }
		.summary-card { background: linear-gradient(135deg, var(--card-bg) 0%, var(--control-bg) 100%); border-radius: 12px; padding: 18px; box-shadow: 0 3px 10px rgba(0,0,0,0.08); border-left: 4px solid var(--primary); }
		.summary-card .card-icon { font-size: 24px; color: var(--primary); margin-bottom: 8px; }
		.summary-card .card-value { font-size: 30px; font-weight: 700; color: var(--heading-color); }
		.summary-card .card-label { font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
		.summary-card.total { border-left-color: #5e64ff; }
		.summary-card.active { border-left-color: #00d4aa; }
		.summary-card.delivered { border-left-color: #ffa726; }
		.summary-card.warehouses { border-left-color: #26c6da; }

		.charts-section { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 20px; }
		.chart-container { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.chart-title { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }

		.frames-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.section-header { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
		#frames-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
		.frame-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; background: var(--control-bg); box-shadow: 0 1px 4px rgba(0,0,0,0.04); transition: transform 0.2s, box-shadow 0.2s; }
		.frame-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
		.frame-card__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
		.frame-ref { font-weight: 700; color: var(--heading-color); font-size: 16px; }
		.frame-item { color: var(--text-muted); font-size: 12px; margin-top: 4px; }
		.frame-status { font-size: 12px; font-weight: 600; padding: 6px 10px; border-radius: 14px; background: var(--bg-light-gray); color: var(--heading-color); }
		.frame-status.active { background: #e0f7f2; color: #0b8c6b; }
		.frame-status.delivered { background: #e3e7ff; color: #2f49d0; }
		.frame-status.in-stock { background: #e0f7f2; color: #0b8c6b; }
		.frame-card__body { display: flex; flex-direction: column; gap: 8px; }
		.frame-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
		.metric-value { font-weight: 700; color: var(--heading-color); font-size: 13px; }
		.muted { color: var(--text-muted); font-size: 12px; }
		.frame-date { color: var(--text-muted); font-size: 11px; display: flex; align-items: center; gap: 4px; }

		.no-data { text-align: center; color: var(--text-muted); padding: 30px 10px; }
		.no-data i { font-size: 32px; margin-bottom: 8px; opacity: 0.6; }

		.frame-no-details-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.frame-no-details-card { background: var(--control-bg); border-radius: 10px; padding: 20px; }
		.details-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid var(--border-color); }
		.details-header h3 { margin: 0; color: var(--heading-color); }
		.details-body { margin-top: 20px; }
		.details-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
		.detail-item { display: flex; flex-direction: column; gap: 5px; }
		.detail-item label { font-weight: 600; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
		.detail-item span { color: var(--heading-color); font-size: 14px; }
	</style>`).appendTo("head");
}

