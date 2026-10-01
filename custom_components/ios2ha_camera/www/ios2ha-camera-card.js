/*
 * ios2ha-camera card: everything the camera does, on one card.
 *
 * It talks only to Home Assistant -- entity states, the integration's actions, and
 * the media source for timelapses -- so it works wherever Home Assistant does,
 * including away from home, and never reaches the camera's service directly.
 * Nothing here is a second copy of the service's rules: the controls are Home
 * Assistant's own entity rows, and the timelapse form is drawn from the
 * build_timelapse action's own description.
 *
 *   type: custom:ios2ha-camera-card
 *   device_id: <the camera's device>      # the editor offers a picker
 *   default_view: still                   # optional: a camera or "timelapses"
 */

const DOMAIN = "ios2ha_camera";
const PREFIX = "ios2ha_camera_";
const CAMERA_ORDER = ["still", "stacked", "live", "screenshot"];
const STREAMS = new Set(["live", "stacked"]);   // keep the phone awake while shown
const REGION = ["colour_region_x0", "colour_region_y0", "colour_region_x1", "colour_region_y1"];
const SECTIONS = [[null, "Controls"], ["config", "Configuration"], ["diagnostic", "Diagnostics"]];

// Which of the service's objects an entity is. The integration sets each entity's
// translation key to it, which survives a renamed entity id and the `_2` a second
// camera's ids get; the id itself is only a fallback for an older integration.
function objectId(entry) {
  if (entry.translation_key) return entry.translation_key;
  const rest = entry.entity_id.split(".")[1] ?? "";
  return rest.startsWith(PREFIX) ? rest.slice(PREFIX.length) : rest;
}

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of children) if (c != null) e.append(c);
  return e;
}

function firstDevice(hass) {
  const entity = Object.values(hass.entities ?? {}).find((e) => e.platform === DOMAIN && e.device_id);
  return entity?.device_id;
}

