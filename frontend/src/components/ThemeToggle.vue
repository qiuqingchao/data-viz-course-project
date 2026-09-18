<script setup>
/**
 * 主题切换器（放在右上角，符合大多数人的使用习惯）。
 *
 * 三档：跟随系统 / 浅色 / 深色。
 * 之所以不用"单击循环"的单个按钮，是因为切换结果不可见 ——
 * 用户点了一下却不知道现在是什么状态，是常见的体验缺陷。
 * 三个并排的小按钮让"当前在哪一档"一眼可见。
 */
import { useTheme } from '../composables/useTheme.js'

const props = defineProps({
  /** 只显示图标（空间紧张时用） */
  iconOnly: { type: Boolean, default: false },
})

const { mode, setMode } = useTheme()

const OPTIONS = [
  { key: 'auto', label: '跟随系统', short: '自动' },
  { key: 'light', label: '浅色皮肤（宣纸）', short: '浅色' },
  { key: 'dark', label: '深色皮肤（夜墨）', short: '深色' },
]
</script>

<template>
  <div class="theme-switch" role="group" aria-label="主题皮肤切换">
    <button
      v-for="opt in OPTIONS"
      :key="opt.key"
      type="button"
      class="theme-switch__btn"
      :class="{ 'is-active': mode === opt.key }"
      :title="opt.label"
      :aria-label="opt.label"
      :aria-pressed="mode === opt.key"
      @click="setMode(opt.key)"
    >
      <!-- 图标用内联 SVG 手写，避免为三个小图标再引入一个图标库 -->
      <svg
        v-if="opt.key === 'auto'"
        viewBox="0 0 16 16"
        width="13"
        height="13"
        aria-hidden="true"
      >
        <rect
          x="1.5"
          y="2.5"
          width="13"
          height="9"
          rx="1.5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
        />
        <line x1="5" y1="14" x2="11" y2="14" stroke="currentColor" stroke-width="1.3" />
      </svg>
      <svg
        v-else-if="opt.key === 'light'"
        viewBox="0 0 16 16"
        width="13"
        height="13"
        aria-hidden="true"
      >
        <circle cx="8" cy="8" r="3.2" fill="none" stroke="currentColor" stroke-width="1.3" />
        <g stroke="currentColor" stroke-width="1.3" stroke-linecap="round">
          <line x1="8" y1="1" x2="8" y2="2.6" />
          <line x1="8" y1="13.4" x2="8" y2="15" />
          <line x1="1" y1="8" x2="2.6" y2="8" />
          <line x1="13.4" y1="8" x2="15" y2="8" />
          <line x1="3.1" y1="3.1" x2="4.2" y2="4.2" />
          <line x1="11.8" y1="11.8" x2="12.9" y2="12.9" />
          <line x1="12.9" y1="3.1" x2="11.8" y2="4.2" />
          <line x1="4.2" y1="11.8" x2="3.1" y2="12.9" />
        </g>
      </svg>
      <svg v-else viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
        <path
          d="M13.2 10.2A5.6 5.6 0 0 1 5.8 2.8a5.8 5.8 0 1 0 7.4 7.4z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
          stroke-linejoin="round"
        />
      </svg>

      <span v-if="!props.iconOnly" class="theme-switch__label">{{ opt.short }}</span>
    </button>
  </div>
</template>

<style scoped>
.theme-switch {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: var(--r-2);
  border: 1px solid var(--line-2);
  background: var(--ink-800);
}

.theme-switch__btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  border: none;
  border-radius: var(--r-1);
  background: transparent;
  color: var(--text-3);
  font-family: var(--font-sans);
  font-size: var(--fs-11);
  line-height: 1.5;
  cursor: pointer;
  transition: background-color var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
}

.theme-switch__btn:hover {
  color: var(--text-1);
  background: var(--ink-700);
}

.theme-switch__btn.is-active {
  background: var(--brand-soft);
  color: var(--brand-text);
  box-shadow: inset 0 0 0 1px var(--brand-line);
}

.theme-switch__label {
  white-space: nowrap;
}

@media (max-width: 620px) {
  .theme-switch__label {
    display: none;
  }
}
</style>
