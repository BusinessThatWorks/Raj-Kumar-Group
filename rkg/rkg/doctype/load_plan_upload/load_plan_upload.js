frappe.ui.form.on("Load Plan Upload", {
	refresh(frm) {
		// Show link to created Load Plans if upload was successful
		if (frm.doc.total_load_plans_created > 0) {
			frm.add_custom_button(__("View Load Plans"), function() {
				frappe.set_route("List", "Load Plan");
			}, __("Actions"));
		}
		
		// Add Validate File button if file is attached and not submitted
		if (frm.doc.excel_file && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Validate File"), function() {
				validate_file_and_show_summary(frm);
			}, __("Actions"));
		}
		
		// Prevent editing if already submitted
		if (frm.doc.docstatus === 1) {
			frm.set_read_only();
			frm.disable_save();
		}
		
		// Reset confirmation flag on refresh
		frm._user_confirmed_submit = false;
		frm._checking_before_submit = false;
		
		// Ensure validation is enabled on refresh (unless we're actively blocking)
		if (!frm._checking_before_submit) {
			frappe.validated = true;
		}
		
		// Reload child table if document is submitted to ensure it's visible
		if (frm.doc.docstatus === 1) {
			// Always refresh child table if document is submitted
			if (frm.doc.upload_items && frm.doc.upload_items.length > 0) {
				frm.refresh_field("upload_items");
			}
			
			// If upload_items is empty but total count > 0, we need to reload
			if (frm.doc.total_load_plans_created > 0 && (!frm.doc.upload_items || frm.doc.upload_items.length === 0)) {
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
		// CRITICAL: Check if document is already submitted FIRST - prevent re-submission
		if (frm.doc.docstatus === 1) {
			frappe.throw(__("This document has already been submitted and processed. Cannot submit again."));
			return false;
		}
		
		// Check for file attachment
		if (!frm.doc.excel_file) {
			frappe.throw(__("Please attach an Excel file before submitting"));
			return false;
		}
		
		// If user already confirmed (from file upload confirmation), allow submit to proceed
		if (frm._user_confirmed_submit) {
			// Clear the flag immediately to prevent accidental reuse
			frm._user_confirmed_submit = false;
			// Explicitly allow validation
			frappe.validated = true;
			return true;  // Allow submit to proceed
		}
		
		// If no confirmation yet, block submission
		frappe.validated = false;
		return false;
	},
	
	excel_file(frm) {
		// Reset results when new file is attached
		if (frm.doc.excel_file) {
			if (frm.doc.docstatus === 0) {
				frm.set_value("total_load_plans_created", 0);
				// Clear child table
				frm.clear_table("upload_items");
				// Reset ALL confirmation flags
				frm._user_confirmed_submit = false;
				frm._file_validated = false;
				frm._checking_before_submit = false;
				
				// Save document first to go to draft mode
				frm.save().then(() => {
					// Now check file and show confirmation
					check_file_and_show_confirmation(frm);
				}).catch((err) => {
					// Save failed - error will be shown by Frappe
				});
			}
		}
	},
	
	after_load(frm) {
		// Clear flags after document load to prevent stale state
		frm._user_confirmed_submit = false;
		frm._checking_before_submit = false;
	}
});

