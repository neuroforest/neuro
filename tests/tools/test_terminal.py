import json
import os

import pytest


kwargs = {
    "port": os.getenv("TEST_PORT"),
    "host": os.getenv("HOST"),
}


pytestmark = pytest.mark.integration


class TestGeo:
    def test_geocode(self):
        from neuro.tools.terminal.commands import geo
        test_data = [
            ("https://maps.app.goo.gl/6tKogiW9Xog87owx5", (61.213906, 78.942735)),
            ("https://goo.gl/maps/k9tRoWb6Fs2eDvJy6", (45.6227285, 23.3104755))
        ]
        for url, coordinates in test_data:
            assert geo.geocode_url(url) == coordinates


class TestQa:
    def test_remove_ghost_tiddler(self, wf_qa):
        from neuro.tools.tw5api import tw_get
        from neuro.tools.terminal.commands import qa
        tid_titles = tw_get.tid_titles("[search:title[Draft of ']!has[draft.of]]", **kwargs)
        assert len(tid_titles) > 0
        qa.remove_ghost_tiddlers(wf_qa.port)
        tid_titles = tw_get.tid_titles("[search:title[Draft of ']!has[draft.of]]", **kwargs)
        assert len(tid_titles) == 0

    def test_resolve_neuro_id_missing(self, wf_qa):
        from neuro.core.data.str import Uuid
        from neuro.tools.tw5api import tw_get
        from neuro.tools.terminal.commands import qa
        qa.resolve_neuro_ids(wf_qa.port)
        example = tw_get.fields("Example", **kwargs)
        assert "neuro.id" in example
        assert Uuid.is_valid_uuid_v4(example["neuro.id"])

    def test_resolve_neuro_id_duplicate(self, wf_qa, capsys):
        from neuro.tools.terminal.commands import qa
        qa_pass = qa.resolve_neuro_ids(port=wf_qa.port, verbose=True)
        assert not qa_pass
        stdout = capsys.readouterr().out
        assert len(stdout.splitlines()) == 5
        assert stdout.count("Duplicate neuro.id") == 2
        assert "20b4f8d3-6e6f-49fb-9be7-97f553c347bd" in stdout

    def test_set_roles(self, wf_qa):
        from neuro.tools.tw5api import tw_get
        from neuro.tools.terminal.commands import qa
        os.environ["ROLE_DICT"] = json.dumps({
            "Taxons": "taxon"
        })
        qa.set_roles(port=wf_qa.port)
        fields = tw_get.fields("Lysobacter enzymogenes", **kwargs)
        assert fields["neuro.role"] == "taxon"

    def test_set_object_sets(self, wf_qa):
        from neuro.tools.tw5api import tw_get
        from neuro.tools.terminal.commands import qa
        os.environ["OBJECT_SETS"] = json.dumps(["Fundamentals"])
        qa.set_object_sets(port=wf_qa.port)
        model = tw_get.fields(". Fundamentals", **kwargs)
        assert model["neuro.role"] == "model"

    def test_validate_tags(self, wf_qa):
        from neuro.tools.terminal.commands import qa
        assert qa.validate_tags(wf_qa.port)

    def test_validate_tags_untagged(self, wf_qa, capsys):
        from neuro.tools.tw5api import tw_put
        from neuro.tools.terminal.commands import qa
        tw_put.fields({"title": "Untagged"}, **kwargs)
        assert not qa.validate_tags(wf_qa.port)
        stdout = capsys.readouterr().out
        assert "Untagged" in stdout
        assert "has no tags" in stdout
        assert len(stdout.splitlines()) == 2

    def test_validate_tags_inexistent(self, wf_qa, capsys):
        from neuro.tools.tw5api import tw_put
        from neuro.tools.terminal.commands import qa
        tw_put.fields({"title": "Inexistent Tag", "tags": "Inexistent"}, **kwargs)
        assert not qa.validate_tags(wf_qa.port)
        stdout = capsys.readouterr().out
        assert "Inexistent Tag" in stdout
        assert "has invalid tags" in stdout
        assert len(stdout.splitlines()) == 2

    def test_resolve_missing_tiddlers(self, wf_qa, capsys):
        from neuro.tools.terminal.commands import qa
        assert not qa.resolve_missing_tiddlers(wf_qa.port)
        stdout = capsys.readouterr().out
        assert "Broken Link" in stdout
        assert "broken link" in stdout
        assert len(stdout.splitlines()) == 2

    def test_resolve_primary_simple(self, wf_qa):
        from neuro.tools.tw5api import tw_get
        from neuro.tools.terminal.commands import qa
        qa.Primary(interactive=False, port=wf_qa.port, verbose=False).run()
        journal_entry = tw_get.fields("2025-04-09", **kwargs)
        assert journal_entry["neuro.primary"] == "JOURNAL"

    def test_resolve_primary_complex(self, wf_qa):
        from neuro.tools.tw5api import tw_get, tw_put
        from neuro.tools.terminal.commands import qa
        tw_put.fields({"title": "MultiTag", "tags": ["Example", "JOURNAL"]}, **kwargs)
        qa_primary_result = qa.Primary(interactive=False, port=wf_qa.port, verbose=False).run()
        assert not qa_primary_result
        fields = tw_get.fields("MultiTag", **kwargs)
        assert "neuro.primary" not in fields

    def test_command_integrity(self, wf_qa):
        from neuro.tools.terminal.commands import qa
        from click.testing import CliRunner
        # noinspection PyTypeChecker
        res = CliRunner().invoke(qa.cli, ["--port", wf_qa.port], standalone_mode=False)
        assert res.exit_code == 0
        assert res.return_value is False


class TestTaxon:
    def test_taxon(self, wf):
        from neuro.tools.terminal.commands import taxon
        from neuro.tools.tw5api import tw_get
        from click.testing import CliRunner
        runner = CliRunner()
        # noinspection PyTypeChecker
        result = runner.invoke(taxon.cli, [f"--port={wf.port}", "-y", "Amata phegea"])
        assert result.exit_code == 0
        species_fields = tw_get.fields("Amata phegea", port=wf.port)
        order_fields = tw_get.fields("Lepidoptera", port=wf.port)
        tid_titles = tw_get.tid_titles("[!is[system]]", port=wf.port)
        assert species_fields["neuro.role"] == "taxon.species"
        assert order_fields["ncbi.txid"] == "7088"
        assert len(tid_titles) == 8
