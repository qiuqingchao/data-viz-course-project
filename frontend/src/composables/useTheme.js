/**
 * 主题（皮肤）管理。
 *
 * 三档模式：
 *   auto  跟随电脑系统设置（默认）
 *   light 浅色「宣纸」
 *   dark  深色「夜墨」
 *
 * 两条硬性要求：
 *   1. 用户的选择要记住（localStorage），下次打开还是他选的皮肤；
 *   2. 选"跟随系统"时，系统在浅色/深色之间切换，页面要实时跟着变。
 *
 * 实现说明：状态放在模块作用域（而不是组件里），这样全站只有一个主题状态，
 * 任何组件 import 进来看到的都是同一份，不会出现"两个开关各说各话"。
 */
import { computed, ref } from 'vue'

import { ECHARTS_THEME, PALETTES } from '../utils/chartTheme.js'

const STORAGE_KEY = 'moheng-theme'
const MODES = ['auto', 'light', 'dark']

function readSavedMode() {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    return MODES.includes(saved) ? saved : 'auto'
  } catch {
    return 'auto'
  }
}

function readSystemDark() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return true
  }
}

const mode = ref(readSavedMode())
const systemDark = ref(readSystemDark())

/** 最终解析出来的皮肤：'light' 或 'dark' */
const resolved = computed(() => {
  if (mode.value === 'auto') return systemDark.value ? 'dark' : 'light'
  return mode.value
})

const isDark = computed(() => resolved.value === 'dark')

/** 图表用的调色板与主题名（图表读不到 CSS 变量，必须单独给一份） */
const palette = computed(() => PALETTES[resolved.value])
const chartThemeName = computed(() => ECHARTS_THEME[resolved.value])

let animTimer = null

/**
 * 把皮肤真正写到页面上。
 * @param animate 是否开启 260ms 的平滑过渡（首次加载时不要动画，否则会闪）
 */
function applyTheme({ animate = false } = {}) {
  const root = document.documentElement
  const dark = isDark.value

  if (animate) {
    root.classList.add('theme-anim')
    if (animTimer) window.clearTimeout(animTimer)
    animTimer = window.setTimeout(() => root.classList.remove('theme-anim'), 340)
  }

  // html.dark 同时是 Element Plus 深色模式的开关，必须与我们的令牌保持一致
  root.classList.toggle('dark', dark)
  root.dataset.themeMode = mode.value
  root.style.colorScheme = dark ? 'dark' : 'light'
}

/** 设置模式并立即生效、记住选择 */
function setMode(next) {
  if (!MODES.includes(next)) return
  mode.value = next
  try {
    window.localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* 隐私模式下写不进去也不影响使用 */
  }
  applyTheme({ animate: true })
}

/** 在"自动 → 浅色 → 深色"之间轮流切换（给单按钮切换用） */
function cycleMode() {
  const order = ['auto', 'light', 'dark']
  setMode(order[(order.indexOf(mode.value) + 1) % order.length])
}

/* ---- 监听系统主题变化：只有"跟随系统"时才需要跟着动 ---- */
if (typeof window !== 'undefined' && window.matchMedia) {
  const mql = window.matchMedia('(prefers-color-scheme: dark)')
  systemDark.value = mql.matches
  const onChange = (event) => {
    systemDark.value = event.matches
    if (mode.value === 'auto') applyTheme({ animate: true })
  }
  if (mql.addEventListener) mql.addEventListener('change', onChange)
  else if (mql.addListener) mql.addListener(onChange)
}

/** 页面启动时调用一次（不要动画，避免打开就闪一下） */
function initTheme() {
  applyTheme({ animate: false })
}

export function useTheme() {
  return {
    mode,
    resolved,
    isDark,
    palette,
    chartThemeName,
    systemDark,
    setMode,
    cycleMode,
    initTheme,
    MODES,
  }
}
