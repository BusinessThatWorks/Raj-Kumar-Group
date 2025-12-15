frappe.pages["load-plan-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Load Plan Visual Dashboard",
		single_column: true,
	});

	add_styles();
	page.load_plan_dashboard = new LoadPlanDashboard(page);
};

frappe.pages["load-plan-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.page.load_plan_dashboard) {
		wrapper.page.load_plan_dashboard.refresh();
	}
};

class LoadPlanDashboard {
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
			<div class="load-plan-dashboard">
				<div class="filters-section">
					<div class="filters-grid">
						<div class="filter-group">
							<label>Status</label>
							<select class="form-control filter-status">
								<option value="">All Statuses</option>
								<option value="Submitted">Submitted</option>
								<option value="In-Transit">In-Transit</option>
								<option value="Partial Dispatched">Partial Dispatched</option>
								<option value="Dispatched">Dispatched</option>
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
						<div class="filter-group">
							<label>Load Reference No</label>
							<input type="text" class="form-control filter-load-ref" placeholder="e.g. HMSI-001">
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
					<div class="summary-card plans">
						<div class="card-icon"><i class="fa fa-clipboard-list"></i></div>
						<div class="card-value" id="total-plans">0</div>
						<div class="card-label">Load Plans</div>
					</div>
					<div class="summary-card planned">
						<div class="card-icon"><i class="fa fa-cubes"></i></div>
						<div class="card-value" id="total-planned">0</div>
						<div class="card-label">Planned Qty</div>
					</div>
					<div class="summary-card dispatched">
						<div class="card-icon"><i class="fa fa-truck-loading"></i></div>
						<div class="card-value" id="total-dispatched">0</div>
						<div class="card-label">Dispatched Qty</div>
					</div>
					<div class="summary-card completion">
						<div class="card-icon"><i class="fa fa-percentage"></i></div>
						<div class="card-value" id="dispatch-completion">0%</div>
						<div class="card-label">Dispatch Completion</div>
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
							<i class="fa fa-chart-line"></i> Planned vs Dispatched (by Date)
						</div>
						<div id="plan-chart"></div>
					</div>
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-bar-chart"></i> Top Planned Models
						</div>
						<div id="models-chart"></div>
					</div>
				</div>

