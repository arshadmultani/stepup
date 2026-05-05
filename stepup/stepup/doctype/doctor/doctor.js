// Copyright (c) 2026, Exponit Labs and contributors
// For license information, please see license.txt

frappe.ui.form.on("Doctor", {
	refresh(frm) {
		frm.add_custom_button("View RCPA Visit", () => {
			frappe.set_route("List", "RCPA Visit", {
				doctor: frm.doc.name,
			});
		});
	},
});
