// Disposition display wording: an entry's optional `display` block (title,
// cause tag) replaces the id-derived title and the class tag on the
// dashboard, and nothing else. Self-contained (node builtins only); run from
// dashboard/ with `bun scripts/test-disposition-display.mjs` or plain node.
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

import {
  DISPLAY_CAUSE_LABELS,
  displayCauseLabel,
  displayTitle,
  humanizeSlug,
} from "../src/utils/dispositionDisplay.mjs";

const root = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, root), "utf8");

// The tag vocabulary matches the validator's DISPLAY_CAUSES.
const python = read("axiom_oracles/comparison/dispositions.py");
const tuple = python.match(/^DISPLAY_CAUSES = \(([^)]*)\)/m);
assert.ok(tuple, "DISPLAY_CAUSES not found in dispositions.py");
const causes = [...tuple[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
assert.deepEqual(Object.keys(DISPLAY_CAUSE_LABELS).sort(), [...causes].sort());
for (const label of Object.values(DISPLAY_CAUSE_LABELS)) {
  assert.ok(label && !/gap/i.test(label), `display cause label ${label} must not name a gap`);
}

// Title: display.title when set, else the humanized id.
assert.equal(humanizeSlug("benefit-cap-not-applied"), "Benefit cap not applied");
assert.equal(displayTitle({ id: "a-b" }), "A b");
assert.equal(displayTitle({ id: "a-b", display: { title: "Plain title" } }), "Plain title");
assert.equal(displayTitle({ id: "a-b", display: { title: "   " } }), "A b");
assert.equal(displayTitle({ id: "a-b", display: { cause: "open" } }), "A b");
assert.equal(displayTitle(null), "");

// Tag: a known display.cause, else null so the caller keeps the class tag.
assert.equal(displayCauseLabel({ display: { cause: "comparison_setup" } }), "comparison set-up");
assert.equal(displayCauseLabel({ display: { cause: "open" } }), "cause open");
for (const entry of [
  {},
  null,
  { display: {} },
  { display: { title: "t" } },
  { display: { cause: "unknown" } },
  { display: { cause: "toString" } },
  { display: { cause: "__proto__" } },
  { display: { cause: ["open"] } },
]) {
  assert.equal(displayCauseLabel(entry), null, JSON.stringify(entry));
}

// Every shipped artifact's display block is well formed and labelled. A title
// holds no line break of any kind (the characters Python's splitlines splits on).
const LINE_BREAKS = [10, 11, 12, 13, 28, 29, 30, 133, 8232, 8233].map((c) => String.fromCharCode(c));
const dir = "dashboard/public/data/dispositions/";
let withDisplay = 0;
let entries = 0;
for (const name of readdirSync(new URL(dir, root)).filter((n) => n.endsWith(".json"))) {
  const artifact = JSON.parse(read(dir + name));
  for (const entry of artifact.entries || []) {
    entries += 1;
    if (!("display" in entry)) continue;
    withDisplay += 1;
    const where = `${name} ${entry.id}`;
    const display = entry.display;
    assert.ok(display && typeof display === "object" && !Array.isArray(display), where);
    assert.ok(Object.keys(display).length > 0, `${where}: empty display`);
    for (const key of Object.keys(display)) {
      assert.ok(["title", "cause"].includes(key), `${where}: unknown display key ${key}`);
    }
    if ("title" in display) {
      assert.equal(typeof display.title, "string", where);
      assert.equal(display.title, display.title.trim(), where);
      assert.ok(display.title && !LINE_BREAKS.some((c) => display.title.includes(c)) && display.title.length <= 120, where);
    }
    if ("cause" in display) {
      assert.ok(displayCauseLabel(entry), `${where}: no label for cause ${display.cause}`);
      assert.ok(
        !["axiom_encoding_gap", "unexplained"].includes(entry.disposition),
        `${where}: display.cause relabels a ${entry.disposition} entry`,
      );
    }
  }
}

// The note renders the display wording ahead of the id and the class tag.
const note = read("dashboard/src/components/DispositionNote.jsx");
assert.ok(note.includes("{displayTitle(e)}"), "DispositionNote no longer titles entries with displayTitle");
assert.ok(
  note.includes("displayCauseLabel(e) || dispositionTag(e.disposition, row)"),
  "DispositionNote no longer prefers the display cause over the class tag",
);

console.log(
  `DISPOSITION DISPLAY: true (${Object.keys(DISPLAY_CAUSE_LABELS).length} causes; ` +
    `${withDisplay} of ${entries} shipped entries carry display wording)`,
);
