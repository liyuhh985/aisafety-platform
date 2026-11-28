import test from 'node:test'
import assert from 'node:assert/strict'

import {
  HAZARD_TAXONOMY,
  LEGACY_HAZARD_MAP,
  getSubcategoriesByMajor,
  resolveHazard,
} from '../src/constants/hazardTaxonomy.js'

const TOTAL = HAZARD_TAXONOMY.reduce(
  (sum, major) => sum + major.subcategories.length,
  0,
)

const RETIRED_CODES = [
  'wall_crack_lean',
  'facade_fall',
  'fire_water_abnormal',
]

test('taxonomy contains exactly 33 canonical subcategories', () => {
  assert.equal(TOTAL, 33)
  for (const code of RETIRED_CODES) {
    assert.equal(
      HAZARD_TAXONOMY.some((major) =>
        major.subcategories.some((sub) => sub.code === code)),
      false,
      code,
    )
  }
})

test('v2b adds four high-value subcategories', () => {
  assert.equal(resolveHazard('fire/ebike_hazard').subcategoryLabel, '电动自行车违规停放/充电')
  assert.equal(resolveHazard('municipal/tree_fall_hazard').subcategoryLabel, '树木倒伏/断枝风险')
  assert.equal(resolveHazard('construction/confined_space').subcategoryLabel, '有限空间作业风险')
  assert.equal(resolveHazard('environment_other/hazmat_storage').subcategoryLabel, '危化品/易燃易爆违规存运')
})

test('bare subcategory codes resolve to their canonical major', () => {
  assert.deepEqual(
    resolveHazard('ebike_hazard'),
    {
      majorCode: 'fire',
      majorLabel: '消防安全',
      subcategoryCode: 'ebike_hazard',
      subcategoryLabel: '电动自行车违规停放/充电',
      displayText: '消防安全 · 电动自行车违规停放/充电',
      isLegacy: false,
      isUnknown: false,
    },
  )
})

test('retired subcategories are not kept as write-path aliases', () => {
  for (const code of RETIRED_CODES) {
    assert.equal(Object.hasOwn(LEGACY_HAZARD_MAP, code), false, code)
  }
})

test('merged targets keep canonical storage paths and slot profiles', () => {
  assert.deepEqual(
    resolveHazard('building/dangerous_building'),
    {
      majorCode: 'building',
      majorLabel: '建筑安全',
      subcategoryCode: 'dangerous_building',
      subcategoryLabel: '危房',
      displayText: '建筑安全 · 危房',
      isLegacy: false,
      isUnknown: false,
    },
  )
  assert.equal(
    resolveHazard('建筑安全/高空坠物').subcategoryCode,
    'falling_object',
  )
  assert.equal(
    resolveHazard('消防安全/消防设施故障').subcategoryCode,
    'fire_equipment_fault',
  )
})

test('major filters expose only the remaining canonical children', () => {
  assert.deepEqual(
    getSubcategoriesByMajor('building').map((sub) => sub.code),
    ['dangerous_building', 'falling_object', 'illegal_structure'],
  )
  assert.deepEqual(
    getSubcategoriesByMajor('fire').map((sub) => sub.code),
    ['fire_lane_blocked', 'fire_equipment_fault', 'ebike_hazard'],
  )
})