function relative(iso) {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const s = Math.round((Date.now() - t) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

const STYLE = `
  :host { display: block; }
  [hidden] { display: none !important; }   /* a class's display must not undo hidden */
  ha-card { overflow: hidden; }
  .head { display: flex; align-items: baseline; gap: .6em; padding: 12px 16px 4px; }
  .head h2 { margin: 0; font-size: 1.2em; font-weight: 500; }
  .head .sub { color: var(--secondary-text-color); font-size: .85em; }
  .tabs { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px 12px 8px; }
  .tabs button { border: 0; border-radius: 16px; padding: 4px 12px; cursor: pointer;
                 background: none; color: var(--secondary-text-color); font: inherit; }
  .tabs button.active { background: var(--secondary-background-color); color: var(--primary-text-color); }
  .view { position: relative; }
  .region { position: absolute; border: 2px dashed #ffd60a; box-shadow: 0 0 0 9999px #0006;
            pointer-events: none; }
  .view.picking { cursor: crosshair; touch-action: none; user-select: none; }
  .glass { position: absolute; inset: 0; }
  .tools { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding: 8px 16px; }
  .tools button, form button { border: 1px solid var(--divider-color); border-radius: 8px;
           padding: 4px 12px; background: var(--card-background-color); color: var(--primary-text-color);
           cursor: pointer; font: inherit; }
  .tools button.on { background: var(--primary-color); color: var(--text-primary-color); border-color: var(--primary-color); }
  .muted { color: var(--secondary-text-color); font-size: .85em; }
  .error { color: var(--error-color); font-size: .85em; }
  .error:empty { display: none; }
  video { display: block; width: 100%; background: #000; }
  form { display: grid; gap: 8px; padding: 0 16px 12px; }
  .fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(10em, 1fr)); gap: 6px 10px; }
  .fields label { display: grid; gap: 2px; font-size: .8em; color: var(--secondary-text-color); }
  .fields input, .fields select, .tools select { font: inherit; color: var(--primary-text-color);
           background: var(--card-background-color); border: 1px solid var(--divider-color);
           border-radius: 6px; padding: 3px 6px; }
  details { border-top: 1px solid var(--divider-color); padding: 0 16px; }
  summary { cursor: pointer; padding: 10px 0; font-weight: 500; }
  .rows > * { display: block; margin: 4px 0; }
`;

class Ios2haCameraCard extends HTMLElement {
  static getConfigElement() { return document.createElement("ios2ha-camera-card-editor"); }

  static getStubConfig(hass) {
    const id = firstDevice(hass);
    return id ? { device_id: id } : {};
  }

  setConfig(config) {
    this._config = { default_view: "still", ...config };
    this._ready = null;           // rebuilt for the new config
    this._view = null;
    this._entry = null;           // the device may have changed
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 9; }

  getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

  // -- what the device has --

  _deviceId() { return this._config.device_id || firstDevice(this._hass); }

  _entities() {
    const id = this._deviceId();
    return Object.values(this._hass.entities ?? {})
      .filter((e) => e.device_id === id && !e.hidden && this._hass.states[e.entity_id]);
  }

  _find(domain, oid) {
    return this._entities().find((e) => e.entity_id.startsWith(`${domain}.`) && objectId(e) === oid);
  }

  _state(domain, oid) {
    const e = this._find(domain, oid);
    return e ? this._hass.states[e.entity_id] : undefined;
  }

  // -- building and updating --

  // Home Assistant sets `hass` many times a second; every one of them waits for
  // the same build, so none can update a card whose parts do not exist yet.
  async _render() {
    if (!this._hass || !this._config) return;
    if (!this._ready) {
      this._ready = (async () => {
        this._helpers = await window.loadCardHelpers();
        this._build();
      })();
    }
    const ready = this._ready;
    await ready;
    if (ready === this._ready) this._update();   // not a build a new config replaced
  }

  _build() {
    const root = this.shadowRoot ?? this.attachShadow({ mode: "open" });
    root.replaceChildren();
    root.append(el("style", { text: STYLE }));
    const device = this._hass.devices?.[this._deviceId()];
    this._title = el("h2", { text: device?.name_by_user || device?.name || "iPhone Camera" });
    this._sub = el("span", { class: "sub" });
    this._tabs = el("div", { class: "tabs" });
    this._stage = el("div", { class: "view" });
    new ResizeObserver(() => this._drawRegion()).observe(this._stage);
    this._below = el("div");
    this._rowsHost = el("div");
    root.append(el("ha-card", {}, el("div", { class: "head" }, this._title, this._sub),
                   this._tabs, this._stage, this._below, this._rowsHost));
    this._cameras = this._entities()
      .filter((e) => e.entity_id.startsWith("camera."))
      .sort((a, b) => CAMERA_ORDER.indexOf(objectId(a)) - CAMERA_ORDER.indexOf(objectId(b)));
    this._views = this._cameras.map((e) => ({ id: objectId(e), entity: e.entity_id,
                                               label: objectId(e) }));
    if (this._find("sensor", "timelapses")) this._views.push({ id: "timelapses", label: "timelapses" });
    this._buildRows();
    const first = this._views.find((v) => v.id === this._config.default_view) ?? this._views[0];
    if (first) this._select(first);
  }

  _update() {
    const hass = this._hass;
    const stream = this._state("sensor", "stream_state")?.state;
    const still = this._state("sensor", "last_still")?.state;
    this._sub.textContent = [stream, still && `still ${relative(still)}`].filter(Boolean).join(" \u00b7 ");
    if (this._shown?.card) this._shown.card.hass = hass;
    for (const row of this._rows ?? []) row.hass = hass;
    if (this._view?.id === "timelapses") this._updateTimelapses();
    if (this._view?.id === "still") {
      this._drawRegion();
      const ref = this._state("sensor", "colour_reference")?.state;
      if (this._refState) this._refState.textContent = ref ? `Reference: ${ref.replaceAll("_", " ")}` : "";
    }
  }

  _tabsDraw() {
    this._tabs.replaceChildren(...this._views.map((v) => el("button", {
      class: v === this._view ? "active" : "", text: v.label, onclick: () => this._select(v),
    })));
  }

  _select(view) {
    this._view = view;
    this._live = false;
    this._picking = false;
    this._overlay = this._refState = null;
    this._tabsDraw();
    this._stage.replaceChildren();
    this._below.replaceChildren();
    this._shown = null;
    if (view.id === "timelapses") this._buildTimelapses();
    else this._showCamera(view);
  }

  // -- cameras --

  _showCamera(view) {
    const stream = STREAMS.has(view.id);
    const card = this._helpers.createCardElement({
      type: "picture-entity", entity: view.entity, show_name: false, show_state: false,
      camera_view: stream && this._live ? "live" : "auto",
    });
    card.hass = this._hass;
    this._shown = { card };
    this._stage.replaceChildren(card);
    const tools = el("div", { class: "tools" });
    if (stream) {
      tools.append(el("button", {
        class: this._live ? "on" : "", text: this._live ? "Stop live view" : "Live view",
        title: "Keeps the phone streaming while it is shown",
        onclick: () => { this._live = !this._live; this._showCamera(view); },
      }));
    }
    if (view.id === "still" && REGION.every((oid) => this._find("number", oid))) this._regionTools(tools);
    this._below.replaceChildren(tools);
  }

  // -- the colour region, drawn on the still --

  _regionBox() {
    const v = REGION.map((oid) => Number(this._state("number", oid)?.state));
    if (v.some(Number.isNaN)) return null;
    return [Math.min(v[0], v[2]), Math.min(v[1], v[3]), Math.max(v[0], v[2]), Math.max(v[1], v[3])];
  }

  _drawRegion(box = this._dragBox ?? this._regionBox()) {
    if (!this._overlay) return;
    const show = box && (this._picking || this._showRegion);
    this._overlay.hidden = !show;
    if (!show) return;
    const r = this._stage.getBoundingClientRect();
    Object.assign(this._overlay.style, {
      left: `${box[0] * r.width}px`, top: `${box[1] * r.height}px`,
      width: `${(box[2] - box[0]) * r.width}px`, height: `${(box[3] - box[1]) * r.height}px`,
    });
  }

  _regionTools(tools) {
    this._overlay = el("div", { class: "region", hidden: true });
    const glass = el("div", { class: "glass", hidden: true });
    this._stage.append(this._overlay, glass);
    const frac = (ev) => {
      const r = this._stage.getBoundingClientRect();
      return [Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)),
              Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height))];
    };
    let from = null;
    const box = (ev) => { const [x, y] = frac(ev);
      return [Math.min(from[0], x), Math.min(from[1], y), Math.max(from[0], x), Math.max(from[1], y)]; };
    glass.addEventListener("pointerdown", (ev) => { ev.preventDefault(); from = frac(ev); glass.setPointerCapture(ev.pointerId); });
    glass.addEventListener("pointermove", (ev) => { if (from) { this._dragBox = box(ev); this._drawRegion(); } });
    glass.addEventListener("pointerup", async (ev) => {
      if (!from) return;
      const b = box(ev);
      from = null;
      if (b[2] - b[0] < 0.01 || b[3] - b[1] < 0.01) { this._dragBox = null; this._drawRegion(); return; }
      setPicking(false);
      this._showRegion = true;
      show.checked = true;
      this._dragBox = b;
      this._drawRegion();
      try {
        for (const [i, oid] of REGION.entries()) {
          const value = Math.round(b[i] * 1000) / 1000;
          const entity = this._find("number", oid).entity_id;
          if (Number(this._hass.states[entity]?.state) === value) continue;
          await this._hass.callService("number", "set_value", { entity_id: entity, value });
        }
        error.textContent = "";
      } catch (err) {
        error.textContent = err.message ?? String(err);
      } finally {
        this._dragBox = null;
        this._drawRegion();
      }
    });
    const pick = el("button", { text: "Pick colour region" });
    const setPicking = (on) => {
      this._picking = on;
      glass.hidden = !on;
      this._stage.classList.toggle("picking", on);
      pick.classList.toggle("on", on);
      pick.textContent = on ? "Drag over the still" : "Pick colour region";
      this._drawRegion();
    };
    pick.addEventListener("click", () => setPicking(!this._picking));
    const show = el("input", { type: "checkbox", onchange: (ev) => { this._showRegion = ev.target.checked; this._drawRegion(); } });
    const error = el("span", { class: "error" });
    const reference = this._find("button", "set_colour_reference");
    const refState = el("span", { class: "muted" });
    this._refState = refState;
    tools.append(pick, el("label", { class: "muted" }, show, " Show region"));
    if (reference) {
      tools.append(el("button", { text: "Set colour reference", onclick: () =>
        this._hass.callService("button", "press", { entity_id: reference.entity_id })
          .catch((err) => { error.textContent = err.message ?? String(err); }) }), refState);
    }
    tools.append(error);
    this._drawRegion();
  }

  // -- timelapses --

  _catalogue() {
    return this._state("sensor", "timelapses")?.attributes?.items ?? {};
  }

  _buildTimelapses() {
    const tl = {};
    tl.video = el("video", { controls: true, playsinline: true, preload: "metadata", hidden: true });
    tl.empty = el("div", { class: "tools muted", text: "No timelapses built yet." });
    this._stage.replaceChildren(tl.video, tl.empty);
    tl.pick = el("select", { onchange: () => this._play(true) });
    tl.status = el("span", { class: "muted" });
    tl.error = el("span", { class: "error" });
    tl.del = el("button", { text: "Delete", onclick: () => this._delete() });
    const service = this._hass.services?.[DOMAIN]?.build_timelapse;
    tl.form = el("form", { onsubmit: (ev) => { ev.preventDefault(); this._build_timelapse(); } });
    tl.inputs = {};
    const fields = el("div", { class: "fields" });
    for (const [name, f] of Object.entries(service?.fields ?? {})) {
      if (name === "device_id") continue;
      const input = this._fieldInput(f);
      if (!input) continue;
      tl.inputs[name] = input;
      fields.append(el("label", { title: f.description ?? "" }, f.name ?? name, input));
    }
    tl.form.append(fields, el("div", {}, el("button", { type: "submit", text: "Build timelapse" })));
    this._below.replaceChildren(el("div", { class: "tools" }, tl.pick, tl.del, tl.status, tl.error),
                                service ? tl.form : el("div", { class: "tools muted",
                                  text: "Building needs ios2ha-camera 2.16.0 or later." }));
    this._tl = tl;
    this._tlSignature = null;
    this._updateTimelapses(true);
  }

  _fieldInput(f) {
    const s = f.selector ?? {};
    if (s.select) {
      return el("select", {}, el("option", { value: "", text: "(none)" }),
        ...(s.select.options ?? []).map((o) => el("option", { value: o.value ?? o, text: o.label ?? o })));
    }
    if (s.number) return el("input", { type: "number", min: s.number.min, max: s.number.max, step: 1,
                                       placeholder: f.example ?? "" });
    if (s.datetime) return el("input", { type: "datetime-local" });
    if (s.text) return el("input", { type: "text" });
    return null;
  }

  _updateTimelapses(force = false) {
    const tl = this._tl;
    if (!tl) return;
    const cat = this._catalogue();
    const names = Object.keys(cat).sort((a, b) => String(cat[b].built).localeCompare(String(cat[a].built)));
    const signature = JSON.stringify(names.map((n) => [n, cat[n].built]));
    if (force || signature !== this._tlSignature) {
      this._tlSignature = signature;
      const keep = names.includes(tl.pick.value) ? tl.pick.value : names[0];
      tl.pick.replaceChildren(...names.map((n) => el("option", { value: n,
        text: `${n}: ${cat[n].frames} frames, ${cat[n].duration_s} s, built ${relative(cat[n].built)}` })));
      tl.pick.value = keep ?? "";
      tl.pick.hidden = tl.del.hidden = !names.length;
      tl.empty.hidden = !!names.length;
      this._play(force);
    }
    const st = this._state("sensor", "timelapse");
    const pct = this._state("sensor", "timelapse_progress")?.state;
    const last = st?.attributes ?? {};
    const why = last.reason && last.result === st?.state ? `: ${last.reason}` : "";
    tl.status.textContent = !st ? "" : st.state === "building"
      ? `Building ${last.name ?? ""} ${pct ?? 0}%` : `${st.state.replaceAll("_", " ")}${why}`;
  }

  async _entryId() {
    if (this._entry) return this._entry;
    const device = this._hass.devices?.[this._deviceId()];
    const root = await this._hass.callWS({ type: "media_source/browse_media",
                                           media_content_id: `media-source://${DOMAIN}` });
    const child = (root.children ?? []).find((c) =>
      device?.config_entries?.includes(c.media_content_id.split("/").pop()));
    this._entry = child?.media_content_id.split("/").pop();
    return this._entry;
  }

  async _play(force) {
    const tl = this._tl;
    const name = tl.pick.value;
    const entry = this._catalogue()[name];
    if (!entry) { tl.video.hidden = true; tl.video.removeAttribute("src"); this._playing = null; return; }
    const key = `${name}@${entry.built}`;
    if (!force && this._playing === key) return;
    this._playing = key;
    try {
      const entryId = await this._entryId();
      // A path on the integration's own view, signed by Home Assistant (for a
      // day), so it plays and seeks wherever Home Assistant is reachable.
      const media = await this._hass.callWS({
        type: "media_source/resolve_media",
        media_content_id: `media-source://${DOMAIN}/${entryId}/timelapse/${name}`,
      });
      if (this._playing !== key) return;
      tl.video.src = media.url;
      tl.video.hidden = false;
      tl.video.load();
      tl.error.textContent = "";
    } catch (err) {
      tl.error.textContent = err.message ?? String(err);
    }
  }

  async _build_timelapse() {
    const tl = this._tl;
    const data = { device_id: this._deviceId() };
    for (const [name, input] of Object.entries(tl.inputs)) {
      const v = input.value;
      if (v === "") continue;
      if (input.type === "number") data[name] = Number(v);
      else if (input.type === "datetime-local") data[name] = `${v.replace("T", " ")}:00`;
      else data[name] = v;
    }
    try {
      await this._hass.callService(DOMAIN, "build_timelapse", data);
      tl.error.textContent = "";
    } catch (err) {
      tl.error.textContent = err.message ?? String(err);
    }
  }

  async _delete() {
    const name = this._tl.pick.value;
    if (!name || !confirm(`Delete the timelapse ${name}?`)) return;
    try {
      await this._hass.callService(DOMAIN, "delete_timelapse", { name, device_id: this._deviceId() });
    } catch (err) {
      this._tl.error.textContent = err.message ?? String(err);
    }
  }

  // -- every other entity, as Home Assistant shows them --

  _buildRows() {
    this._rows = [];
    const entities = this._entities().filter((e) => !e.entity_id.startsWith("camera."));
    const sections = SECTIONS.map(([category, title]) => {
      const list = entities.filter((e) => (e.entity_category ?? null) === category);
      if (!list.length) return null;
      const rows = el("div", { class: "rows" });
      for (const e of list) {
        const row = this._helpers.createRowElement({ entity: e.entity_id });
        row.hass = this._hass;
        this._rows.push(row);
        rows.append(row);
      }
      const d = el("details", {}, el("summary", { text: `${title} (${list.length})` }), rows);
      if (category === null) d.open = true;
      return d;
    });
    this._rowsHost.replaceChildren(...sections.filter(Boolean));
  }
}

class Ios2haCameraCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._draw(); }

  set hass(hass) { this._hass = hass; this._draw(); }

  _draw() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => ({ device_id: "Camera", default_view: "Show first" })[s.name] ?? s.name;
      this._form.addEventListener("value-changed", (ev) => {
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: ev.detail.value },
                                                              bubbles: true, composed: true }));
      });
      this.append(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      { name: "device_id", selector: { device: { integration: DOMAIN } } },
      { name: "default_view", selector: { select: { options: [...CAMERA_ORDER, "timelapses"] } } },
    ];
  }
}

customElements.define("ios2ha-camera-card", Ios2haCameraCard);
customElements.define("ios2ha-camera-card-editor", Ios2haCameraCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "ios2ha-camera-card",
  name: "iPhone Camera",
  description: "The ios2ha camera: its pictures, timelapses and every control.",
  preview: true,
});
