// ==UserScript==
// @id             iitc-plugin-triangle-mu@local
// @name           IITC plugin: Triangle MU
// @category       Info
// @version        0.1.1
// @namespace      https://github.com/InvestigateXM/Ingress-MU-Calculation
// @description    Reports the Mind Units (MU) of triangles drawn with Draw Tools, using the Ingress-MU-Calculation API.
// @include        https://intel.ingress.com/*
// @include        https://intel-x.ingress.com/*
// @match          https://intel.ingress.com/*
// @match          https://intel-x.ingress.com/*
// @grant          none
// ==/UserScript==

function wrapper(plugin_info) {
  if (typeof window.plugin !== 'function') window.plugin = function () {};

  plugin_info.buildName = 'local';
  plugin_info.dateTimeVersion = '20261117000000';
  plugin_info.pluginId = 'triangle-mu';

  var STORAGE_KEY = 'plugin-triangle-mu-api';
  var DEFAULT_API = 'https://api.investigatexm.com';
  var TIMEOUT_MS = 25000;
  var BULK_LIMIT = 50; // API accepts 1-50 fields per bulk request

  window.plugin.triangleMU = function () {};
  var self = window.plugin.triangleMU;
  self.labelLayer = null;

  // ---------- settings ----------

  self.normalizeApi = function (url) {
    url = String(url || '').trim().replace(/\/+$/, '');
    return /^https?:\/\/\S+$/i.test(url) ? url : null;
  };

  self.getApi = function () {
    try {
      return self.normalizeApi(localStorage.getItem(STORAGE_KEY)) || DEFAULT_API;
    } catch (e) {
      return DEFAULT_API;
    }
  };

  self.setApi = function (url) {
    var clean = self.normalizeApi(url);
    if (!clean) return false;
    try { localStorage.setItem(STORAGE_KEY, clean); } catch (e) { /* ignore */ }
    return true;
  };

  // ---------- helpers ----------

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function flatten(latlngs) {
    // Leaflet 0.7 returns a flat array; Leaflet 1.x returns nested rings.
    while (latlngs.length && Array.isArray(latlngs[0])) latlngs = latlngs[0];
    return latlngs.slice();
  }

  function fmtCoord(ll) {
    return ll.lat.toFixed(6) + ',' + ll.lng.toFixed(6);
  }

  // ---------- collecting triangles ----------

  self.collectTriangles = function () {
    var dt = window.plugin.drawTools;
    var triangles = [];
    var skipped = 0;

    dt.drawnItems.eachLayer(function (layer) {
      if (!(layer instanceof L.Polygon) || layer instanceof L.Rectangle) return;
      var pts = flatten(layer.getLatLngs());
      if (pts.length > 1 && pts[0].lat === pts[pts.length - 1].lat && pts[0].lng === pts[pts.length - 1].lng) {
        pts.pop(); // drop a duplicated closing vertex
      }
      if (pts.length !== 3) { skipped++; return; }
      triangles.push({ layer: layer, points: pts });
    });

    return { triangles: triangles, skipped: skipped };
  };

  // ---------- API ----------

  self.requestMU = function (triangles) {
    var fields = triangles.map(function (t, i) {
      return { id: 't' + i, coordinates: t.points.map(fmtCoord) };
    });

    var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, TIMEOUT_MS) : null;

    return fetch(self.getApi() + '/getMUbulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields: fields }),
      signal: controller ? controller.signal : undefined
    }).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (body) {
        if (!resp.ok) throw new Error(body.error || ('HTTP ' + resp.status));
        if (!body.results) throw new Error('Unexpected response from the MU API.');
        return body;
      });
    }).then(function (body) {
      if (timer) clearTimeout(timer);
      return body;
    }, function (err) {
      if (timer) clearTimeout(timer);
      if (err && err.name === 'AbortError') throw new Error('The MU API did not answer within ' + (TIMEOUT_MS / 1000) + ' s.');
      throw err;
    });
  };

  // ---------- map labels ----------

  self.clearLabels = function () {
    if (self.labelLayer) self.labelLayer.clearLayers();
  };

  self.addLabel = function (triangle, text) {
    var pts = triangle.points;
    var lat = (pts[0].lat + pts[1].lat + pts[2].lat) / 3;
    var lng = (pts[0].lng + pts[1].lng + pts[2].lng) / 3;
    var icon = L.divIcon({
      className: 'plugin-triangle-mu-label',
      html: '<span>' + esc(text) + '</span>',
      iconSize: [100, 20],
      iconAnchor: [50, 10]
    });
    self.labelLayer.addLayer(L.marker([lat, lng], { icon: icon, clickable: false, keyboard: false }));
  };

  // ---------- UI ----------

  function showDialog(html, buttons) {
    window.dialog({
      id: 'plugin-triangle-mu',
      title: 'Triangle MU',
      html: html,
      width: 520,
      buttons: buttons || {},
      closeCallback: function () { self.clearLabels(); }
    });
  }

  function dialogButtons() {
    return {
      'Recalculate': function () { self.run(); },
      'Set API URL': function () {
        var v = window.prompt(
          'MU API base URL (e.g. http://localhost:8000 for a self-hosted container):',
          self.getApi()
        );
        if (v === null) return;
        if (!self.setApi(v)) {
          window.alert('Please enter a valid http(s) URL.');
          return;
        }
        self.run();
      }
    };
  }

  self.run = function () {
    if (!window.plugin.drawTools || !window.plugin.drawTools.drawnItems) {
      showDialog('<p>The <b>Draw Tools</b> plugin is required. Enable it and draw a triangle (a polygon with exactly 3 vertices).</p>');
      return;
    }

    var found = self.collectTriangles();
    var triangles = found.triangles;

    if (!triangles.length) {
      var msg = '<p>No triangle found. Draw a polygon with exactly <b>3 vertices</b> using Draw Tools.</p>';
      if (found.skipped) msg += '<p>' + found.skipped + ' drawn polygon(s) ignored because they do not have 3 vertices.</p>';
      showDialog(msg, dialogButtons());
      return;
    }

    var batch = triangles.slice(0, BULK_LIMIT);
    var overflow = triangles.length - batch.length;

    showDialog('<p>Calculating MU for ' + batch.length + ' triangle(s)&hellip;</p>');

    self.requestMU(batch).then(function (body) {
      self.clearLabels();

      var rows = '';
      body.results.forEach(function (r, i) {
        var t = batch[i];
        var verts = t.points.map(function (p) { return esc(fmtCoord(p)); }).join('<br>');
        if (r.ok) {
          self.addLabel(t, r.mu.toLocaleString() + ' MU');
          rows += '<tr><td>' + (i + 1) + '</td>' +
            '<td class="mu"><b>' + r.mu.toLocaleString() + '</b></td>' +
            '<td>' + Number(r.area_km2).toLocaleString(undefined, { maximumFractionDigits: 3 }) + '</td>' +
            '<td class="v">' + verts + '</td></tr>';
        } else {
          rows += '<tr><td>' + (i + 1) + '</td><td colspan="2" class="err">' + esc(r.error || 'Failed') + '</td>' +
            '<td class="v">' + verts + '</td></tr>';
        }
      });

      var html = '<table class="plugin-triangle-mu-table">' +
        '<thead><tr><th>#</th><th>MU</th><th>km&sup2;</th><th>Vertices (lat,lng)</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>';
      if (overflow > 0) html += '<p>Only the first ' + BULK_LIMIT + ' triangles were calculated; ' + overflow + ' more were skipped.</p>';
      if (found.skipped) html += '<p>' + found.skipped + ' drawn polygon(s) ignored (not 3 vertices).</p>';
      html += '<p class="note">API: ' + esc(self.getApi()) + '<br>Model: ' + esc(body.model || 'unknown') + '</p>';

      showDialog(html, dialogButtons());
    }).catch(function (err) {
      showDialog('<p class="plugin-triangle-mu-error">Could not get MU: ' + esc(err && err.message ? err.message : err) +
        '</p><p class="note">API: ' + esc(self.getApi()) + '</p>', dialogButtons());
    });
  };

  // ---------- setup ----------

  var setup = function () {
    $('<style>').prop('type', 'text/css').html(
      '.plugin-triangle-mu-label{pointer-events:none;text-align:center;}' +
      '.plugin-triangle-mu-label span{display:inline-block;padding:1px 6px;border-radius:3px;' +
      'background:rgba(0,0,0,.75);color:#ffce00;border:1px solid #ffce00;font-size:12px;white-space:nowrap;}' +
      '.plugin-triangle-mu-table{width:100%;border-collapse:collapse;}' +
      '.plugin-triangle-mu-table th,.plugin-triangle-mu-table td{padding:3px 6px;text-align:left;vertical-align:top;' +
      'border-bottom:1px solid #20A8B1;}' +
      '.plugin-triangle-mu-table td.mu{font-size:15px;color:#ffce00;}' +
      '.plugin-triangle-mu-table td.v{font-family:monospace;font-size:11px;}' +
      '.plugin-triangle-mu-table td.err,.plugin-triangle-mu-error{color:#ff6666;}' +
      '#dialog-plugin-triangle-mu .note{opacity:.7;font-size:11px;}'
    ).appendTo('head');

    self.labelLayer = new L.LayerGroup();
    window.addLayerGroup('Triangle MU labels', self.labelLayer, true);

    $('#toolbox').append(
      '<a id="plugin-triangle-mu-link" onclick="window.plugin.triangleMU.run();return false;" ' +
      'title="Calculate Mind Units for triangles drawn with Draw Tools">Triangle MU</a>'
    );
  };

  setup.info = plugin_info;
  if (!window.bootPlugins) window.bootPlugins = [];
  window.bootPlugins.push(setup);
  if (window.iitcLoaded && typeof setup === 'function') setup();
}

var script = document.createElement('script');
var info = {};
if (typeof GM_info !== 'undefined' && GM_info && GM_info.script) {
  info.script = {
    version: GM_info.script.version,
    name: GM_info.script.name,
    description: GM_info.script.description
  };
}
script.appendChild(document.createTextNode('(' + wrapper + ')(' + JSON.stringify(info) + ');'));
(document.body || document.head || document.documentElement).appendChild(script);

