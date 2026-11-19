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
