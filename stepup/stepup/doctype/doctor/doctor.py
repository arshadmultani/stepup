# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Doctor(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		address: DF.SmallText | None
		area: DF.Literal["Vasai E", "Vasai W", "Nalasopra E", "Nalasopara W"]
		clinic_name: DF.Data | None
		doctor_name: DF.Data
		phone: DF.Data | None
	# end: auto-generated types

	pass
