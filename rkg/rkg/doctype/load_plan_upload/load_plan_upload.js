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
		console.log("=== LOAD PLAN UPLOAD: before_submit START ===");
		console.log("Document status (docstatus):", frm.doc.docstatus);
		console.log("Confirmation flag (_user_confirmed_submit):", frm._user_confirmed_submit);
		
		// CRITICAL: Check if document is already submitted FIRST - prevent re-submission
		if (frm.doc.docstatus === 1) {
			console.error("Document already submitted. Blocking re-submission.");
			frappe.throw(__("This document has already been submitted and processed. Cannot submit again."));
			return false;
		}
		
		// Check for file attachment
		if (!frm.doc.excel_file) {
			console.error("No Excel file attached. Blocking submission.");
			frappe.throw(__("Please attach an Excel file before submitting"));
			return false;
		}
		
		// If user already confirmed (from file upload confirmation), allow submit to proceed
		if (frm._user_confirmed_submit) {
			console.log("✓ User already confirmed. Allowing submit to proceed.");
			console.log("=== LOAD PLAN UPLOAD: before_submit END (ALLOWING SUBMIT) ===");
			// Clear the flag immediately to prevent accidental reuse
			frm._user_confirmed_submit = false;
			// Explicitly allow validation
			frappe.validated = true;
			return true;  // Allow submit to proceed
		}
		
		// If no confirmation yet, block submission
		console.log("No confirmation yet. Blocking submission.");
		console.log("Please confirm via the dialog shown when file was uploaded.");
		frappe.validated = false;
		return false;
	},
	
	excel_file(frm) {
		console.log("=== NEW FILE ATTACHED ===");
		console.log("File URL:", frm.doc.excel_file);
		
		// Reset results when new file is attached
		if (frm.doc.excel_file) {
			if (frm.doc.docstatus === 0) {
				console.log("Resetting results and flags...");
				frm.set_value("total_load_plans_created", 0);
				// Clear child table
				frm.clear_table("upload_items");
				// Reset ALL confirmation flags
				frm._user_confirmed_submit = false;
				frm._file_validated = false;
				frm._checking_before_submit = false;
				console.log("Reset complete");
				
				// Save document first to go to draft mode
				console.log("Saving document to draft mode...");
				frm.save().then(() => {
					console.log("✓ Document saved to draft");
					console.log("Document status:", frm.doc.docstatus);
					
					// Now check file and show confirmation
					check_file_and_show_confirmation(frm);
				}).catch((err) => {
					console.error("!!! SAVE FAILED !!!");
					console.error("Error details:", err);
				});
			}
		}
	},
	
	after_load(frm) {
		console.log("=== DOCUMENT LOADED ===");
		console.log("Document name:", frm.doc.name);
		console.log("Document status:", frm.doc.docstatus);
		// Clear flags after document load to prevent stale state
		frm._user_confirmed_submit = false;
		frm._checking_before_submit = false;
		console.log("Flags cleared after load");
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
	console.log("=== CHECKING FILE AND SHOWING CONFIRMATION ===");
	console.log("File URL:", frm.doc.excel_file);
	
	if (!frm.doc.excel_file) {
		console.error("No file attached");
		return;
	}
	
	// Prevent multiple concurrent checks
	if (frm._checking_before_submit) {
		console.warn("Already checking file. Skipping duplicate check.");
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
			console.log("Server response received:", r);
			
			if (!r.message) {
				console.error("No message in response. File reading failed.");
				frm._checking_before_submit = false;
				frappe.msgprint({
					title: __("Error"),
					message: __("Error reading file"),
					indicator: "red"
				});
				return;
			}
			
			const check_result = r.message;
			console.log("File check result:", check_result);
			console.log("Load Reference count:", check_result.count);
			console.log("Has multiple:", check_result.has_multiple);
			console.log("Load References:", check_result.unique_load_refs);
			
			// Check if load reference numbers found
			if (check_result.count === 0) {
				console.error("No Load Reference Numbers found in file.");
				frm._checking_before_submit = false;
				frappe.msgprint({
					title: __("Error"),
					message: __("No Load Reference Numbers found in the file. Please check the file format."),
					indicator: "red"
				});
				return;
			}
			
			console.log("Building confirmation dialog...");
			
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
			console.log("*** SHOWING CONFIRMATION DIALOG - NO LOAD PLANS CREATED YET ***");
			console.log("Document is in Draft mode. Waiting for user confirmation to submit...");
			
			frappe.confirm(
				confirmation_html,
				function() {
					// Yes callback - User confirmed, SUBMIT DOCUMENT DIRECTLY
					console.log("=== USER CLICKED YES - SUBMITTING DOCUMENT DIRECTLY ===");
					frm._checking_before_submit = false;
					
					// Set flag to allow submit on the next before_submit call
					frm._user_confirmed_submit = true;
					console.log("Confirmation flag set to TRUE");
					
					// CRITICAL: Now allow validation since user confirmed
					frappe.validated = true;
					console.log("Validation enabled - submission can proceed");
					
					// Show submitting message
					frappe.show_alert({
						message: __("Submitting document..."),
						indicator: "blue"
					}, 3);
					
					console.log("Calling frm.savesubmit() - Document will be submitted NOW");
					console.log(">>> before_submit will be called (will see flag and allow) <<<");
					
					// SUBMIT DOCUMENT DIRECTLY - savesubmit does both save and submit in one call
					// This will call before_submit, which will see the flag and return true
					// Then on_submit will run and create Load Plans
					frm.savesubmit().then(() => {
						console.log("✓ Submit completed successfully");
						console.log(">>> on_submit has run - Load Plans should be created now <<<");
						console.log("Waiting 1 second before reload...");
						
						// After submit completes successfully, reload to show results
						setTimeout(() => {
							console.log("Reloading document to show child table...");
							frm.reload_doc().then(() => {
								console.log("✓ Document reloaded successfully");
								console.log("Child table items count:", frm.doc.upload_items ? frm.doc.upload_items.length : 0);
								console.log("Total Load Plans created:", frm.doc.total_load_plans_created);
								
								// Show success message after reload
								frappe.show_alert({
									message: __("Load Plans processed successfully. See results below."),
									indicator: "green"
								}, 5);
								
								// Ensure child table is visible
								if (frm.doc.upload_items && frm.doc.upload_items.length > 0) {
									console.log("Refreshing child table field...");
									frm.refresh_field("upload_items");
								}
								
								console.log("=== LOAD PLAN UPLOAD: COMPLETE ===");
							});
						}, 1000);
					}).catch((err) => {
						// If submit fails, clear flags and show error
						console.error("!!! SUBMIT FAILED !!!");
						console.error("Error details:", err);
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
					console.log("=== USER CLICKED NO - SUBMISSION CANCELLED ===");
					console.log("*** NO LOAD PLANS WILL BE CREATED ***");
					frm._user_confirmed_submit = false;
					frm._checking_before_submit = false;
					// Keep blocking validation
					frappe.validated = false;
					console.log("Flags cleared. Document remains in Draft status.");
					console.log("Validation remains blocked - document will NOT be submitted");
					frappe.show_alert({
						message: __("Submit cancelled. Document remains in Draft."),
						indicator: "orange"
					}, 3);
					console.log("=== LOAD PLAN UPLOAD: CANCELLED ===");
				}
			);
		},
		error: function(err) {
			console.error("!!! SERVER CALL FAILED !!!");
			console.error("Error details:", err);
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


