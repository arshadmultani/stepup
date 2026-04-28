# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Chemist(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		address: DF.SmallText | None
		name1: DF.Data | None
		select_zctt: DF.Literal["Vasai E", "Vasai W", "Nalasopara E", "Nalasopara W"]
	# end: auto-generated types

	pass
