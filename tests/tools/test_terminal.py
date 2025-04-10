from click.testing import CliRunner

from ..helper import create_and_run_wiki_folder


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
    def test_qa(self):
        from neuro.tools.terminal.commands import qa
        from neuro.tools.api import tw_get, tw_put, tw_del
        port = 8069
        process = create_and_run_wiki_folder("qa", port=port)
        runner = CliRunner()
        result = runner.invoke(qa.cli, [f"--port={port}"], env={"ENVIRONMENT": "Testing"})
        assert result.exit_code == 0

        example = tw_get.tiddler("example", port=port)
        assert example["size"] == "2000"

        # Removed ghost tiddlers
        tid_titles = tw_get.tid_titles("[search:title[Draft of ']!has[draft.of]]", port=port)
        assert len(tid_titles) == 0

        # Set model roles
        model = tw_get.tiddler(". Fundamentals", port=port)
        assert model["neuro.role"] == "model"

        # Set journal
        journal_entry = tw_get.tiddler("2025-04-09", port=port)
        assert journal_entry["neuro.role"] == "journal"

        # Validate tags
        assert qa.validate_tags(port)
        tw_put.tiddler({"title": "untagged-tiddler"}, port=port)
        assert not qa.validate_tags(port)
        tw_del.tiddler("untagged-tiddler", port=port)
        assert qa.validate_tags(port)
        tw_put.tiddler({"title": "untagged-tiddler", "tags": "inexistent-tag"}, port=port)
        assert not qa.validate_tags(port)
        tw_del.tiddler("untagged-tiddler", port=port)
        assert qa.validate_tags(port)

        # Recognize missing tiddlers
        assert not qa.resolve_missing_tiddlers(port)
        tw_put.tiddler({"title": "missing-tiddler"}, port=port)
        assert qa.resolve_missing_tiddlers(port)
        tw_del.tiddler("missing-tiddler", port=port)
        assert not qa.resolve_missing_tiddlers(port)

        # Resolve neuro.primary
        journal_entry = tw_get.tiddler("2025-04-09", port=port)
        assert journal_entry["neuro.primary"] == "JOURNAL"
        tw_put.tiddler({"title": "multitag-tiddler", "tags": ["example", "JOURNAL"]}, port=port)
        qa_primary_result = qa.Primary(False, port, False).run()
        multitag_tiddler = tw_get.tiddler("multitag-tiddler", port=port)
        assert "neuro.primary" not in multitag_tiddler
        assert not qa_primary_result
        tw_del.tiddler("multitag-tiddler", port=port)
        qa_primary_result = qa.Primary(False, port, False).run()
        assert qa_primary_result

        # Resolve neuro.id
        example = tw_get.tiddler("example", port=port)
        assert "neuro.id" in example
        assert example["neuro.id"][14] == "4"

        process.kill()
