"""Extract small orientation maps; no population rasters needed.

Install optional extraction dependencies: pip install pyshp shapely
Run after exporting traces: python tools/extract_maps.py --cache /path/to/cache
Downloads are cached. Delete a cached source to refresh it. OSM data changes over
time, so retain the cache to reproduce a particular extract. Outputs are separate
ODbL (OSM) and public-domain (Natural Earth) databases; see site/maps/README.md.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import shapefile
from shapely.geometry import shape, box, LineString, Polygon
from shapely.ops import transform, linemerge

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anim.common import Proj, Ortho, RE, ROOT  # noqa: E402

NE = {
    'urban': ('cultural', 'urban_areas'),
    'water': ('physical', 'lakes'),
    'river': ('physical', 'rivers_lake_centerlines'),
    'road': ('cultural', 'roads'),
    'place': ('cultural', 'populated_places'),
}


def download(cache, name, url, data=None):
    path = cache / name
    if not path.exists():
        request = urllib.request.Request(url, data=data, headers={
            'User-Agent': 'MU-calculator-static-map-extract/1.0'})
        with urllib.request.urlopen(request, timeout=45) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def bounds(tr):
    p = Proj(*tr['center'])
    x, y, w, h = tr['view']
    points = []
    for xx in (x, x+w):
        for yy in (y, y+h):
            v = p.c + xx / RE * p.e - yy / RE * p.n
            v /= np.linalg.norm(v)
            points.append((math.degrees(math.atan2(v[1], v[0])), math.degrees(math.asin(v[2]))))
    return [min(a for a, b in points), min(b for a, b in points),
            max(a for a, b in points), max(b for a, b in points)]


def osm(cache, bbox):
    w, s, e, n = bbox
    # Small API tiles avoid the API's node-count limit. Only selected features
    # are retained. Complete ways include their referenced nodes outside a tile.
    nx, ny = math.ceil((e-w)/.03), math.ceil((n-s)/.02)
    nodes, ways, dates, retrieved = {}, {}, [], []
    for ix in range(nx):
        for iy in range(ny):
            bb = [w+(e-w)*ix/nx, s+(n-s)*iy/ny, w+(e-w)*(ix+1)/nx, s+(n-s)*(iy+1)/ny]
            key = ','.join(f'{v:.6f}' for v in bb)
            raw = download(cache, 'osm-'+key+'.xml', 'https://api.openstreetmap.org/api/0.6/map?bbox='+key)
            retrieved.append((cache / ('osm-'+key+'.xml')).stat().st_mtime)
            tree = ET.fromstring(raw)
            meta = tree.find('meta')
            if meta is not None: dates.append(meta.get('osm_base', ''))
            for node in tree.findall('node'):
                nodes[node.get('id')] = dict(type='node', lon=float(node.get('lon')), lat=float(node.get('lat')),
                    tags={t.get('k'): t.get('v') for t in node.findall('tag')})
            for way in tree.findall('way'): ways[way.get('id')] = way
    elements = [node for node in nodes.values() if node['tags'].get('place') in ('town', 'village', 'suburb', 'neighbourhood') and 'name' in node['tags']]
    for way in ways.values():
        tags = {t.get('k'): t.get('v') for t in way.findall('tag')}
        if (tags.get('highway', '').removesuffix('_link') in ('motorway', 'trunk', 'primary', 'secondary')
            or tags.get('railway') == 'rail' or tags.get('natural') == 'water'
            or tags.get('waterway') in ('river', 'canal', 'stream')):
            refs = [node.get('ref') for node in way.findall('nd')]
            if all(ref in nodes for ref in refs):
                elements.append(dict(type='way', tags=tags, geometry=[nodes[ref] for ref in refs]))
    date = max(dates, default='') or datetime.fromtimestamp(max(retrieved), timezone.utc).strftime('%Y-%m-%d')
    data = dict(elements=elements, osm3s=dict(timestamp_osm_base=date))
    features, places = [], []
    for item in data['elements']:
        t = item.get('tags', {})
        if item['type'] == 'node':
            places.append((t['name'], item['lon'], item['lat']))
        elif 'geometry' in item:
            points = [(p['lon'], p['lat']) for p in item['geometry']]
            kind = 'water' if t.get('natural') == 'water' else 'river' if 'waterway' in t else 'rail' if 'railway' in t else 'road'
            if len(points) >= 2:
                geom = Polygon(points) if kind == 'water' and points[0] == points[-1] and len(points) >= 4 else LineString(points)
                if geom.is_valid: features.append((kind, geom))
    return features, places, data.get('osm3s', {}).get('timestamp_osm_base', '')


def natural_earth(cache):
    features, places = [], []
    for kind, (category, name) in NE.items():
        stem = 'ne_10m_' + name
        url = f'https://naturalearth.s3.amazonaws.com/10m_{category}/{stem}.zip'
        archive = zipfile.ZipFile(io.BytesIO(download(cache, stem+'.zip', url)))
        reader = shapefile.Reader(shp=io.BytesIO(archive.read(stem+'.shp')),
                                  shx=io.BytesIO(archive.read(stem+'.shx')),
                                  dbf=io.BytesIO(archive.read(stem+'.dbf')))
        for record in reader.iterShapeRecords():
            geom = shape(record.shape.__geo_interface__)
            if kind == 'place':
                places.append((record.record.as_dict()['NAME'], geom.x, geom.y))
            else:
                features.append((kind, geom))
                if kind == 'water':
                    name = record.record.as_dict().get('name', '')
                    if name in ('Lake Mead', 'Starnberger See', 'Ammersee'):
                        point = geom.representative_point()
                        places.append((name, point.x, point.y))
    return features, places


def extract(tr, features, places, source, date=''):
    p = Proj(*tr['center'])
    x, y, w, h = tr['view']; clip = box(x, y, x+w, y+h)
    geo_clip = box(*bounds(tr))
    def project(lon, lat, z=None):
        # Shapely accepts scalar and vector calls.
        if hasattr(lon, '__iter__'):
            xy = [p.ll(b, a) for a, b in zip(lon, lat)]
            return [v[0] for v in xy], [v[1] for v in xy]
        return p.ll(lat, lon)
    out = []
    def emit(kind, g):
        if g.is_empty: return
        if g.geom_type in ('Polygon', 'LineString'):
            coords = list(g.exterior.coords) if g.geom_type == 'Polygon' else list(g.coords)
            if len(coords) >= 2:
                out.append([kind, [[round(a, 3), round(b, 3)] for a, b in coords], g.geom_type == 'Polygon'])
        elif hasattr(g, 'geoms'):
            for child in g.geoms: emit(kind, child)
    lines = {}
    def collect_lines(g, result):
        if g.is_empty: return
        if g.geom_type == 'LineString': result.append(g)
        elif hasattr(g, 'geoms'):
            for part in g.geoms: collect_lines(part, result)
    for kind, geom in features:
        if not geom.is_valid or not geom.intersects(geo_clip): continue
        g = transform(project, geom.intersection(geo_clip)).intersection(clip)
        if kind in ('road', 'rail', 'river'):
            collect_lines(g, lines.setdefault(kind, []))
        elif g.area > w*w/50000:
            emit(kind, g.simplify(w / 400, preserve_topology=True))
    for kind, parts in lines.items():
        if not parts: continue
        merged = linemerge(parts)
        for g in getattr(merged, 'geoms', [merged]):
            if g.length >= w/70:
                emit(kind, g.simplify(w/400, preserve_topology=True))
    labels = []
    for name, lon, lat in sorted(places, key=lambda p: (p[0] not in ('Las Vegas', 'Munich', 'Lake Mead'), p[0])):
        xx, yy = p.ll(lat, lon)
        if x+w*.08 < xx < x+w*.92 and y+h*.1 < yy < y+h*.9:
            if all(math.hypot(xx-a, yy-b) > w*.18 for _, a, b in labels):
                labels.append([name, xx, yy])
    return dict(source=source, date=date, center=tr['center'], view=tr['view'],
                features=out, labels=labels[:5])


def globe(cache, tr, scale='110m', tol=20.0):
    """Orientation map for a globe trace (Ortho projection): sea disc, land, one label."""
    p = Ortho(*tr['center'])
    stem = f'ne_{scale}_land'
    url = f'https://naturalearth.s3.amazonaws.com/{scale}_physical/{stem}.zip'
    archive = zipfile.ZipFile(io.BytesIO(download(cache, stem+'.zip', url)))
    reader = shapefile.Reader(shp=io.BytesIO(archive.read(stem+'.shp')),
                              shx=io.BytesIO(archive.read(stem+'.shx')),
                              dbf=io.BytesIO(archive.read(stem+'.dbf')))
    disc = Polygon([(RE * math.cos(a), RE * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 181)[:-1]])
    out = [['water', [[round(a), round(b)] for a, b in disc.exterior.coords], True]]
    def emit(g):
        if g.is_empty: return
        if g.geom_type == 'Polygon':
            if g.area > 4e4:
                out.append(['urban', [[round(a), round(b)] for a, b in g.exterior.coords], True])
        elif hasattr(g, 'geoms'):
            for child in g.geoms: emit(child)
    for record in reader.iterShapeRecords():
        geom = shape(record.shape.__geo_interface__).segmentize(1.0)
        for part in getattr(geom, 'geoms', [geom]):
            ring = [p.ll(lat, lon, 3) for lon, lat in part.exterior.coords]  # behind -> horizon
            g = Polygon(ring).buffer(0).intersection(disc)
            emit(g.simplify(tol, preserve_topology=True))
    xx, yy = p.ll(34.0, -42.0)  # Munich is labelled by the trace itself, at every zoom
    return dict(source=f'Natural Earth 1:{scale[:-1]}m / public domain', date='', center=tr['center'], view=tr['view'],
                features=out, labels=[['Atlantic Ocean', xx, yy]])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--only', choices=['osm', 'ne', 'all'], default='all')
    ap.add_argument('--globe', action='store_true', help='only write the globe map site/maps/a6w.json')
    args = ap.parse_args(); args.cache.mkdir(parents=True, exist_ok=True)
    if args.globe:
        tr = json.loads((ROOT/'site'/'traces'/'a6w.json').read_text(encoding='utf-8'))
        text = json.dumps(globe(args.cache, tr), ensure_ascii=False, separators=(',', ':'))+'\n'
        (ROOT/'site'/'maps'/'a6w.json').write_text(text, encoding='utf-8', newline='\n')
        print('a6w', len(text.encode()), 'bytes')
        return
    traces = [json.loads((ROOT/'site'/'traces'/f'a{i}.json').read_text(encoding='utf-8')) for i in range(1, 6)]
    bb = [bounds(t) for t in traces[:3]]
    osm_features, osm_places, date = osm(args.cache, [min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb)]) if args.only != 'ne' else ([], [], '')
    ne_features, ne_places = natural_earth(args.cache) if args.only != 'osm' else ([], [])
    out = ROOT/'site'/'maps'; out.mkdir(exist_ok=True)
    for i, tr in enumerate(traces):
        if (i < 3 and args.only == 'ne') or (i >= 3 and args.only == 'osm'): continue
        data = extract(tr, osm_features if i < 3 else ne_features, osm_places if i < 3 else ne_places,
                       'OpenStreetMap / ODbL-1.0' if i < 3 else 'Natural Earth 1:10m / public domain', date if i < 3 else '')
        text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))+'\n'
        (out/(tr['id']+'.json')).write_text(text, encoding='utf-8', newline='\n')
        print(tr['id'], len(text.encode()), 'bytes;', len(data['features']), 'features;', data['labels'])
    sources = sorted(list(args.cache.glob('ne_10m_*.zip')) + list(args.cache.glob('osm-*.xml')))
    (out/'sources.json').write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}, indent=2)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__': main()
