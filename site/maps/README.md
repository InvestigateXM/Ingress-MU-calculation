# Animation orientation maps

These small vector databases are drawn beneath the animation cells in the same
gnomonic projection. They are simplified orientation maps, not population data,
survey maps or navigation maps. Coordinates are kilometres on the tangent plane;
`center` and `view` match the corresponding trace. Polygon holes are omitted.

* [Map 1](a1.json), [map 2](a2.json), [map 3](a3.json):
  © OpenStreetMap contributors. These derivative databases are distributed under
  the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
  [Copyright and contributors](https://www.openstreetmap.org/copyright).
  Source: selected major roads, railways, water ways and named places from the
  [OpenStreetMap map API](https://wiki.openstreetmap.org/wiki/API_v0.6#Retrieving_map_data_by_bounding_box:_GET_/api/0.6/map).
  The `date` field records the source database timestamp, or the cached retrieval
  date when the API does not provide one. Source file hashes are in [sources.json](sources.json).
* [Map 4](a4.json), [map 5](a5.json): Natural Earth 1:10m, public domain.
  [Terms of use](https://www.naturalearthdata.com/about/terms-of-use/).
  Source ZIPs at `https://naturalearth.s3.amazonaws.com/10m_cultural/`:
  `ne_10m_urban_areas.zip`, `ne_10m_roads.zip`, `ne_10m_populated_places.zip`;
  and at `https://naturalearth.s3.amazonaws.com/10m_physical/`:
  `ne_10m_lakes.zip`, `ne_10m_rivers_lake_centerlines.zip`.

Regenerate after exporting the traces:

```sh
pip install pyshp shapely
python tools/extract_maps.py --cache /path/to/map-cache
python site/build.py
```

The script clips to each SVG viewport, joins connected line segments, omits
very small features, simplifies at viewport width / 400 and
rounds to metre precision. Place names come from the sources, with a small number
selected for legibility. It caches downloaded source files; keep that cache to
reproduce the extract. To refresh a source, remove its cached files first.
`--only osm` and `--only ne` can refresh the two sources independently.
The site build embeds the five JSON layers in the HTML: the browser makes no
additional map requests, and never contacts a map provider. Downloadable JSON
copies and this attribution file are also included in the static site.
