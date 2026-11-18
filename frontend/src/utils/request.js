/**
 * 统一网络请求工具封装 (基于原生 Fetch)
 * 具备自动 Token 鉴权注入、Query 参数序列化、401 拦截与响应结果解析能力
 */

class ApiError extends Error {
  constructor(message, status, code, data) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.data = data
  }
}

/**
 * 基础请求函数
 */
async function request(url, options = {}) {
  const {
    method = 'GET',
    params,
    data,
    headers = {},
    ...customOptions
  } = options

  // 1. 处理 URL 查询参数
  let finalUrl = url
  if (params && Object.keys(params).length > 0) {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        query.append(key, String(val))
      }
    })
    const queryString = query.toString()
    if (queryString) {
      finalUrl += (finalUrl.includes('?') ? '&' : '?') + queryString
    }
  }

  // 2. 组装请求头（自动注入 JWT Token）
  const finalHeaders = {
    ...headers
  }

  const token = localStorage.getItem('token')
  if (token && !finalHeaders['Authorization']) {
    finalHeaders['Authorization'] = `Bearer ${token}`
  }

  // 3. 处理请求体
  let body = undefined
  if (data !== undefined && data !== null) {
    if (data instanceof FormData) {
      body = data
      // FormData 不需要手动设置 Content-Type，浏览器会自动设置 boundary
    } else {
      finalHeaders['Content-Type'] = 'application/json'
      body = JSON.stringify(data)
    }
  }

  // 4. 发起网络请求
  try {
    const resp = await fetch(finalUrl, {
      method,
      headers: finalHeaders,
      body,
      ...customOptions
    })

    // 401 未授权拦截处理
    if (resp.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('userId')
      localStorage.removeItem('role')
      // 若处于非登录页面，重定向至登录页
      if (typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
        window.location.href = '/login'
      }
      throw new ApiError('登录状态已失效，请重新登录', 401, 401, null)
    }

    // 尝试解析 JSON
    let result = null
    const contentType = resp.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      result = await resp.json()
    } else {
      result = await resp.text()
    }

    if (!resp.ok) {
      const errMsg = (result && result.message) || `HTTP 请求错误: ${resp.status}`
      throw new ApiError(errMsg, resp.status, result?.code || resp.status, result)
    }

    return result
  } catch (err) {
    if (err instanceof ApiError) {
      throw err
    }
    throw new ApiError(err.message || '网络连接异常，请检查网络设置', 0, 0, null)
  }
}

export default {
  get(url, params, options = {}) {
    return request(url, { ...options, method: 'GET', params })
  },
  post(url, data, options = {}) {
    return request(url, { ...options, method: 'POST', data })
  },
  put(url, data, options = {}) {
    return request(url, { ...options, method: 'PUT', data })
  },
  delete(url, options = {}) {
    return request(url, { ...options, method: 'DELETE' })
  },
  request
}
