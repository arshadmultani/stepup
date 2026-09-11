# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

import time
import requests
import frappe
from frappe import _


def get_telegram_settings():
	"""Fetch cached or fresh Telegram Settings single document."""
	if not frappe.db.exists("DocType", "Telegram Settings"):
		return None
	return frappe.get_cached_doc("Telegram Settings")


def normalize_chat_id(chat_id: str | int | None) -> str:
	"""
	Normalize chat_id for Telegram API.
	Telegram supergroups and channels start with -100 (e.g. -1003737286931).
	If a user inputs 1003737286931 without minus or prefix, normalize it.
	"""
	if not chat_id:
		return ""
	cid = str(chat_id).strip()
	if cid.startswith("@"):
		return cid
	if cid.isdigit():
		if cid.startswith("100"):
			return f"-{cid}"
		else:
			return f"-100{cid}"
	return cid


def send_telegram_message(bot_token, chat_id, text, message_thread_id=None, parse_mode="HTML"):
	"""Send a text message via Telegram Bot API."""
	chat_id = normalize_chat_id(chat_id)
	url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
	payload = {
		"chat_id": chat_id,
		"text": text,
		"parse_mode": parse_mode,
		"disable_web_page_preview": True,
	}
	if message_thread_id:
		try:
			payload["message_thread_id"] = int(str(message_thread_id).strip())
		except (ValueError, TypeError):
			pass
	try:
		response = requests.post(url, json=payload, timeout=20)
		res_json = response.json()
		if not res_json.get("ok"):
			error_desc = res_json.get("description", "Unknown error from Telegram API")
			frappe.log_error(
				title="Telegram sendMessage Failed",
				message=f"Error: {error_desc}\nStatus: {response.status_code}\nPayload: {payload}\nResponse: {response.text}",
			)
			return False, error_desc
		return True, "Message delivered successfully"
	except Exception as e:
		error_msg = str(e)
		frappe.log_error(
			title="Telegram sendMessage Exception",
			message=frappe.get_traceback(),
		)
		return False, error_msg


def send_telegram_document(bot_token, chat_id, file_content, filename, caption, message_thread_id=None, parse_mode="HTML"):
	"""Send a document/PDF via Telegram Bot API."""
	chat_id = normalize_chat_id(chat_id)
	url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

	# Telegram document caption limit is 1024 characters
	if len(caption) > 1024:
		caption = caption[:1020] + "..."

	data = {
		"chat_id": chat_id,
		"caption": caption,
		"parse_mode": parse_mode,
	}
	if message_thread_id:
		try:
			data["message_thread_id"] = int(str(message_thread_id).strip())
		except (ValueError, TypeError):
			pass
	files = {
		"document": (filename, file_content, "application/pdf"),
	}

	try:
		response = requests.post(url, data=data, files=files, timeout=40)
		res_json = response.json()
		if not res_json.get("ok"):
			error_desc = res_json.get("description", "Unknown error from Telegram API")
			frappe.log_error(
				title="Telegram sendDocument Failed",
				message=f"Error: {error_desc}\nStatus: {response.status_code}\nResponse: {response.text}",
			)
			return False, error_desc
		return True, "Document delivered successfully"
	except Exception as e:
		error_msg = str(e)
		frappe.log_error(
			title="Telegram sendDocument Exception",
			message=frappe.get_traceback(),
		)
		return False, error_msg


def format_sales_invoice_caption(doc, settings=None):
	"""Format a clean, professional HTML summary of the Sales Invoice for Telegram."""
	currency = doc.currency or frappe.defaults.get_global_default("currency") or "₹"
	customer_name = doc.customer_name or doc.customer or "Customer"

	lines = [
		"🧾 <b>Sales Invoice Submitted</b>",
		"",
		f"<b>Invoice:</b> <code>{doc.name}</code>",
		f"<b>Customer:</b> {frappe.utils.escape_html(customer_name)}",
		f"<b>Posting Date:</b> {frappe.utils.formatdate(doc.posting_date)}",
	]

	if doc.due_date:
		lines.append(f"<b>Due Date:</b> {frappe.utils.formatdate(doc.due_date)}")

	lines.append(f"<b>Grand Total:</b> {frappe.utils.fmt_money(doc.grand_total, currency=currency)}")

	if doc.outstanding_amount is not None and doc.outstanding_amount != doc.grand_total:
		lines.append(f"<b>Outstanding:</b> {frappe.utils.fmt_money(doc.outstanding_amount, currency=currency)}")

	if doc.items:
		lines.append("")
		lines.append(f"<b>Items ({len(doc.items)}):</b>")
		for idx, item in enumerate(doc.items, 1):
			item_title = frappe.utils.escape_html(item.item_name or item.item_code)
			qty = int(item.qty) if item.qty == int(item.qty) else item.qty
			rate = frappe.utils.fmt_money(item.rate, currency=currency)
			amt = frappe.utils.fmt_money(item.amount, currency=currency)
			line = f"• {item_title} — {qty} × {rate} = {amt}"

			# Stay comfortably below Telegram caption limit of 1024 characters
			tentative = "\n".join(lines + [line])
			if len(tentative) > 940:
				remaining = len(doc.items) - idx + 1
				lines.append(f"<i>... and {remaining} more items (see attached PDF)</i>")
				break
			lines.append(line)

	return "\n".join(lines)


