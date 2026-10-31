# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

from typing import Any
import requests
import frappe
from frappe import _
from frappe.model.document import Document
from stepup.stepup.utils.discord_backup import (
	DEFAULT_WEBHOOK_URL,
	send_discord_notification,
	take_and_send_backup,
)


class DiscordBackupSettings(Document):
	pass


@frappe.whitelist()
def send_test_message(webhook_url: str | None = None) -> dict[str, Any]:
	"""Test Discord webhook connectivity from ERPNext Desk UI."""
	settings = frappe.get_single("Discord Backup Settings")

	url = webhook_url
	if not url or all(c == "*" for c in url.strip()):
		url = settings.get_password("webhook_url") if hasattr(settings, "get_password") else settings.webhook_url

	if not url:
		url = DEFAULT_WEBHOOK_URL

	test_embed = {
		"title": "🧪 ERPNext Discord Backup Test",
		"description": "Your Discord webhook is working! Automated site backups will be sent to this channel.",
		"color": 3447003,  # Blue (#3498db)
		"fields": [
			{"name": "Site", "value": f"`{frappe.local.site}`", "inline": True},
			{"name": "App", "value": "StepUp", "inline": True},
			{"name": "Status", "value": "Connected ✅", "inline": True},
		],
		"footer": {"text": "StepUp Backup Integration"},
	}

	ok, msg = send_discord_notification(url, content="🔔 **Test Notification from ERPNext**", embeds=[test_embed])
	if not ok:
		frappe.throw(_("Discord Test Failed: {0}").format(msg))

	return {"success": True, "message": _("Test message sent successfully to Discord!")}


@frappe.whitelist()
def trigger_backup_now() -> dict[str, Any]:
	"""Trigger an immediate backup and dispatch to Discord."""
	result = take_and_send_backup(force=True)
	if not result.get("success"):
		frappe.throw(_("Backup dispatch failed: {0}").format(result.get("error", "Unknown error")))
	return result
