# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

import json
import os
import time
from datetime import datetime
import requests

import frappe
from frappe import _
from frappe.utils.backups import new_backup

DEFAULT_WEBHOOK_URL = (
	"https://discord.com/api/webhooks/1508133384713670659/"
	"PHryn1cIKSyqDCBtCAMqmMYrWavsQyCidyuTK7pMDmC4Bmp_CeW1CxPJdjxbDG4GHtGJ"
)

# Discord attachment limit is 25 MB for standard servers
MAX_DISCORD_FILE_BYTES = 24 * 1024 * 1024


def format_bytes(size: int | float) -> str:
	"""Convert bytes to human-readable string (KB, MB, GB)."""
	for unit in ["B", "KB", "MB", "GB", "TB"]:
		if size < 1024.0:
			return f"{size:.2f} {unit}"
		size /= 1024.0
	return f"{size:.2f} PB"


def get_discord_backup_settings() -> dict:
	"""
	Fetch Discord Backup settings from Discord Backup Settings DocType,
	site_config.json, or fallback to the provided default webhook.
	"""
	settings = {
		"enabled": True,
		"webhook_url": DEFAULT_WEBHOOK_URL,
		"send_database": True,
		"send_config": True,
		"send_files": False,
	}

	# Check Single DocType if migrated
	if frappe.db.exists("DocType", "Discord Backup Settings"):
		try:
			doc = frappe.get_cached_doc("Discord Backup Settings")
			settings["enabled"] = bool(doc.enabled)
			stored_url = doc.get_password("webhook_url") if hasattr(doc, "get_password") else doc.webhook_url
			if stored_url:
				settings["webhook_url"] = stored_url.strip()
			settings["send_database"] = bool(getattr(doc, "send_database", 1))
			settings["send_config"] = bool(getattr(doc, "send_config", 1))
			settings["send_files"] = bool(getattr(doc, "send_files", 0))
			return settings
		except Exception:
			pass

	# Check site_config.json
	conf_url = frappe.conf.get("discord_backup_webhook_url")
	if conf_url:
		settings["webhook_url"] = conf_url.strip()

	return settings


def send_discord_notification(webhook_url: str, content: str = "", embeds: list | None = None, file_tuples: list | None = None) -> tuple[bool, str]:
	"""
	Post message, embeds, and optional files to Discord webhook.
	file_tuples: list of (field_name, (filename, bytes_or_stream, mime_type))
	"""
	payload = {}
	if content:
		payload["content"] = content
	if embeds:
		payload["embeds"] = embeds

	try:
		if file_tuples:
			files_dict = {
				"payload_json": (None, json.dumps(payload), "application/json")
			}
			for idx, (filename, fileobj, mimetype) in enumerate(file_tuples):
				files_dict[f"files[{idx}]"] = (filename, fileobj, mimetype)
			resp = requests.post(webhook_url, files=files_dict, timeout=120)
		else:
			resp = requests.post(webhook_url, json=payload, timeout=30)

		if resp.status_code in (200, 204):
			return True, "Notification sent successfully."
		else:
			err = f"Discord Webhook returned status {resp.status_code}: {resp.text}"
			frappe.log_error(title="Discord Webhook Error", message=err)
			return False, err
	except Exception as e:
		err = f"Exception sending to Discord Webhook: {e}"
		frappe.log_error(title="Discord Webhook Exception", message=frappe.get_traceback())
		return False, err


