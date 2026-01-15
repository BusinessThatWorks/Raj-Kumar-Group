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
		this.allFrames = [];
		this.filteredFrames = [];
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
					<div class="summary-card warehouses">
						<div class="card-icon"><i class="fa fa-warehouse"></i></div>
						<div class="card-value" id="total-warehouses">0</div>
						<div class="card-label">Warehouses</div>
					</div>
				</div>

				<div class="charts-section">
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
						<div style="flex: 1;">
							<span><i class="fa fa-list"></i> Frames</span>
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
							<select class="form-control sort-select" style="width: 150px;">
								<option value="creation-desc">Newest First</option>
								<option value="creation-asc">Oldest First</option>
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
					this.render_warehouse_chart(r.message.warehouse_chart || {});
					this.render_item_chart(r.message.item_chart || {});
					this.render_date_chart(r.message.date_chart || {});
					this.render_frames_list(r.message.frames || []);
				} else {
					this.render_summary({});
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
		const total_warehouses = Object.keys(warehouse_counts).length;

		this.wrapper.find("#total-frames").text(format_number(total, 0));
		this.wrapper.find("#active-frames").text(format_number(active, 0));
		this.wrapper.find("#total-warehouses").text(format_number(total_warehouses, 0));
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
				frame.battery_serial_no || "",
				frame.battery_type || "",
				frame.battery_aging_days?.toString() || ""
			].join(" ").toLowerCase();
			return searchable.includes(searchTerm);
		});

		// Sort frames
		this.filteredFrames.sort((a, b) => {
			let aVal = a[this.sortField] || "";
			let bVal = b[this.sortField] || "";
			
			// Handle dates
			if (this.sortField === "creation") {
				aVal = new Date(a.creation || 0);
				bVal = new Date(b.creation || 0);
			}
			
			// Convert to strings for comparison
			aVal = String(aVal).toLowerCase();
			bVal = String(bVal).toLowerCase();
			
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
			const statusClass = (frame.status || "Unknown").toLowerCase().replace(/\s+/g, "-");
			const batteryAgeDays = frame.battery_aging_days !== null && frame.battery_aging_days !== undefined ? frame.battery_aging_days : null;
			const ageClass = batteryAgeDays !== null ? 
				(batteryAgeDays <= 60 ? "age-new" : batteryAgeDays <= 90 ? "age-warning" : batteryAgeDays <= 120 ? "age-medium" : "age-old") : "";
			const batteryBadge = frame.has_battery ? 
				(frame.is_discarded ? '<span class="badge badge-danger">Discarded</span>' : 
				 `<span class="age-badge ${ageClass}">${batteryAgeDays !== null ? batteryAgeDays + ' days' : 'N/A'}</span>`) : 
				'<span class="badge badge-secondary">No Battery</span>';
			
			return `
				<tr class="frame-row" data-name="${frame.name}" style="cursor: pointer;">
					<td><strong>${frame.frame_no || frame.name || "-"}</strong></td>
					<td>${frame.item_code || "-"}</td>
					<td>${frame.item_name || "-"}</td>
					<td>${frame.warehouse || "-"}</td>
					<td><span class="frame-status ${statusClass}">${frame.status || "Unknown"}</span></td>
					<td>${frame.battery_serial_no || "-"}</td>
					<td>${frame.battery_type || "-"}</td>
					<td>${batteryBadge}</td>
					<td>${frame.swap_count || 0}</td>
					<td>${frame.color_code || "-"}</td>
					<td>${frame.purchase_date ? frame.purchase_date.split(' ')[0] : "-"}</td>
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
							<th>Battery Serial No</th>
							<th>Battery Type</th>
							<th>Battery Age</th>
							<th>Swaps</th>
							<th>Color</th>
							<th>Purchase Date</th>
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
		const statusClass = (frame.status || "Unknown").toLowerCase().replace(/\s+/g, "-");
		const batteryAgeDays = frame.battery_aging_days !== null && frame.battery_aging_days !== undefined ? frame.battery_aging_days : null;
		const ageClass = batteryAgeDays !== null ? 
			(batteryAgeDays <= 60 ? "age-new" : batteryAgeDays <= 90 ? "age-warning" : batteryAgeDays <= 120 ? "age-medium" : "age-old") : "";
		const batteryInfo = frame.has_battery ? 
			(frame.is_discarded ? '<div class="frame-battery"><span class="badge badge-danger">Battery Discarded</span></div>' : 
			 `<div class="frame-battery">
				<div><span class="muted">Battery:</span> <strong>${frame.battery_serial_no || "-"}</strong></div>
				<div><span class="muted">Type:</span> ${frame.battery_type || "-"}</div>
				<div><span class="age-badge ${ageClass}">${batteryAgeDays !== null ? batteryAgeDays + ' days' : 'N/A'}</span></div>
				${frame.swap_count > 0 ? `<div><span class="muted">Swaps:</span> ${frame.swap_count}</div>` : ""}
			</div>`) : 
			'<div class="frame-battery"><span class="badge badge-secondary">No Battery</span></div>';
		
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
					${batteryInfo}
					${frame.purchase_date ? `<div class="frame-date"><i class="fa fa-calendar"></i> Purchase Date: ${frame.purchase_date.split(' ')[0]}</div>` : ""}
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
		const batteryAgeDays = frame.battery_aging_days !== null && frame.battery_aging_days !== undefined ? frame.battery_aging_days : null;
		const ageClass = batteryAgeDays !== null ? 
			(batteryAgeDays <= 60 ? "age-new" : batteryAgeDays <= 90 ? "age-warning" : batteryAgeDays <= 120 ? "age-medium" : "age-old") : "";
		
		// Build swap history HTML
		let swapHistoryHTML = "";
		if (frame.swap_history && frame.swap_history.length > 0) {
			swapHistoryHTML = `
				<div class="details-section">
					<h4><i class="fa fa-exchange"></i> Battery Swap History (${frame.swap_count || 0})</h4>
					<div class="table-container">
						<table class="table table-bordered">
							<thead>
								<tr>
									<th>Swap Date</th>
									<th>Swapped With Frame</th>
									<th>Old Battery</th>
									<th>New Battery</th>
									<th>Swapped By</th>
								</tr>
							</thead>
							<tbody>
								${frame.swap_history.map(swap => `
									<tr>
										<td>${swap.swap_date ? frappe.datetime.str_to_user(swap.swap_date) : "-"}</td>
										<td>${swap.swapped_with_frame || "-"}</td>
										<td>${swap.old_battery_serial_no || "-"}</td>
										<td>${swap.new_battery_serial_no || "-"}</td>
										<td>${swap.swapped_by || "-"}</td>
									</tr>
								`).join("")}
							</tbody>
						</table>
					</div>
				</div>
			`;
		}
		
		// Build action buttons
		let actionButtons = "";
		if (frame.frame_bundle_name && frame.has_battery && !frame.is_discarded) {
			actionButtons = `
				<div class="details-actions">
					<button class="btn btn-primary btn-swap-battery" data-frame="${frame.frame_bundle_name}" data-battery="${frame.battery_serial_no}">
						<i class="fa fa-exchange"></i> Swap Battery
					</button>
					<button class="btn btn-default btn-view-frame-bundle" data-frame="${frame.frame_bundle_name}">
						<i class="fa fa-eye"></i> View Frame Bundle
					</button>
				</div>
			`;
		}

		container.html(`
			<div class="frame-no-details-card">
				<div class="details-header">
					<h3>${frame.frame_no || frame.name || "-"}</h3>
					<div>
						<span class="badge badge-info">${frame.status || "Unknown"}</span>
						${batteryAgeDays !== null ? `<span class="age-badge ${ageClass}">${batteryAgeDays} days</span>` : ""}
					</div>
				</div>
				${actionButtons}
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
					<div class="details-row">
						<div class="detail-item">
							<label>Battery Installed On:</label>
							<span>${frame.battery_installed_on ? frappe.datetime.str_to_user(frame.battery_installed_on) : "-"}</span>
						</div>
						<div class="detail-item">
							<label>Battery Aging Days:</label>
							<span><strong>${batteryAgeDays !== null ? batteryAgeDays : "-"}</strong></span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Battery Status:</label>
							<span>${frame.is_discarded ? '<span class="badge badge-danger">Discarded</span>' : '<span class="badge badge-success">Active</span>'}</span>
						</div>
						<div class="detail-item">
							<label>Swap Count:</label>
							<span><strong>${frame.swap_count || 0}</strong></span>
						</div>
					</div>
					` : ""}
					<div class="details-row">
						<div class="detail-item">
							<label>Purchase Date:</label>
							<span>${frame.purchase_date ? frame.purchase_date.split(' ')[0] : "-"}</span>
						</div>
						<div class="detail-item">
							<label>Color Code:</label>
							<span>${frame.color_code || "-"}</span>
						</div>
					</div>
					<div class="details-row">
						<div class="detail-item">
							<label>Engine Number:</label>
							<span>${frame.custom_engine_number || "-"}</span>
						</div>
						<div class="detail-item">
							<label>Key No:</label>
							<span>${frame.custom_key_no || "-"}</span>
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
				${swapHistoryHTML}
			</div>
		`);
		
		// Setup action button handlers
		const self = this;
		container.find(".btn-swap-battery").on("click", function() {
			const frameName = $(this).data("frame");
			const batteryName = $(this).data("battery");
			// Navigate to Frame Bundle and trigger swap
			frappe.set_route("Form", "Frame Bundle", frameName);
		});
		
		container.find(".btn-view-frame-bundle").on("click", function() {
			const frameName = $(this).data("frame");
			frappe.set_route("Form", "Frame Bundle", frameName);
		});
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
		.summary-card.warehouses { border-left-color: #26c6da; }

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
		.frame-status.active { background: #e0f7f2; color: #0b8c6b; }
		.frame-status.delivered { background: #e3e7ff; color: #2f49d0; }
		.frame-status.in-stock { background: #e0f7f2; color: #0b8c6b; }
		.frame-card__body { display: flex; flex-direction: column; gap: 8px; }
		.frame-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
		.metric-value { font-weight: 700; color: var(--heading-color); font-size: 13px; }
		.muted { color: var(--text-muted); font-size: 12px; }
		.frame-date { color: var(--text-muted); font-size: 11px; display: flex; align-items: center; gap: 4px; }
		
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
		.details-actions { margin-bottom: 20px; display: flex; gap: 10px; flex-wrap: wrap; }
		.details-body { margin-top: 20px; }
		.details-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
		.detail-item { display: flex; flex-direction: column; gap: 5px; }
		.detail-item label { font-weight: 600; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
		.detail-item span { color: var(--heading-color); font-size: 14px; }
		.details-section { margin-top: 30px; padding-top: 20px; border-top: 2px solid var(--border-color); }
		.details-section h4 { margin-bottom: 15px; color: var(--heading-color); display: flex; align-items: center; gap: 8px; }
		.frame-battery { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-color); }
		.age-badge { font-size: 12px; font-weight: 600; padding: 6px 10px; border-radius: 14px; display: inline-block; }
		.age-badge.age-new { background: #e0f7f2; color: #0b8c6b; }
		.age-badge.age-warning { background: #fff3e0; color: #e65100; }
		.age-badge.age-medium { background: #ffe0b2; color: #e65100; }
		.age-badge.age-old { background: #ffcdd2; color: #c62828; }
		.badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
		.badge-success { background: #d4edda; color: #155724; }
		.badge-danger { background: #f8d7da; color: #721c24; }
		.badge-secondary { background: #e2e3e5; color: #383d41; }
		.badge-info { background: #d1ecf1; color: #0c5460; }
	</style>`).appendTo("head");
}

