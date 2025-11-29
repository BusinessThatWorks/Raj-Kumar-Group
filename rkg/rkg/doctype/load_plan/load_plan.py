# Copyright (c) 2025, beetashoke.chakraborty@clapgrow.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class LoadPlan(Document):
	def validate(self):
		"""Calculate total quantity from child table items."""
		self.calculate_total_quantity()
	
	def calculate_total_quantity(self):
		"""Sum up quantity from all Load Plan Item child table rows."""
		total_quantity = 0
		if self.table_tezh:
			for item in self.table_tezh:
				total_quantity += flt(item.quantity) or 0
		self.total_quantity = total_quantity
