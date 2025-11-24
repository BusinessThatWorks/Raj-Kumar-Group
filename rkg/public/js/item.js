frappe.ui.form.on('Item', {
	refresh: function(frm) {
		// Set up event listeners for Model Variant and Model Serial Number
		setup_item_name_auto_populate(frm);
		
		// If "Has Serial Number" is checked and Item is saved, fetch serial numbers
		if (frm.doc.has_serial_no && frm.doc.name && !frm.is_new()) {
			fetch_serial_numbers_for_item(frm);
		}
	},

	has_serial_no: function(frm) {
		// When "Has Serial Number" is checked, fetch and populate Frame Numbers
		if (frm.doc.has_serial_no && frm.doc.name) {
			fetch_serial_numbers_for_item(frm);
		} else if (!frm.doc.has_serial_no) {
			// Clear Frame Numbers if unchecked
			frm.set_value('custom_frame_numbers', '');
		}
	},

	custom_model_variant: function(frm) {
		update_item_name(frm);
	},

	custom_model_serial_number: function(frm) {
		update_item_name(frm);
	}
});

function setup_item_name_auto_populate(frm) {
	// Ensure event listeners are set up
	if (frm.fields_dict.custom_model_variant) {
		frm.fields_dict.custom_model_variant.$input.on('input', function() {
			update_item_name(frm);
		});
	}
	
	if (frm.fields_dict.custom_model_serial_number) {
		frm.fields_dict.custom_model_serial_number.$input.on('input', function() {
			update_item_name(frm);
		});
	}
}

function update_item_name(frm) {
	let model_variant = (frm.doc.custom_model_variant || '').trim();
	let model_serial_number = (frm.doc.custom_model_serial_number || '').trim();
	
	// Only update if both Model Variant and Model Serial Number have values
	if (!model_variant || !model_serial_number) {
		return;
	}
	
	// Extract serial number up to "ID" (case-insensitive)
	let serial_part = '';
	// Find "ID" in the serial number (case-insensitive)
	const id_index = model_serial_number.toUpperCase().indexOf('ID');
	if (id_index !== -1) {
		// Take everything up to and including "ID"
		serial_part = model_serial_number.substring(0, id_index + 2);
	} else {
		// If "ID" not found, use the entire serial number
		serial_part = model_serial_number;
	}
	
	// Combine Model Variant + ( Serial Number (up to ID) )
	let item_name = model_variant + '( ' + serial_part + ' )';
	
	// Update the item_name field if it's different
	if (frm.doc.item_name !== item_name) {
		frm.set_value('item_name', item_name);
	}
}

function fetch_serial_numbers_for_item(frm) {
	// Fetch all Serial Numbers for this Item
	frappe.call({
		method: 'frappe.client.get_list',
		args: {
			doctype: 'Serial No',
			filters: {
				item_code: frm.doc.name
			},
			fields: ['name'],
			order_by: 'name asc'
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				// Get all serial number names
				let serial_numbers = r.message.map(function(serial) {
					return serial.name;
				});
				
				// Condition: If more than one serial number exists, join with comma
				let frame_numbers = '';
				if (serial_numbers.length === 1) {
					// Single serial number - use it directly
					frame_numbers = serial_numbers[0];
				} else if (serial_numbers.length > 1) {
					// Multiple serial numbers - join with comma and space
					frame_numbers = serial_numbers.join(', ');
				}
				
				// Update the Frame Numbers field
				frm.set_value('custom_frame_numbers', frame_numbers);
			} else {
				// No serial numbers found
				frm.set_value('custom_frame_numbers', '');
			}
		}
	});
}

