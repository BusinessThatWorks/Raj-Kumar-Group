// RKG App - Global JavaScript
// Global handler for CSRF token errors

$(document).ready(function() {
	// Handle CSRF token errors globally
	$(document).ajaxError(function(event, jqxhr, settings, thrownError) {
		if (jqxhr.responseText && jqxhr.responseText.includes("CSRFTokenError")) {
			frappe.msgprint({
				title: __('Session Refresh Required'),
				message: __('Your session token has expired. Click the button below to refresh and continue.'),
				indicator: 'orange',
				primary_action: {
					label: __('Refresh Page'),
					action: function() {
						location.reload();
					}
				}
			});
		}
	});
});

