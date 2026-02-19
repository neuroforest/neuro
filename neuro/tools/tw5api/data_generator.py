"""
Generate datasets from NeuroForest wiki.
"""

import csv
import logging

from neuro.core.file.text import TextCsv
from neuro.tools.tw5api import tw_get
from neuro.utils import internal_utils


def generate_dataset(tw_filter, fields, dataset_path, allow_empty=False):
    """
    Generate a dataset given a filter and a collection of fields.
    :param tw_filter:
    :param fields: list of fields to extract form NeuroForest wiki
    :param dataset_path: full path to dataset
    :param allow_empty: if True entities that do not contain all the fields
        specified are also included in the dataset
    :return:
    """
    tw_fields = tw_get.tw_fields(fields, tw_filter)

    rows = list()
    rows.append(tuple(fields))  # Header
    for i in tw_fields:
        if len(i) != len(fields) and not allow_empty:
            continue
        row_tuple = tuple()
        for field in fields:
            if field in i:
                row_tuple += (i[field], )
            else:
                row_tuple += "",
        rows.append(row_tuple)

    with open(dataset_path, "w+", newline="", encoding="utf-8") as f:
        csv_writer = csv.writer(f)
        csv_writer.writerows(rows)


def generate_dataset_taxon_ranks():
    tw_filter = "[search:neuro.role:regexp[^taxon$]]"
    fields = [
        "name",
        "inat.rank.level",
        "encoding"
    ]
    path = internal_utils.get_path("resources") / "data" / "taxon-ranks.csv"
    generate_dataset(tw_filter, fields, path)

    # Validate
    text_csv = TextCsv(path)
    for field in fields:
        if not text_csv.is_identifier(field):
            logging.error(f"Column not identifier: {field}")


if __name__ == "__main__":
    generate_dataset_taxon_ranks()
