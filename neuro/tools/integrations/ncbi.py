import os
from xml.etree import ElementTree

import requests


def resolve_taxon_name(taxon_name):
    # Quoted phrase + field tag: an unquoted term goes through Entrez automatic
    # term mapping, which silently drops unmatched words - "Escherichia coli
    # tip 6" became `6[All Names]` and resolved to [Eubacterium] cellulosolvens.
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    phrase = taxon_name.replace('"', "").strip()
    params = {
        "db": "taxonomy",
        "term": f'"{phrase}"[All Names]',
        "retmode": "json",
        "api_key": os.getenv("NCBI_API_KEY")
    }
    res = requests.get(url, params)
    return res.json()["esearchresult"]["idlist"]


def get_lineage(taxon_id):
    url = "http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "taxonomy",
        "id": taxon_id,
        "retmode": "xml",
        "api_key": os.getenv("NCBI_API_KEY")
    }
    res = requests.get(url, params)
    element_tree = ElementTree.fromstring(res.text)
    lineage_elements = element_tree.findall(".//LineageEx/Taxon")
    lineage = list()
    for le in lineage_elements:
        lineage.append({
            "TaxId": le.find("TaxId").text,
            "ScientificName": le.find("ScientificName").text,
            "Rank": le.find("Rank").text
        })

    lineage.append({
        "TaxId": element_tree.find(".//Taxon/TaxId").text,
        "ScientificName": element_tree.find(".//Taxon/ScientificName").text,
        "Rank": element_tree.find(".//Taxon/Rank").text
    })

    return lineage


def fetch_taxa(taxon_ids, batch=100):
    """Entrez's current record for each taxid, by id - ``{TaxId, ScientificName,
    Rank, ParentTaxId, AkaTaxIds, LineageEx}`` with ``LineageEx`` root first as
    ``get_lineage`` shapes it. Batched POSTs, ``batch`` ids each.

    The result is keyed by the id Entrez *returns*, which is not always the one
    asked: a merged taxid comes back as the surviving record with the old id in
    its ``AkaTaxIds``, and a deleted one comes back as nothing. Both are the
    caller's to read off the dictionary - ``merged(asked, fetched)`` does it.

    One bad id fails its whole batch, so a batch that errors is retried one id
    at a time; an id that still fails is simply absent from the result."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    ids = [str(i) for i in taxon_ids]
    out = {}
    for start in range(0, len(ids), batch):
        chunk = ids[start:start + batch]
        try:
            out.update(_efetch(url, chunk))
        except (requests.RequestException, ElementTree.ParseError, ValueError):
            if len(chunk) == 1:
                continue
            for one in chunk:
                try:
                    out.update(_efetch(url, [one]))
                except (requests.RequestException, ElementTree.ParseError, ValueError):
                    pass
    return out


def _efetch(url, ids):
    data = {"db": "taxonomy", "id": ",".join(ids), "retmode": "xml",
            "api_key": os.getenv("NCBI_API_KEY")}
    res = requests.post(url, data=data, timeout=60)
    res.raise_for_status()
    tree = ElementTree.fromstring(res.text)
    records = {}
    for taxon in tree.findall("./Taxon"):
        lineage = [{"TaxId": le.findtext("TaxId"), "ScientificName": le.findtext("ScientificName"),
                    "Rank": le.findtext("Rank")}
                   for le in taxon.findall("./LineageEx/Taxon")]
        record = {
            "TaxId": taxon.findtext("TaxId"),
            "ScientificName": taxon.findtext("ScientificName"),
            "Rank": taxon.findtext("Rank"),
            "ParentTaxId": taxon.findtext("ParentTaxId"),
            "AkaTaxIds": [e.text for e in taxon.findall("./AkaTaxIds/TaxId")],
            "LineageEx": lineage,
        }
        records[record["TaxId"]] = record
    return records


def merged(asked, fetched):
    """``{old id: surviving id}`` for every asked id Entrez answered with another
    record - the merges - read off a ``fetch_taxa`` result."""
    asked = {str(i) for i in asked}
    out = {}
    for tax_id, record in fetched.items():
        for aka in record["AkaTaxIds"]:
            if aka in asked and aka != tax_id:
                out[aka] = tax_id
    return out


def get_taxon_info(taxon_id):
    url = "http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "taxonomy",
        "id": taxon_id,
        "retmode": "xml",
        "api_key": os.getenv("NCBI_API_KEY")
    }

    res = requests.get(url, params)
    element_tree = ElementTree.fromstring(res.text)

    return {
        "Division": element_tree.find(".//Taxon/Division").text,
        "TaxId": element_tree.find(".//Taxon/TaxId").text,
        "ScientificName": element_tree.find(".//Taxon/ScientificName").text,
        "ParentTaxId": element_tree.find(".//Taxon/ParentTaxId").text,
        "Rank": element_tree.find(".//Taxon/Rank").text
    }
