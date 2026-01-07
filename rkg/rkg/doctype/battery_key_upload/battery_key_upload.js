frappe.ui.form.on("Battery Key Upload", {
	refresh(frm) {
		// Show link to Serial No list if upload was successful
		if (frm.doc.total_frames_updated > 0) {
			frm.add_custom_button(__("View Serial Nos"), function() {
				frappe.set_route("List", "Serial No");
			}, __("Actions"));
		}
		
		// Add Preview File button if file is attached and not submitted
		if (frm.doc.excel_file && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Preview File"), function() {
				preview_file(frm);
			}, __("Actions"));
			
			// If file is attached but child table is empty, trigger file processing
			if ((!frm.doc.upload_items || frm.doc.upload_items.length === 0)) {
				// Trigger the excel_file event to process the file
				frm.trigger("excel_file");
			}
		}
		
		// Prevent editing if already submitted
		if (frm.doc.docstatus === 1) {
			frm.set_read_only();
			frm.disable_save();
		}
		
		// Reload child table if document is submitted to ensure it's visible
		if (frm.doc.docstatus === 1) {
			if (frm.doc.upload_items && frm.doc.upload_items.length > 0) {
				frm.refresh_field("upload_items");
			}
			
			// If upload_items is empty but total count > 0, we need to reload
			if (frm.doc.total_frames_updated > 0 && 
			    (!frm.doc.upload_items || frm.doc.upload_items.length === 0)) {
				// Reload to get child table data immediately
				frm.reload_doc().then(() => {
					if (frm.doc.upload_items && frm.doc.upload_items.length > 0) {
						frm.refresh_field("upload_items");
					}
				});
			}
		}
	},
	
	before_submit(frm) {
		// Check if document is already submitted
		if (frm.doc.docstatus === 1) {
			frappe.throw(__("This document has already been submitted and processed. Cannot submit again."));
			return false;
		}
		
		// Check for file attachment
		if (!frm.doc.excel_file) {
			frappe.throw(__("Please attach an Excel file before submitting"));
			return false;
		}
		
		return true;
	},
	
	on_submit(frm) {
		// After submit completes, reload to show child table
		setTimeout(() => {
			frm.reload_doc().then(() => {
				// Show success message
				frappe.show_alert({
					message: __("File processed successfully. {0} frames updated.", [
						frm.doc.total_frames_updated || 0
					]),
					indicator: "green"
				}, 5);
				
				// Ensure child table is visible
				if (frm.doc.upload_items && frm.doc.upload_items.length > 0) {
					frm.refresh_field("upload_items");
				} else if (frm.doc.total_frames_updated > 0) {
					// If counts show data but table is empty, reload again
					setTimeout(() => {
						frm.reload_doc().then(() => {
							if (frm.doc.upload_items && frm.doc.upload_items.length > 0) {
								frm.refresh_field("upload_items");
							}
						});
					}, 500);
				}
			});
		}, 1000);
	},
	
	excel_file(frm) {
		// Event listener for when Excel/CSV file is attached - same pattern as Load Dispatch
		if (frm.doc.excel_file) {
			frappe.show_alert({
				message: __("Processing attached file..."),
				indicator: "blue"
			}, 3);

			// Call server method to process file and get rows
			frappe.call({
				method: "rkg.rkg.doctype.battery_key_upload.battery_key_upload.process_excel_file_for_preview",
				args: {
					file_url: frm.doc.excel_file
				},
				freeze: true,
				freeze_message: __("Reading and processing file..."),
				callback: function(r) {
					try {
						if (r && r.message) {
							const result = r.message;
							
							// Check for errors
							if (result.error) {
								frappe.msgprint({
									title: __("Error"),
									message: result.error,
									indicator: "red"
								});
								return;
							}
							
							const child_table_data = result.child_table_data || [];
							
							if (child_table_data.length === 0) {
								frappe.msgprint({
									title: __("No Data"),
									message: __("No valid data found in the file."),
									indicator: "orange"
								});
								return;
							}
							
							// Clear existing items
							frm.clear_table("upload_items");
							
							// Populate child table - same pattern as Load Dispatch
							child_table_data.forEach(function(row_data) {
								const child_row = frm.add_child("upload_items");
								child_row.frame_no = row_data.frame_no || "";
								child_row.key_no = row_data.key_no || "";
								child_row.battery_serial_no = row_data.battery_serial_no || "";
								child_row.battery_brand = row_data.battery_brand || "";
								child_row.battery_type = row_data.battery_type || "";
								child_row.sample_charging_date = row_data.sample_charging_date || "";
								child_row.charging_date = row_data.charging_date || null;
								child_row.status = row_data.status || "Pending";
								child_row.item_code = row_data.item_code || "";
								child_row.error_message = row_data.error_message || "";
							});
							
							// Refresh child table to make it visible
							frm.refresh_field("upload_items");
							
							// Update summary fields
							frm.set_value("total_frames_updated", result.total_updated || 0);
							
							// Save the document to persist child table data
							frm.save().then(function() {
								// Show success message after save
								frappe.show_alert({
									message: __("Successfully imported {0} rows from file. {1} ready.", [
										child_table_data.length,
										result.total_updated || 0
									]),
									indicator: "green"
								}, 8);
							}).catch(function(err) {
								console.error("Error saving document:", err);
								frappe.show_alert({
									message: __("Data imported but save failed. Please save manually."),
									indicator: "orange"
								}, 5);
							});
						} else {
							frappe.show_alert({
								message: __("Unexpected response format from server"),
								indicator: "orange"
							}, 5);
						}
					} catch (error) {
						console.error("Error processing file import:", error);
						frappe.show_alert({
							message: __("Error processing imported data: {0}", [error.message || "Unknown error"]),
							indicator: "red"
						}, 5);
					}
				},
				error: function(err) {
					frappe.show_alert({
						message: __("Error processing file: {0}", [err.message || "Unknown error"]),
						indicator: "red"
					}, 5);
				}
			});
		} else {
			// File cleared - reset values
			frm.set_value("total_frames_updated", 0);
			frm.clear_table("upload_items");
		}
	},
	
});

