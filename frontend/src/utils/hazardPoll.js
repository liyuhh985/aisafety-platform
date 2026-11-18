export const HAZARD_POLL_FAST_LIMIT_MS = 10 * 1000
export const HAZARD_POLL_LIMIT_MS = 60 * 1000
export const HAZARD_POLL_MAX_MS = 10 * 60 * 1000
export const HAZARD_POLL_FAST_INTERVAL_MS = 1000
export const HAZARD_POLL_SLOW_INTERVAL_MS = 3000
export const HAZARD_POLL_IDLE_INTERVAL_MS = 30000

/**
 * 建单状态轮询的分级间隔；返回 -1 表示停止轮询。
 * 0~10s 每 1s；10~60s 每 3s；60s~10min 每 30s；超 10min 停止。
 */
export function nextHazardPollDelay(elapsedMs) {
  const elapsed = Number.isFinite(elapsedMs) && elapsedMs > 0 ? elapsedMs : 0
  if (elapsed >= HAZARD_POLL_MAX_MS) return -1
  let interval = HAZARD_POLL_IDLE_INTERVAL_MS
  if (elapsed < HAZARD_POLL_FAST_LIMIT_MS) {
    interval = HAZARD_POLL_FAST_INTERVAL_MS
  } else if (elapsed < HAZARD_POLL_LIMIT_MS) {
    interval = HAZARD_POLL_SLOW_INTERVAL_MS
  }
  return Math.min(interval, HAZARD_POLL_MAX_MS - elapsed)
}
