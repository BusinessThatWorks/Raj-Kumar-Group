// Helper function to format numbers
function format_number(value, precision) {
	const num = parseFloat(value) || 0;
	if (precision === 0) {
		return Math.round(num).toString();
	}
	return num.toFixed(precision);
}

frappe.pages["frame-aging-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Frame Aging Dashboard",
		single_column: true,
	});

	add_styles();
	page.frame_aging_dashboard = new FrameAgingDashboard(page);
};

frappe.pages["frame-aging-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.page.frame_aging_dashboard) {
		wrapper.page.frame_aging_dashboard.refresh();
	}
};

class FrameAgingDashboard {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.charts = {};
		this.allFrames = [];
		this.filteredFrames = [];
		this.currentPage = 1;
		this.itemsPerPage = 50;
		this.viewMode = "table"; // "table" or "grid"
		this.sortField = "age_days";
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
			<div class="frame-aging-dashboard">
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
					<div class="summary-card age-0-30">
						<div class="card-icon"><i class="fa fa-check-circle"></i></div>
						<div class="card-value" id="age-0-30">0</div>
						<div class="card-label">0-30 Days</div>
					</div>
					<div class="summary-card age-30-60">
						<div class="card-icon"><i class="fa fa-clock-o"></i></div>
						<div class="card-value" id="age-30-60">0</div>
						<div class="card-label">30-60 Days</div>
					</div>
					<div class="summary-card age-60-90">
						<div class="card-icon"><i class="fa fa-exclamation-triangle"></i></div>
						<div class="card-value" id="age-60-90">0</div>
						<div class="card-label">60-90 Days</div>
					</div>
					<div class="summary-card age-90-plus">
						<div class="card-icon"><i class="fa fa-times-circle"></i></div>
						<div class="card-value" id="age-90-plus">0</div>
						<div class="card-label">90+ Days</div>
					</div>
				</div>

				<div class="info-banner">
					<div class="info-item">
						<label>Start Date:</label>
						<span id="start-date-info">Purchase Receipt Creation Date</span>
					</div>
					<div class="info-item">
						<label>End Date:</label>
						<span id="end-date-info">Today's Date</span>
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
				</div>

				<div class="frames-section">
					<div class="section-header">
						<div style="flex: 1;">
							<span><i class="fa fa-list"></i> Frame Aging Data</span>
							<span class="frames-count-badge" id="frames-count">0</span>
						</div>
						<div class="frames-controls">
							<div class="search-box">
								<input type="text" class="form-control frame-search" placeholder="Search frames..." />
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
							<select class="form-control sort-select" style="width: 180px;">
								<option value="age_days-desc">Age (High to Low)</option>
								<option value="age_days-asc">Age (Low to High)</option>
								<option value="purchase_date-desc">Purchase Date (Newest)</option>
								<option value="purchase_date-asc">Purchase Date (Oldest)</option>
								<option value="frame_no-asc">Frame No (A-Z)</option>
								<option value="frame_no-desc">Frame No (Z-A)</option>
								<option value="item_code-asc">Item Code (A-Z)</option>
								<option value="warehouse-asc">Warehouse (A-Z)</option>
								<option value="status-asc">Status (A-Z)</option>
							</select>
						</div>
					</div>
					<div id="frames-list"></div>
					<div class="pagination-container" id="pagination-container"></div>
				</div>

