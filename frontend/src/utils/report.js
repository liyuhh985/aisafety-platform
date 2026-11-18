function toRectificationList(value) {
  if (Array.isArray(value)) return value.filter(Boolean).map(String)
  if (value === null || value === undefined || value === '') return []
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text) return []
    try {
      const parsed = JSON.parse(text)
      if (Array.isArray(parsed)) return parsed.filter(Boolean).map(String)
      if (typeof parsed === 'string' && parsed.trim()) return [parsed]
    } catch {
      // Keep legacy plain-text suggestions as one item.
    }
  }
  return [String(value)]
}

export function normalizeReport(record = {}) {
  const vision = record.vision || {}
  return {
    id: record.id,
    imageUrl: record.imageUrl || '',
    hazardCategory: record.hazardCategory || record.hazard_category || vision.hazardCategory || vision.hazard_category || '',
    severity: record.severity || vision.severity || '',
    description: record.description || vision.description || '',
    rectification: toRectificationList(record.rectification ?? vision.rectification),
    reportText: record.reportText || vision.reportText || '',
    createdAt: record.createTime || record.createdAt || '',
  }
}