def get_invoice_pdf(doc, settings):
	"""Generate invoice PDF in memory, falling back gracefully if custom format fails."""
	preferred_format = getattr(settings, "print_format", None)
	if not preferred_format:
		if frappe.db.exists("Print Format", "StepUp Sales Invoice"):
			preferred_format = "StepUp Sales Invoice"
		else:
			preferred_format = "Standard"

	letterhead = getattr(settings, "letter_head", None) or None

	try:
		return frappe.get_print(
			doctype="Sales Invoice",
			name=doc.name,
			print_format=preferred_format,
			letterhead=letterhead,
			as_pdf=True,
		)
	except Exception as e:
		frappe.log_error(
			title=f"Telegram PDF Generation Failed ({preferred_format}) for {doc.name}",
			message=frappe.get_traceback(),
		)

	# Fallback 1: Try StepUp Sales Invoice if available and different from preferred
	if preferred_format != "StepUp Sales Invoice" and frappe.db.exists("Print Format", "StepUp Sales Invoice"):
		try:
			return frappe.get_print(
				doctype="Sales Invoice",
				name=doc.name,
				print_format="StepUp Sales Invoice",
				letterhead=letterhead,
				as_pdf=True,
			)
		except Exception:
			pass

	# Fallback 2: Try Standard print format
	if preferred_format != "Standard":
		try:
			return frappe.get_print(
				doctype="Sales Invoice",
				name=doc.name,
				print_format="Standard",
				letterhead=letterhead,
				as_pdf=True,
			)
		except Exception:
			frappe.log_error(
				title=f"Telegram Standard PDF Fallback Failed for {doc.name}",
				message=frappe.get_traceback(),
			)

	return None


def send_sales_invoice_to_telegram(doc, method=None):
	"""
	Hook called on Sales Invoice on_submit.
	Enqueues asynchronous dispatch so invoice submission remains immediate.
	"""
	try:
		settings = get_telegram_settings()
		if not settings or not settings.enabled:
			return

		bot_token = settings.get_password("bot_token")
		chat_id = settings.chat_id

		if not bot_token or not chat_id:
			return

		# Enqueue to background worker (or run immediately in tests)
		frappe.enqueue(
			"stepup.stepup.utils.telegram.enqueue_send_sales_invoice",
			queue="short",
			doc_name=doc.name,
			now=frappe.flags.in_test or False,
		)
	except Exception:
		frappe.log_error(
			title=f"Telegram Notification Queue Error for {doc.name}",
			message=frappe.get_traceback(),
		)


def enqueue_send_sales_invoice(doc_name):
	"""Background worker job to fetch PDF and dispatch to Telegram."""
	try:
		settings = get_telegram_settings()
		if not settings or not settings.enabled:
			return

		bot_token = settings.get_password("bot_token")
		chat_id = settings.chat_id

		if not bot_token or not chat_id:
			return

		doc = frappe.get_doc("Sales Invoice", doc_name)
		caption = format_sales_invoice_caption(doc, settings)
		message_thread_id = getattr(settings, "message_thread_id", None) or None

		pdf_bytes = None
		if getattr(settings, "attach_pdf", True):
			pdf_bytes = get_invoice_pdf(doc, settings)

		if pdf_bytes:
			filename = f"{doc.name}.pdf"
			ok, _ = send_telegram_document(
				bot_token, chat_id, pdf_bytes, filename, caption, message_thread_id=message_thread_id
			)
			if not ok:
				# If document sending fails (e.g. timeout on file), fall back to text message
				send_telegram_message(bot_token, chat_id, caption, message_thread_id=message_thread_id)
		else:
			send_telegram_message(bot_token, chat_id, caption, message_thread_id=message_thread_id)

	except Exception:
		frappe.log_error(
			title=f"Telegram Enqueue Send Error for {doc_name}",
			message=frappe.get_traceback(),
		)


def sync_all_submitted_invoices(delay: float = 1.5):
	"""
	Send all submitted Sales Invoices to Telegram in chronological order.
	Includes delay between calls to respect Telegram rate limits.
	"""
	settings = get_telegram_settings()
	if not settings or not settings.enabled:
		frappe.throw(_("Telegram Settings are not enabled."))

	invoices = frappe.db.get_list(
		"Sales Invoice",
		filters={"docstatus": 1},
		fields=["name", "posting_date"],
		order_by="posting_date asc, creation asc",
	)

	sent_count = 0
	failed = []

	for inv in invoices:
		try:
			enqueue_send_sales_invoice(inv.name)
			sent_count += 1
			frappe.db.commit()
			time.sleep(delay)
		except Exception as e:
			failed.append({"invoice": inv.name, "error": str(e)})

	return {"total": len(invoices), "sent": sent_count, "failed": failed}

