// Helper function to format numbers
function format_number(value, precision) {
	const num = parseFloat(value) || 0;
	if (precision === 0) {
		return Math.round(num).toString();
	}
	return num.toFixed(precision);
}

frappe.pages["battery-ageing-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Battery Ageing Dashboard",
		single_column: true,
	});

	add_styles();
	page.battery_ageing_dashboard = new BatteryAgeingDashboard(page);
};

frappe.pages["battery-ageing-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.page.battery_ageing_dashboard) {
		wrapper.page.battery_ageing_dashboard.refresh();
	}
};

class BatteryAgeingDashboard {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.charts = {};
		this.allBatteries = [];
		this.filteredBatteries = [];
		this.currentPage = 1;
		this.itemsPerPage = 50;
		this.viewMode = "table"; // "table" or "grid"
		this.sortField = "creation";
		this.sortOrder = "desc";
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
			<div class="battery-ageing-dashboard">
				<div class="filters-section">
					<div class="filters-grid">
						<div class="filter-group">
							<label>Brand</label>
							<select class="form-control filter-brand">
								<option value="">All Brands</option>
							</select>
						</div>
						<div class="filter-group">
							<label>Battery Type</label>
							<select class="form-control filter-battery-type">
								<option value="">All Types</option>
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
						<div class="card-icon"><i class="fa fa-battery-full"></i></div>
						<div class="card-value" id="total-batteries">0</div>
						<div class="card-label">Total Batteries</div>
					</div>
					<div class="summary-card age-0-30">
						<div class="card-icon"><i class="fa fa-check-circle"></i></div>
						<div class="card-value" id="age-0-30">0</div>
						<div class="card-label">0-30 Days</div>
					</div>
					<div class="summary-card age-60-days">
						<div class="card-icon"><i class="fa fa-calendar"></i></div>
						<div class="card-value" id="age-60-days">0</div>
						<div class="card-label">~60 Days Old</div>
					</div>
					<div class="summary-card age-31-90">
						<div class="card-icon"><i class="fa fa-clock-o"></i></div>
						<div class="card-value" id="age-31-90">0</div>
						<div class="card-label">31-90 Days</div>
					</div>
					<div class="summary-card age-365-plus">
						<div class="card-icon"><i class="fa fa-exclamation-triangle"></i></div>
						<div class="card-value" id="age-365-plus">0</div>
						<div class="card-label">365+ Days</div>
					</div>
				</div>

				<div class="expiry-risk-section">
					<div class="section-header">
						<span><i class="fa fa-exclamation-circle"></i> Expiry Risk / Attention Indicator</span>
					</div>
					<div class="risk-indicator-cards">
						<div class="risk-card safe" id="risk-safe-card">
							<div class="risk-card-header">
								<div class="risk-icon"><i class="fa fa-check-circle"></i></div>
								<div class="risk-label">Safe</div>
							</div>
							<div class="risk-value" id="risk-safe-count">0</div>
							<div class="risk-percentage" id="risk-safe-percentage">0%</div>
							<div class="risk-description">0-180 days</div>
						</div>
						<div class="risk-card warning" id="risk-warning-card">
							<div class="risk-card-header">
								<div class="risk-icon"><i class="fa fa-exclamation-triangle"></i></div>
								<div class="risk-label">Warning</div>
							</div>
							<div class="risk-value" id="risk-warning-count">0</div>
							<div class="risk-percentage" id="risk-warning-percentage">0%</div>
							<div class="risk-description">181-365 days</div>
						</div>
						<div class="risk-card critical" id="risk-critical-card">
							<div class="risk-card-header">
								<div class="risk-icon"><i class="fa fa-times-circle"></i></div>
								<div class="risk-label">Critical</div>
							</div>
							<div class="risk-value" id="risk-critical-count">0</div>
							<div class="risk-percentage" id="risk-critical-percentage">0%</div>
							<div class="risk-description">365+ days</div>
						</div>
					</div>
				</div>

