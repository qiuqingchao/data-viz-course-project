/**
 * 数字滚动动画。
 *
 * 用途：关键指标卡片上的大数字从 0 滚到目标值，
 * 让"这是一份实时数据"这件事被看见 —— 属于**携带信息**的动画，不是装饰。
 *
 * 两条规矩：
 *   1. 尊重系统的"减少动效"设置：此时直接显示最终值，不做任何滚动；
 *   2. 动画结束必须回到"精确值"，不能停在某个四舍五入的中间态。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

function prefersReducedMotion() {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/** 缓出曲线：起步快、收尾慢，读数"稳住"的感觉 */
function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3)
}

/**
 * @param target 目标值。可以直接给数字，也可以给一个返回数字的函数（便于响应式）。
 */
export function useCountUp(target, { duration = 900, delay = 0 } = {}) {
  const value = ref(0)
  const finished = ref(false)
  let rafId = null
  let timerId = null

  const resolveTarget = () => {
    const raw = typeof target === 'function' ? target() : target
    const n = Number(raw)
    return Number.isFinite(n) ? n : 0
  }

  function run() {
    const to = resolveTarget()

    if (prefersReducedMotion() || duration <= 0) {
      value.value = to
      finished.value = true
      return
    }

    const startAt = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - startAt) / duration)
      value.value = to * easeOutCubic(t)
      if (t < 1) {
        rafId = requestAnimationFrame(tick)
      } else {
        value.value = to // 收尾精确归位
        finished.value = true
        rafId = null
      }
    }
    rafId = requestAnimationFrame(tick)
  }

  onMounted(() => {
    if (delay > 0) timerId = window.setTimeout(run, delay)
    else run()
  })

  onBeforeUnmount(() => {
    if (rafId) cancelAnimationFrame(rafId)
    if (timerId) window.clearTimeout(timerId)
    rafId = null
    timerId = null
  })

  return { value, finished }
}
