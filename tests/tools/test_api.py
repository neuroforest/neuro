"""
Unit tests for the package neuro.tools.api.
"""

import pytest

from neuro.tools.api import tw_get

from ..helper import PORT


class TestTwGet:
    @pytest.mark.integration
    def test_get_tiddler(self):
        tiddler = tw_get.tiddler("test", port=PORT)
        assert tiddler["title"] == "test"
