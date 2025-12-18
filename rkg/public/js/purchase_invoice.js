// // Purchase Invoice - Make "Use Serial No / Batch Fields" read-only when created from Load Dispatch or Purchase Receipt
// frappe.ui.form.on("Purchase Invoice", {
// 	refresh(frm) {
// 		// Check if this Purchase Invoice was created from Load Dispatch or Purchase Receipt
// 		const isFromLoadDispatch = frm.doc.custom_load_dispatch;
// 		const isFromPurchaseReceipt = frm.doc.purchase_receipt;
		
// 		if (isFromLoadDispatch || isFromPurchaseReceipt) {
// 			// Set use_serial_batch_fields to checked on all items if not already set
// 			if (frm.doc.items) {
// 				frm.doc.items.forEach(function(item) {
// 					if (!item.use_serial_batch_fields) {
// 						frappe.model.set_value(item.doctype, item.name, "use_serial_batch_fields", 1);
// 					}
// 				});
// 			}
			
// 			// Make the field read-only on child table if from Load Dispatch
// 			if (isFromLoadDispatch && frm.fields_dict.items) {
// 				frm.fields_dict.items.grid.update_docfield_property("use_serial_batch_fields", "read_only", 1);
// 			}
// 		}
// 	}
// });

// // Purchase Invoice Item - Prevent unchecking use_serial_batch_fields
// frappe.ui.form.on("Purchase Invoice Item", {
// 	use_serial_batch_fields(frm, cdt, cdn) {
// 		let item = locals[cdt][cdn];
// 		// Check if parent Purchase Invoice was created from Load Dispatch
// 		if (frm.doc.custom_load_dispatch && !item.use_serial_batch_fields) {
// 			frappe.msgprint({
// 				title: __("Cannot Uncheck"),
// 				message: __("'Use Serial No / Batch Fields' must remain checked for Purchase Invoice Items created from Load Dispatch."),
// 				indicator: "orange"
// 			});
// 			frappe.model.set_value(cdt, cdn, "use_serial_batch_fields", 1);
// 		}
// 	}
// });

