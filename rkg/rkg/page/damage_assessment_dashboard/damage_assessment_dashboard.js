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
							<label>Load Dispatch</label>
							<select class="form-control filter-load-dispatch">
								<option value="">All Load Dispatches</option>
							</select>
						</div>
						<div class="filter-group">
							<label>Status</label>
							<select class="form-control filter-status">
								<option value="">All Status</option>
								<option value="OK">OK</option>
								<option value="Not OK">Not OK (Damaged)</option>
							</select>
						</div>
						<div class="filter-group">
							<label>Warehouse</label>
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
					<div class="summary-card total">
						<div class="card-icon"><i class="fa fa-cubes"></i></div>
						<div class="card-value" id="total-frames">0</div>
						<div class="card-label">Total Frames</div>
					</div>
					<div class="summary-card not-ok">
						<div class="card-icon"><i class="fa fa-exclamation-triangle"></i></div>
						<div class="card-value" id="not-ok-frames">0</div>
						<div class="card-label">Damaged Frames</div>
					</div>
					<div class="summary-card cost">
						<div class="card-icon"><i class="fa fa-rupee"></i></div>
						<div class="card-value" id="total-cost">₹0</div>
						<div class="card-label">Total Estimated Cost</div>
					</div>
				</div>

				<div class="frames-section">
					<div class="section-header">
						<span><i class="fa fa-list"></i> Frames Assessment</span>
					</div>
					<div class="table-container">
						<table class="table table-bordered frames-table">
							<thead>
								<tr>
									<th>Frame No</th>
									<th>Status</th>
									<th>Load Dispatch</th>
									<th>Load Ref. No</th>
									<th>From Warehouse</th>
									<th>To Warehouse</th>
									<th>Issues</th>
									<th>Damage Desc.</th>
									<th>Est. Amount</th>
									<th>Date</th>
								</tr>
							</thead>
							<tbody id="frames-list">
								<tr><td colspan="10" class="text-center">Loading...</td></tr>
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
			this.wrapper.find(".filter-load-dispatch").val("");
			this.wrapper.find(".filter-status").val("");
			this.wrapper.find(".filter-warehouse").val("");
			this.refresh();
		});
	}

	load_filter_options() {
		frappe.call({
			method: "rkg.rkg.page.damage_assessment_dashboard.damage_assessment_dashboard.get_filter_options",
			callback: (r) => {
				if (r.message) {
					// Load dispatch list
					if (r.message.load_dispatch_list) {
						const select = this.wrapper.find(".filter-load-dispatch");
						select.empty().append(`<option value="">All Load Dispatches</option>`);
						r.message.load_dispatch_list.forEach((ref) => {
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
			load_dispatch: this.wrapper.find(".filter-load-dispatch").val(),
			status: this.wrapper.find(".filter-status").val(),
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
		this.wrapper.find("#not-ok-frames").text(summary.not_ok_frames || 0);
		
		// Format currency - simple manual formatting to avoid HTML rendering issues
		const totalCost = flt(summary.total_cost || 0);
		const formattedCost = "₹ " + totalCost.toLocaleString('en-IN', { 
			minimumFractionDigits: 2, 
			maximumFractionDigits: 2 
		});
		this.wrapper.find("#total-cost").text(formattedCost);
	}

	render_frames_table(frames) {
		const tbody = this.wrapper.find("#frames-list");
		tbody.empty();

		if (!frames || frames.length === 0) {
			tbody.html(`<tr><td colspan="10" class="text-center">No frames found for the selected filters.</td></tr>`);
			return;
		}

		const rows = frames.map((frame) => {
			const status = frame.status || "OK";
			const statusClass = status === "Not OK" ? "status-not-ok" : "status-ok";
			const statusIcon = status === "Not OK" ? "fa-exclamation-triangle" : "fa-check-circle";
			
			// Build issues string from issue_1, issue_2, issue_3
			const issues = [];
			if (frame.issue_1) issues.push(frame.issue_1);
			if (frame.issue_2) issues.push(frame.issue_2);
			if (frame.issue_3) issues.push(frame.issue_3);
			const issuesText = issues.length > 0 ? issues.join(", ") : "-";
			
			// Truncate damage description if too long
			const damageDesc = frame.damage_description || "-";
			const truncatedDesc = damageDesc.length > 30 ? damageDesc.substring(0, 30) + "..." : damageDesc;
			
			// Truncate warehouse names if too long
			const truncateText = (text, maxLen = 20) => {
				if (!text || text === "-") return "-";
				return text.length > maxLen ? text.substring(0, maxLen) + "..." : text;
			};
			
			return `
				<tr class="${statusClass}">
					<td>
						${frame.serial_no ? `<a href="/app/serial-no/${frame.serial_no}" target="_blank">${frame.serial_no}</a>` : "-"}
					</td>
					<td>
						<span class="status-badge ${statusClass}">
							<i class="fa ${statusIcon}"></i> ${status}
						</span>
					</td>
					<td>
						${frame.load_dispatch ? `<a href="/app/load-dispatch/${frame.load_dispatch}" target="_blank">${frame.load_dispatch}</a>` : "-"}
					</td>
					<td>
						${frame.load_reference_no ? `<a href="/app/load-plan/${frame.load_reference_no}" target="_blank" title="${frame.load_reference_no}">${truncateText(frame.load_reference_no, 15)}</a>` : "-"}
					</td>
					<td title="${frame.from_warehouse || '-'}">${truncateText(frame.from_warehouse, 20) || "-"}</td>
					<td title="${frame.to_warehouse || '-'}">${truncateText(frame.to_warehouse, 20) || "-"}</td>
					<td title="${issuesText}">${truncateText(issuesText, 25)}</td>
					<td title="${damageDesc}">${truncatedDesc}</td>
					<td>${frappe.format(frame.estimated_cost || 0, { fieldtype: "Currency" })}</td>
					<td>${frame.assessment_date ? frappe.datetime.str_to_user(frame.assessment_date) : "-"}</td>
				</tr>
			`;
		}).join("");

		tbody.html(rows);
	}
}

function add_styles() {
	$(`<style>
		.damage-assessment-dashboard { 
			padding: 20px; 
			background: var(--bg-color); 
			max-width: 100%;
		}
		
		.filters-section { 
			background: var(--card-bg); 
			padding: 20px; 
			border-radius: 8px; 
			box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
			margin-bottom: 20px; 
		}
		
		.filters-grid { 
			display: grid; 
			grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
			gap: 16px; 
			align-items: end; 
		}
		
		.filter-group label { 
			font-size: 12px; 
			font-weight: 600; 
			color: var(--text-muted); 
			text-transform: uppercase; 
			margin-bottom: 6px; 
			display: block;
		}
		
		.filter-group .form-control {
			width: 100%;
		}
		
		.filter-actions { 
			display: flex; 
			gap: 10px; 
			align-items: flex-end;
		}
		
		.filter-actions .btn {
			white-space: nowrap;
		}

		.summary-cards { 
			display: grid; 
			grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); 
			gap: 16px; 
			margin-bottom: 20px; 
		}
		
		.summary-card { 
			background: var(--card-bg); 
			border-radius: 8px; 
			padding: 20px; 
			box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
			border-left: 4px solid var(--primary); 
			transition: transform 0.2s, box-shadow 0.2s;
		}
		
		.summary-card:hover {
			transform: translateY(-2px);
			box-shadow: 0 4px 8px rgba(0,0,0,0.12);
		}
		
		.summary-card .card-icon { 
			font-size: 28px; 
			margin-bottom: 10px; 
		}
		
		.summary-card.total .card-icon { color: #4dabf7; }
		.summary-card.not-ok .card-icon { color: #ff6b6b; }
		.summary-card.cost .card-icon { color: #ffd43b; }
		
		.summary-card .card-value { 
			font-size: 32px; 
			font-weight: 700; 
			color: var(--heading-color); 
			margin-bottom: 4px;
		}
		
		.summary-card .card-label { 
			font-size: 12px; 
			color: var(--text-muted); 
			text-transform: uppercase; 
			letter-spacing: 0.5px; 
		}
		
		.summary-card.total { border-left-color: #4dabf7; }
		.summary-card.not-ok { border-left-color: #ff6b6b; }
		.summary-card.cost { border-left-color: #ffd43b; }
		
		.status-badge { 
			display: inline-flex; 
			align-items: center; 
			gap: 6px; 
			padding: 4px 10px; 
			border-radius: 4px; 
			font-size: 11px; 
			font-weight: 600; 
			white-space: nowrap;
		}
		
		.status-badge.status-ok { 
			background: #d3f9d8; 
			color: #2b8a3e; 
		}
		
		.status-badge.status-not-ok { 
			background: #ffe0e0; 
			color: #c92a2a; 
		}
		
		.frames-table tbody tr.status-not-ok { 
			background: #fff5f5; 
		}
		
		.frames-table tbody tr.status-ok { 
			background: #f8fff9; 
		}

		.frames-section { 
			background: var(--card-bg); 
			border-radius: 8px; 
			padding: 20px; 
			box-shadow: 0 2px 4px rgba(0,0,0,0.08); 
		}
		
		.section-header { 
			font-weight: 600; 
			font-size: 16px;
			color: var(--heading-color); 
			margin-bottom: 16px; 
			display: flex; 
			align-items: center; 
			gap: 8px; 
			padding-bottom: 12px;
			border-bottom: 2px solid var(--border-color);
		}
		
		.table-container { 
			width: 100%;
			overflow: visible;
			position: relative;
		}
		
		.frames-table { 
			width: 100%; 
			border-collapse: separate;
			border-spacing: 0;
			margin-top: 0;
			table-layout: fixed;
		}
		
		.frames-table thead { 
			background: var(--bg-light-gray); 
		}
		
		.frames-table th { 
			padding: 12px 8px; 
			text-align: left; 
			font-weight: 600; 
			font-size: 12px;
			color: var(--heading-color); 
			border: 1px solid var(--border-color);
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
		}
		
		.frames-table td { 
			padding: 10px 8px; 
			border: 1px solid var(--border-color);
			font-size: 13px;
			word-wrap: break-word;
			overflow-wrap: break-word;
		}
		
		.frames-table tbody tr:nth-child(even) { 
			background: var(--bg-color); 
		}
		
		.frames-table tbody tr:hover { 
			background: var(--control-bg); 
		}
		
		.frames-table a { 
			color: var(--primary); 
			text-decoration: none; 
		}
		
		.frames-table a:hover { 
			text-decoration: underline; 
		}
		
		/* Column width management - optimized to prevent horizontal scroll */
		.frames-table th:nth-child(1), .frames-table td:nth-child(1) { width: 11%; min-width: 120px; } /* Frame No */
		.frames-table th:nth-child(2), .frames-table td:nth-child(2) { width: 7%; min-width: 80px; } /* Status */
		.frames-table th:nth-child(3), .frames-table td:nth-child(3) { width: 9%; min-width: 100px; } /* Load Dispatch */
		.frames-table th:nth-child(4), .frames-table td:nth-child(4) { width: 11%; min-width: 120px; } /* Load Reference No */
		.frames-table th:nth-child(5), .frames-table td:nth-child(5) { width: 13%; min-width: 140px; } /* From Warehouse */
		.frames-table th:nth-child(6), .frames-table td:nth-child(6) { width: 13%; min-width: 140px; } /* To Warehouse */
		.frames-table th:nth-child(7), .frames-table td:nth-child(7) { width: 12%; min-width: 130px; } /* Issues */
		.frames-table th:nth-child(8), .frames-table td:nth-child(8) { width: 10%; min-width: 110px; } /* Damage Description */
		.frames-table th:nth-child(9), .frames-table td:nth-child(9) { width: 8%; min-width: 90px; } /* Estimated Amount */
		.frames-table th:nth-child(10), .frames-table td:nth-child(10) { width: 7%; min-width: 80px; } /* Assessment Date */
		
		/* Responsive adjustments */
		@media (max-width: 1400px) {
			.frames-table th, .frames-table td {
				font-size: 12px;
				padding: 8px 6px;
			}
		}
		
		/* Better text handling for long content - show tooltip on hover */
		.frames-table td {
			position: relative;
		}
		
		/* Ensure proper text overflow handling */
		.frames-table td:nth-child(1) a,
		.frames-table td:nth-child(3) a,
		.frames-table td:nth-child(4) a {
			display: inline-block;
			max-width: 100%;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}
		
		/* Tooltip effect for truncated cells */
		.frames-table td[title]:hover::after {
			content: attr(title);
			position: absolute;
			left: 50%;
			transform: translateX(-50%);
			bottom: 100%;
			margin-bottom: 5px;
			padding: 6px 10px;
			background: rgba(0, 0, 0, 0.85);
			color: white;
			border-radius: 4px;
			font-size: 12px;
			white-space: normal;
			word-wrap: break-word;
			max-width: 250px;
			z-index: 1000;
			pointer-events: none;
			box-shadow: 0 2px 8px rgba(0,0,0,0.2);
		}
		
		.frames-table td[title]:hover::before {
			content: '';
			position: absolute;
			left: 50%;
			transform: translateX(-50%);
			bottom: 100%;
			margin-bottom: -1px;
			border: 5px solid transparent;
			border-top-color: rgba(0, 0, 0, 0.85);
			z-index: 1001;
			pointer-events: none;
		}
	</style>`).appendTo("head");
}

