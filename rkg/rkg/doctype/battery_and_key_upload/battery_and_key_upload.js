frappe.ui.form.on("Battery and Key Upload", {
	refresh(frm) {
		// Store validation state
		frm._frame_validation_blocked = false;
		// Add Preview File button if file is attached and not submitted
		if (frm.doc.excel_file && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Preview File"), function() {
				preview_file(frm);
			}, __("Actions"));
			
			// If file is attached but child table is empty, trigger file processing
			// Only process if not already processing to avoid duplicate notifications
			if ((!frm.doc.upload_items || frm.doc.upload_items.length === 0) && !frm._processing_file) {
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
		}
	},
	
	before_save(frm) {
		// Prevent save if validation was blocked
		if (frm._frame_validation_blocked) {
			frappe.throw(__("Please resolve frame validation issues before saving."));
		}
	},
	
	before_submit(frm) {
		// Prevent submit if validation was blocked
		if (frm._frame_validation_blocked) {
			frappe.throw(__("Please resolve frame validation issues before submitting."));
		}
		
		// Check if document is already submitted
		if (frm.doc.docstatus === 1) {
			frappe.throw(__("This document has already been submitted and processed. Cannot submit again."));
		}
		
		// Check for file attachment
		if (!frm.doc.excel_file) {
			frappe.throw(__("Please attach an Excel file before submitting"));
		}
	},
	
	on_submit(frm) {
		// After submit completes, reload to show child table
		setTimeout(() => {
			frm.reload_doc().then(() => {
				// Ensure child table is visible (no extra notification - Frappe shows submit success)
				if (frm.doc.upload_items && frm.doc.upload_items.length > 0) {
					frm.refresh_field("upload_items");
				}
			});
		}, 1000);
	},
	
	date(frm) {
		// When date changes, reset validation block
		// User will need to re-select frame_no to re-validate with new date
		frm._frame_validation_blocked = false;
	},
	
	excel_file(frm) {
		// Event listener for when Excel/CSV file is attached - same pattern as Load Dispatch
		if (frm.doc.excel_file) {
			// Prevent duplicate processing
			if (frm._processing_file) {
				return;
			}
			frm._processing_file = true;

			// Call server method to process file and get rows
			frappe.call({
				method: "rkg.rkg.doctype.battery_and_key_upload.battery_and_key_upload.process_excel_file_for_preview",
				args: {
					file_url: frm.doc.excel_file
				},
				freeze: true,
				freeze_message: __("Reading and processing file..."),
				callback: function(r) {
					try {
						frm._processing_file = false;
						
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
								child_row.item_code = row_data.item_code || "";
							});
							
							// Refresh child table to make it visible
							frm.refresh_field("upload_items");
							
							// Save the document to persist child table data
							// Use save with suppress_message flag to reduce notifications
							frm.save().then(function() {
								// Only show success message if save was successful
								// The default "Saved" notification will show, but we'll show a more specific one
								setTimeout(() => {
									frappe.show_alert({
										message: __("Imported {0} rows from file.", [
											child_table_data.length
										]),
										indicator: "green"
									}, 4);
								}, 500);
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
						frm._processing_file = false;
						console.error("Error processing file import:", error);
						frappe.show_alert({
							message: __("Error processing imported data: {0}", [error.message || "Unknown error"]),
							indicator: "red"
						}, 5);
					}
				},
				error: function(err) {
					frm._processing_file = false;
					frappe.show_alert({
						message: __("Error processing file: {0}", [err.message || "Unknown error"]),
						indicator: "red"
					}, 5);
				}
			});
		} else {
			// File cleared - reset values
			frm.clear_table("upload_items");
			frm._processing_file = false;
		}
	},
	
});

// Handle frame_no validation in child table
frappe.ui.form.on("Battery Key Upload Item", {
	frame_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		
		// If frame_no is cleared, reset validation block
		if (!row.frame_no) {
			frm._frame_validation_blocked = false;
			return;
		}
		
		// Reset validation block when new frame is selected
		frm._frame_validation_blocked = false;
		
		// Check if date field is set
		if (!frm.doc.date) {
			frappe.show_alert({
				message: __("Please set the Date field first."),
				indicator: "orange"
			}, 3);
			return;
		}
		
		// No popup confirmation - just allow the frame to be added
		// Email notification will be sent on submit if needed
	}
});

// Function to validate all frames in the child table
function validate_all_frames(frm) {
	// Removed - no validation popups needed
	// Email notification will be handled on server side during submit
}

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
		method: "rkg.rkg.doctype.battery_and_key_upload.battery_and_key_upload.preview_excel_file",
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