// Function to validate file and show summary
function validate_file_and_show_summary(frm) {
	if (!frm.doc.excel_file) {
		frappe.msgprint({
			title: __("Error"),
			message: __("Please attach an Excel file first"),
			indicator: "red"
		});
		return;
	}
	
	frappe.call({
		method: "rkg.rkg.doctype.load_plan_upload.load_plan_upload.check_multiple_load_reference_numbers",
		args: {
			file_url: frm.doc.excel_file
		},
		freeze: true,
		freeze_message: __("Reading file..."),
		callback: function(r) {
			if (!r.message) {
				frappe.msgprint({
					title: __("Error"),
					message: __("Error reading file"),
					indicator: "red"
				});
				return;
			}
			
			const result = r.message;
			frm._file_validated = true;
			frm._validation_result = result;
			
			// Show summary dialog
			show_file_validation_summary(result);
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

// Function to check file and show confirmation dialog (called after file upload)
function check_file_and_show_confirmation(frm) {
	if (!frm.doc.excel_file) {
		return;
	}
	
	// Prevent multiple concurrent checks
	if (frm._checking_before_submit) {
		return;
	}
	
	frm._checking_before_submit = true;
	
	frappe.call({
		method: "rkg.rkg.doctype.load_plan_upload.load_plan_upload.check_multiple_load_reference_numbers",
		args: {
			file_url: frm.doc.excel_file
		},
		freeze: true,
		freeze_message: __("Reading file..."),
		callback: function(r) {
			if (!r.message) {
				frm._checking_before_submit = false;
				frappe.msgprint({
					title: __("Error"),
					message: __("Error reading file"),
					indicator: "red"
				});
				return;
			}
			
			const check_result = r.message;
			
			// Check if load reference numbers found
			if (check_result.count === 0) {
				frm._checking_before_submit = false;
				frappe.msgprint({
					title: __("Error"),
					message: __("No Load Reference Numbers found in the file. Please check the file format."),
					indicator: "red"
				});
				return;
			}
			
			// Build detailed confirmation message with row counts
			const details = check_result.load_ref_details || [];
			let confirmation_html = `<div style="max-height: 300px; overflow-y: auto;">`;
			
			if (check_result.has_multiple) {
				confirmation_html += `<p><b>Found ${check_result.count} Load Reference Number(s) in the file:</b></p>`;
			} else {
				confirmation_html += `<p><b>Found 1 Load Reference Number in the file:</b></p>`;
			}
			
			confirmation_html += `<table class="table table-bordered" style="width: 100%; margin-top: 10px; font-size: 12px;">`;
			confirmation_html += `<thead><tr><th>Load Reference No</th><th>Rows</th><th>Total Quantity</th></tr></thead>`;
			confirmation_html += `<tbody>`;
			
			details.forEach(function(detail) {
				confirmation_html += `<tr>`;
				confirmation_html += `<td><b>${detail.load_reference_no || ""}</b></td>`;
				confirmation_html += `<td>${detail.rows_count || 0}</td>`;
				confirmation_html += `<td>${detail.total_quantity || 0}</td>`;
				confirmation_html += `</tr>`;
			});
			
			confirmation_html += `</tbody></table>`;
			confirmation_html += `<p style="margin-top: 10px; color: #666; font-size: 11px;">`;
			confirmation_html += `<i>Note: Load Plans that already exist will be skipped automatically.</i>`;
			confirmation_html += `</p>`;
			confirmation_html += `</div>`;
			
			// Show confirmation dialog - this happens BEFORE any Load Plans are created
			frappe.confirm(
				confirmation_html,
				function() {
					// Yes callback - User confirmed, SUBMIT DOCUMENT DIRECTLY
					frm._checking_before_submit = false;
					
					// Set flag to allow submit on the next before_submit call
					frm._user_confirmed_submit = true;
					
					// CRITICAL: Now allow validation since user confirmed
					frappe.validated = true;
					
					// Show submitting message
					frappe.show_alert({
						message: __("Submitting document..."),
						indicator: "blue"
					}, 3);
					
					// SUBMIT DOCUMENT DIRECTLY - savesubmit does both save and submit in one call
					// This will call before_submit, which will see the flag and return true
					// Then on_submit will run and create Load Plans
					frm.savesubmit().then(() => {
						// After submit completes successfully, reload to show results
						setTimeout(() => {
							frm.reload_doc().then(() => {
								// Show success message after reload
								frappe.show_alert({
									message: __("Load Plans processed successfully. See results below."),
									indicator: "green"
								}, 5);
								
								// Ensure child table is visible
								if (frm.doc.upload_items && frm.doc.upload_items.length > 0) {
									frm.refresh_field("upload_items");
								}
							});
						}, 1000);
					}).catch((err) => {
						// If submit fails, clear flags and show error
						frm._user_confirmed_submit = false;
						frm._checking_before_submit = false;
						frappe.validated = false;
						frappe.msgprint({
							title: __("Error"),
							message: __("Failed to process Load Plans: {0}", [err.message || "Unknown error"]),
							indicator: "red"
						});
					});
				},
				function() {
					// No callback - User cancelled
					frm._user_confirmed_submit = false;
					frm._checking_before_submit = false;
					// Keep blocking validation
					frappe.validated = false;
					frappe.show_alert({
						message: __("Submit cancelled. Document remains in Draft."),
						indicator: "orange"
					}, 3);
				}
			);
		},
		error: function(err) {
			frm._checking_before_submit = false;
			frappe.msgprint({
				title: __("Error"),
				message: __("Error reading file: {0}", [err.message || "Unknown error"]),
				indicator: "red"
			});
		}
	});
}

// Function to show file validation summary
function show_file_validation_summary(result) {
	const details = result.load_ref_details || [];
	let summary_html = `<div style="max-height: 400px; overflow-y: auto;">`;
	
	if (result.has_multiple) {
		summary_html += `<p><b>Found ${result.count} Load Reference Number(s) in the file:</b></p>`;
	} else {
		summary_html += `<p><b>Found 1 Load Reference Number in the file:</b></p>`;
	}
	
	summary_html += `<table class="table table-bordered" style="width: 100%; margin-top: 10px;">`;
	summary_html += `<thead><tr><th>Load Reference No</th><th>Rows</th><th>Total Quantity</th></tr></thead>`;
	summary_html += `<tbody>`;
	
	details.forEach(function(detail) {
		summary_html += `<tr>`;
		summary_html += `<td>${detail.load_reference_no || ""}</td>`;
		summary_html += `<td>${detail.rows_count || 0}</td>`;
		summary_html += `<td>${detail.total_quantity || 0}</td>`;
		summary_html += `</tr>`;
	});
	
	summary_html += `</tbody></table>`;
	summary_html += `<p style="margin-top: 10px; color: #666; font-size: 12px;">`;
	summary_html += `<i>Note: Load Plans that already exist will be skipped automatically during processing.</i>`;
	summary_html += `</p>`;
	summary_html += `</div>`;
	
	frappe.msgprint({
		title: __("File Validation Summary"),
		message: summary_html,
		indicator: "blue"
	});
}


