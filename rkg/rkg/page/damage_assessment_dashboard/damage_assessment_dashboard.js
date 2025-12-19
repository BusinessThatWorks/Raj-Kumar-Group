frappe.pages["damage-assessment-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Damaged Frames Dashboard",
		single_column: true,
	});

	add_styles();
	page.damage_assessment_dashboard = new DamageAssessmentDashboard(page);
};

frappe.pages["damage-assessment-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.page.damage_assessment_dashboard) {
		wrapper.page.damage_assessment_dashboard.refresh();
	}
};

class DamageAssessmentDashboard {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
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
			<div class="damage-assessment-dashboard">
				<div class="filters-section">
					<div class="filters-grid">
						<div class="filter-group">
							<label>Load Plan Reference</label>
							<select class="form-control filter-load-plan">
								<option value="">All Load Plans</option>
							</select>
						</div>
						<div class="filter-group">
							<label>Current Warehouse</label>
							<select class="form-control filter-warehouse">
								<option value="">All Warehouses</option>
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

				<div class="summary-cards">
					<div class="summary-card frames">
						<div class="card-icon"><i class="fa fa-cubes"></i></div>
						<div class="card-value" id="total-frames">0</div>
						<div class="card-label">Total Damaged Frames</div>
					</div>
				</div>

				<div class="frames-section">
					<div class="section-header">
						<span><i class="fa fa-list"></i> Damaged Frames</span>
					</div>
					<div class="table-container">
						<table class="table table-bordered frames-table">
							<thead>
								<tr>
									<th>Frame No</th>
									<th>Load Plan Reference</th>
									<th>From Warehouse</th>
									<th>To Warehouse</th>
									<th>Current Warehouse</th>
									<th>Type of Damage</th>
									<th>Estimated Cost</th>
									<th>Assessment Date</th>
								</tr>
							</thead>
							<tbody id="frames-list">
								<tr><td colspan="8" class="text-center">Loading...</td></tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>
		`);
	}

	setup_filters() {
		this.wrapper.find(".btn-refresh").on("click", () => this.refresh());
		this.wrapper.find(".btn-clear").on("click", () => {
			this.wrapper.find(".filter-load-plan").val("");
			this.wrapper.find(".filter-warehouse").val("");
			this.refresh();
		});
	}

	load_filter_options() {
		frappe.call({
			method: "rkg.rkg.page.damage_assessment_dashboard.damage_assessment_dashboard.get_filter_options",
			callback: (r) => {
				if (r.message) {
					// Load plan references
					if (r.message.load_plan_references) {
						const select = this.wrapper.find(".filter-load-plan");
						select.empty().append(`<option value="">All Load Plans</option>`);
						r.message.load_plan_references.forEach((ref) => {
							select.append(`<option value="${ref}">${ref}</option>`);
						});
					}
					// Load warehouses
					if (r.message.warehouses) {
						const select = this.wrapper.find(".filter-warehouse");
						select.empty().append(`<option value="">All Warehouses</option>`);
						r.message.warehouses.forEach((wh) => {
							select.append(`<option value="${wh}">${wh}</option>`);
						});
					}
				}
			},
		});
	}

	refresh() {
		const filters = {
			load_plan_reference: this.wrapper.find(".filter-load-plan").val(),
			warehouse: this.wrapper.find(".filter-warehouse").val(),
		};

		frappe.call({
			method: "rkg.rkg.page.damage_assessment_dashboard.damage_assessment_dashboard.get_damaged_frames_data",
			args: filters,
			callback: (r) => {
				if (r.message) {
					this.render_summary(r.message.summary || {});
					this.render_frames_table(r.message.frames || []);
				} else {
					this.render_summary({});
					this.render_frames_table([]);
				}
			},
			error: (r) => {
				console.error("Error loading dashboard data:", r);
				frappe.msgprint(__("Unable to load dashboard data right now."));
				this.render_summary({});
				this.render_frames_table([]);
			},
		});
	}

	render_summary(summary) {
		this.wrapper.find("#total-frames").text(summary.total_frames || 0);
	}

	render_frames_table(frames) {
		const tbody = this.wrapper.find("#frames-list");
		tbody.empty();

		if (!frames || frames.length === 0) {
			tbody.html(`<tr><td colspan="8" class="text-center">No damaged frames found for the selected filters.</td></tr>`);
			return;
		}

		const rows = frames.map((frame) => {
			return `
				<tr>
					<td>
						${frame.serial_no ? `<a href="/app/serial-no/${frame.serial_no}" target="_blank">${frame.serial_no}</a>` : "-"}
					</td>
					<td>
						${frame.load_plan_reference_no ? `<a href="/app/load-plan/${frame.load_plan_reference_no}" target="_blank">${frame.load_plan_reference_no}</a>` : "-"}
					</td>
					<td>${frame.from_warehouse || "-"}</td>
					<td>${frame.to_warehouse || "-"}</td>
					<td>${frame.current_warehouse || "-"}</td>
					<td>${frame.type_of_damage || "-"}</td>
					<td>${frappe.format(frame.estimated_cost || 0, { fieldtype: "Currency" })}</td>
					<td>${frame.assessment_date || "-"}</td>
				</tr>
			`;
		}).join("");

		tbody.html(rows);
	}
}

function add_styles() {
	$(`<style>
		.damage-assessment-dashboard { padding: 18px; background: var(--bg-color); }
		.filters-section { background: var(--card-bg); padding: 16px; border-radius: 12px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); margin-bottom: 18px; }
		.filters-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; align-items: end; }
		.filter-group label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; }
		.filter-actions { display: flex; gap: 10px; }

		.summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 14px; margin-bottom: 18px; }
		.summary-card { background: linear-gradient(135deg, var(--card-bg) 0%, var(--control-bg) 100%); border-radius: 12px; padding: 18px; box-shadow: 0 3px 10px rgba(0,0,0,0.08); border-left: 4px solid var(--primary); }
		.summary-card .card-icon { font-size: 24px; color: var(--primary); margin-bottom: 8px; }
		.summary-card .card-value { font-size: 30px; font-weight: 700; color: var(--heading-color); }
		.summary-card .card-label { font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
		.summary-card.frames { border-left-color: #ff6b6b; }

		.frames-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.section-header { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
		.table-container { overflow-x: auto; }
		.frames-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
		.frames-table thead { background: var(--bg-light-gray); }
		.frames-table th { padding: 12px; text-align: left; font-weight: 600; color: var(--heading-color); border: 1px solid var(--border-color); }
		.frames-table td { padding: 10px 12px; border: 1px solid var(--border-color); }
		.frames-table tbody tr:nth-child(even) { background: var(--bg-color); }
		.frames-table tbody tr:hover { background: var(--control-bg); }
		.frames-table a { color: var(--primary); text-decoration: none; }
		.frames-table a:hover { text-decoration: underline; }
	</style>`).appendTo("head");
}

