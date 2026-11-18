import assert from "node:assert/strict";
import { nextHazardPollDelay, HAZARD_POLL_MAX_MS } from "../src/utils/hazardPoll.js";

const cases = [
  [0, 1000, "起始 → 1 秒"],
  [9900, 1000, "9.9 秒 → 1 秒"],
  [9999, 1000, "9.999 秒 → 1 秒"],
  [10000, 3000, "10 秒 → 3 秒"],
  [59999, 3000, "59.999 秒 → 3 秒"],
  [60000, 30000, "60 秒 → 30 秒"],
  [599000, 1000, "9 分 59 秒 → 最多 1 秒后停止"],
  [599999, 1, "距上限 1ms → 1ms 后停止"],
  [600000, -1, "10 分钟 → 停止"],
  [700000, -1, "超过 10 分钟 → 停止"],
  [-100, 1000, "非法负数按 0 处理"],
  [undefined, 1000, "非法 undefined 按 0 处理"],
];

for (const [elapsed, expected, label] of cases) {
  const actual = nextHazardPollDelay(elapsed);
  assert.equal(actual, expected, label + "（实际 " + actual + "）");
}

for (let t = 0; t < HAZARD_POLL_MAX_MS; t += 1000) {
  const d = nextHazardPollDelay(t);
  assert.ok(d > 0 && d <= 30000, "间隔必须落在 (0, 30000]，t=" + t + " d=" + d);
}

console.log("hazardPoll: all " + cases.length + " boundary cases + sweep passed");
