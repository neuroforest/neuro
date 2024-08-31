"""
Collection of classes related to biology.
"""

from neuro.core.deep import File

from Bio import SeqIO
from matplotlib import pyplot as plt


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

    def show_read_length_distribution(self):
        reads = SeqIO.parse(self.path, "fastq")
        read_lengths = list()
        for read in reads:
            read_lengths.append(len(read.seq))
        plt.hist(read_lengths, bins=range(min(read_lengths), max(read_lengths) + 1),
                 edgecolor='black')
        plt.title('Read Length Distribution')
        plt.xlabel('Read Length')
        plt.ylabel('Frequency')
        plt.show()
