export const ANALYSIS_SESSION_KEY = 'safety_analysis'

export function clearAnalysisState(storage) {
  storage.removeItem(ANALYSIS_SESSION_KEY)
}

export function readAnalysisState(storage, userId) {
  const raw = storage.getItem(ANALYSIS_SESSION_KEY)
  if (!raw) return null

  try {
    const state = JSON.parse(raw)
    if (!userId || String(state?.userId) !== String(userId)) {
      clearAnalysisState(storage)
      return null
    }
    return state
  } catch {
    clearAnalysisState(storage)
    return null
  }
}
