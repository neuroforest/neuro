from neuro.base.schema import ObjectValidator, OntologyNodeInfo


class Ontology:
    """Accessor for ontology operations on NeuroBase."""

    def __init__(self, nb):
        self._nb = nb

    def is_valid_node(self, node):
        """Validate a node against the ontology."""
        validator = ObjectValidator(self._nb, node)
        violations = validator.get_violations()
        return not bool(violations)

    def info(self, label):
        """Return an OntologyNodeInfo for the given label."""
        return OntologyNodeInfo(self._nb, label)

