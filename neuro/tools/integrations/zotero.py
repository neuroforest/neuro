import os
import subprocess

from bs4 import BeautifulSoup

from neuro.utils import config


def get_citation_text(item_id,
                      library_id=os.getenv("ZOTERO_LIBRARY_ID"),
                      api_key=os.getenv("ZOTERO_API_KEY"),
                      style="apa",
                      library_type="user",
                      locale="en-US"):
    """
    Get the citation text for a specific item in a Zotero library.

    :param item_id:
    :param library_id:
    :param api_key:
    :param style:
    :param library_type: 'user' or 'group'
    :param locale: locale for the citation style, default is 'en-US'
    """

    if not library_id:
        print("No Zotero library ID provided")
        return None

    command = [
        "curl",
        f"https://api.zotero.org/{library_type}s/{library_id}/items/{item_id}?format=bib&style={style}&locale={locale}"
    ]

    if api_key:
        command.insert(1, f"Zotero-API-Key: {api_key}")
        command.insert(1, "-H")

    result = subprocess.run(command, capture_output=True, text=True)
    soup = BeautifulSoup(result.stdout, "xml")
    zotero_citation_text = soup.find("div", class_="csl-entry").get_text(strip=True)

    return zotero_citation_text