				<div class="plans-section">
					<div class="section-header">
						<span><i class="fa fa-list"></i> Load Plan Progress</span>
					</div>
					<div id="plan-list"></div>
				</div>
			</div>
		`);
	}

	setup_filters() {
		const today = frappe.datetime.get_today();
		const thirtyDaysAgo = frappe.datetime.add_days(today, -30);

		this.wrapper.find(".filter-from-date").val(thirtyDaysAgo);
		this.wrapper.find(".filter-to-date").val(today);

		this.wrapper.find(".btn-refresh").on("click", () => this.refresh());
		this.wrapper.find(".btn-clear").on("click", () => {
			this.wrapper.find(".filter-status").val("");
			this.wrapper.find(".filter-from-date").val(thirtyDaysAgo);
			this.wrapper.find(".filter-to-date").val(today);
			this.wrapper.find(".filter-load-ref").val("");
			this.refresh();
		});
	}

	load_filter_options() {
		frappe.call({
			method: "rkg.rkg.page.load_plan_dashboard.load_plan_dashboard.get_filter_options",
			callback: (r) => {
				if (r.message && r.message.statuses) {
					const select = this.wrapper.find(".filter-status");
					select.empty().append(`<option value="">All Statuses</option>`);
					r.message.statuses.forEach((st) => {
						select.append(`<option value="${st}">${st}</option>`);
					});
				}
			},
		});
	}

	refresh() {
		const filters = {
			status: this.wrapper.find(".filter-status").val(),
			from_date: this.wrapper.find(".filter-from-date").val(),
			to_date: this.wrapper.find(".filter-to-date").val(),
			load_reference: this.wrapper.find(".filter-load-ref").val(),
		};

		frappe.call({
			method: "rkg.rkg.page.load_plan_dashboard.load_plan_dashboard.get_dashboard_data",
			args: filters,
			callback: (r) => {
				if (r.message) {
					this.render_summary(r.message.summary || {});
					this.render_status_chart(r.message.status_chart);
					this.render_plan_chart(r.message.plan_vs_dispatch);
					this.render_models_chart(r.message.top_models);
					this.render_plan_list(r.message.plans);
				}
			},
			error: () => {
				frappe.msgprint(__("Unable to load dashboard data right now."));
			},
		});
	}

	render_summary(summary) {
		this.wrapper.find("#total-plans").text(summary.total_plans || 0);
		this.wrapper.find("#total-planned").text(frappe.utils.flt(summary.total_planned_qty || 0, 0));
		this.wrapper.find("#total-dispatched").text(frappe.utils.flt(summary.total_dispatched_qty || 0, 0));
		this.wrapper.find("#dispatch-completion").text(`${frappe.utils.flt(summary.dispatch_completion || 0, 1)}%`);
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
			data: { labels: data.labels, datasets: [{ name: "Load Plans", values: data.values }] },
			type: "pie",
			height: 260,
			colors: ["#5e64ff", "#ffa726", "#00d4aa", "#ff6b6b", "#26c6da", "#9ccc65"],
		});
	}

	render_plan_chart(data) {
		const container = this.wrapper.find("#plan-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No plan data"));
			return;
		}
		// Destroy existing chart if it exists
		if (this.charts.planChart && typeof this.charts.planChart.destroy === "function") {
			this.charts.planChart.destroy();
		}
		$(container).empty();
		this.charts.planChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [
					{ name: "Planned Qty", values: data.planned, chartType: "bar" },
					{ name: "Dispatched Qty", values: data.dispatched, chartType: "line" },
				],
			},
			type: "axis-mixed",
			height: 280,
			colors: ["#5e64ff", "#00d4aa"],
			axisOptions: { xAxisMode: "tick", xIsSeries: true },
			barOptions: { spaceRatio: 0.5 },
		});
	}

	render_models_chart(data) {
		const container = this.wrapper.find("#models-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No model data"));
			return;
		}
		// Destroy existing chart if it exists
		if (this.charts.modelsChart && typeof this.charts.modelsChart.destroy === "function") {
			this.charts.modelsChart.destroy();
		}
		$(container).empty();
		this.charts.modelsChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [{ name: "Planned Qty", values: data.values }],
			},
			type: "bar",
			height: 280,
			colors: ["#ffb347"],
			barOptions: { spaceRatio: 0.5 },
		});
	}

	render_plan_list(plans) {
		const container = this.wrapper.find("#plan-list");
		container.empty();

		if (!plans || plans.length === 0) {
			container.html(no_data("No Load Plans found for filters."));
			return;
		}

		const cards = plans.slice(0, 80).map((p) => this.build_plan_card(p)).join("");
		container.html(cards);
	}

	build_plan_card(plan) {
		const progress = plan.progress || 0;
		const remaining = plan.remaining || 0;
		const dispatched = plan.load_dispatch_quantity || 0;
		const planned = plan.total_quantity || 0;
		const statusClass = (plan.status || "").toLowerCase().replace(/\s+/g, "-");
		const overdueBadge = plan.is_overdue ? `<span class="badge badge-danger">Overdue</span>` : "";

		return `
			<div class="plan-card">
				<div class="plan-card__header">
					<div>
						<div class="plan-ref">${plan.load_reference_no || "-"}</div>
						<div class="plan-dates">
							${plan.dispatch_plan_date ? `Dispatch: ${plan.dispatch_plan_date}` : ""}
							${plan.payment_plan_date ? ` · Payment: ${plan.payment_plan_date}` : ""}
						</div>
					</div>
					<div class="plan-status ${statusClass}">
						${plan.status || "Submitted"} ${overdueBadge}
					</div>
				</div>
				<div class="plan-card__body">
					<div class="plan-metrics">
						<div><span class="muted">Planned</span><div class="metric-value">${planned}</div></div>
						<div><span class="muted">Dispatched</span><div class="metric-value">${dispatched}</div></div>
						<div><span class="muted">Balance</span><div class="metric-value">${remaining}</div></div>
					</div>
					<div class="progress-bar">
						<div class="progress-fill" style="width:${progress}%;"></div>
					</div>
					<div class="progress-label">${progress}% dispatched</div>
				</div>
			</div>
		`;
	}
}

function no_data(message) {
	return `<div class="no-data"><i class="fa fa-info-circle"></i><p>${message}</p></div>`;
}

function add_styles() {
	$(`<style>
		.load-plan-dashboard { padding: 18px; background: var(--bg-color); }
		.filters-section { background: var(--card-bg); padding: 16px; border-radius: 12px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); margin-bottom: 18px; }
		.filters-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; align-items: end; }
		.filter-group label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; }
		.filter-actions { display: flex; gap: 10px; }

		.summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 14px; margin-bottom: 18px; }
		.summary-card { background: linear-gradient(135deg, var(--card-bg) 0%, var(--control-bg) 100%); border-radius: 12px; padding: 18px; box-shadow: 0 3px 10px rgba(0,0,0,0.08); border-left: 4px solid var(--primary); }
		.summary-card .card-icon { font-size: 24px; color: var(--primary); margin-bottom: 8px; }
		.summary-card .card-value { font-size: 30px; font-weight: 700; color: var(--heading-color); }
		.summary-card .card-label { font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
		.summary-card.plans { border-left-color: #5e64ff; }
		.summary-card.planned { border-left-color: #26c6da; }
		.summary-card.dispatched { border-left-color: #00d4aa; }
		.summary-card.completion { border-left-color: #ffa726; }

		.charts-section { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 20px; }
		.chart-container { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.chart-title { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }

		.plans-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.section-header { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
		#plan-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
		.plan-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; background: var(--control-bg); box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
		.plan-card__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
		.plan-ref { font-weight: 700; color: var(--heading-color); }
		.plan-dates { color: var(--text-muted); font-size: 12px; }
		.plan-status { font-size: 12px; font-weight: 600; padding: 6px 10px; border-radius: 14px; background: var(--bg-light-gray); color: var(--heading-color); }
		.plan-status.submitted { background: #e3e7ff; color: #2f49d0; }
		.plan-status.in-transit { background: #e0f3ff; color: #0b7ecb; }
		.plan-status.partial-dispatched { background: #fff4e0; color: #f08a00; }
		.plan-status.dispatched { background: #e0f7f2; color: #0b8c6b; }
		.plan-card__body { display: flex; flex-direction: column; gap: 8px; }
		.plan-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
		.metric-value { font-weight: 700; color: var(--heading-color); }
		.muted { color: var(--text-muted); font-size: 12px; }
		.progress-bar { height: 8px; background: var(--bg-light-gray); border-radius: 8px; overflow: hidden; }
		.progress-fill { height: 100%; background: linear-gradient(90deg, #5e64ff, #00d4aa); transition: width 0.3s ease; }
		.progress-label { font-size: 12px; color: var(--text-muted); }
		.badge-danger { background: #ffe0e0; color: #c62828; padding: 2px 8px; border-radius: 10px; font-size: 11px; margin-left: 6px; }

		.no-data { text-align: center; color: var(--text-muted); padding: 30px 10px; }
		.no-data i { font-size: 32px; margin-bottom: 8px; opacity: 0.6; }
	</style>`).appendTo("head");
}

