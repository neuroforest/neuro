class TestGeo:
    def test_geocode(self):
        from neuro.tools.terminal.commands import geo
        test_data = [
            ("https://maps.app.goo.gl/6tKogiW9Xog87owx5", (61.213906, 78.942735)),
            ("https://goo.gl/maps/k9tRoWb6Fs2eDvJy6", (45.6227285, 23.3104755))
        ]
        for url, coordinates in test_data:
            assert geo.geocode_url(url) == coordinates
