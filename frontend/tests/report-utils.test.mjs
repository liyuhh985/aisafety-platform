import assert from 'node:assert/strict'
import { normalizeReport } from '../src/utils/report.js'

const report = normalizeReport({
  id: 7,
  imageUrl: '/uploads/hazard.jpg',
  hazardCategory: '????',
  severity: '?',
  description: '????',
  rectification: ['????', '????'],
  reportText: '??????',
  createTime: '2026-07-27T10:20:00',
  vision: {
    hazard_category: '?????',
    severity: '?',
    description: '?????',
  },
})

assert.deepEqual(report, {
  id: 7,
  imageUrl: '/uploads/hazard.jpg',
  hazardCategory: '????',
  severity: '?',
  description: '????',
  rectification: ['????', '????'],
  reportText: '??????',
  createdAt: '2026-07-27T10:20:00',
})

assert.deepEqual(normalizeReport({ rectification: '????' }).rectification, ['????'])
assert.deepEqual(normalizeReport({ rectification: '["one","two"]' }).rectification, ['one', 'two'])
console.log('report utils tests passed')
