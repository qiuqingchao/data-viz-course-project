<script setup>
/**
 * 关键指标卡。
 * 设计要点（呼应"高实用性"）：
 *   · 数字用等宽字体 + 定宽数字，四张卡纵向对齐，扫一眼就能比较大小；
 *   · 单位比数字小一号且弱化，不抢数字的注意力；
 *   · 左侧 3px 色条表示这枚指标的性质（松石=常规 / 黄铜=规模 / 红=异常）；
 *   · 数字带滚动动画：让"数据是活的"这件事被看见。
 */
import { computed } from 'vue'

import { useCountUp } from '../composables/useCountUp.js'

const props = defineProps({
  label: { type: String, required: true },
  /** 动画结束后的精确显示值（已格式化好的字符串，例如 "36.73"） */
  display: { type: [String, Number], required: true },
  displayUnit: { type: String, default: '' },
  hint: { type: String, default: '' },
  tone: { type: String, default: 'brand' }, // brand | brass | danger
  /** 滚动动画的目标数字（不传则不做动画） */
  animateTo: { type: [Number, String], default: null },
  /** 滚动过程中保留的小数位 */
  digits: { type: Number, default: 0 },
  prefix: { type: String, default: '' },
  /** 错峰延迟，让四张卡依次滚起来 */
  delay: { type: Number, default: 0 },
})

const canAnimate = computed(
  () => props.animateTo !== null && Number.isFinite(Number(props.animateTo)),
)

const { value: rolling, finished } = useCountUp(
  () => (canAnimate.value ? Number(props.animateTo) : 0),
  { delay: props.delay, duration: 900 },
)

/** 动画结束后一律显示精确值，避免停在四舍五入的中间态 */
const text = computed(() => {
  if (!canAnimate.value) return props.display
  if (finished.value) {
    // 到达精确值后再交还给传入的 display 文案
    return typeof props.display === 'number' ? String(props.display) : props.display
  }
  return props.prefix + rolling.value.toFixed(props.digits)
})
</script>

<template>
  <div class="stat" :class="[`stat--${tone}`, { 'stat--rolling': canAnimate && !finished }]">
    <div class="stat__label">{{ label }}</div>
    <div class="stat__value">
      <span class="stat__number num">{{ text }}</span>
      <span class="stat__unit">{{ displayUnit }}</span>
    </div>
    <div v-if="hint" class="stat__hint">{{ hint }}</div>
  </div>
</template>

<style scoped>
.stat {
  position: relative;
  padding: var(--sp-4) var(--sp-5) var(--sp-4) var(--sp-6);
  background: var(--ink-850);
  border: 1px solid var(--line-1);
  border-radius: var(--r-3);
  box-shadow: var(--shadow-panel);
  overflow: hidden;
}

/* 左侧色条：一眼分辨指标性质 */
.stat::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--brand-500);
}

.stat--brass::before {
  background: var(--brass-500);
}

.stat--danger::before {
  background: var(--danger);
}

.stat__label {
  font-size: var(--fs-13);
  color: var(--text-2);
  margin-bottom: var(--sp-2);
}

.stat__value {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.stat__number {
  font-size: var(--fs-28);
  font-weight: 600;
  line-height: 1.1;
  color: var(--text-1);
}

/* 数字滚动时用黄铜色，停稳后回到常规色：
   颜色变化本身在提示"正在计算"，而不是纯装饰 */
.stat--rolling .stat__number {
  color: var(--brass-400);
}

.stat__unit {
  font-size: var(--fs-13);
  color: var(--text-3);
}

.stat__hint {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  /* 这是说明口径的真文字，不是装饰，所以用 text-3 */
  color: var(--text-3);
}
</style>