				<!-- Frame No Details Section -->
				<div class="frame-no-details-section" id="frame-no-details-section" style="display: none;">
					<div class="section-header">
						<button class="btn btn-sm btn-default btn-back-to-list" style="margin-right: 10px;">
							<i class="fa fa-arrow-left"></i> Back to List
						</button>
						<span><i class="fa fa-info-circle"></i> Frame Aging Details</span>
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
			this.wrapper.find(".frame-search").val("");
			this.refresh();
		});

		// Back to list button
		this.wrapper.find(".btn-back-to-list").on("click", () => {
			this.hide_frame_no_details();
		});

		// Search box
		const self = this;
		this.wrapper.find(".frame-search").on("input", function() {
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
			method: "rkg.rkg.page.frame_aging_dashboard.frame_aging_dashboard.get_filter_options",
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
			method: "rkg.rkg.page.frame_aging_dashboard.frame_aging_dashboard.get_dashboard_data",
			args: filters,
			callback: (r) => {
				if (r.message) {
					this.render_summary(r.message.summary || {});
					this.render_age_chart(r.message.age_chart || {});
					this.render_warehouse_chart(r.message.warehouse_chart || {});
					this.render_item_chart(r.message.item_chart || {});
					this.render_frames_list(r.message.frames || []);
					
					// Update info banner
					const today = r.message.summary?.today_date || new Date().toISOString().split('T')[0];
					this.wrapper.find("#end-date-info").text(frappe.datetime.str_to_user(today));
				} else {
					this.render_summary({});
					this.render_age_chart({});
					this.render_warehouse_chart({});
					this.render_item_chart({});
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
		const age_ranges = summary.age_ranges || {};
		
		this.wrapper.find("#total-frames").text(format_number(total, 0));
		this.wrapper.find("#age-0-30").text(format_number(age_ranges["0-30 days"] || 0, 0));
		this.wrapper.find("#age-30-60").text(format_number(age_ranges["30-60 days"] || 0, 0));
		this.wrapper.find("#age-60-90").text(format_number(age_ranges["60-90 days"] || 0, 0));
		const age90Plus = (age_ranges["90-180 days"] || 0) + (age_ranges["180+ days"] || 0);
		this.wrapper.find("#age-90-plus").text(format_number(age90Plus, 0));
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
			data: {
				labels: data.labels,
				datasets: [{ name: "Frames", values: data.values }],
			},
			type: "pie",
			height: 260,
			colors: ["#00d4aa", "#5e64ff", "#ffa726", "#ff6b6b", "#c62828"],
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

	render_frames_list(frames) {
		// Store all frames
		this.allFrames = frames || [];
		this.currentPage = 1; // Reset to first page when new data loads
		this.filterAndRender();
	}

	filterAndRender() {
		// Filter by search term
		const searchTerm = this.wrapper.find(".frame-search").val().toLowerCase().trim();
		this.filteredFrames = this.allFrames.filter(frame => {
			if (!searchTerm) return true;
			const searchable = [
				frame.frame_no || "",
				frame.item_code || "",
				frame.item_name || "",
				frame.warehouse || "",
				frame.status || "",
				frame.color_code || "",
				frame.custom_engine_number || "",
				frame.age_days?.toString() || "",
				frame.purchase_date || ""
			].join(" ").toLowerCase();
			return searchable.includes(searchTerm);
		});

		// Sort frames
		this.filteredFrames.sort((a, b) => {
			let aVal = a[this.sortField] || "";
			let bVal = b[this.sortField] || "";
			
			// Handle dates and numbers
			if (this.sortField === "age_days") {
				aVal = parseFloat(aVal) || 0;
				bVal = parseFloat(bVal) || 0;
			} else if (this.sortField === "purchase_date" || this.sortField === "creation") {
				aVal = new Date(aVal || 0);
				bVal = new Date(bVal || 0);
			} else {
				// Convert to strings for comparison
				aVal = String(aVal).toLowerCase();
				bVal = String(bVal).toLowerCase();
			}
			
			if (this.sortOrder === "asc") {
				return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
			} else {
				return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
			}
		});

		// Update count
		this.wrapper.find("#frames-count").text(this.filteredFrames.length);

		// Paginate
		const totalPages = Math.ceil(this.filteredFrames.length / this.itemsPerPage);
		const startIndex = (this.currentPage - 1) * this.itemsPerPage;
		const endIndex = startIndex + this.itemsPerPage;
		const paginatedFrames = this.filteredFrames.slice(startIndex, endIndex);

		// Render based on view mode
		const container = this.wrapper.find("#frames-list");
		container.empty();

		if (paginatedFrames.length === 0) {
			container.html(no_data("No Frames found."));
			this.wrapper.find("#pagination-container").empty();
			return;
		}

		if (this.viewMode === "table") {
			container.html(this.build_table_view(paginatedFrames));
		} else {
			container.html(this.build_grid_view(paginatedFrames));
		}

		// Add click handlers
		const self = this;
		container.find(".frame-row, .frame-card").on("click", (e) => {
			const element = $(e.currentTarget);
			const name = element.data("name");
			if (name) {
				self.show_frame_no_details(name);
			}
		});

		// Render pagination
		this.render_pagination(totalPages);
	}

	build_table_view(frames) {
		const rows = frames.map(frame => {
			const ageDays = frame.age_days || 0;
			const ageClass = ageDays <= 30 ? "age-new" : ageDays <= 60 ? "age-recent" : ageDays <= 90 ? "age-moderate" : ageDays <= 180 ? "age-old" : "age-very-old";
			const purchaseDate = frame.purchase_date ? frame.purchase_date.split(' ')[0] : "-";
			
			return `
				<tr class="frame-row ${ageClass}" data-name="${frame.name}" style="cursor: pointer;">
					<td><strong>${frame.frame_no || frame.name || "-"}</strong></td>
					<td>${frame.item_code || "-"}</td>
					<td>${frame.item_name || "-"}</td>
					<td>${frame.warehouse || "-"}</td>
					<td><span class="frame-status">${frame.status || "Unknown"}</span></td>
					<td><span class="age-badge ${ageClass}">${ageDays} days</span></td>
					<td>${purchaseDate}</td>
					<td>${frame.today_date ? frame.today_date.split(' ')[0] : "-"}</td>
					<td>${frame.color_code || "-"}</td>
				</tr>
			`;
		}).join("");

		return `
			<div class="table-container">
				<table class="table table-bordered frames-table">
					<thead>
						<tr>
							<th>Frame No</th>
							<th>Item Code</th>
							<th>Item Name</th>
							<th>Warehouse</th>
							<th>Status</th>
							<th>Age (Days)</th>
							<th>Start Date (PR Creation)</th>
							<th>End Date (Today)</th>
							<th>Color</th>
						</tr>
					</thead>
					<tbody>
						${rows}
					</tbody>
				</table>
			</div>
		`;
	}

	build_grid_view(frames) {
		const cards = frames.map((frame) => this.build_frame_card(frame)).join("");
		return `<div class="frames-grid">${cards}</div>`;
	}

	render_pagination(totalPages) {
		if (totalPages <= 1) {
			this.wrapper.find("#pagination-container").empty();
			return;
		}

		const container = this.wrapper.find("#pagination-container");
		let paginationHTML = `<div class="pagination-info">Showing ${((this.currentPage - 1) * this.itemsPerPage) + 1} to ${Math.min(this.currentPage * this.itemsPerPage, this.filteredFrames.length)} of ${this.filteredFrames.length} frames</div>`;
		paginationHTML += `<div class="pagination-buttons">`;

		// Previous button
		if (this.currentPage > 1) {
			paginationHTML += `<button class="btn btn-sm btn-default page-btn" data-page="${this.currentPage - 1}"><i class="fa fa-chevron-left"></i> Previous</button>`;
		}

		// Page numbers
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

		// Next button
		if (this.currentPage < totalPages) {
			paginationHTML += `<button class="btn btn-sm btn-default page-btn" data-page="${this.currentPage + 1}">Next <i class="fa fa-chevron-right"></i></button>`;
		}

		paginationHTML += `</div>`;
		container.html(paginationHTML);

		// Add click handlers
		const self = this;
		container.find(".page-btn").on("click", function() {
			self.currentPage = parseInt($(this).data("page"));
			self.filterAndRender();
			// Scroll to top of frames section
			self.wrapper.find(".frames-section")[0].scrollIntoView({ behavior: "smooth", block: "start" });
		});
	}

	build_frame_card(frame) {
		const ageDays = frame.age_days || 0;
		const ageClass = ageDays <= 30 ? "age-new" : ageDays <= 60 ? "age-recent" : ageDays <= 90 ? "age-moderate" : ageDays <= 180 ? "age-old" : "age-very-old";
		const purchaseDate = frame.purchase_date ? frame.purchase_date.split(' ')[0] : "-";
		const todayDate = frame.today_date ? frame.today_date.split(' ')[0] : "-";
		
		return `
			<div class="frame-card ${ageClass}" data-name="${frame.name || ''}" style="cursor: pointer;">
				<div class="frame-card__header">
					<div>
						<div class="frame-ref">${frame.frame_no || frame.name || "-"}</div>
						<div class="frame-item">${frame.item_code || "-"} ${frame.item_name ? `(${frame.item_name})` : ""}</div>
					</div>
					<div class="age-badge ${ageClass}">${ageDays} days</div>
				</div>
				<div class="frame-card__body">
					<div class="frame-metrics">
						<div><span class="muted">Warehouse</span><div class="metric-value">${frame.warehouse || "-"}</div></div>
						<div><span class="muted">Status</span><div class="metric-value">${frame.status || "Unknown"}</div></div>
						<div><span class="muted">Color</span><div class="metric-value">${frame.color_code || "-"}</div></div>
					</div>
					<div class="frame-aging-info">
						<div class="aging-row">
							<span class="muted">Start Date (PR):</span>
							<span class="aging-value">${purchaseDate}</span>
						</div>
						<div class="aging-row">
							<span class="muted">End Date (Today):</span>
							<span class="aging-value">${todayDate}</span>
						</div>
						<div class="aging-row">
							<span class="muted">Age:</span>
							<span class="aging-value"><strong>${ageDays} days</strong></span>
						</div>
					</div>
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
			method: "rkg.rkg.page.frame_aging_dashboard.frame_aging_dashboard.get_frame_aging_details",
			args: { name: name },
			callback: (r) => {
				if (r.message) {
					this.render_frame_no_details(r.message);
				}
			},
			error: () => {
				frappe.msgprint(__("Unable to load Frame Aging details."));
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
		const ageDays = frame.age_days || 0;
		const ageClass = ageDays <= 30 ? "age-new" : ageDays <= 60 ? "age-recent" : ageDays <= 90 ? "age-moderate" : ageDays <= 180 ? "age-old" : "age-very-old";
		
		container.html(`
			<div class="frame-no-details-card">
				<div class="details-header">
					<h3>${frame.frame_no || frame.name || "-"}</h3>
					<div>
						<span class="age-badge ${ageClass}">${ageDays} days old</span>
						<span class="badge badge-info">${frame.status || "Unknown"}</span>
					</div>
				</div>
				<div class="details-body">
					<div class="aging-highlight">
						<div class="aging-highlight-item">
							<label>Start Date (Purchase Receipt Creation):</label>
							<span class="aging-value-large">${frame.start_date ? frappe.datetime.str_to_user(frame.start_date) : "-"}</span>
						</div>
						<div class="aging-highlight-item">
							<label>End Date (Today):</label>
							<span class="aging-value-large">${frame.end_date ? frappe.datetime.str_to_user(frame.end_date) : "-"}</span>
						</div>
						<div class="aging-highlight-item">
							<label>Frame Age:</label>
							<span class="aging-value-large age-badge ${ageClass}">${ageDays} days</span>
						</div>
					</div>
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
					${frame.battery_serial_no ? `
					<div class="details-row">
						<div class="detail-item">
							<label>Battery Serial No:</label>
							<span><strong>${frame.battery_serial_no_display || frame.battery_serial_no || "-"}</strong></span>
						</div>
						<div class="detail-item">
							<label>Battery Type:</label>
							<span><strong>${frame.battery_type || "-"}</strong></span>
						</div>
					</div>
					` : ""}
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
		.frame-aging-dashboard { padding: 18px; background: var(--bg-color); }
		.filters-section { background: var(--card-bg); padding: 16px; border-radius: 12px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); margin-bottom: 18px; }
		.filters-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; align-items: end; }
		.filter-group label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; }
		.filter-actions { display: flex; gap: 10px; }

		.summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap: 14px; margin-bottom: 18px; }
		.summary-card { background: linear-gradient(135deg, var(--card-bg) 0%, var(--control-bg) 100%); border-radius: 12px; padding: 18px; box-shadow: 0 3px 10px rgba(0,0,0,0.08); border-left: 4px solid var(--primary); }
		.summary-card .card-icon { font-size: 24px; color: var(--primary); margin-bottom: 8px; }
		.summary-card .card-value { font-size: 30px; font-weight: 700; color: var(--heading-color); }
		.summary-card .card-label { font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
		.summary-card.total { border-left-color: #5e64ff; }
		.summary-card.age-0-30 { border-left-color: #00d4aa; }
		.summary-card.age-30-60 { border-left-color: #5e64ff; }
		.summary-card.age-60-90 { border-left-color: #ffa726; }
		.summary-card.age-90-plus { border-left-color: #ff6b6b; }

		.info-banner { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); margin-bottom: 18px; display: flex; gap: 30px; flex-wrap: wrap; }
		.info-banner .info-item { display: flex; flex-direction: column; gap: 4px; }
		.info-banner .info-item label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
		.info-banner .info-item span { font-size: 14px; font-weight: 600; color: var(--heading-color); }

		.charts-section { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 20px; }
		.chart-container { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.chart-title { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }

		.frames-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.section-header { font-weight: 600; color: var(--heading-color); margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
		.frames-count-badge { background: var(--primary); color: white; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; margin-left: 8px; }
		.frames-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
		.search-box { position: relative; width: 250px; }
		.search-box input { padding-right: 30px; }
		.search-box i { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); color: var(--text-muted); pointer-events: none; }
		.view-toggle { display: flex; gap: 4px; }
		.view-btn { padding: 6px 12px; }
		.view-btn.active { background: var(--primary); color: white; }
		.sort-select { height: 32px; font-size: 12px; }
		
		.table-container { overflow-x: auto; margin-top: 12px; }
		.frames-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.frames-table thead { background: var(--bg-light-gray); position: sticky; top: 0; z-index: 10; }
		.frames-table th { padding: 12px 10px; text-align: left; font-weight: 600; color: var(--heading-color); border: 1px solid var(--border-color); white-space: nowrap; }
		.frames-table td { padding: 10px; border: 1px solid var(--border-color); }
		.frames-table tbody tr { background: var(--control-bg); }
		.frames-table tbody tr:hover { background: var(--bg-color); cursor: pointer; }
		.frames-table tbody tr:nth-child(even) { background: var(--card-bg); }
		.frames-table tbody tr:nth-child(even):hover { background: var(--bg-color); }
		
		.frames-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
		.frame-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; background: var(--control-bg); box-shadow: 0 1px 4px rgba(0,0,0,0.04); transition: transform 0.2s, box-shadow 0.2s; }
		.frame-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
		.frame-card__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
		.frame-ref { font-weight: 700; color: var(--heading-color); font-size: 16px; }
		.frame-item { color: var(--text-muted); font-size: 12px; margin-top: 4px; }
		.frame-status { font-size: 12px; font-weight: 600; padding: 6px 10px; border-radius: 14px; background: var(--bg-light-gray); color: var(--heading-color); display: inline-block; }
		.frame-card__body { display: flex; flex-direction: column; gap: 8px; }
		.frame-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
		.metric-value { font-weight: 700; color: var(--heading-color); font-size: 13px; }
		.muted { color: var(--text-muted); font-size: 12px; }
		.frame-aging-info { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border-color); }
		.aging-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
		.aging-value { font-weight: 600; color: var(--heading-color); font-size: 12px; }
		
		.frame-row.age-new { border-left: 3px solid #00d4aa; }
		.frame-row.age-recent { border-left: 3px solid #5e64ff; }
		.frame-row.age-moderate { border-left: 3px solid #ffa726; }
		.frame-row.age-old { border-left: 3px solid #ff6b6b; }
		.frame-row.age-very-old { border-left: 3px solid #c62828; }
		.frame-card.age-new { border-left: 4px solid #00d4aa; }
		.frame-card.age-recent { border-left: 4px solid #5e64ff; }
		.frame-card.age-moderate { border-left: 4px solid #ffa726; }
		.frame-card.age-old { border-left: 4px solid #ff6b6b; }
		.frame-card.age-very-old { border-left: 4px solid #c62828; }
		
		.age-badge { font-size: 12px; font-weight: 600; padding: 6px 10px; border-radius: 14px; display: inline-block; }
		.age-badge.age-new { background: #e0f7f2; color: #0b8c6b; }
		.age-badge.age-recent { background: #e3e7ff; color: #2f49d0; }
		.age-badge.age-moderate { background: #fff3e0; color: #e65100; }
		.age-badge.age-old { background: #ffebee; color: #c62828; }
		.age-badge.age-very-old { background: #ffcdd2; color: #c62828; }
		
		.pagination-container { margin-top: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
		.pagination-info { color: var(--text-muted); font-size: 13px; }
		.pagination-buttons { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
		.page-btn { padding: 6px 12px; min-width: 40px; }
		.page-btn.active { background: var(--primary); color: white; border-color: var(--primary); }
		.pagination-ellipsis { padding: 0 8px; color: var(--text-muted); }

		.no-data { text-align: center; color: var(--text-muted); padding: 30px 10px; }
		.no-data i { font-size: 32px; margin-bottom: 8px; opacity: 0.6; }

		.frame-no-details-section { background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }
		.frame-no-details-card { background: var(--control-bg); border-radius: 10px; padding: 20px; }
		.details-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid var(--border-color); flex-wrap: wrap; gap: 10px; }
		.details-header h3 { margin: 0; color: var(--heading-color); }
		.details-body { margin-top: 20px; }
		.aging-highlight { background: var(--card-bg); border-radius: 8px; padding: 20px; margin-bottom: 20px; border: 2px solid var(--border-color); }
		.aging-highlight-item { display: flex; flex-direction: column; gap: 8px; margin-bottom: 15px; }
		.aging-highlight-item:last-child { margin-bottom: 0; }
		.aging-highlight-item label { font-weight: 600; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
		.aging-value-large { font-weight: 700; color: var(--heading-color); font-size: 18px; }
		.details-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
		.detail-item { display: flex; flex-direction: column; gap: 5px; }
		.detail-item label { font-weight: 600; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
		.detail-item span { color: var(--heading-color); font-size: 14px; }
		.badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
		.badge-info { background: #d1ecf1; color: #0c5460; }
	</style>`).appendTo("head");
}