def take_and_send_backup(webhook_url: str | None = None, force: bool = True) -> dict:
	"""
	Generate a fresh Frappe backup and dispatch database & site_config to Discord.
	"""
	start_time = time.time()
	settings = get_discord_backup_settings()
	target_url = (webhook_url or settings.get("webhook_url") or DEFAULT_WEBHOOK_URL).strip()
	site_name = frappe.local.site or "exponit.localhost"

	if not target_url:
		frappe.throw(_("Discord Webhook URL is missing."))

	try:
		# Trigger Frappe's backup generator
		send_files = settings.get("send_files", False)
		odb = new_backup(
			older_than=0,
			ignore_files=not send_files,
			compress=True,
			force=force,
		)

		files_to_send = []
		file_descriptions = []
		open_handles = []

		# 1. Database backup
		db_path = getattr(odb, "backup_path_db", None)
		if db_path and os.path.exists(db_path) and settings.get("send_database", True):
			db_name = os.path.basename(db_path)
			db_size = os.path.getsize(db_path)
			size_str = format_bytes(db_size)

			if db_size <= MAX_DISCORD_FILE_BYTES:
				fh = open(db_path, "rb")
				open_handles.append(fh)
				files_to_send.append((db_name, fh, "application/gzip"))
				file_descriptions.append(f"📦 **Database**: `{db_name}` ({size_str}) — *Attached*")
			else:
				file_descriptions.append(
					f"⚠️ **Database**: `{db_name}` ({size_str}) — *Exceeds Discord 25MB limit (stored on server)*"
				)

		# 2. Site config backup
		conf_path = getattr(odb, "backup_path_conf", None)
		if conf_path and os.path.exists(conf_path) and settings.get("send_config", True):
			conf_name = os.path.basename(conf_path)
			conf_size = os.path.getsize(conf_path)
			size_str = format_bytes(conf_size)

			if conf_size <= MAX_DISCORD_FILE_BYTES:
				fh = open(conf_path, "rb")
				open_handles.append(fh)
				files_to_send.append((conf_name, fh, "application/json"))
				file_descriptions.append(f"⚙️ **Site Config**: `{conf_name}` ({size_str}) — *Attached*")
			else:
				file_descriptions.append(
					f"⚠️ **Site Config**: `{conf_name}` ({size_str}) — *Stored on server*"
				)

		duration = round(time.time() - start_time, 2)
		now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

		embed = {
			"title": f"📦 Site Backup Completed: {site_name}",
			"description": "\n".join(file_descriptions) if file_descriptions else "No backup files configured to send.",
			"color": 3066993,  # Emerald Green (#2ecc71)
			"fields": [
				{"name": "🌐 Site", "value": f"`{site_name}`", "inline": True},
				{"name": "⏱️ Time Taken", "value": f"{duration}s", "inline": True},
				{"name": "🕒 Timestamp", "value": f"`{now_str}`", "inline": True},
			],
			"footer": {
				"text": "ERPNext / StepUp Automated Site Backup"
			},
			"timestamp": datetime.utcnow().isoformat() + "Z",
		}

		success, msg = send_discord_notification(
			webhook_url=target_url,
			content="🚀 **New Site Backup Ready**",
			embeds=[embed],
			file_tuples=files_to_send,
		)

		# Close any open file handles
		for fh in open_handles:
			try:
				fh.close()
			except Exception:
				pass

		if not success:
			return {"success": False, "error": msg}

		return {
			"success": True,
			"site": site_name,
			"database_backup": db_path,
			"duration": duration,
			"message": "Backup generated and dispatched to Discord successfully.",
		}

	except Exception as e:
		err_trace = frappe.get_traceback()
		frappe.log_error(title=f"Site Backup Dispatch Error ({site_name})", message=err_trace)

		# Notify Discord about the failure
		fail_embed = {
			"title": f"❌ Backup Failed: {site_name}",
			"description": f"An error occurred while generating or dispatching the backup:\n```\n{str(e)[:1800]}\n```",
			"color": 15158332,  # Red (#e74c3c)
			"fields": [
				{"name": "Site", "value": f"`{site_name}`", "inline": True},
				{"name": "Timestamp", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True},
			],
		}
		send_discord_notification(webhook_url=target_url, embeds=[fail_embed])

		return {"success": False, "error": str(e)}


def scheduled_backup() -> dict:
	"""
	Scheduled entrypoint invoked by Frappe Scheduler or external OS Cron.
	"""
	settings = get_discord_backup_settings()
	if not settings.get("enabled", True):
		return {"success": True, "skipped": True, "reason": "Discord backup is disabled in settings."}

	return take_and_send_backup()
