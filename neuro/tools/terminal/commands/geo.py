import json
import re
import subprocess
import urllib

import click
import requests
import tqdm

from neuro.tools.tw5api import tw_get, tw_put
from neuro.tools.terminal.cli import pass_environment


def geocode_url(short_url):
    if "https://goo.gl/maps/" in short_url:
        res = requests.get(short_url)
        long_url = urllib.parse.unquote(res.url)
        long_url = urllib.parse.unquote(long_url)
        pattern = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+))")
        try:
            lat, lon = pattern.findall(long_url)[0]
            lat, lon = float(lat), float(lon)
        except IndexError:
            return None, None
    elif "https://maps.app.goo.gl/" in short_url:
        p = subprocess.Popen([
            "curl",
            "-Ls",
            "-o /dev/null",
            "-w %{url_effective}",
            short_url
        ], stdout=subprocess.PIPE, text=True)
        long_url = p.communicate()[0]
        pattern = r"/search/([-+]?\d*\.\d+|\d+),([-+]?\d*\.\d+|\d+)"
        match = re.search(pattern, long_url)

        if match:
            return float(match.group(1)), float(match.group(2))
        else:
            return None, None
    else:
        return None, None

    return lat, lon


def extract_url_data(mode="default"):
    if mode == "default":
        tw_filter = "[has[gmaps]!has[g.lat]!has[g.lng]]"
    elif mode == "all":
        tw_filter = "[has[gmaps]]"
    else:
        print(f"Mode '{mode}' not supported.")
        return

    failed = list()
    fields_list = tw_get.tw_fields(["gmaps", "title"], tw_filter)
    for fields in tqdm.tqdm(fields_list):
        tid_title = fields["title"]
        short_url = fields["gmaps"]
        lat, lon = geocode_url(short_url)
        if not lat or not lon:
            failed.append(tid_title)
        else:
            neuro_tid = tw_get.neuro_tid(tid_title)
            neuro_tid.fields["g.lat"], neuro_tid.fields["g.lon"] = lat, lon
            tw_put.neuro_tid(neuro_tid)

    print(f"Geocoding failed for: {failed}")


def export_geo_data(export_path):
    """
    Export latitude and longitude data combinations from NeuroWiki as JSON.
    """
    lod = tw_get.tw_fields(["g.lat", "g.lon", "title"], "[has[g.lat]has[g.lon]]")

    key_mapping = {"g.lat": "lat", "g.lon": "lng"}
    lod = [{key_mapping.get(key, key): value for key, value in item.items()} for item in lod]

    with open(export_path, "w") as f:
        json.dump(lod, f)


@click.command("geo", short_help="access tools for geospatial data")
@click.option("-c", "--convert", nargs=1)
@click.option("-e", "--export", nargs=1, type=click.Path(exists=False, resolve_path=True, writable=True))
@click.option("-g", "--geocode", is_flag=True)
@click.option("-a", "--geocode_all", is_flag=True)
@pass_environment
def cli(ctx, convert, export, geocode, geocode_all):
    if convert:
        click.echo(geocode_url(convert))
        return

    if geocode:
        extract_url_data()
    elif geocode_all:
        extract_url_data(mode="all")

    if export:
        export_geo_data(export)

