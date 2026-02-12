"""
Unit tests for the module neuro.tools.migrate
"""


def test_migrate_html_to_wf(test_file):
    from neuro.tools import migrate
    input_legacy_html = test_file.get("input/wikis/tw5-legacy.html")
    input_html = test_file.get("input/wikis/tw5.html")
    output_wf_legacy = test_file.path("output/wf-migrate-legacy")
    output_wf = test_file.path("output/wf-migrate")
    migrate.migrate_html_to_wf(input_legacy_html, output_wf_legacy, port=8099)
    migrate.migrate_html_to_wf(input_html, output_wf, port=8099)
    assert test_file.get("output/wf-migrate-legacy/tiddlers/Test.tid")
    assert test_file.get("output/wf-migrate/tiddlers/Test-1.tid")

