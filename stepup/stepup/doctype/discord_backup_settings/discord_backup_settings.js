// Copyright (c) 2026, Exponit Labs and contributors
// For license information, please see license.txt

frappe.ui.form.on("Discord Backup Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Webhook"), () => {
			frm.events.test_webhook(frm);
		});

		frm.add_custom_button(__("Backup & Send Now"), () => {
			frm.events.backup_now(frm);
		}).addClass("btn-primary");

		frm.events.render_cron_instructions(frm);
	},

	test_webhook_btn(frm) {
		frm.events.test_webhook(frm);
	},

	backup_now_btn(frm) {
		frm.events.backup_now(frm);
	},

	test_webhook(frm) {
		let url = frm.doc.webhook_url || "";
		if (/^\*+$/.test(url.trim())) {
			url = "";
		}

		frappe.call({
			method: "stepup.stepup.doctype.discord_backup_settings.discord_backup_settings.send_test_message",
			args: { webhook_url: url },
			freeze: true,
			freeze_message: __("Connecting to Discord webhook..."),
			callback(r) {
				if (!r.exc && r.message && r.message.success) {
					frappe.msgprint({
						title: __("Delivered"),
						indicator: "green",
						message: __("Test message sent successfully to Discord! Check your Discord channel.")
					});
				}
			}
		});
	},

	backup_now(frm) {
		frappe.confirm(
			__("Generate a fresh backup of exponit.localhost and upload it to Discord right now?"),
			() => {
				frappe.call({
					method: "stepup.stepup.doctype.discord_backup_settings.discord_backup_settings.trigger_backup_now",
					freeze: true,
					freeze_message: __("Creating database backup & uploading to Discord..."),
					callback(r) {
						if (!r.exc && r.message && r.message.success) {
							frappe.msgprint({
								title: __("Backup Sent!"),
								indicator: "green",
								message: __("Site backup created and sent to Discord successfully in {0}s!").format(r.message.duration)
							});
						}
					}
				});
			}
		);
	},

	render_cron_instructions(frm) {
		const html = `
		<div style="padding: 10px; background: var(--control-bg); border-radius: 6px; font-family: monospace; font-size: 13px;">
			<p><b>Option 1: System Cron (Recommended for reliable offsite backup)</b></p>
			<p style="color: var(--text-muted); margin-bottom: 5px;">Run <code>crontab -e</code> in terminal and add:</p>
			<pre style="background: var(--fg-color-light); padding: 8px; border-radius: 4px; overflow-x: auto;">0 2 * * * cd /Users/arm/Desktop/Exponit/bench && /Users/arm/Desktop/Exponit/bench/env/bin/bench --site exponit.localhost execute stepup.stepup.utils.discord_backup.scheduled_backup >> /Users/arm/Desktop/Exponit/bench/logs/discord_backup.log 2>&1</pre>
			
			<p style="margin-top: 15px;"><b>Option 2: Frappe Native Scheduler Hook</b></p>
			<p style="color: var(--text-muted); margin-bottom: 5px;">Configured in <code>stepup/hooks.py</code> under <code>scheduler_events</code>:</p>
			<pre style="background: var(--fg-color-light); padding: 8px; border-radius: 4px; overflow-x: auto;">scheduler_events = {
    "daily": [
        "stepup.stepup.utils.discord_backup.scheduled_backup"
    ]
}</pre>
		</div>
		`;
		frm.set_df_property("cron_instructions", "options", html);
	}
});
