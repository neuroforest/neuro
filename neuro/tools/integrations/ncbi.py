import os
from xml.etree import ElementTree

import requests

from neuro.utils import exceptions


def resolve_taxon_name(taxon_name):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "taxonomy",
        "term": taxon_name,
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
        "ScientificName": element_tree.find(".//Taxon/ScientificName").text,
        "ParentTaxId": element_tree.find(".//Taxon/ParentTaxId").text,
        "Rank": element_tree.find(".//Taxon/Rank")
    }


def get_ncbi_lineage(taxon):
    try:
        taxon_data = get_ncbi_taxonomy_data(taxon)
        lineage = taxon_data[0]['LineageEx']
        lineage.append({
            "TaxId": taxon_data[0]["TaxId"],
            "ScientificName": taxon_data[0]["ScientificName"],
            "Rank": taxon_data[0]["Rank"]
        })
    except BaseException as e:
        if "HTTP Error 400" in str(e):
            return exceptions.InternalError("HTTP Error 400")
        elif "Search Backend failed" in str(e):
            return exceptions.InternalError("Search Backend failed")
        else:
            return e

    return lineage