				<div class="charts-section">
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-pie-chart"></i> Age Distribution
						</div>
						<div id="age-chart"></div>
					</div>
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-bar-chart"></i> Brand Distribution
						</div>
						<div id="brand-chart"></div>
					</div>
					<div class="chart-container">
						<div class="chart-title">
							<i class="fa fa-bar-chart"></i> Battery Type Distribution
						</div>
						<div id="battery-type-chart"></div>
					</div>
				</div>

				<div class="batteries-section">
					<div class="section-header">
						<div style="flex: 1;">
							<span><i class="fa fa-list"></i> Batteries</span>
							<span class="batteries-count-badge" id="batteries-count">0</span>
						</div>
						<div class="batteries-controls">
							<div class="search-box">
								<input type="text" class="form-control battery-search" placeholder="Search batteries..." />
								<i class="fa fa-search"></i>
							</div>
							<div class="view-toggle">
								<button class="btn btn-sm btn-default view-btn active" data-view="table" title="Table View">
									<i class="fa fa-table"></i>
								</button>
								<button class="btn btn-sm btn-default view-btn" data-view="grid" title="Grid View">
									<i class="fa fa-th"></i>
								</button>
							</div>
							<select class="form-control sort-select" style="width: 150px;">
								<option value="creation-desc">Newest First</option>
								<option value="creation-asc">Oldest First</option>
								<option value="age_days-asc">Age (Low to High)</option>
								<option value="age_days-desc">Age (High to Low)</option>
								<option value="battery_serial_no-asc">Serial No (A-Z)</option>
								<option value="brand-asc">Brand (A-Z)</option>
								<option value="battery_type-asc">Type (A-Z)</option>
							</select>
						</div>
					</div>
					<div id="batteries-list"></div>
					<div class="pagination-container" id="pagination-container"></div>
				</div>