// Function to preview file and show what will be processed
function preview_file(frm) {
	if (!frm.doc.excel_file) {
		frappe.msgprint({
			title: __("Error"),
			message: __("Please attach an Excel file first"),
			indicator: "red"
		});
		return;
	}
	
	frappe.call({
		method: "rkg.rkg.doctype.battery_key_upload.battery_key_upload.preview_excel_file",
		args: {
			file_url: frm.doc.excel_file
		},
		freeze: true,
		freeze_message: __("Reading file..."),
		callback: function(r) {
			if (r.message && r.message.error) {
				frappe.msgprint({
					title: __("Error"),
					message: r.message.error,
					indicator: "red"
				});
				return;
			}
			
			const result = r.message || {};
			show_preview_summary(result);
		},
		error: function(err) {
			frappe.msgprint({
				title: __("Error"),
				message: __("Error reading file: {0}", [err.message || "Unknown error"]),
				indicator: "red"
			});
		}
	});
}

// Function to show preview summary
function show_preview_summary(result) {
	const preview_html = `
		<div style="max-height: 400px; overflow-y: auto;">
			<p><b>File Preview Summary</b></p>
			<table class="table table-bordered" style="width: 100%; margin-top: 10px; font-size: 12px;">
				<thead>
					<tr>
						<th>Total Rows</th>
						<th>Valid Frames</th>
						<th>Frames Not Found</th>
						<th>Frames Not Linked</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<td>${result.total_rows || 0}</td>
						<td>${result.valid_frames || 0}</td>
						<td>${result.frames_not_found || 0}</td>
						<td>${result.frames_not_linked || 0}</td>
					</tr>
				</tbody>
			</table>
			${result.sample_rows ? `
				<p style="margin-top: 15px;"><b>Sample Rows (first 5):</b></p>
				<table class="table table-bordered" style="width: 100%; font-size: 11px;">
					<thead>
						<tr>
							<th>Frame No</th>
							<th>Key No</th>
							<th>Battery Serial No</th>
							<th>Battery Brand</th>
							<th>Battery Type</th>
							<th>Status</th>
						</tr>
					</thead>
					<tbody>
						${result.sample_rows.map(row => `
							<tr>
								<td>${row.frame_no || "-"}</td>
								<td>${row.key_no || "-"}</td>
								<td>${row.battery_serial_no || "-"}</td>
								<td>${row.battery_brand || "-"}</td>
								<td>${row.battery_type || "-"}</td>
								<td><span class="badge ${row.status === 'Valid' ? 'badge-success' : 'badge-danger'}">${row.status || "-"}</span></td>
							</tr>
						`).join('')}
					</tbody>
				</table>
			` : ''}
			<p style="margin-top: 15px; color: #666; font-size: 11px;">
				<i>Note: This is a preview. Click Submit to process the file and update Serial No records.</i>
			</p>
		</div>
	`;
	
	frappe.msgprint({
		title: __("File Preview"),
		message: preview_html,
		indicator: "blue"
	});
}

