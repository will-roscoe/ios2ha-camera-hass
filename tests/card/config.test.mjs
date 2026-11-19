// The card's configuration: which parts `hide` removes, which sections `open`
// unfolds, and how the visual editor maps card YAML to its form and back.
// Run with `node --test`; pytest runs it through tests/test_card_config.py.

import assert from "node:assert/strict";
import { test } from "node:test";

import { card } from "./load-card.mjs";

const {
  hiddenKeys,
  openSections,
  isShown,
  deviceParts,
  visibleViews,
  pickView,
  editorSchema,
  toFormData,
  fromFormData,
} = card;

/** One camera device, as Home Assistant's registries and states describe it. */
export function fakeHass() {
  const ent = (entity_id, translation_key, entity_category = null) => ({
    entity_id, device_id: "dev1", platform: "ios2ha_camera", translation_key, entity_category, hidden: false,
  });
  const list = [
    ent("camera.ios2ha_camera_still", "still"),
    ent("camera.ios2ha_camera_stacked", "stacked"),
    ent("camera.ios2ha_camera_live", "live"),
    ent("sensor.ios2ha_camera_timelapses", "timelapses"),
    ent("sensor.ios2ha_camera_battery_level", "battery_level", "diagnostic"),
    ent("number.ios2ha_camera_interval", "interval", "config"),
    ent("switch.ios2ha_camera_on_demand", "on_demand"),
    ent("sensor.ios2ha_camera_legacy_thing", undefined),
  ];
  const names = {
    still: "Still", stacked: "Stacked", live: "Live", timelapses: "Timelapses",
    battery_level: "Battery level", interval: "Interval", on_demand: "On demand",
  };
  return {
    entities: Object.fromEntries(list.map((e) => [e.entity_id, e])),
    states: Object.fromEntries(list.map((e) => [e.entity_id, {
      entity_id: e.entity_id, state: "1",
      attributes: { friendly_name: `iPhone Camera ${names[e.translation_key] ?? "Legacy thing"}` },
    }])),
    devices: { dev1: { name: "iPhone Camera", config_entries: ["e1"] } },
    services: {
      ios2ha_camera: {
        build_timelapse: {
          fields: {
            device_id: { name: "Camera", selector: { device: {} } },
            start: { name: "Start", selector: { datetime: {} } },
            fps: { name: "Frames per second", selector: { number: { min: 1, max: 60 } } },
          },
        },
      },
    },
    callService: async () => {},
    callWS: async () => ({}),
  };
}

test("hide and open accept a scalar", () => {
  assert.deepEqual([...hiddenKeys({ hide: "tab.live" })], ["tab.live"]);
  assert.deepEqual(openSections({ open: "diagnostics" }), ["diagnostics"]);
  assert.deepEqual(openSections({}), ["controls"]);
  assert.deepEqual(openSections({ open: [] }), []);
  assert.deepEqual([...hiddenKeys({})], []);
});

test("isShown is false only for a hidden key", () => {
  assert.equal(isShown({ hide: ["tab.live"] }, "tab.live"), false);
  assert.equal(isShown({ hide: ["tab.live"] }, "tab.still"), true);
  assert.equal(isShown({}, "row.anything"), true);
});

test("visibleViews drops hidden tabs", () => {
  const views = [{ id: "still" }, { id: "live" }, { id: "timelapses" }];
  assert.deepEqual(visibleViews(views, { hide: ["tab.live"] }).map((v) => v.id), ["still", "timelapses"]);
});

test("pickView falls back past a hidden default and returns null when all are hidden", () => {
  const views = [{ id: "still" }, { id: "live" }, { id: "timelapses" }];
  assert.equal(pickView(views, { default_view: "live" }).id, "live");
  assert.equal(pickView(views, { default_view: "still", hide: ["tab.still"] }).id, "live");
  assert.equal(pickView(views, { default_view: "nonsense" }).id, "still");
  assert.equal(pickView(views, { hide: ["tab.still", "tab.live", "tab.timelapses"] }), null);
});

test("deviceParts lists tabs, rows by section with legacy fallback, and fields", () => {
  const p = deviceParts(fakeHass(), "dev1");
  assert.deepEqual(p.tabs, ["still", "stacked", "live", "timelapses"]);
  // The device's name is dropped from each label: every row would repeat it.
  assert.deepEqual(p.sections.diagnostics, [{ key: "row.battery_level", label: "Battery level" }]);
  assert.deepEqual(p.sections.configuration.map((r) => r.key), ["row.interval"]);
  assert.ok(p.sections.controls.some((r) => r.key === "row.legacy_thing"));
  assert.ok(p.sections.controls.some((r) => r.key === "row.on_demand"));
  assert.ok(!p.sections.controls.some((r) => r.key.startsWith("row.still")), "cameras are tabs, not rows");
  assert.deepEqual(p.fields, [{ name: "start", label: "Start" }, { name: "fps", label: "Frames per second" }]);
});

