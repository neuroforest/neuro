"""
NeuroWiki migration tools
"""

import json
import shutil

import tqdm

from neuro.core import Moment
from neuro.core.tid import WikiFolder, TiddlywikiHtml
from neuro.tools.tw5api import tw_get, tw_put
from neuro.base.api import NeuroBase, nb_get
from neuro.utils import config  # noqa: F401
from neuro.utils import internal_utils


def prepare_tiddler(tiddler):
    def convert_time(t, field):
        if field in t:
            moment = Moment.from_tid_val(t[field])
            t[field] = moment.to_iso()
            return t
        else:
            return t

    tiddler = convert_time(tiddler, "created")
    tiddler = convert_time(tiddler, "modified")

    del tiddler["revision"]
    return tiddler


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
    nb = NeuroBase(**kwargs)
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
            tiddler = tw_get.tiddler(tid_title, port=port, **kwargs)
            del tiddler["revision"]
            nb.save_object(tiddler)
        print(f"Finished importing {len(tid_titles)} tiddlers")


def migrate_neo4j_to_wf(wf_path, port=8222, **kwargs):
    """
    Migrate data from Neo4j database to a WikiFolder.
    :param wf_path:
    :param port: WF port
    """
    objects = nb_get.all_tiddlers(**kwargs)

    # Run a WikiFolder
    tw_path = internal_utils.get_path("tiddlywiki.js")
    shutil.rmtree(wf_path, ignore_errors=True)
    wf = WikiFolder(wf_path, tw5=tw_path, port=port, **kwargs)
    with wf:
        for o in objects:
            o = prepare_object(o)
            tw_put.fields(o, port=port, params={"preserve": "yes"})


def migrate_neo4j_to_json(json_path):
    objects = nb_get.all_tiddlers()
    with open(json_path, "w+") as f:
        json.dump(objects, f)


def migrate_wf_to_json(wf_path, json_path, port=8222, **kwargs):
    wf = WikiFolder(wf_path, port=port, silent=True, **kwargs)
    process = wf.start()
    tiddlers = tw_get.all_tiddlers(port=port, params={"exclude": ","})
    with open(json_path, "w+") as f:
        json.dump(tiddlers, f)
    process.kill()


def migrate_html_to_wf(html_path, wf_path, port=8222, **kwargs):
    try:
        ntw = TiddlywikiHtml().from_html(html_path)
    except AttributeError:
        ntw = TiddlywikiHtml().from_html_legacy(html_path)

    ntw.write_to_wf(wf_path, port=port, **kwargs)
