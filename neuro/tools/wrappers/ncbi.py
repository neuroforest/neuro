import logging

from Bio import Entrez


def get_ncbi_taxonomy_data(taxon):
    # Search taxon
    Entrez.email = "your_email@example.com"
    search_handle = Entrez.esearch(db="taxonomy", term=taxon)
    search_results = Entrez.read(search_handle)
    search_handle.close()
    if not search_results['IdList']:
        logging.info(f"No taxon found for: {taxon}")
        return lineage
    tax_id = search_results['IdList'][0]

    # Fetch taxonomy details
    fetch_handle = Entrez.efetch(db="taxonomy", id=tax_id, retmode="xml")
    taxon_data = Entrez.read(fetch_handle)
    fetch_handle.close()
    return taxon_data


def get_ncbi_lineage(taxon):
    lineage = []
    try:
        taxon_data = get_ncbi_taxonomy_data(taxon)
        lineage = taxon_data[0]['LineageEx']
        lineage.append({
            "TaxId": taxon_data[0]["TaxId"],
            "ScientificName": taxon_data[0]["ScientificName"],
            "Rank": taxon_data[0]["Rank"]
        })
    except Exception as e:
        logging.error(e)

    return lineage