test("no build_timelapse service: no field options, no throw", () => {
  const hass = fakeHass();
  hass.services = {};
  assert.deepEqual(deviceParts(hass, "dev1").fields, []);
  const schema = editorSchema(hass, { device_id: "dev1" });
  assert.ok(Array.isArray(schema));
  assert.ok(!JSON.stringify(schema).includes("timelapse.field."));
});

test("untouched form round-trips to the same config", () => {
  const cfg = { type: "custom:ios2ha-camera-card", device_id: "dev1", default_view: "still" };
  assert.deepEqual(fromFormData(fakeHass(), cfg, toFormData(fakeHass(), cfg)), cfg);
});

test("toFormData ticks everything shown and the open sections", () => {
  const data = toFormData(fakeHass(), { device_id: "dev1", hide: ["tab.live"], open: ["configuration"] });
  assert.ok(!data.shown_tabs.includes("tab.live"));
  assert.ok(data.shown_tabs.includes("tab.still"));
  assert.ok(data.section_configuration.includes("open.configuration"));
  assert.ok(!data.section_controls.includes("open.controls"));
  assert.ok(data.section_controls.includes("section.controls"));
  assert.ok(data.shown_tools.includes("timelapse.field.fps"));
});

test("unticking writes hide keys; ticking open writes open", () => {
  const cfg = { device_id: "dev1" };
  const data = toFormData(fakeHass(), cfg);
  data.shown_tabs = data.shown_tabs.filter((k) => k !== "tab.live");
  data.rows_diagnostics = data.rows_diagnostics.filter((k) => k !== "row.battery_level");
  data.section_diagnostics = [...data.section_diagnostics, "open.diagnostics"];
  const out = fromFormData(fakeHass(), cfg, data);
  assert.deepEqual([...out.hide].sort(), ["row.battery_level", "tab.live"]);
  assert.deepEqual([...out.open].sort(), ["controls", "diagnostics"]);
});

test("closing every section writes an empty open list", () => {
  const cfg = { device_id: "dev1" };
  const data = toFormData(fakeHass(), cfg);
  data.section_controls = data.section_controls.filter((k) => k !== "open.controls");
  assert.deepEqual(fromFormData(fakeHass(), cfg, data).open, []);
});

test("hide keys the form does not offer survive a save", () => {
  const cfg = { device_id: "dev1", hide: ["row.gone_entity"] };
  assert.deepEqual(fromFormData(fakeHass(), cfg, toFormData(fakeHass(), cfg)).hide, ["row.gone_entity"]);
});

test("re-ticking everything removes hide from the config", () => {
  const cfg = { device_id: "dev1", hide: ["tab.live"] };
  const data = toFormData(fakeHass(), cfg);
  data.shown_tabs = [...data.shown_tabs, "tab.live"];
  assert.equal("hide" in fromFormData(fakeHass(), cfg, data), false);
});

test("editor schema: device, show-first limited to visible tabs, collapsed groups per section", () => {
  const s = editorSchema(fakeHass(), { device_id: "dev1", hide: ["tab.stacked"] });
  assert.equal(s[0].name, "device_id");
  const first = s.find((x) => x.name === "default_view");
  assert.deepEqual(first.selector.select.options.map((o) => o.value ?? o), ["still", "live", "timelapses"]);
  const groups = s.filter((x) => x.type === "expandable");
  const titles = groups.map((x) => x.title);
  assert.deepEqual(titles.slice(0, 3), ["Header", "Tabs", "Tools"]);
  assert.ok(titles.includes("Diagnostics (1)"));
  for (const g of groups) assert.equal(g.flatten, true);
  const lists = groups.flatMap((g) => g.schema).filter((f) => f.selector?.select);
  for (const f of lists) {
    assert.equal(f.selector.select.multiple, true);
    assert.equal(f.selector.select.mode, "list");
  }
});

// -- the card as drawn --

import { defined, walk } from "./load-card.mjs";

async function drawn(config) {
  const Card = defined.get("ios2ha-camera-card");
  const c = new Card();
  c.setConfig({ type: "custom:ios2ha-camera-card", device_id: "dev1", ...config });
  c.hass = fakeHass();
  await c._render();
  return [...walk(c)];
}
const byClass = (els, name) => els.filter((e) => e.className?.split(" ").includes(name));
const byTag = (els, tag) => els.filter((e) => e.localName === tag);
const sectionsOf = (els) => byTag(els, "details").map((d) => ({
  title: d.children.find((x) => x.localName === "summary")?.textContent ?? "", open: d.open,
}));
const buttonTexts = (els) => byTag(els, "button").map((b) => b.textContent);

