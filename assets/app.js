/* Palau Bathymetry Viewer
 * Shows the Coral Reef Research Foundation's outer-reef bathymetry tile services (ArcGIS Online) as one
 * map and reports the depth (feet) under the cursor. Depth comes from data/<section>.depth.png on the
 * global zoom-13 Web Mercator pixel grid: R*256+G = metres, B = flag (see tools/tiles/build_data.py).
 */
(() => {
  'use strict';
  const FT = 3.28084;
  const fmt = (n) => Math.round(n).toLocaleString('en-US');
  const $ = (id) => document.getElementById(id);

  const map = L.map('map', { zoomControl: false, worldCopyJump: true, maxZoom: 19 });
  window.bathyMap = map; // handy for debugging from the console
  L.control.zoom({ position: 'topright' }).addTo(map);
  L.control.scale({ position: 'bottomright' }).addTo(map);

  const basemaps = {
    'Satellite': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19, maxNativeZoom: 18, attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    }),
    'Ocean': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19, maxNativeZoom: 13, attribution: '&copy; Esri, GEBCO, NOAA, Garmin',
    }),
    'Dark': L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19, subdomains: 'abcd', attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    }),
  };
  basemaps.Satellite.addTo(map);
  const bathy = L.layerGroup().addTo(map);
  L.control.layers(basemaps, { 'Bathymetry': bathy }, { position: 'topright' }).addTo(map);
  map.attributionControl.addAttribution(
    'Bathymetry &copy; 2026 <a href="https://www.coralreefpalau.org" target="_blank" rel="noopener">Coral Reef Research Foundation</a>');

  const ro = { depth: $('ro-depth'), meta: $('ro-meta'), coords: $('ro-coords') };
  const tip = $('tip');
  let areas = [], Z = 13, ramp = [], activeLegend = null;

  const fitPad = () => {
    const r = $('panel').getBoundingClientRect();
    return window.innerWidth <= 640
      ? { paddingTopLeft: [20, 20], paddingBottomRight: [20, r.height + 24] }
      : { paddingTopLeft: [r.right + 20, 20], paddingBottomRight: [60, 20] };
  };

  fetch('data/manifest.json').then((r) => r.json()).then((m) => {
    areas = m.areas; Z = m.zoom; ramp = m.ramp;
    const all = L.latLngBounds([]);
    const groups = {};
    for (const a of areas) {
      a.llBounds = L.latLngBounds(a.bounds);
      all.extend(a.llBounds);
      (groups[a.group] = groups[a.group] || []).push(a);
    }
    // where sections overlap, draw the narrower colour stretches underneath so the
    // common 0-2,000 m stretch stays consistent on top
    [...areas].sort((p, q) => p.scaleMax_m - q.scaleMax_m).forEach((a, i) => {
      a.layer = L.tileLayer(a.tiles, {
        bounds: a.llBounds.pad(0.02), maxNativeZoom: a.maxNativeZoom, maxZoom: 19, opacity: 0.9, zIndex: 10 + i,
      }).addTo(bathy);
    });
    const box = $('areas');
    const chip = (label, bounds, parent) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.onclick = () => map.flyToBounds(bounds, { ...fitPad(), duration: 1.2 });
      parent.appendChild(b);
    };
    const top = document.createElement('div'); top.className = 'chips'; box.appendChild(top);
    chip('All of Palau', all, top);
    for (const [g, list] of Object.entries(groups)) {
      const h = document.createElement('h3'); h.textContent = g; box.appendChild(h);
      const row = document.createElement('div'); row.className = 'chips'; box.appendChild(row);
      const gb = L.latLngBounds([]); list.forEach((a) => gb.extend(a.llBounds));
      if (list.length > 1) chip(`All ${g.toLowerCase()}`, gb, row);
      for (const a of list) chip(a.name, a.llBounds, row);
    }
    drawRampBar();
    setLegend(areas.find((a) => a.scaleMax_m === 2000) || areas[0]);
    map.fitBounds(all, fitPad());
  });

  // ---- depth grids (loaded per section on first hover) -------------------------
  function loadGrid(a) {
    if (!a.loading) a.loading = (async () => {
      const blob = await (await fetch(`data/${a.id}.depth.png`)).blob();
      let src;
      try { src = await createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' }); }
      catch { src = await new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = bad; i.src = URL.createObjectURL(blob); }); }
      const c = document.createElement('canvas'); c.width = a.width; c.height = a.height;
      const ctx = c.getContext('2d', { willReadFrequently: true }); ctx.drawImage(src, 0, 0);
      const px = ctx.getImageData(0, 0, a.width, a.height).data, n = a.width * a.height;
      const m = new Uint16Array(n), f = new Uint8Array(n);
      for (let i = 0, j = 0; i < n; i++, j += 4) { m[i] = (px[j] << 8) | px[j + 1]; f[i] = px[j + 2]; }
      a.grid = { m, f };
    })();
    return a.loading;
  }

  // sections overlap at their edges: prefer a direct tile reading, then a reef-top limit,
  // then a report-figure value, then the deepest "deeper than" limit
  const RANK = { 1: 4, 4: 3, 3: 2, 2: 1 };
  function sample(latlng) {
    const p = map.project(latlng, Z);
    let best = null, pending = null;
    for (const a of areas) {
      const col = Math.floor(p.x) - a.x0, row = Math.floor(p.y) - a.y0;
      if (col < 0 || row < 0 || col >= a.width || row >= a.height) continue;
      if (!a.grid) { pending = pending || a; loadGrid(a).then(() => last && update(last.latlng, last.point)); continue; }
      const i = row * a.width + col, flag = a.grid.f[i];
      if (!flag) continue;
      const c = { area: a, m: a.grid.m[i], flag };
      if (!best || RANK[flag] > RANK[best.flag] || (flag === 2 && best.flag === 2 && c.m > best.m)) best = c;
    }
    if (pending && (!best || best.flag !== 1)) return { area: pending, loading: true };
    return best;
  }

  function describe(s) {
    const ft = fmt(s.m * FT), m = fmt(s.m);
    switch (s.flag) {
      case 2: return { big: `> ${ft} ft`, small: `deeper than ${m} m (beyond the map's colour scale)`, tip: `> ${ft} ft` };
      case 3: return { big: `${ft} ft`, small: `${m} m · from the 2025 report figure (less precise)`, tip: `${ft} ft <small>${m} m</small>` };
      case 4: return { big: `< ${ft} ft`, small: `shallower than ${m} m (reef top)`, tip: `< ${ft} ft` };
      default: return { big: `${ft} ft`, small: `${m} m`, tip: `${ft} ft <small>${m} m</small>` };
    }
  }

  const dms = (v, pos, neg) => {
    const h = v >= 0 ? pos : neg; v = Math.abs(v);
    const d = Math.floor(v), mm = (v - d) * 60;
    return `${d}°${mm.toFixed(3).padStart(6, '0')}′${h}`;
  };

  let last = null, raf = false;
  function update(latlng, point) {
    last = { latlng, point: point || (last && last.point) };
    ro.coords.textContent = `${dms(latlng.lat, 'N', 'S')}  ${dms(latlng.lng, 'E', 'W')}`;
    const s = map.hasLayer(bathy) ? sample(latlng) : null;
    if (!s) { ro.depth.textContent = '—'; ro.meta.textContent = 'No survey data here'; tip.hidden = true; return; }
    setLegend(s.area);
    if (s.loading) { ro.depth.textContent = '…'; ro.meta.textContent = `Loading ${s.area.name}`; tip.hidden = true; return; }
    const d = describe(s);
    ro.depth.textContent = d.big;
    ro.meta.textContent = `${d.small} · ${s.area.name}`;
    tip.innerHTML = d.tip;
    if (last.point) { tip.style.left = `${last.point.x}px`; tip.style.top = `${last.point.y}px`; }
    tip.hidden = false;
  }

  map.on('mousemove', (e) => {
    if (raf) return; raf = true;
    requestAnimationFrame(() => { raf = false; update(e.latlng, e.containerPoint); });
  });
  map.on('click', (e) => update(e.latlng, e.containerPoint)); // touch devices
  map.on('mouseout movestart', () => { tip.hidden = true; });

  $('opacity').addEventListener('input', (e) => areas.forEach((a) => a.layer.setOpacity(e.target.value / 100)));
  $('toggle').addEventListener('change', (e) => { if (e.target.checked) bathy.addTo(map); else map.removeLayer(bathy); });
  map.on('overlayadd overlayremove', () => { $('toggle').checked = map.hasLayer(bathy); });

  // ---- legend: CRRF's colour ramp, labelled for the section under the cursor ---------
  function drawRampBar() {
    const cv = $('legend'), ctx = cv.getContext('2d');
    for (let x = 0; x < cv.width; x++) {
      const t = (x / (cv.width - 1)) * (ramp.length - 1), k = Math.min(Math.floor(t), ramp.length - 2), f = t - k;
      const c = ramp[k].map((v, i) => Math.round(v + (ramp[k + 1][i] - v) * f));
      ctx.fillStyle = `rgb(${c})`; ctx.fillRect(x, 0, 1, cv.height);
    }
  }
  function setLegend(a) {
    if (!a || activeLegend === a) return;
    activeLegend = a;
    const lo = a.scaleMin_m, hi = a.scaleMax_m;
    $('legend-title').textContent = `Depth (feet) · ${a.name}`;
    $('legend-ticks').innerHTML = [0, 0.25, 0.5, 0.75, 1].map((t) => {
      const ft = (lo + t * (hi - lo)) * FT;
      const label = t === 0 ? `< ${fmt(ft)}` : t === 1 ? `> ${fmt(ft)}` : fmt(Math.round(ft / 50) * 50);
      return `<span style="left:${t * 100}%">${label}</span>`;
    }).join('');
  }
})();
