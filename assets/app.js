/* Palau Bathymetry Viewer
 * Combines the five CRRF bathymetry maps into one Leaflet map and reports the depth (feet)
 * under the cursor. Depth comes from data/<id>.depth.png:
 *   R,G = depth in decimetres (16 bit), B = 0 no data / 1 depth / 2 deeper than figure scale.
 */
(() => {
  'use strict';
  const FT_PER_M = 3.28084;
  const fmt = (n) => Math.round(n).toLocaleString('en-US');

  const map = L.map('map', { zoomControl: false, preferCanvas: true, worldCopyJump: true });
  window.bathyMap = map; // handy for debugging from the console
  L.control.zoom({ position: 'topright' }).addTo(map);
  L.control.scale({ position: 'bottomright', imperial: true, metric: true }).addTo(map);

  const basemaps = {
    'Satellite': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 18, attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    }),
    'Ocean': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 13, attribution: '&copy; Esri, GEBCO, NOAA, Garmin',
    }),
    'Dark': L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19, subdomains: 'abcd', attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    }),
  };
  basemaps.Satellite.addTo(map);

  const $ = (id) => document.getElementById(id);
  const ro = { depth: $('ro-depth'), meta: $('ro-meta'), coords: $('ro-coords') };
  const tip = $('tip');
  const overlayGroup = L.layerGroup().addTo(map);
  L.control.layers(basemaps, { 'Bathymetry': overlayGroup }, { position: 'topright' }).addTo(map);
  map.attributionControl.addAttribution('Bathymetry &copy; <a href="https://www.coralreefpalau.org" target="_blank" rel="noopener">Coral Reef Research Foundation</a>');

  let areas = [];
  // keep fitted areas clear of the info panel (left on desktop, bottom on phones)
  const fitPad = () => {
    const r = $('panel').getBoundingClientRect();
    return window.innerWidth <= 640
      ? { paddingTopLeft: [20, 20], paddingBottomRight: [20, r.height + 24] }
      : { paddingTopLeft: [r.right + 20, 20], paddingBottomRight: [60, 20] };
  };

  fetch('data/manifest.json').then((r) => r.json()).then((manifest) => {
    areas = manifest.areas;
    drawLegend(manifest.ramp);
    const all = L.latLngBounds([]);
    const list = $('areas');
    const addButton = (label, bounds) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.onclick = () => map.flyToBounds(bounds, { ...fitPad(), duration: 1.2 });
      list.appendChild(b);
    };
    for (const a of areas) {
      a.llBounds = L.latLngBounds(a.bounds);
      all.extend(a.llBounds);
      a.overlay = L.imageOverlay(`data/${a.id}.webp`, a.llBounds, { opacity: 0.9, interactive: false }).addTo(overlayGroup);
    }
    addButton('All of Palau', all);
    for (const a of areas) addButton(a.name, a.llBounds);
    map.fitBounds(all, fitPad());
  });

  // ---- depth sampling -------------------------------------------------------
  async function loadDepth(a) {
    if (a.grid || a.loading) return a.loading;
    a.loading = (async () => {
      const blob = await (await fetch(`data/${a.id}.depth.png`)).blob();
      let src;
      try {
        src = await createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
      } catch {
        src = await new Promise((res, rej) => {
          const img = new Image(); img.onload = () => res(img); img.onerror = rej; img.src = URL.createObjectURL(blob);
        });
      }
      const c = document.createElement('canvas');
      c.width = a.width; c.height = a.height;
      const ctx = c.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(src, 0, 0);
      const px = ctx.getImageData(0, 0, a.width, a.height).data;
      const n = a.width * a.height;
      const dm = new Uint16Array(n), flag = new Uint8Array(n);
      for (let i = 0, j = 0; i < n; i++, j += 4) { dm[i] = (px[j] << 8) | px[j + 1]; flag[i] = px[j + 2]; }
      a.grid = { dm, flag };
    })();
    return a.loading;
  }

  function sample(latlng) {
    const p = L.CRS.EPSG3857.project(latlng);
    for (const a of areas) {
      if (!a.llBounds.contains(latlng)) continue;
      const [x0, y0, x1, y1] = a.mercBounds;
      const col = Math.floor((p.x - x0) / (x1 - x0) * a.width);
      const row = Math.floor((y1 - p.y) / (y1 - y0) * a.height);
      if (col < 0 || row < 0 || col >= a.width || row >= a.height) continue;
      if (!a.grid) { loadDepth(a).then(() => lastLatLng && update(lastLatLng)); return { area: a, loading: true }; }
      const i = row * a.width + col;
      const flag = a.grid.flag[i];
      if (flag === 0) continue;
      return { area: a, m: a.grid.dm[i] / 10, deeper: flag === 2 };
    }
    return null;
  }

  function describe(s) {
    const a = s.area;
    if (s.deeper) return { big: `> ${fmt(a.scaleMax_m * FT_PER_M)} ft`, small: `deeper than ${fmt(a.scaleMax_m)} m (edge of map scale)` };
    if (s.m < a.shallowLimit_m) return { big: `< ${fmt(a.shallowLimit_m * FT_PER_M)} ft`, small: `reef edge, too shallow to resolve at this map's scale` };
    return { big: `${fmt(s.m * FT_PER_M)} ft`, small: `${fmt(s.m)} m` };
  }

  const dms = (v, pos, neg) => {
    const h = v >= 0 ? pos : neg; v = Math.abs(v);
    const d = Math.floor(v), m = (v - d) * 60;
    return `${d}°${m.toFixed(3).padStart(6, '0')}′${h}`;
  };

  let lastLatLng = null, pending = false, lastPoint = null;
  function update(latlng, point) {
    lastLatLng = latlng; if (point) lastPoint = point;
    ro.coords.textContent = `${dms(latlng.lat, 'N', 'S')}  ${dms(latlng.lng, 'E', 'W')}`;
    const s = map.hasLayer(overlayGroup) ? sample(latlng) : null;
    if (!s) {
      ro.depth.textContent = '—'; ro.meta.textContent = 'No survey data here'; tip.hidden = true; return;
    }
    if (s.loading) { ro.depth.textContent = '…'; ro.meta.textContent = `Loading ${s.area.name}`; tip.hidden = true; return; }
    const d = describe(s);
    ro.depth.textContent = d.big;
    ro.meta.textContent = `${d.small} · ${s.area.name}`;
    tip.innerHTML = `${d.big} <small>${s.deeper || s.m < s.area.shallowLimit_m ? '' : d.small}</small>`;
    if (lastPoint) { tip.style.left = `${lastPoint.x}px`; tip.style.top = `${lastPoint.y}px`; }
    tip.hidden = false;
  }

  map.on('mousemove', (e) => {
    if (pending) return; pending = true;
    requestAnimationFrame(() => { pending = false; update(e.latlng, e.containerPoint); });
  });
  map.on('click', (e) => update(e.latlng, e.containerPoint)); // touch devices
  map.on('mouseout', () => { tip.hidden = true; });
  map.on('movestart', () => { tip.hidden = true; });

  // ---- controls ---------------------------------------------------------------
  $('opacity').addEventListener('input', (e) => {
    const v = e.target.value / 100;
    for (const a of areas) a.overlay && a.overlay.setOpacity(v);
  });
  $('toggle').addEventListener('change', (e) => {
    if (e.target.checked) overlayGroup.addTo(map); else map.removeLayer(overlayGroup);
  });
  map.on('overlayadd overlayremove', () => { $('toggle').checked = map.hasLayer(overlayGroup); });

  // ---- legend (same sqrt-scaled ramp used by tools/export.py) ------------------
  function drawLegend(ramp) {
    const cv = $('legend'), ctx = cv.getContext('2d');
    const max = ramp[ramp.length - 1].ft, sq = ramp.map((s) => Math.sqrt(s.ft));
    for (let x = 0; x < cv.width; x++) {
      const t = (x / (cv.width - 1)) * sq[sq.length - 1];
      let k = 0; while (k < sq.length - 2 && t > sq[k + 1]) k++;
      const f = (t - sq[k]) / (sq[k + 1] - sq[k]);
      const c = ramp[k].rgb.map((v, i) => Math.round(v + (ramp[k + 1].rgb[i] - v) * f));
      ctx.fillStyle = `rgb(${c})`; ctx.fillRect(x, 0, 1, cv.height);
    }
    const ticks = [0, 1000, 3000, 6000, max];
    $('legend-ticks').innerHTML = ticks.map((ft) =>
      `<span style="left:${(Math.sqrt(ft) / Math.sqrt(max)) * 100}%">${ft === max ? fmt(ft) + '+' : fmt(ft)}</span>`).join('');
  }
})();
