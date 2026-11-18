import request from '../utils/request.js'

/**
 * 身份认证与账号管理接口
 */
export function login(email, password) {
  return request.post('/api/auth/login', { email, password })
}

export function register(data) {
  return request.post('/api/auth/register', data)
}

export function sendEmailCode(email) {
  return request.post('/api/auth/code', { email })
}

export function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('userId')
  localStorage.removeItem('role')
}
