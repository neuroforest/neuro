"""
Unit tests for the package .
"""

from ..helper import get_test_file


class Test:
    def test_migrate_html_to_wf(self):
        from neuro.tools import migrate
        input_legacy_html = get_test_file("input/wikis/tw5-legacy.html")
        input_html = get_test_file("input/wikis/tw5.html")
        output_wf_legacy = get_test_file("output/wf-migrate-legacy", exists=False)
        output_wf = get_test_file("output/wf-migrate", exists=False)
        migrate.migrate_html_to_wf(input_legacy_html, output_wf_legacy, port=8099)
        migrate.migrate_html_to_wf(input_html, output_wf, port=8099)
        assert get_test_file("output/wf-migrate-legacy/tiddlers/Test.tid", exists=True)
        assert get_test_file("output/wf-migrate/tiddlers/Test-1.tid", exists=True)