				<!-- Battery Information Section -->
				<div class="battery-details-section" id="battery-details-section" style="display: none;">
					<div class="section-header">
						<button class="btn btn-sm btn-default btn-back-to-list" style="margin-right: 10px;">
							<i class="fa fa-arrow-left"></i> Back to List
						</button>
						<span><i class="fa fa-info-circle"></i> Battery Information</span>
					</div>
					<div id="battery-details"></div>
				</div>
			</div>
		`);
	}

	setup_filters() {
		this.wrapper.find(".btn-refresh").on("click", () => this.refresh());
		this.wrapper.find(".btn-clear").on("click", () => {
			this.wrapper.find(".filter-brand").val("");
			this.wrapper.find(".filter-battery-type").val("");
			this.wrapper.find(".filter-from-date").val("");
			this.wrapper.find(".filter-to-date").val("");
			this.wrapper.find(".battery-search").val("");
			this.refresh();
		});

		// Back to list button
		this.wrapper.find(".btn-back-to-list").on("click", () => {
			this.hide_battery_details();
		});

		// Search box
		const self = this;
		this.wrapper.find(".battery-search").on("input", function() {
			self.filterAndRender();
		});

		// View toggle
		this.wrapper.find(".view-btn").on("click", function() {
			self.wrapper.find(".view-btn").removeClass("active");
			$(this).addClass("active");
			self.viewMode = $(this).data("view");
			self.filterAndRender();
		});

		// Sort select
		this.wrapper.find(".sort-select").on("change", function() {
			const value = $(this).val().split("-");
			self.sortField = value[0];
			self.sortOrder = value[1];
			self.filterAndRender();
		});
	}

	load_filter_options() {
		frappe.call({
			method: "rkg.rkg.page.battery_ageing_dashboard.battery_ageing_dashboard.get_filter_options",
			callback: (r) => {
				if (r.message) {
					// Load brands
					if (r.message.brands) {
						const select = this.wrapper.find(".filter-brand");
						select.empty().append(`<option value="">All Brands</option>`);
						r.message.brands.forEach((brand) => {
							select.append(`<option value="${brand}">${brand}</option>`);
						});
					}
					// Load battery types
					if (r.message.battery_types) {
						const select = this.wrapper.find(".filter-battery-type");
						select.empty().append(`<option value="">All Types</option>`);
						r.message.battery_types.forEach((type) => {
							select.append(`<option value="${type}">${type}</option>`);
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
			brand: this.wrapper.find(".filter-brand").val() || null,
			battery_type: this.wrapper.find(".filter-battery-type").val() || null,
			from_date: from_date_val && from_date_val.trim() ? from_date_val : null,
			to_date: to_date_val && to_date_val.trim() ? to_date_val : null,
		};

		frappe.call({
			method: "rkg.rkg.page.battery_ageing_dashboard.battery_ageing_dashboard.get_dashboard_data",
			args: filters,
			callback: (r) => {
				if (r.message) {
					this.render_summary(r.message.summary || {});
					this.render_age_chart(r.message.age_chart || {});
					this.render_brand_chart(r.message.brand_chart || {});
					this.render_battery_type_chart(r.message.battery_type_chart || {});
					this.render_batteries_list(r.message.batteries || []);
				} else {
					this.render_summary({});
					this.render_age_chart({});
					this.render_brand_chart({});
					this.render_battery_type_chart({});
					this.render_batteries_list([]);
				}
			},
			error: (r) => {
				console.error("Error loading dashboard data:", r);
				frappe.msgprint(__("Unable to load dashboard data right now."));
				this.render_summary({});
				this.render_batteries_list([]);
			},
		});
	}

	render_summary(summary) {
		const total = summary.total_batteries || 0;
		const age_ranges = summary.age_ranges || {};
		const expiry_risk_counts = summary.expiry_risk_counts || {};
		const expiry_risk_percentages = summary.expiry_risk_percentages || {};
		const batteries_60_days = summary.batteries_60_days || 0;
		
		this.wrapper.find("#total-batteries").text(format_number(total, 0));
		this.wrapper.find("#age-0-30").text(format_number(age_ranges["0-30 days"] || 0, 0));
		this.wrapper.find("#age-60-days").text(format_number(batteries_60_days, 0));
		this.wrapper.find("#age-31-90").text(format_number((age_ranges["31-90 days"] || 0) + (age_ranges["91-180 days"] || 0) + (age_ranges["181-365 days"] || 0), 0));
		this.wrapper.find("#age-365-plus").text(format_number(age_ranges["365+ days"] || 0, 0));
		
		// Render Expiry Risk indicators
		this.render_expiry_risk_indicators(expiry_risk_counts, expiry_risk_percentages);
	}

	render_expiry_risk_indicators(expiry_risk_counts, expiry_risk_percentages) {
		const safe_count = expiry_risk_counts.safe || 0;
		const warning_count = expiry_risk_counts.warning || 0;
		const critical_count = expiry_risk_counts.critical || 0;
		
		const safe_percentage = expiry_risk_percentages.safe || 0;
		const warning_percentage = expiry_risk_percentages.warning || 0;
		const critical_percentage = expiry_risk_percentages.critical || 0;
		
		this.wrapper.find("#risk-safe-count").text(format_number(safe_count, 0));
		this.wrapper.find("#risk-safe-percentage").text(format_number(safe_percentage, 1) + "%");
		
		this.wrapper.find("#risk-warning-count").text(format_number(warning_count, 0));
		this.wrapper.find("#risk-warning-percentage").text(format_number(warning_percentage, 1) + "%");
		
		this.wrapper.find("#risk-critical-count").text(format_number(critical_count, 0));
		this.wrapper.find("#risk-critical-percentage").text(format_number(critical_percentage, 1) + "%");
	}

	render_age_chart(data) {
		const container = this.wrapper.find("#age-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No age data"));
			return;
		}
		if (this.charts.ageChart && typeof this.charts.ageChart.destroy === "function") {
			this.charts.ageChart.destroy();
		}
		$(container).empty();
		this.charts.ageChart = new frappe.Chart(container, {
			data: { labels: data.labels, datasets: [{ name: "Batteries", values: data.values }] },
			type: "pie",
			height: 260,
			colors: ["#00d4aa", "#5e64ff", "#ffa726", "#ff6b6b", "#ab47bc"],
		});
	}

	render_brand_chart(data) {
		const container = this.wrapper.find("#brand-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No brand data"));
			return;
		}
		if (this.charts.brandChart && typeof this.charts.brandChart.destroy === "function") {
			this.charts.brandChart.destroy();
		}
		$(container).empty();
		this.charts.brandChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [{ name: "Batteries", values: data.values }],
			},
			type: "bar",
			height: 260,
			colors: ["#5e64ff"],
			barOptions: { spaceRatio: 0.5 },
		});
	}

	render_battery_type_chart(data) {
		const container = this.wrapper.find("#battery-type-chart")[0];
		if (!data || !data.labels || data.labels.length === 0) {
			$(container).html(no_data("No battery type data"));
			return;
		}
		if (this.charts.batteryTypeChart && typeof this.charts.batteryTypeChart.destroy === "function") {
			this.charts.batteryTypeChart.destroy();
		}
		$(container).empty();
		this.charts.batteryTypeChart = new frappe.Chart(container, {
			data: {
				labels: data.labels,
				datasets: [{ name: "Batteries", values: data.values }],
			},
			type: "bar",
			height: 260,
			colors: ["#00d4aa"],
			barOptions: { spaceRatio: 0.5 },
		});
	}

	render_batteries_list(batteries) {
		this.allBatteries = batteries || [];
		this.currentPage = 1;
		this.filterAndRender();
	}

	filterAndRender() {
		const searchTerm = this.wrapper.find(".battery-search").val().toLowerCase().trim();
		this.filteredBatteries = this.allBatteries.filter(battery => {
			if (!searchTerm) return true;
			const searchable = [
				battery.battery_serial_no || "",
				battery.brand || "",
				battery.battery_type || "",
				battery.frame_no || "",
				battery.charging_code || "",
				battery.age_days?.toString() || ""
			].join(" ").toLowerCase();
			return searchable.includes(searchTerm);
		});

		this.filteredBatteries.sort((a, b) => {
			let aVal = a[this.sortField] || "";
			let bVal = b[this.sortField] || "";
			
			if (this.sortField === "creation" || this.sortField === "age_days") {
				aVal = parseFloat(aVal) || 0;
				bVal = parseFloat(bVal) || 0;
			} else {
				aVal = String(aVal).toLowerCase();
				bVal = String(bVal).toLowerCase();
			}
			
			if (this.sortOrder === "asc") {
				return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
			} else {
				return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
			}
		});

		this.wrapper.find("#batteries-count").text(this.filteredBatteries.length);

		const totalPages = Math.ceil(this.filteredBatteries.length / this.itemsPerPage);
		const startIndex = (this.currentPage - 1) * this.itemsPerPage;
		const endIndex = startIndex + this.itemsPerPage;
		const paginatedBatteries = this.filteredBatteries.slice(startIndex, endIndex);

		const container = this.wrapper.find("#batteries-list");
		container.empty();

		if (paginatedBatteries.length === 0) {
			container.html(no_data("No Batteries found."));
			this.wrapper.find("#pagination-container").empty();
			return;
		}

		if (this.viewMode === "table") {
			container.html(this.build_table_view(paginatedBatteries));
		} else {
			container.html(this.build_grid_view(paginatedBatteries));
		}

		const self = this;
		container.find(".battery-row, .battery-card").on("click", (e) => {
			const element = $(e.currentTarget);
			const name = element.data("name");
			if (name) {
				self.show_battery_details(name);
			}
		});

		this.render_pagination(totalPages);
	}

	build_table_view(batteries) {
		const rows = batteries.map(battery => {
			const ageDays = battery.age_days || 0;
			const ageClass = ageDays <= 30 ? "age-new" : ageDays <= 365 ? "age-medium" : "age-old";
			return `
				<tr class="battery-row ${ageClass}" data-name="${battery.name}" style="cursor: pointer;">
					<td><strong>${battery.battery_serial_no || "-"}</strong></td>
					<td>${battery.brand || "-"}</td>
					<td>${battery.battery_type || "-"}</td>
					<td><span class="age-badge ${ageClass}">${ageDays} days</span></td>
					<td>${battery.charging_date ? battery.charging_date.split(' ')[0] : "-"}</td>
					<td>${battery.status || "Active"}</td>
				</tr>
			`;
		}).join("");

		return `
			<div class="table-container">
				<table class="table table-bordered batteries-table">
					<thead>
						<tr>
							<th>Battery Serial No</th>
							<th>Brand</th>
							<th>Battery Type</th>
							<th>Age</th>
							<th>Charging Date</th>
							<th>Status</th>
						</tr>
					</thead>
					<tbody>
						${rows}
					</tbody>
				</table>
			</div>
		`;
	}

	build_grid_view(batteries) {
		const cards = batteries.map((battery) => this.build_battery_card(battery)).join("");
		return `<div class="batteries-grid">${cards}</div>`;
	}

	render_pagination(totalPages) {
		if (totalPages <= 1) {
			this.wrapper.find("#pagination-container").empty();
			return;
		}

		const container = this.wrapper.find("#pagination-container");
		let paginationHTML = `<div class="pagination-info">Showing ${((this.currentPage - 1) * this.itemsPerPage) + 1} to ${Math.min(this.currentPage * this.itemsPerPage, this.filteredBatteries.length)} of ${this.filteredBatteries.length} batteries</div>`;
		paginationHTML += `<div class="pagination-buttons">`;

		if (this.currentPage > 1) {
			paginationHTML += `<button class="btn btn-sm btn-default page-btn" data-page="${this.currentPage - 1}"><i class="fa fa-chevron-left"></i> Previous</button>`;
		}

		const maxPages = 7;
		let startPage = Math.max(1, this.currentPage - Math.floor(maxPages / 2));
		let endPage = Math.min(totalPages, startPage + maxPages - 1);
		
		if (endPage - startPage < maxPages - 1) {
			startPage = Math.max(1, endPage - maxPages + 1);
		}

		if (startPage > 1) {
			paginationHTML += `<button class="btn btn-sm btn-default page-btn" data-page="1">1</button>`;
			if (startPage > 2) {
				paginationHTML += `<span class="pagination-ellipsis">...</span>`;
			}
		}

		for (let i = startPage; i <= endPage; i++) {
			const activeClass = i === this.currentPage ? "active" : "";
			paginationHTML += `<button class="btn btn-sm btn-default page-btn ${activeClass}" data-page="${i}">${i}</button>`;
		}

		if (endPage < totalPages) {
			if (endPage < totalPages - 1) {
				paginationHTML += `<span class="pagination-ellipsis">...</span>`;
			}
			paginationHTML += `<button class="btn btn-sm btn-default page-btn" data-page="${totalPages}">${totalPages}</button>`;
		}

		if (this.currentPage < totalPages) {
			paginationHTML += `<button class="btn btn-sm btn-default page-btn" data-page="${this.currentPage + 1}">Next <i class="fa fa-chevron-right"></i></button>`;
		}

		paginationHTML += `</div>`;
		container.html(paginationHTML);

		const self = this;
		container.find(".page-btn").on("click", function() {
			self.currentPage = parseInt($(this).data("page"));
			self.filterAndRender();
			self.wrapper.find(".batteries-section")[0].scrollIntoView({ behavior: "smooth", block: "start" });
		});
	}

	build_battery_card(battery) {
		const ageDays = battery.age_days || 0;
		const ageClass = ageDays <= 30 ? "age-new" : ageDays <= 365 ? "age-medium" : "age-old";
		
		return `
			<div class="battery-card ${ageClass}" data-doctype="Battery Information" data-name="${battery.name || ''}" style="cursor: pointer;">
				<div class="battery-card__header">
					<div>
						<div class="battery-code">${battery.battery_serial_no || "-"}</div>
						<div class="battery-name">${battery.brand || "-"}</div>
					</div>
					<div class="age-badge ${ageClass}">
						${ageDays} days
					</div>
				</div>
				<div class="battery-card__body">
					<div class="battery-metrics">
						<div><span class="muted">Brand</span><div class="metric-value">${battery.brand || "-"}</div></div>
						<div><span class="muted">Type</span><div class="metric-value">${battery.battery_type || "-"}</div></div>
						<div><span class="muted">Status</span><div class="metric-value">${battery.status || "Active"}</div></div>
					</div>
					${battery.charging_date ? `<div class="battery-date"><i class="fa fa-bolt"></i> Charged: ${battery.charging_date.split(' ')[0]}</div>` : ""}
					<div class="battery-date"><i class="fa fa-calendar"></i> Created: ${battery.creation_date ? battery.creation_date.split(' ')[0] : "-"}</div>
				</div>
			</div>
		`;
	}

	show_battery_details(name) {
		this.wrapper.find(".batteries-section").hide();
		this.wrapper.find("#battery-details-section").show();

		frappe.call({
			method: "rkg.rkg.page.battery_ageing_dashboard.battery_ageing_dashboard.get_battery_details",
			args: { name: name },
			callback: (r) => {
				if (r.message) {
					this.render_battery_details(r.message);
				}
			},
			error: () => {
				frappe.msgprint(__("Unable to load Battery Information."));
			},
		});
	}

	hide_battery_details() {
		this.wrapper.find("#battery-details-section").hide();
		this.wrapper.find(".batteries-section").show();
	}

	render_battery_details(data) {
		const container = this.wrapper.find("#battery-details");
		const battery = data.battery || {};
		const ageDays = battery.age_days || 0;
		const ageClass = ageDays <= 30 ? "age-new" : ageDays <= 365 ? "age-medium" : "age-old";

		container.html(`
			<div class="battery-details-card">
				<div class="details-header">
					<h3>${battery.battery_serial_no || battery.name || "-"}</h3>
					<span class="age-badge ${ageClass}">${ageDays} days old</span>
				</div>
				<div class="details-body">
					<div class="details-row">
						<div class="detail-item">
							<label>Battery Serial No:</label>
							<span><strong>${battery.battery_serial_no || "-"}</strong></span>
						</div>
						<div class="detail-item">
							<label>Status:</label>
							<span><strong>${battery.status || "Active"}</strong></span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Brand:</label>
							<span><strong>${battery.brand || "-"}</strong></span>
						</div>
						<div class="detail-item">
							<label>Battery Type:</label>
							<span><strong>${battery.battery_type || "-"}</strong></span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Charging Date:</label>
							<span>${battery.charging_date ? battery.charging_date.split(' ')[0] : "-"}</span>
						</div>
						<div class="detail-item">
							<label>Age:</label>
							<span><strong>${ageDays} days</strong></span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Created:</label>
							<span>${battery.creation ? frappe.datetime.str_to_user(battery.creation) : "-"}</span>
						</div>
						<div class="detail-item">
							<label>Modified:</label>
							<span>${battery.modified ? frappe.datetime.str_to_user(battery.modified) : "-"}</span>
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
		.battery-ageing-dashboard { padding: 18px; background: var(--bg-color); }
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
		.summary-card.age-0-30 { border-left-color: #00d4aa; }
		.summary-card.age-60-days { border-left-color: #ff9800; }
		.summary-card.age-31-90 { border-left-color: #ffa726; }
		.summary-card.age-365-plus { border-left-color: #ff6b6b; }

		.expiry-risk-section { background: var(--card-bg); border-radius: 12px; padding: 20px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); margin-bottom: 20px; }
		.risk-indicator-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-top: 16px; }
		.risk-card { border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: transform 0.2s, box-shadow 0.2s; border-top: 4px solid; }
		.risk-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
		.risk-card.safe { border-top-color: #00d4aa; background: linear-gradient(135deg, #e8f5e9 0%, #f1f8e9 100%); }
		.risk-card.warning { border-top-color: #ffa726; background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); }
		.risk-card.critical { border-top-color: #ff6b6b; background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%); }
		.risk-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
		.risk-icon { font-size: 24px; }
		.risk-card.safe .risk-icon { color: #00d4aa; }
		.risk-card.warning .risk-icon { color: #ffa726; }
		.risk-card.critical .risk-icon { color: #ff6b6b; }
		.risk-label { font-size: 16px; font-weight: 700; color: var(--heading-color); text-transform: uppercase; letter-spacing: 0.5px; }
		.risk-value { font-size: 36px; font-weight: 700; color: var(--heading-color); margin-bottom: 4px; }
		.risk-percentage { font-size: 18px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; }
		.risk-description { font-size: 13px; color: var(--text-muted); font-style: italic; }

		.charts-section { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 20px; }
		.chart-container { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.chart-title { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }

		.batteries-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.section-header { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
		.batteries-count-badge { background: var(--primary); color: white; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; margin-left: 8px; }
		.batteries-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
		.search-box { position: relative; width: 250px; }
		.search-box input { padding-right: 30px; }
		.search-box i { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); color: var(--text-muted); pointer-events: none; }
		.view-toggle { display: flex; gap: 4px; }
		.view-btn { padding: 6px 12px; }
		.view-btn.active { background: var(--primary); color: white; }
		.sort-select { height: 32px; font-size: 12px; }
		
		.table-container { overflow-x: auto; margin-top: 12px; }
		.batteries-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.batteries-table thead { background: var(--bg-light-gray); position: sticky; top: 0; z-index: 10; }
		.batteries-table th { padding: 12px 10px; text-align: left; font-weight: 600; color: var(--heading-color); border: 1px solid var(--border-color); white-space: nowrap; }
		.batteries-table td { padding: 10px; border: 1px solid var(--border-color); }
		.batteries-table tbody tr { background: var(--control-bg); }
		.batteries-table tbody tr:hover { background: var(--bg-color); cursor: pointer; }
		.batteries-table tbody tr:nth-child(even) { background: var(--card-bg); }
		.batteries-table tbody tr:nth-child(even):hover { background: var(--bg-color); }
		
		.age-badge { font-size: 12px; font-weight: 600; padding: 6px 10px; border-radius: 14px; display: inline-block; }
		.age-badge.age-new { background: #e0f7f2; color: #0b8c6b; }
		.age-badge.age-medium { background: #ffe0b2; color: #e65100; }
		.age-badge.age-old { background: #ffcdd2; color: #c62828; }
		.battery-row.age-new { border-left: 3px solid #00d4aa; }
		.battery-row.age-medium { border-left: 3px solid #ffa726; }
		.battery-row.age-old { border-left: 3px solid #ff6b6b; }
		
		.batteries-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
		.battery-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; background: var(--control-bg); box-shadow: 0 1px 4px rgba(0,0,0,0.04); transition: transform 0.2s, box-shadow 0.2s; }
		.battery-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
		.battery-card.age-new { border-left: 4px solid #00d4aa; }
		.battery-card.age-medium { border-left: 4px solid #ffa726; }
		.battery-card.age-old { border-left: 4px solid #ff6b6b; }
		.battery-card__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
		.battery-code { font-weight: 700; color: var(--heading-color); font-size: 16px; }
		.battery-name { color: var(--text-muted); font-size: 12px; margin-top: 4px; }
		.battery-card__body { display: flex; flex-direction: column; gap: 8px; }
		.battery-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
		.metric-value { font-weight: 700; color: var(--heading-color); font-size: 13px; }
		.muted { color: var(--text-muted); font-size: 12px; }
		.battery-date { color: var(--text-muted); font-size: 11px; display: flex; align-items: center; gap: 4px; }
		.battery-date.expiry-warning { color: #ff6b6b; font-weight: 600; }
		.text-danger { color: #ff6b6b !important; }
		.text-warning { color: #ffa726 !important; }
		
		.pagination-container { margin-top: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
		.pagination-info { color: var(--text-muted); font-size: 13px; }
		.pagination-buttons { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
		.page-btn { padding: 6px 12px; min-width: 40px; }
		.page-btn.active { background: var(--primary); color: white; border-color: var(--primary); }
		.pagination-ellipsis { padding: 0 8px; color: var(--text-muted); }

		.no-data { text-align: center; color: var(--text-muted); padding: 30px 10px; }
		.no-data i { font-size: 32px; margin-bottom: 8px; opacity: 0.6; }

		.battery-details-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.battery-details-card { background: var(--control-bg); border-radius: 10px; padding: 20px; }
		.details-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid var(--border-color); }
		.details-header h3 { margin: 0; color: var(--heading-color); }
		.details-body { margin-top: 20px; }
		.details-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
		.detail-item { display: flex; flex-direction: column; gap: 5px; }
		.detail-item label { font-weight: 600; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
		.detail-item span { color: var(--heading-color); font-size: 14px; }
	</style>`).appendTo("head");
}

