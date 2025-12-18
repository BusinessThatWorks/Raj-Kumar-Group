// // Purchase Receipt - Make "Use Serial No / Batch Fields" read-only when created from Load Dispatch
// frappe.ui.form.on("Purchase Receipt", {
// 	refresh(frm) {
// 		// Check if this Purchase Receipt was created from Load Dispatch
// 		if (frm.doc.custom_load_dispatch) {
// 			// Set use_serial_batch_fields to checked on all items if not already set
// 			if (frm.doc.items) {
// 				frm.doc.items.forEach(function(item) {
// 					if (!item.use_serial_batch_fields) {
// 						frappe.model.set_value(item.doctype, item.name, "use_serial_batch_fields", 1);
// 					}
// 				});
// 			}
			
// 			// Make the field read-only on child table
// 			if (frm.fields_dict.items) {
// 				frm.fields_dict.items.grid.update_docfield_property("use_serial_batch_fields", "read_only", 1);
// 			}
// 		}
// 	}
// });

// // Purchase Receipt Item - Prevent unchecking use_serial_batch_fields
// frappe.ui.form.on("Purchase Receipt Item", {
// 	use_serial_batch_fields(frm, cdt, cdn) {
// 		let item = locals[cdt][cdn];
// 		// Check if parent Purchase Receipt was created from Load Dispatch
// 		if (frm.doc.custom_load_dispatch && !item.use_serial_batch_fields) {
// 			frappe.msgprint({
// 				title: __("Cannot Uncheck"),
// 				message: __("'Use Serial No / Batch Fields' must remain checked for Purchase Receipt Items created from Load Dispatch."),
// 				indicator: "orange"
// 			});
// 			frappe.model.set_value(cdt, cdn, "use_serial_batch_fields", 1);
// 		}
// 	}
// });

