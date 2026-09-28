import assert from "node:assert/strict";
import test from "node:test";
import { dialogControls, isolateDialogBackground, trapDialogTab } from "../app/overlay-focus.ts";

class ElementStub {
  inert = false;
  tabIndex = 0;
  disabled = false;
  hidden = false;
  visible = true;
  children: ElementStub[] = [];
  attributes = new Map<string, string>();
  ownerDocument: { activeElement: ElementStub | null } = { activeElement: null };
  getAttribute(name: string) { return this.attributes.get(name) ?? null; }
  setAttribute(name: string, value: string) { this.attributes.set(name, value); }
  removeAttribute(name: string) { this.attributes.delete(name); }
  contains(element: ElementStub): boolean { return this.children.includes(element) || this.children.some((child) => child.contains(element)); }
  querySelectorAll() { return this.children; }
  matches() { return this.disabled; }
  closest() { return this.inert || this.hidden || this.getAttribute("aria-hidden") === "true" ? this : null; }
  getClientRects() { return this.visible ? [{}] : []; }
  focus() { this.ownerDocument.activeElement = this; }
  asElement() { return this as unknown as HTMLElement; }
}

function fixture() {
  const root = new ElementStub();
  const first = new ElementStub();
  const last = new ElementStub();
  first.ownerDocument = root.ownerDocument;
  last.ownerDocument = root.ownerDocument;
  root.children = [first, last];
  return { root, first, last };
}
function tab(root: ElementStub, shiftKey = false, key = "Tab") {
  let prevented = false;
  trapDialogTab(root.asElement(), { key, shiftKey, preventDefault: () => { prevented = true; } } as KeyboardEvent);
  return prevented;
}

test("modal Tab and Shift+Tab wrap, while ordinary keys remain untouched", () => {
  const { root, first, last } = fixture();
  last.focus();
  assert.equal(tab(root), true);
  assert.equal(root.ownerDocument.activeElement, first);
  assert.equal(tab(root, true), true);
  assert.equal(root.ownerDocument.activeElement, last);
  assert.equal(tab(root, false, "a"), false);
});

test("tab traversal recomputes controls after asynchronous content changes", () => {
  const { root, first, last } = fixture();
  last.disabled = true;
  first.focus();
  assert.equal(tab(root), true);
  assert.equal(root.ownerDocument.activeElement, first);
  const added = new ElementStub();
  added.ownerDocument = root.ownerDocument;
  root.children.push(added);
  added.focus();
  assert.equal(tab(root), true);
  assert.equal(root.ownerDocument.activeElement, first);
});

test("hidden, inert, aria-hidden and negative-tabindex controls are excluded", () => {
  const { root, first } = fixture();
  const excluded = Array.from({ length: 5 }, () => new ElementStub());
  excluded[0].hidden = true;
  excluded[1].inert = true;
  excluded[2].setAttribute("aria-hidden", "true");
  excluded[3].tabIndex = -1;
  excluded[4].visible = false;
  root.children = [first, ...excluded];
  assert.deepEqual(dialogControls(root.asElement()), [first]);
});

test("lost focus returns inside dialog; empty dialog retains keyboard focus", () => {
  const { root, last } = fixture();
  root.ownerDocument.activeElement = new ElementStub();
  assert.equal(tab(root, true), true);
  assert.equal(root.ownerDocument.activeElement, last);
  root.children = [];
  assert.equal(tab(root), true);
  assert.equal(root.ownerDocument.activeElement, root);
});

test("Utilities is excluded from background isolation by containment, not class name", () => {
  const cockpit = new ElementStub();
  const background = new ElementStub();
  const utilitiesLayer = new ElementStub();
  const dialog = new ElementStub();
  utilitiesLayer.children = [dialog];
  cockpit.children = [background, utilitiesLayer];
  const restore = isolateDialogBackground(cockpit.asElement(), dialog.asElement());
  assert.equal(background.inert, true);
  assert.equal(background.getAttribute("aria-hidden"), "true");
  assert.equal(utilitiesLayer.inert, false);
  assert.equal(utilitiesLayer.getAttribute("aria-hidden"), null);
  restore();
  assert.equal(background.inert, false);
  assert.equal(background.getAttribute("aria-hidden"), null);
});

test("cleanup preserves preexisting inert and aria-hidden states and later owners", () => {
  const cockpit = new ElementStub();
  const preexisting = new ElementStub();
  preexisting.inert = true;
  preexisting.setAttribute("aria-hidden", "false");
  const changed = new ElementStub();
  const dialog = new ElementStub();
  cockpit.children = [preexisting, changed, dialog];
  const restore = isolateDialogBackground(cockpit.asElement(), dialog.asElement());
  changed.setAttribute("aria-hidden", "false");
  changed.inert = false;
  restore();
  assert.equal(preexisting.inert, true);
  assert.equal(preexisting.getAttribute("aria-hidden"), "false");
  assert.equal(changed.inert, false);
  assert.equal(changed.getAttribute("aria-hidden"), "false");
});
