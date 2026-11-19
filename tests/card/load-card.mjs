// Load the camera card in Node with just enough browser stand-ins for it to
// build: HTMLElement, customElements, window, document.createElement and
// ResizeObserver. Elements are FakeElements that keep their children, so a
// test can walk what the card drew.
//
// The card is imported from a data: URL so Node treats it as an ES module
// whatever the nearest package.json says about `.js` files.

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const defined = new Map();

// Attributes the card sets as `true` that a browser exposes as boolean properties.
const BOOLEAN = new Set(["hidden", "open", "controls", "playsinline", "disabled", "checked"]);

export class FakeElement extends EventTarget {
  constructor() {
    super();
    this.children = [];
    this.shadowRoot = null;
    this.attributes = {};
    this.style = {};
    this.textContent = "";
    this.hidden = false;
    this.open = false;
    this.className = "";
    const owner = this;
    this.classList = {
      toggle(name, on) {
        const names = new Set(owner.className.split(" ").filter(Boolean));
        if (on ?? !names.has(name)) names.add(name);
        else names.delete(name);
        owner.className = [...names].join(" ");
      },
      contains: (name) => owner.className.split(" ").includes(name),
    };
  }
  attachShadow() {
    this.shadowRoot = new FakeElement();
    return this.shadowRoot;
  }
  append(...children) {
    this.children.push(...children);
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  replaceChildren(...children) {
    this.children = [...children];
  }
  setAttribute(name, value) {
    this.attributes[name] = value;
    if (name === "class") this.className = value;
    else if (BOOLEAN.has(name)) this[name] = true;
    else this[name] = value;
  }
  removeAttribute(name) {
    delete this.attributes[name];
  }
  getBoundingClientRect() {
    return { left: 0, top: 0, width: 100, height: 100 };
  }
  setPointerCapture() {}
  load() {}
}

/** Every element under `root` (itself included), through children and shadow roots. */
export function* walk(root) {
  if (!root || typeof root !== "object") return;
  yield root;
  if (root.shadowRoot) yield* walk(root.shadowRoot);
  for (const child of root.children ?? []) yield* walk(child);
}

/** Card helpers as Home Assistant's loadCardHelpers gives them, drawing FakeElements. */
export function fakeHelpers() {
  const make = (localName, config) => {
    const e = new FakeElement();
    e.localName = localName;
    e.config = config;
    return e;
  };
  return {
    createCardElement: (config) => make(`hui-${config.type}-card`, config),
    createRowElement: (config) => make("entity-row", config),
  };
}

globalThis.HTMLElement = FakeElement;
globalThis.window = globalThis;
globalThis.customElements = {
  get: (name) => defined.get(name),
  define: (name, cls) => defined.set(name, cls),
};
globalThis.document = {
  createElement(tag) {
    const Cls = defined.get(tag);
    const el = Cls ? new Cls() : new FakeElement();
    el.localName = tag;
    return el;
  },
};
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {}
};
globalThis.loadCardHelpers = async () => fakeHelpers();

// The card announces its version on load; keep the test output quiet.
const info = console.info;
console.info = () => {};
const here = path.dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  path.join(here, "..", "..", "custom_components", "ios2ha_camera", "www", "ios2ha-camera-card.js"),
  "utf8",
);
export const card = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64")
);
console.info = info;
