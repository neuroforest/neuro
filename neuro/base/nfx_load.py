"""
Loading an `.nfx` document into a base, whatever its type.

An ontology and a knowledge module are written by different machinery - the
schema reconciler of `Metaontology.import_nfx`, the instance sync of
`NodesAccessor.sync_nfx` - and every caller used to choose between them
by assuming what a dependency closure could contain: ontologies only. A
knowledge module pinned by another was therefore never loaded. `load_document`
is the one place that reads the `type` and picks the writer; pair it with
`PluginIndex.closure`, which says what to load and in which order.
"""

from neuro.base import nfx


def load_document(nb, idx, path, on_import=None):
    """Write the document at `path` into `nb`. Its dependencies are expected to
    be there already - load `idx.closure(path)` first, in order.

    `idx` resolves every pin of the document, so it has to see all types (an
    `NfxIndex`). For a knowledge module the nodes its dependencies declare are
    passed to the sync as foreign: a module that re-declares one as an edge
    endpoint must not take it over from its owner.
    """
    doc = nfx.read(path)
    if doc.type == "knowledge":
        nb.nodes.sync_nfx(path, dependency_nids=idx.dependency_node_nids(path), index=idx)
    else:
        nb.metaontology.import_nfx(path, index=idx, on_import=on_import)
