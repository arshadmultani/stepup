// Copyright (c) 2026, Exponit Labs and contributors
// For license information, please see license.txt

frappe.ui.form.on("Telegram Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Send Test Message"), () => {
			frm.events.trigger_test_message(frm);
		});
	},

	send_test_btn(frm) {
		frm.events.trigger_test_message(frm);
	},

	trigger_test_message(frm) {
		let token = frm.doc.bot_token || "";
		if (/^\*+$/.test(token.trim())) {
			token = "";
		}
		let cid = frm.doc.chat_id || "";

		if (!cid) {
			frappe.msgprint({
				title: __("Missing Chat ID"),
				indicator: "orange",
				message: __("Please enter a Chat ID or Channel ID before testing.")
			});
			return;
		}

		let thread_id = frm.doc.message_thread_id || "";

		frappe.call({
			method: "stepup.stepup.doctype.telegram_settings.telegram_settings.send_test_message",
			args: {
				bot_token: token,
				chat_id: cid,
				message_thread_id: thread_id
			},
			freeze: true,
			freeze_message: __("Sending test message to Telegram..."),
			callback(r) {
				if (!r.exc && r.message && r.message.success) {
					frappe.msgprint({
						title: __("Delivered"),
						indicator: "green",
						message: __("Test message sent successfully to Telegram! Check your Telegram chat/channel.")
					});
				}
			}
		});
	}
});
