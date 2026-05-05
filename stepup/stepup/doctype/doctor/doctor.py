# Copyright (c) 2026, Exponit Labs and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import json


class Doctor(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		address: DF.SmallText | None
		area: DF.Literal["Vasai E", "Vasai W", "Nalasopra E", "Nalasopara W"]
		clinic_name: DF.Data | None
		coordinates: DF.Data | None
		doctor_name: DF.Data
		latitude: DF.Float
		longitude: DF.Float
		phone: DF.Data | None
	# end: auto-generated types

	def before_save(self):

		if not self.coordinates:
			return
		try:
			lat,long=[float(x.strip()) for x in self.coordinates.split(",")]
		except Exception as e:
			frappe.throw("Invalid coordinates format. Please use 'latitude, longitude' format.")

		#validate property
		if not(-90 <= lat <=90):
			frappe.throw("Latitude must be between -90 and 90.")
		if not(-180 <= long <=180):
			frappe.throw("Longitude must be between -180 and 180.")

		#detect common mistakes(swapped values)
		if lat>50 and long<50:
			frappe.throw("It seems like the latitude and longitude values are swapped. Please check and correct them.")
		
		#store clean values
		self.latitude=lat
		self.longitude=long

		#Set Geolocation data for map rendering
		self.geolocation=json.dumps({
			"type":"FeatureCollection",
			"features": [
				{
					"type": "Feature",
					"properties": {},
					"geometry": {
						"type": "Point",
						"coordinates": [long, lat]
					}
				}
			]
		})
