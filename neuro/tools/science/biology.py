"""
Biology tools.
"""
import logging

from neuro.core.deep import File
from neuro.tools.api import tw_get


def get_prefix(taxon_rank):
    """
    Get the prefix according to the taxon rank.
    :param taxon_rank:
    :return: NeuroTid object
    """
    neuro_keyword = f"taxon.{taxon_rank}"
    tw_filter = f"[search:neuro.keyword:literal[{neuro_keyword}]]"
    match = tw_get.tw_fields(["title", "neuro.keyword", "encoding"], tw_filter)
    if len(match) != 1:
        logging.info(f"Error: failed to find the prefix for {neuro_keyword}")
        return
    else:
        try:
            prefix = match[0]["encoding"].replace("`", "")
            return prefix
        except KeyError:
            logging.info(f"Error: no encoding for taxon \"{match[0]['title']}\"")
            return


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


class Fastq(File):
    """
    Tools for FASTQ file EDA.
    """
    def __init__(self, path=""):
        super().__init__(path)

    def get_read_number(self):
        with open(self.path, "r") as f:
            read_number = int(sum(0.25 for row in f))
        return read_number
