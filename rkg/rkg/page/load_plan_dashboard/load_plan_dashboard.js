// Helper function to format numbers
function format_number(value, precision) {
	const num = parseFloat(value) || 0;
	if (precision === 0) {
		return Math.round(num).toString();
	}
	return num.toFixed(precision);
}

frappe.pages["load-plan-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Load Plan & Load Dispatch Dashboard",
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
				<div class="dashboard-tabs">
					<button class="tab-btn active" data-tab="load-plan">
						<i class="fa fa-clipboard-list"></i> Load Plan
					</button>
					<button class="tab-btn" data-tab="load-dispatch">
						<i class="fa fa-truck"></i> Load Dispatch
					</button>
				</div>

				<div class="filters-section">
					<div class="filters-grid">
						<div class="filter-group">
							<label>Status</label>
							<select class="form-control filter-status">
								<option value="">All Statuses</option>
							</select>
						</div>
						<div class="filter-group">
							<label>Load Reference No</label>
							<select class="form-control filter-load-ref">
								<option value="">All Load References</option>
							</select>
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

				<!-- Load Plan Section -->
				<div class="dashboard-content" id="load-plan-content">

				<div class="summary-cards">
					<div class="summary-card plans">
						<div class="card-icon"><i class="fa fa-clipboard-list"></i></div>
						<div class="card-value" id="total-plans">0</div>
						<div class="card-label">Load Plans</div>
					</div>
					<div class="summary-card dispatched-count">
						<div class="card-icon"><i class="fa fa-truck-loading"></i></div>
						<div class="card-value" id="total-submitted-dispatches">0</div>
						<div class="card-label">Dispatch</div>
					</div>
					<div class="summary-card dispatched">
						<div class="card-icon"><i class="fa fa-cubes"></i></div>
						<div class="card-value" id="total-dispatch-qty-sum">0</div>
						<div class="card-label">Total Frames</div>
					</div>
				</div>

				<div class="plans-section">
					<div class="section-header">
						<span><i class="fa fa-list"></i> Load Plans</span>
					</div>
					<div id="plan-list"></div>
				</div>

				<!-- Load Plan Details Section -->
				<div class="plan-details-section" id="plan-details-section" style="display: none;">
					<div class="section-header">
						<button class="btn btn-sm btn-default btn-back-to-list" style="margin-right: 10px;">
							<i class="fa fa-arrow-left"></i> Back to List
						</button>
						<span><i class="fa fa-info-circle"></i> Load Plan Details</span>
					</div>
					<div id="plan-details"></div>
				</div>
				</div>

				<!-- Load Dispatch Section -->
				<div class="dashboard-content" id="load-dispatch-content" style="display: none;">
					<div class="summary-cards">
						<div class="summary-card dispatches">
							<div class="card-icon"><i class="fa fa-truck"></i></div>
							<div class="card-value" id="total-dispatches">0</div>
							<div class="card-label">Load Dispatches</div>
						</div>
						<div class="summary-card dispatched-qty">
							<div class="card-icon"><i class="fa fa-cubes"></i></div>
							<div class="card-value" id="total-dispatch-qty">0</div>
							<div class="card-label">Dispatch Qty</div>
						</div>
						<div class="summary-card received">
							<div class="card-icon"><i class="fa fa-check-circle"></i></div>
							<div class="card-value" id="total-received-qty">0</div>
							<div class="card-label">Received Qty</div>
						</div>
						<div class="summary-card billed">
							<div class="card-icon"><i class="fa fa-file-invoice"></i></div>
							<div class="card-value" id="total-billed-qty">0</div>
							<div class="card-label">Billed Qty</div>
						</div>
					</div>

					<div class="dispatches-section">
						<div class="section-header">
							<span><i class="fa fa-list"></i> Load Dispatch Progress</span>
						</div>
						<div id="dispatch-list"></div>
					</div>
				</div>
			</div>
		`);
	}

	setup_filters() {
		// Tab switching
		this.wrapper.find(".tab-btn").on("click", (e) => {
			const tab = $(e.currentTarget).data("tab");
			this.switch_tab(tab);
		});

		this.wrapper.find(".btn-refresh").on("click", () => this.refresh());
		this.wrapper.find(".btn-clear").on("click", () => {
			this.wrapper.find(".filter-status").val("");
			this.wrapper.find(".filter-load-ref").val("");
			this.refresh();
		});

		// Back to list button
		this.wrapper.find(".btn-back-to-list").on("click", () => {
			this.hide_load_plan_details();
		});

		this.current_tab = "load-plan";
	}

	switch_tab(tab) {
		this.current_tab = tab;
		this.wrapper.find(".tab-btn").removeClass("active");
		this.wrapper.find(`.tab-btn[data-tab="${tab}"]`).addClass("active");
		
		this.wrapper.find(".dashboard-content").hide();
		this.load_filter_options(); // Reload filter options for the selected tab
		
		if (tab === "load-dispatch") {
			this.wrapper.find("#load-dispatch-content").show();
			this.load_dispatch_data();
		} else {
			this.wrapper.find("#load-plan-content").show();
			this.load_plan_data();
		}
	}

	load_filter_options() {
		const doctype = this.current_tab === "load-dispatch" ? "Load Dispatch" : "Load Plan";
		frappe.call({
			method: "rkg.rkg.page.load_plan_dashboard.load_plan_dashboard.get_filter_options",
			args: { doctype: doctype },
			callback: (r) => {
				if (r.message) {
					// Load statuses
					if (r.message.statuses) {
						const select = this.wrapper.find(".filter-status");
						select.empty().append(`<option value="">All Statuses</option>`);
						r.message.statuses.forEach((st) => {
							select.append(`<option value="${st}">${st}</option>`);
						});
					}
					// Load reference numbers
					if (r.message.load_references) {
						const select = this.wrapper.find(".filter-load-ref");
						select.empty().append(`<option value="">All Load References</option>`);
						r.message.load_references.forEach((ref) => {
							select.append(`<option value="${ref}">${ref}</option>`);
						});
					}
				}
			},
		});
	}

	refresh() {
		if (this.current_tab === "load-dispatch") {
			this.load_dispatch_data();
		} else {
			this.load_plan_data();
		}
	}

	load_plan_data() {
		const filters = {
			status: this.wrapper.find(".filter-status").val(),
			load_reference: this.wrapper.find(".filter-load-ref").val(),
			doctype: "Load Plan",
		};

		const selectedLoadRef = filters.load_reference;

		frappe.call({
			method: "rkg.rkg.page.load_plan_dashboard.load_plan_dashboard.get_dashboard_data",
			args: filters,
			callback: (r) => {
				if (r.message) {
					this.render_summary(r.message.summary || {});
					
					// If a specific Load Reference No is selected, show it in expanded format
					if (selectedLoadRef && selectedLoadRef.trim() !== "") {
						const plans = r.message.plans || [];
						if (plans.length > 0) {
							// Find the exact match (in case of partial matches)
							const selectedPlan = plans.find(p => p.load_reference_no === selectedLoadRef) || plans[0];
							if (selectedPlan && selectedPlan.load_reference_no) {
								this.show_load_plan_details(selectedPlan.load_reference_no);
								return;
							}
						}
					}
					
					// Otherwise, show the list of plans
					this.hide_load_plan_details();
					this.render_plan_list(r.message.plans || []);
				} else {
					this.hide_load_plan_details();
					this.render_plan_list([]);
				}
			},
			error: (r) => {
				console.error("Error loading dashboard data:", r);
				frappe.msgprint(__("Unable to load dashboard data right now."));
				this.hide_load_plan_details();
				this.render_plan_list([]);
			},
		});
	}

	load_dispatch_data() {
		const filters = {
			status: this.wrapper.find(".filter-status").val(),
			load_reference: this.wrapper.find(".filter-load-ref").val(),
			doctype: "Load Dispatch",
		};

		frappe.call({
			method: "rkg.rkg.page.load_plan_dashboard.load_plan_dashboard.get_dashboard_data",
			args: filters,
			callback: (r) => {
				if (r.message) {
					this.render_dispatch_summary(r.message.summary || {});
					this.render_dispatch_list(r.message.dispatches);
				}
			},
			error: () => {
				frappe.msgprint(__("Unable to load dashboard data right now."));
			},
		});
	}

	render_summary(summary) {
		this.wrapper.find("#total-plans").text(summary.total_plans || 0);
		this.wrapper.find("#total-dispatch-qty-sum").text(format_number(summary.total_dispatch_qty_sum || 0, 0));
		this.wrapper.find("#total-submitted-dispatches").text(summary.total_submitted_dispatches || 0);
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
		if (!container.length) {
			console.error("Plan list container not found!");
			return;
		}
		
		container.empty();

		if (!plans || plans.length === 0) {
			container.html(no_data("No Load Plans found for filters."));
			return;
		}

		console.log("Rendering plans:", plans.length, plans);
		const cards = plans.slice(0, 80).map((p) => this.build_plan_card(p)).join("");
		container.html(cards);
		
		// Add click handlers
		const self = this;
		container.find(".plan-card").on("click", (e) => {
			const card = $(e.currentTarget);
			const load_reference_no = card.data("name");
			if (load_reference_no) {
				self.show_load_plan_details(load_reference_no);
			}
		});
	}

	build_plan_card(plan) {
		const progress = plan.progress || 0;
		const remaining = plan.remaining || 0;
		const dispatched = plan.load_dispatch_quantity || 0;
		const planned = plan.total_quantity || 0;
		const statusClass = (plan.status || "").toLowerCase().replace(/\s+/g, "-");
		const overdueBadge = plan.is_overdue ? `<span class="badge badge-danger">Overdue</span>` : "";

		return `
			<div class="plan-card" data-doctype="Load Plan" data-name="${plan.load_reference_no || ''}" style="cursor: pointer;">
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
						<div><span class="muted">Total Qty</span><div class="metric-value">${planned}</div></div>
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

	render_dispatch_summary(summary) {
		this.wrapper.find("#total-dispatches").text(summary.total_dispatches || 0);
		this.wrapper.find("#total-dispatch-qty").text(format_number(summary.total_dispatch_qty || 0, 0));
		this.wrapper.find("#total-received-qty").text(format_number(summary.total_received_qty || 0, 0));
		this.wrapper.find("#total-billed-qty").text(format_number(summary.total_billed_qty || 0, 0));
	}

	render_dispatch_status_chart(data) {
		const container = this.wrapper.find("#dispatch-status-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No status data"));
			return;
		}
		if (this.charts.dispatchStatusChart && typeof this.charts.dispatchStatusChart.destroy === "function") {
			this.charts.dispatchStatusChart.destroy();
		}
		$(container).empty();
		this.charts.dispatchStatusChart = new frappe.Chart(container, {
			data: { labels: data.labels, datasets: [{ name: "Load Dispatches", values: data.values }] },
			type: "pie",
			height: 260,
			colors: ["#5e64ff", "#00d4aa", "#ffa726", "#ff6b6b"],
		});
	}

	render_dispatch_chart(data) {
		const container = this.wrapper.find("#dispatch-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No dispatch data"));
			return;
		}
		if (this.charts.dispatchChart && typeof this.charts.dispatchChart.destroy === "function") {
			this.charts.dispatchChart.destroy();
		}
		$(container).empty();
		this.charts.dispatchChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [
					{ name: "Dispatched Qty", values: data.dispatched, chartType: "bar" },
					{ name: "Received Qty", values: data.received, chartType: "line" },
					{ name: "Billed Qty", values: data.billed, chartType: "line" },
				],
			},
			type: "axis-mixed",
			height: 280,
			colors: ["#5e64ff", "#00d4aa", "#ffa726"],
			axisOptions: { xAxisMode: "tick", xIsSeries: true },
			barOptions: { spaceRatio: 0.5 },
		});
	}

	render_dispatch_models_chart(data) {
		const container = this.wrapper.find("#dispatch-models-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No model data"));
			return;
		}
		if (this.charts.dispatchModelsChart && typeof this.charts.dispatchModelsChart.destroy === "function") {
			this.charts.dispatchModelsChart.destroy();
		}
		$(container).empty();
		this.charts.dispatchModelsChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [{ name: "Dispatched Qty", values: data.values }],
			},
			type: "bar",
			height: 280,
			colors: ["#ffb347"],
			barOptions: { spaceRatio: 0.5 },
		});
	}

	render_dispatch_list(dispatches) {
		const container = this.wrapper.find("#dispatch-list");
		container.empty();

		if (!dispatches || dispatches.length === 0) {
			container.html(no_data("No Load Dispatches found for filters."));
			return;
		}

		const cards = dispatches.slice(0, 80).map((d) => this.build_dispatch_card(d)).join("");
		container.html(cards);
		
		// Add click handlers
		container.find(".plan-card").on("click", (e) => {
			const card = $(e.currentTarget);
			const doctype = card.data("doctype");
			const name = card.data("name");
			if (name) {
				frappe.set_route("Form", doctype, name);
			}
		});
	}

	build_dispatch_card(dispatch) {
		const receive_progress = dispatch.receive_progress || 0;
		const bill_progress = dispatch.bill_progress || 0;
		const dispatched = dispatch.total_dispatch_quantity || 0;
		const received = dispatch.total_received_quantity || 0;
		const billed = dispatch.total_billed_quantity || 0;
		const statusClass = (dispatch.status || "").toLowerCase().replace(/\s+/g, "-");

		return `
			<div class="plan-card" data-doctype="Load Dispatch" data-name="${dispatch.name || ''}" style="cursor: pointer;">
				<div class="plan-card__header">
					<div>
						<div class="plan-ref">${dispatch.dispatch_no || dispatch.name || "-"}</div>
						<div class="plan-dates">
							${dispatch.load_reference_no ? `Load Ref: ${dispatch.load_reference_no}` : ""}
							${dispatch.invoice_no ? ` · Invoice: ${dispatch.invoice_no}` : ""}
						</div>
					</div>
					<div class="plan-status ${statusClass}">
						${dispatch.status || "In-Transit"}
					</div>
				</div>
				<div class="plan-card__body">
					<div class="plan-metrics">
						<div><span class="muted">Dispatched</span><div class="metric-value">${dispatched}</div></div>
						<div><span class="muted">Received</span><div class="metric-value">${received}</div></div>
						<div><span class="muted">Billed</span><div class="metric-value">${billed}</div></div>
					</div>
					<div class="progress-section">
						<div class="progress-item">
							<div class="progress-label-small">Receive: ${receive_progress}%</div>
							<div class="progress-bar">
								<div class="progress-fill" style="width:${receive_progress}%; background: #00d4aa;"></div>
							</div>
						</div>
						<div class="progress-item">
							<div class="progress-label-small">Bill: ${bill_progress}%</div>
							<div class="progress-bar">
								<div class="progress-fill" style="width:${bill_progress}%; background: #ffa726;"></div>
							</div>
						</div>
					</div>
				</div>
			</div>
		`;
	}

	show_load_plan_details(load_reference_no) {
		// Hide list, show details
		this.wrapper.find(".plans-section").hide();
		this.wrapper.find("#plan-details-section").show();

		// Fetch Load Plan details
		frappe.call({
			method: "rkg.rkg.page.load_plan_dashboard.load_plan_dashboard.get_load_plan_details",
			args: { load_reference_no: load_reference_no },
			callback: (r) => {
				if (r.message) {
					this.render_load_plan_details(r.message);
				}
			},
			error: () => {
				frappe.msgprint(__("Unable to load Load Plan details."));
			},
		});
	}

	hide_load_plan_details() {
		this.wrapper.find("#plan-details-section").hide();
		this.wrapper.find(".plans-section").show();
	}

	render_load_plan_details(data) {
		const container = this.wrapper.find("#plan-details");
		const plan = data.plan || {};
		const items = data.items || [];

		let itemsHtml = "";
		if (items.length > 0) {
			itemsHtml = `
				<div class="details-table-container">
					<h4><i class="fa fa-list"></i> Load Plan Items</h4>
					<table class="table table-bordered">
						<thead>
							<tr>
								<th>Model</th>
								<th>Model Name</th>
								<th>Type</th>
								<th>Variant</th>
								<th>Color</th>
								<th>Group Color</th>
								<th>Option</th>
								<th>Quantity</th>
							</tr>
						</thead>
						<tbody>
							${items.map(item => `
								<tr>
									<td>${item.model || "-"}</td>
									<td>${item.model_name || "-"}</td>
									<td>${item.model_type || "-"}</td>
									<td>${item.model_variant || "-"}</td>
									<td>${item.model_color || "-"}</td>
									<td>${item.group_color || "-"}</td>
									<td>${item.option || "-"}</td>
									<td>${item.quantity || 0}</td>
								</tr>
							`).join("")}
						</tbody>
					</table>
				</div>
			`;
		} else {
			itemsHtml = `<div class="no-data"><i class="fa fa-info-circle"></i><p>No items found in this Load Plan</p></div>`;
		}

		container.html(`
			<div class="plan-details-card">
				<div class="details-header">
					<h3>${plan.load_reference_no || "-"}</h3>
					<span class="badge badge-${plan.status === "Dispatched" ? "success" : plan.status === "Draft" ? "danger" : "info"}">${plan.status || "Submitted"}</span>
				</div>
				<div class="details-body">
					<div class="details-row">
						<div class="detail-item">
							<label>Dispatch Plan Date:</label>
							<span>${plan.dispatch_plan_date || "-"}</span>
						</div>
						<div class="detail-item">
							<label>Payment Plan Date:</label>
							<span>${plan.payment_plan_date || "-"}</span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Total Quantity:</label>
							<span><strong>${plan.total_quantity || 0}</strong></span>
						</div>
						<div class="detail-item">
							<label>Dispatched Quantity:</label>
							<span><strong>${plan.load_dispatch_quantity || 0}</strong></span>
						</div>
					</div>
					${itemsHtml}
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
		.load-plan-dashboard { padding: 18px; background: var(--bg-color); }
		.dashboard-tabs { display: flex; gap: 8px; margin-bottom: 18px; border-bottom: 2px solid var(--border-color); }
		.tab-btn { padding: 12px 20px; background: transparent; border: none; border-bottom: 3px solid transparent; 
			cursor: pointer; font-weight: 600; color: var(--text-muted); transition: all 0.3s; }
		.tab-btn:hover { color: var(--heading-color); }
		.tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
		.dashboard-content { display: block; }
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
		.summary-card.dispatched-count { border-left-color: #ffa726; }
		.summary-card.completion { border-left-color: #ffa726; }

		.charts-section { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 20px; }
		.chart-container { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.chart-title { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }

		.plans-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.section-header { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
		#plan-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
		.plan-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; background: var(--control-bg); box-shadow: 0 1px 4px rgba(0,0,0,0.04); margin: 10px; }
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
		.progress-section { display: flex; flex-direction: column; gap: 8px; }
		.progress-item { display: flex; flex-direction: column; gap: 4px; }
		.progress-label-small { font-size: 11px; color: var(--text-muted); }
		.badge-danger { background: #ffe0e0; color: #c62828; padding: 2px 8px; border-radius: 10px; font-size: 11px; margin-left: 6px; }

		.no-data { text-align: center; color: var(--text-muted); padding: 30px 10px; }
		.no-data i { font-size: 32px; margin-bottom: 8px; opacity: 0.6; }

		.plan-details-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.plan-details-card { background: var(--control-bg); border-radius: 10px; padding: 20px; }
		.details-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid var(--border-color); }
		.details-header h3 { margin: 0; color: var(--heading-color); }
		.details-body { margin-top: 20px; }
		.details-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
		.detail-item { display: flex; flex-direction: column; gap: 5px; }
		.detail-item label { font-weight: 600; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
		.detail-item span { color: var(--heading-color); font-size: 14px; }
		.details-table-container { margin-top: 30px; }
		.details-table-container h4 { margin-bottom: 15px; color: var(--heading-color); }
		.details-table-container table { width: 100%; border-collapse: collapse; }
		.details-table-container table th { background: var(--bg-light-gray); padding: 12px; text-align: left; font-weight: 600; color: var(--heading-color); border: 1px solid var(--border-color); }
		.details-table-container table td { padding: 10px 12px; border: 1px solid var(--border-color); }
		.details-table-container table tr:nth-child(even) { background: var(--bg-color); }
	</style>`).appendTo("head");
}

