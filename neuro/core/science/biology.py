"""
Collection of classes related to biology.
"""


class BioTaxon:
	"""
	Taxon object.
	"""
	def __init__(self):
		self.scientific_name: str


class BioTaxonChain(tuple):
	"""
	Chain of taxon objects, from narrow to broad.
	"""
	def __init__(self):
		pass
