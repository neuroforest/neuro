from neuro.base.schema import Metaproperties, OntologyNodeInfo, Violations


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


class ObjectValidator:
    """Validates an object to be inserted into NeuroBase."""

    def __init__(self, nb, o):
        self.nb = nb
        self.object = o
        self.violations = Violations()

    def get_violations(self):
        self.validate_labels()
        self.validate_properties()
        return self.violations

    def validate_label(self, label):
        query = """
        MATCH (n:OntologyNode {label: $label})
        RETURN n.label as label;
        """
        ontology_node = self.nb.get_data(query, parameters={"label": label})
        if not ontology_node:
            self.violations.undefined_labels.append(label)
        elif len(ontology_node) > 1:
            raise ValueError(f"Multiple ontology nodes found with label: {label}")
        else:
            pass

    def validate_labels(self):
        for label in self.object.labels:
            self.validate_label(label)

    def validate_properties(self):
        for label in self.object.labels:
            if label in self.violations.undefined_labels:
                continue
            metaproperties = Metaproperties.from_ontology(self.nb, label)
            self.violations = metaproperties.validate_properties(self.object.properties, self.violations)

