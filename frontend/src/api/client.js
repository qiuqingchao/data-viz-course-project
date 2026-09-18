/**
 * 与后端对话的唯一出口。
 *
 * 为什么要把所有请求集中到这里？
 *   1. 登录令牌的读取、附带、失效处理只写一遍，不会有的地方带、有的地方忘；
 *   2. 错误提示统一成"人话"，页面里不用每处都判断一次；
 *   3. 将来接口地址变了，只改这一个文件。
 */

const TOKEN_KEY = 'moheng-token'

/* ------------------------------------------------------------ 令牌存取 */

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token)
    else window.localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* 隐私模式下写不进去时，本次会话仍然可用 */
  }
}

export function clearToken() {
  setToken('')
}

/* -------------------------------------------------------------- 错误类型 */

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 把后端返回的各种错误形状，统一翻译成一句人话 */
function humanMessage(status, payload) {
  const detail = payload?.detail

  if (typeof detail === 'string' && detail) return detail

  // FastAPI 的参数校验错误是一个数组
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0]
    const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : ''
    return field ? `参数「${field}」不合法：${first?.msg || '格式错误'}` : first?.msg || '参数不合法'
  }

  if (status === 0) return '连不上后端服务，请确认后端已经启动'
  if (status === 401) return '登录状态已失效，请重新登录'
  if (status === 403) return '没有权限执行这个操作'
  if (status === 404) return '请求的接口不存在'
  if (status === 413) return '文件太大了'
  if (status === 429) return '操作太频繁，请稍后再试'
  if (status >= 500) return '服务器出错了，请查看后端控制台的日志'
  return `请求失败（HTTP ${status}）`
}

/* ---------------------------------------------------------------- 请求 */

/**
 * @param {string} path   形如 '/api/auth/login'
 * @param {object} options { method, body, auth, timeoutMs }
 */
export async function request(path, options = {}) {
  const { method = 'GET', body, auth = true, timeoutMs = 15000 } = options

  const headers = {}
  let payload

  if (body instanceof FormData) {
    // 传文件时不能手动设置 Content-Type，浏览器要自己带上 multipart 的分界符
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  // 给请求加超时：后端卡住时不能让页面一直转圈
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  let res
  try {
    res = await fetch(path, { method, headers, body: payload, signal: controller.signal })
  } catch (err) {
    window.clearTimeout(timer)
    if (err?.name === 'AbortError') {
      throw new ApiError('请求超时，后端可能没响应', 0)
    }
    throw new ApiError('连不上后端服务，请确认后端已经启动', 0)
  }
  window.clearTimeout(timer)

  let data = null
  const text = await res.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text.slice(0, 200) }
    }
  }

  if (!res.ok) {
    // 令牌失效：立刻清掉本地令牌，避免页面反复用坏令牌去撞
    if (res.status === 401) clearToken()
    throw new ApiError(humanMessage(res.status, data), res.status)
  }

  return data
}

export const api = {
  health: () => request('/api/health', { auth: false }),

  register: (username, password, displayName) =>
    request('/api/auth/register', {
      method: 'POST',
      auth: false,
      body: { username, password, display_name: displayName || null },
    }),

  login: (username, password) =>
    request('/api/auth/login', { method: 'POST', auth: false, body: { username, password } }),

  me: () => request('/api/auth/me'),

  overview: () => request('/api/auth/overview'),

  logout: () => request('/api/auth/logout', { method: 'POST' }),

  // ── 第 8 阶段：一键体验（写库版）──
  /** 后端跑完整管道生成 数据集+4图+大屏，480 行规模给足 60s 余量 */
  seedDemo: () => request('/api/demo/seed', { method: 'POST', timeoutMs: 60000 }),
  /** 清空当前账号全部数据（二次确认由前端负责） */
  resetDemoData: () => request('/api/demo/reset', { method: 'POST', timeoutMs: 30000 }),

  listSamples: () => request('/api/datasets/samples'),

  previewSample: (filename, sheetName) =>
    request('/api/datasets/preview-sample', {
      method: 'POST',
      body: { filename, sheet_name: sheetName || null },
    }),

  previewDataset: (formData) =>
    request('/api/datasets/preview', {
      method: 'POST',
      body: formData,
      timeoutMs: 30000,
    }),

  previewExcelSheet: (formData) =>
    request('/api/datasets/preview-sheet', {
      method: 'POST',
      body: formData,
      timeoutMs: 30000,
    }),

  cleanPreview: (data) =>
    request('/api/datasets/clean-preview', {
      method: 'POST',
      body: data,
    }),

  saveDataset: (data) =>
    request('/api/datasets/save', {
      method: 'POST',
      body: data,
    }),

  listMyDatasets: () => request('/api/datasets/list'),

  deleteDataset: (id) => request(`/api/datasets/${id}`, { method: 'DELETE' }),

  aggregateChart: (params) =>
    request('/api/charts/aggregate', {
      method: 'POST',
      body: params,
    }),

  saveChart: (params) =>
    request('/api/charts/save', {
      method: 'POST',
      body: params,
    }),

  listMyCharts: () => request('/api/charts/list'),

  getChartDetail: (id) => request(`/api/charts/${id}`),

  deleteChart: (id) => request(`/api/charts/${id}`, { method: 'DELETE' }),

  // ── 第 6 阶段：大屏组装 ──
  saveDashboard: (params) =>
    request('/api/dashboards/save', {
      method: 'POST',
      body: params,
    }),

  listMyDashboards: () => request('/api/dashboards/list'),

  getDashboardDetail: (id) => request(`/api/dashboards/${id}`),

  updateDashboard: (id, params) =>
    request(`/api/dashboards/${id}`, {
      method: 'PUT',
      body: params,
    }),

  deleteDashboard: (id) => request(`/api/dashboards/${id}`, { method: 'DELETE' }),

  // ── 第 7 阶段：只读分享 ──
  /** 开启（或复用）分享，返回 { share_token, share_path } */
  shareDashboard: (id) => request(`/api/dashboards/${id}/share`, { method: 'POST' }),
  /** 关闭分享：旧链接立即失效 */
  unshareDashboard: (id) => request(`/api/dashboards/${id}/share`, { method: 'DELETE' }),
  /** 公开只读查看：不携带任何登录态（auth:false） */
  getSharedDashboard: (shareToken) =>
    request(`/api/share/dashboards/${encodeURIComponent(shareToken)}`, { auth: false }),
}
