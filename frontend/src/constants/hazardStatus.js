/**
 * 隐患全生命周期状态枚举与渲染助手
 */

export const HAZARD_STATUS = Object.freeze({
  PENDING: 0,       // 待处理（未接单，可撤回/可修改定位）
  ASSIGNED: 1,      // 责任专员已接单
  PROCESSING: 2,    // 现场施工整改中
  COMPLETED: 3,     // 处置完成（reviewed=0 为待验收，reviewed=1 为已办结）
  REJECTED: 4,      // 审查驳回（需退回返工）
  WITHDRAWN: 5      // 上报人主动撤回
})

export const STATUS_TEXT_MAP = Object.freeze({
  [HAZARD_STATUS.PENDING]: '待处理',
  [HAZARD_STATUS.ASSIGNED]: '已接单',
  [HAZARD_STATUS.PROCESSING]: '整改中',
  [HAZARD_STATUS.COMPLETED]: '已办结',
  [HAZARD_STATUS.REJECTED]: '已驳回',
  [HAZARD_STATUS.WITHDRAWN]: '已撤回'
})

/**
 * 根据状态和终审标识获取统一展示文案
 */
export function getStatusText(status, reviewed = null) {
  if (status === null || status === undefined) return '未知'
  const st = Number(status)
  if (st === HAZARD_STATUS.COMPLETED) {
    return (reviewed === 1) ? '已办结' : '待验收'
  }
  return STATUS_TEXT_MAP[st] || '未知'
}

/**
 * 获取统一状态徽章的 CSS Class
 */
export function getStatusBadgeClass(status, reviewed = null) {
  if (status === null || status === undefined) return 'status-0'
  const st = Number(status)
  if (st === HAZARD_STATUS.COMPLETED) {
    return (reviewed === 1) ? 'status-3' : 'status-pending-review'
  }
  if (st === HAZARD_STATUS.WITHDRAWN) {
    return 'status-5 status-withdrawn'
  }
  return `status-${st}`
}
