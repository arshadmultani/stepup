# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class MonthlySalesTarget(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		company: DF.Link | None
		description: DF.SmallText | None
		month: DF.Date | None
		target_amount: DF.Currency
	# end: auto-generated types

	pass
