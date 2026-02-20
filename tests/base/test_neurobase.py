"""
Integration tests for NeuroBase database availability.
"""

import pytest


@pytest.mark.integration
class TestNeuroBase:
    def test_connectivity(self, nb):
        nb.driver.verify_connectivity()

    def test_count_nodes(self, nb):
        count = nb.count()
        assert isinstance(count, int)