test("every tab hidden: no tab bar, an empty stage, no throw", async () => {
  const els = await drawn({ hide: ["tab.still", "tab.stacked", "tab.live", "tab.timelapses"] });
  const [tabs] = byClass(els, "tabs");
  assert.ok(tabs.hidden || tabs.children.length === 0);
  assert.deepEqual(byClass(els, "view")[0].children, []);
  assert.ok(sectionsOf(els).length > 0, "sections still draw");
});

test("one tab left: the tab bar hides itself", async () => {
  const els = await drawn({ hide: ["tab.stacked", "tab.live", "tab.timelapses"] });
  assert.equal(byClass(els, "tabs")[0].hidden, true);
});

test("a hidden section is not drawn", async () => {
  const els = await drawn({ hide: ["section.diagnostics"] });
  assert.ok(!sectionsOf(els).some((s) => s.title.startsWith("Diagnostics")));
  assert.ok(sectionsOf(els).some((s) => s.title.startsWith("Controls")));
});

test("open chooses the sections unfolded on load", async () => {
  const sections = sectionsOf(await drawn({ open: ["configuration"] }));
  assert.equal(sections.find((s) => s.title.startsWith("Configuration")).open, true);
  assert.equal(sections.find((s) => s.title.startsWith("Controls")).open, false);
  const byDefault = sectionsOf(await drawn({}));
  assert.equal(byDefault.find((s) => s.title.startsWith("Controls")).open, true);
});

test("a hidden row is not drawn, and a section left empty is not drawn", async () => {
  const els = await drawn({ hide: ["row.on_demand", "row.battery_level"] });
  const rows = byTag(els, "entity-row").map((r) => r.config.entity);
  assert.ok(!rows.includes("switch.ios2ha_camera_on_demand"));
  assert.ok(rows.includes("sensor.ios2ha_camera_legacy_thing"));
  assert.ok(!sectionsOf(els).some((s) => s.title.startsWith("Diagnostics")));
});

test("header parts follow their keys; both hidden means no header", async () => {
  assert.equal(byClass(await drawn({ hide: ["header.title", "header.status"] }), "head").length, 0);
  const els = await drawn({ hide: ["header.status"] });
  assert.equal(byClass(els, "sub").length, 0);
  assert.equal(byTag(els, "h2").length, 1);
});

test("tool.live_view hides the Live view button", async () => {
  assert.ok(buttonTexts(await drawn({ default_view: "stacked" })).includes("Live view"));
  assert.ok(!buttonTexts(await drawn({ default_view: "stacked", hide: ["tool.live_view"] })).includes("Live view"));
});

test("timelapse parts follow their keys", async () => {
  const all = await drawn({ default_view: "timelapses" });
  assert.ok(buttonTexts(all).includes("Delete"));
  assert.ok(buttonTexts(all).includes("Build timelapse"));
  const trimmed = await drawn({ default_view: "timelapses",
                                hide: ["timelapse.delete", "timelapse.field.fps"] });
  assert.ok(!buttonTexts(trimmed).includes("Delete"));
  const labels = byTag(trimmed, "label").map((l) => l.children[0]);
  assert.ok(labels.includes("Start") && !labels.includes("Frames per second"));
  const noBuild = await drawn({ default_view: "timelapses", hide: ["timelapse.build", "timelapse.player"] });
  assert.ok(!buttonTexts(noBuild).includes("Build timelapse"));
  assert.equal(byTag(noBuild, "video").length, 0);
});

test("the editor shows the schema and saves through fromFormData", () => {
  const Editor = defined.get("ios2ha-camera-card-editor");
  const ed = new Editor();
  const cfg = { type: "custom:ios2ha-camera-card", device_id: "dev1" };
  ed.setConfig(cfg);
  ed.hass = fakeHass();
  const form = ed.children[0];
  assert.deepEqual(form.schema, editorSchema(fakeHass(), cfg));
  assert.deepEqual(form.data, toFormData(fakeHass(), cfg));
  let saved = null;
  ed.addEventListener("config-changed", (ev) => { saved = ev.detail.config; });
  const data = { ...form.data, shown_tabs: form.data.shown_tabs.filter((k) => k !== "tab.live") };
  form.dispatchEvent(Object.assign(new Event("value-changed"), { detail: { value: data } }));
  assert.deepEqual(saved, { ...cfg, hide: ["tab.live"] });
});
