# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RCPAVisit(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from stepup.stepup.doctype.rcpa_doctor_row.rcpa_doctor_row import RCPADoctorRow

		chemist: DF.Link | None
		date: DF.Date | None
		doctor_entries: DF.Table[RCPADoctorRow]
	# end: auto-generated types

	pass
