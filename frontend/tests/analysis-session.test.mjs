import assert from 'node:assert/strict'
import { readAnalysisState } from '../src/utils/analysis-session.js'

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial))
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null },
    setItem(key, value) { values.set(key, String(value)) },
    removeItem(key) { values.delete(key) },
    has(key) { return values.has(key) },
  }
}

const storage = createStorage({
  safety_analysis: JSON.stringify({ userId: 'user-1', imageUrl: 'old-image' }),
})

assert.equal(readAnalysisState(storage, 'user-2'), null)
assert.equal(storage.has('safety_analysis'), false)

const currentUserStorage = createStorage({
  safety_analysis: JSON.stringify({ userId: 'user-2', imageUrl: 'current-image' }),
})

assert.deepEqual(readAnalysisState(currentUserStorage, 'user-2'), {
  userId: 'user-2',
  imageUrl: 'current-image',
})

