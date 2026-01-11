from lark import Transformer, Lark, Tree, Token
from lark.reconstruct import Reconstructor

from neuro.utils import internal_utils


class NqlParser(Lark):
    def __init__(self, maybe_placeholders=True):
        nql_grammar_path = internal_utils.get_path("resources") + "/nql-grammar.lark"
        with open(nql_grammar_path, "r") as f:
            nql_grammar = f.read()
        super().__init__(nql_grammar, maybe_placeholders=maybe_placeholders)


class NqlTransformer(Transformer):
    @staticmethod
    def ontology(children):
        ont_type, node = children
        return {
            "type": ont_type.value,
            "label": node["label"],
            "properties": node["properties"]
        }

    @staticmethod
    def ontology_node(items):
        return {
            "label": items[0],
            "properties": items[1] if items[1] else dict()
        }

    @staticmethod
    def label(items):
        return items[0].value

    @staticmethod
    def properties(items):
        if len(items) == 0:
            return dict()
        else:
            return dict(items)

    @staticmethod
    def pair(items):
        key = str(items[0])
        val = str(items[1]).strip('"')
        return key, val


class NqlReconstructor(Reconstructor):
    def __init__(self, maybe_placeholders=False):
        parser = NqlParser(maybe_placeholders=maybe_placeholders)
        super().__init__(parser)


class NqlGenerator:
    @staticmethod
    def properties(properties_dict):
        properties_tree = Tree(Token('RULE', 'properties'), [])
        for key, value in properties_dict.items():
            if "." in key or "-" in key:
                token = Tree(Token("RULE", "property_key"), [Token("ESCAPED_KEY", f"`{key}`")])
            else:
                token = Tree(Token("RULE", "property_key"), [Token("CNAME", key)])
            item_tree = Tree(Token('RULE', 'pair'), [
                token,
                Token('ESCAPED_STRING', f'"{value}"')
            ])
            properties_tree.children.append(item_tree)
        return properties_tree

    def properties_string(self, properties):
        properties_tree = self.properties(properties)
        return NqlReconstructor().reconstruct(properties_tree)
