# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RCPADoctorRow(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		doctor: DF.Link | None
		doctor_name: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		quantity: DF.Float
		remarks: DF.SmallText | None
	# end: auto-generated types

	pass
