import request from '../utils/request.js'

/**
 * 隐患工单业务 API 模块
 */

/** 分页获取工单列表 */
export function getHazardPage(params = { current: 1, size: 10 }) {
  return request.get('/api/hazard', params)
}

/** 获取工单详情 (支持三级缓存) */
export function getHazardDetail(id) {
  return request.get(`/api/hazard/${id}`)
}

/** 普通手动建单 */
export function createHazard(data) {
  return request.post('/api/hazard', data)
}

/** 处突专员认领接单 (0 -> 1) */
export function acceptHazard(id) {
  return request.post(`/api/hazard/${id}/accept`)
}

/** 管理员指派责任人 (0 -> 1) */
export function assignHazard(id, handlerId) {
  return request.post(`/api/hazard/${id}/assign`, { handlerId })
}

/** 处突专员接单/开始整改 (1 -> 2) */
export function startHazard(id) {
  return request.post(`/api/hazard/${id}/start`)
}

/** 处突专员完成整改提交待验 (2 -> 3) */
export function completeHazard(id) {
  return request.post(`/api/hazard/${id}/complete`)
}

/** 指挥长审核验收 (3 -> 3 办结 或 4 驳回) */
export function reviewHazard(id, pass, remark = '') {
  return request.post(`/api/hazard/${id}/review`, { pass, remark })
}

/** 指挥长批量审核 */
export function batchReviewHazard(ids, pass, remark = '') {
  return request.post('/api/hazard/batch-review', { ids, pass, remark })
}

/** 建单人撤回未受理的工单 (0 -> 5) */
export function withdrawHazard(id) {
  return request.post(`/api/hazard/${id}/withdraw`)
}

/** 建单人本人或管理员修改工单点位与地址 (仅 status=0) */
export function updateHazardLocation(id, locationData) {
  return request.put(`/api/hazard/${id}/location`, locationData)
}

/** 轮询 MQ 异步建单受理结果状态 */
export function getHazardRequestStatus(requestId) {
  return request.get(`/api/hazard/requests/${encodeURIComponent(requestId)}`)
}

/** 获取大屏与首页统计指标看板数据 */
export function getHazardStats() {
  return request.get('/api/hazard/stats')
}
