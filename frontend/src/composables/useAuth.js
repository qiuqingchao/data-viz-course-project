/**
 * 登录状态。
 *
 * 状态放在模块作用域（全站一份），任何页面 import 进来看到的都是同一个登录用户，
 * 不会出现"这个页面显示已登录、那个页面显示未登录"。
 *
 * 页面刷新后怎么还是登录状态？—— 令牌存在浏览器本地，
 * 启动时拿它去问后端"我是谁"，问得到就恢复会话，问不到就当作没登录。
 */
import { computed, ref } from 'vue'

import { api, clearToken, getToken, setToken } from '../api/client.js'

const user = ref(null)
const restoring = ref(false)

const isLoggedIn = computed(() => !!user.value)
const displayName = computed(() => user.value?.display_name || user.value?.username || '')

function applySession(payload) {
  if (payload?.token) setToken(payload.token)
  user.value = payload?.user || null
  return user.value
}

/** 登录 */
async function login(username, password) {
  const payload = await api.login(username, password)
  return applySession(payload)
}

/** 注册（后端注册成功会直接签发令牌，所以注册完就是已登录） */
async function register(username, password, displayName) {
  const payload = await api.register(username, password, displayName)
  return applySession(payload)
}

/** 退出登录：先告诉后端，再清掉本地状态。后端失败也要清本地，否则退不出去。 */
async function logout() {
  try {
    if (getToken()) await api.logout()
  } catch {
    /* 后端不通也要让用户退出去 */
  }
  clearToken()
  user.value = null
}

/** 刷新页面后恢复会话。返回是否恢复成功。 */
async function restore() {
  if (!getToken()) return false
  restoring.value = true
  try {
    user.value = await api.me()
    return true
  } catch {
    clearToken()
    user.value = null
    return false
  } finally {
    restoring.value = false
  }
}

/** 拉取"我的数据概况"（工作台首页用） */
async function fetchOverview() {
  return api.overview()
}

export function useAuth() {
  return {
    user,
    isLoggedIn,
    displayName,
    restoring,
    login,
    register,
    logout,
    restore,
    fetchOverview,
  }
}
