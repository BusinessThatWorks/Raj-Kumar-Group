# Copyright (c) 2025, beetashoke.chakraborty@clapgrow.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname

class VehicleModelVariant(Document):
	def autoname(self):
		naming_rule = str(self.model or '')+str(self.model_type or '')+str(self.model_color or '')
		self.name = naming_rule
		self.variant_name = self.name 