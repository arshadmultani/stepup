from typing import Any
import frappe
from frappe import _
from frappe.model.document import Document
from stepup.stepup.utils.telegram import normalize_chat_id, send_telegram_message


class TelegramSettings(Document):
	def validate(self):
		if self.chat_id:
			self.chat_id = normalize_chat_id(self.chat_id)


@frappe.whitelist()
def send_test_message(
	bot_token: str | None = None,
	chat_id: str | None = None,
	message_thread_id: str | None = None,
) -> dict[str, Any]:
	"""Test Telegram connection directly from Desk UI."""
	settings = frappe.get_doc("Telegram Settings")

	# If token is not provided or is masked as asterisks from the UI, load from DB
	if not bot_token or all(c == "*" for c in bot_token.strip()):
		token = settings.get_password("bot_token")
	else:
		token = bot_token.strip()

	cid = normalize_chat_id(chat_id or settings.chat_id)
	thread_id = message_thread_id or getattr(settings, "message_thread_id", None) or None

	if not token:
		frappe.throw(_("Please enter a Bot Token before testing."))
	if not cid:
		frappe.throw(_("Please enter a Chat ID or Channel ID before testing."))

	topic_str = f" (Topic: {thread_id})" if thread_id else ""
	test_text = (
		"🤖 <b>ERPNext StepUp Telegram Integration</b>\n\n"
		f"✅ <b>Connection successful!{topic_str}</b>\n\n"
		"Your Telegram bot is configured properly. When a Sales Invoice is submitted in ERPNext, "
		"a message with details and the invoice PDF will be sent to this chat."
	)

	ok, msg = send_telegram_message(token, cid, test_text, message_thread_id=thread_id)
	if not ok:
		frappe.throw(_("Telegram Error: {0}").format(msg))

	return {"success": True, "message": _("Test message sent successfully to Telegram!")}

