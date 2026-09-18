<script setup>
/**
 * 品牌标识「墨衡」。
 * 图形含义：左侧黄铜刻度（衡量） + 右侧上升柱体（数据） + 横向基准线（对比）。
 * 这是全套视觉的识别符号，登录页、顶栏、大屏统一使用它。
 */
defineProps({
  compact: { type: Boolean, default: false },
  showTagline: { type: Boolean, default: true },
})
</script>

<template>
  <div class="brand" :class="{ 'brand--compact': compact }">
    <svg class="brand__mark" viewBox="0 0 40 40" role="img" aria-label="墨衡">
      <rect
        x="0.5"
        y="0.5"
        width="39"
        height="39"
        rx="9"
        fill="#0f1621"
        stroke="rgba(255,255,255,0.12)"
      />
      <g stroke="#d8a24a" stroke-width="1" opacity="0.8">
        <line x1="7" y1="10" x2="11" y2="10" />
        <line x1="7" y1="15" x2="11" y2="15" />
        <line x1="7" y1="20" x2="11" y2="20" />
        <line x1="7" y1="25" x2="11" y2="25" />
        <line x1="7" y1="30" x2="11" y2="30" />
      </g>
      <g fill="#17b8a6">
        <rect x="15" y="24" width="4" height="8" rx="1" />
        <rect x="21" y="18" width="4" height="14" rx="1" />
        <rect x="27" y="12" width="4" height="20" rx="1" />
      </g>
      <line
        x1="14"
        y1="27.5"
        x2="33.5"
        y2="27.5"
        stroke="#edbb6a"
        stroke-width="1"
        stroke-dasharray="2 2"
        opacity="0.85"
      />
    </svg>

    <div class="brand__text">
      <div class="brand__name">墨衡</div>
      <div v-if="showTagline" class="brand__tagline">INK &amp; MEASURE</div>
    </div>
  </div>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.brand__mark {
  width: 38px;
  height: 38px;
  flex: none;
  display: block;
}

.brand__name {
  font-size: var(--fs-18);
  font-weight: 600;
  letter-spacing: 0.14em;
  color: var(--text-1);
  line-height: 1.2;
}

.brand__tagline {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.2em;
  color: var(--text-3);
  line-height: 1.4;
}

.brand--compact .brand__mark {
  width: 30px;
  height: 30px;
}

.brand--compact .brand__name {
  font-size: var(--fs-16);
}
</style>
