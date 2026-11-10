import assert from "node:assert/strict";
import test from "node:test";

import { productTagline } from "../lib/status-label.ts";

test("product tagline matches landing hero", () => {
  assert.equal(productTagline(), "Find the Right Talent, Faster.");
});
