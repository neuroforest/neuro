"""
NeuroWiki migration tools
"""

import json
import shutil

import tqdm

from neuro.core import Moment, Node
from neuro.core.tid import WikiFolder, TiddlywikiHtml
from neuro.tools.tw5api import tw_get, tw_put
from neuro.base import NeuroBase
from neuro.utils import internal_utils


def prepare_fields(fields):
    def convert_time(t, field):
        if field in t:
            moment = Moment.from_tid_val(t[field])
            t[field] = moment.to_iso()
            return t
        else:
            return t

    fields = convert_time(fields, "created")
    fields = convert_time(fields, "modified")

    del fields["revision"]
    return fields


def prepare_object(o):
    def convert_time(t, field):
        if field in t:
            iso_string = t[field]
            moment = Moment.from_string(iso_string, "%Y-%m-%dT%H:%M:%S.%fZ")
            t[field] = moment.to_tid_val()
            return t
        else:
            return t

    o = convert_time(o, "created")
    o = convert_time(o, "modified")

    return o


def migrate_wf_to_neo4j(wf_path, port=8222, **kwargs):
    """
    Migrate data from filesystem to Neo4j database.
    :param wf_path:
    :param port: WF port
    """
    with NeuroBase(**kwargs) as nb:
        try:
            nb.driver.verify_connectivity()
        except Exception as e:
            print(f"Error connecting to Neo4j: {e}")
            return

        # Run a WikiFolder
        tw_path = internal_utils.get_path("tiddlywiki.js")
        wf = WikiFolder(wf_path, tw5=tw_path, silent=True, **kwargs)
        with wf:
            tid_titles = tw_get.tid_titles(
                "[all[tiddlers]!is[system]] [is[system]has[neuro.id]]",
                port=port, **kwargs
            )
            for tid_title in tqdm.tqdm(tid_titles):
                fields = tw_get.fields(tid_title, port=port, **kwargs)
                del fields["revision"]
                node = Node(labels=["Tiddler"], uuid=fields["neuro.id"], properties=fields)
                nb.nodes.put(node)
            print(f"Finished importing {len(tid_titles)} tiddlers")


def migrate_neo4j_to_wf(wf_path, port=8222, **kwargs):
    """
    Migrate data from Neo4j database to a WikiFolder.
    :param wf_path:
    :param port: WF port
    """
    with NeuroBase(**kwargs) as nb:
        fields_list = nb.tiddlers.all_fields()

    tw_path = internal_utils.get_path("tiddlywiki.js")
    shutil.rmtree(wf_path, ignore_errors=True)
    wf = WikiFolder(wf_path, tw5=tw_path, port=port, **kwargs)
    with wf:
        for fields in fields_list:
            fields = prepare_object(fields)
            tw_put.fields(fields, port=port, params={"preserve": "yes"})


def migrate_neo4j_to_json(json_path):
    with NeuroBase() as nb:
        fields_list = nb.tiddlers.all_fields()
    with open(json_path, "w+") as f:
        json.dump(fields_list, f)


def migrate_wf_to_json(wf_path, json_path, port=8222, **kwargs):
    wf = WikiFolder(wf_path, port=port, silent=True, **kwargs)
    process = wf.start()
    fields_list = tw_get.all_fields(port=port, params={"exclude": ","})
    with open(json_path, "w+") as f:
        json.dump(fields_list, f)
    process.kill()


def migrate_html_to_wf(html_path, wf_path, port=8222, **kwargs):
    try:
        ntw = TiddlywikiHtml().from_html(html_path)
    except AttributeError:
        ntw = TiddlywikiHtml().from_html_legacy(html_path)

    ntw.write_to_wf(wf_path, port=port, **kwargs)
