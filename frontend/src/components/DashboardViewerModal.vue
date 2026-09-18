<script setup>
/**
 * 大屏查看器 —— "放映模式"。
 * 整屏沉浸渲染已保存的布局：无网格、无把手、无面板按钮，
 * 画布按 1920×1080 设计坐标系自动等比缩放到任意屏幕。
 */
import { nextTick, ref, watch } from 'vue'

import { api } from '../api/client.js'
import DashboardCanvas from './DashboardCanvas.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  dashboardId: { type: Number, default: 0 },
})
const emit = defineEmits(['close'])

const loading = ref(false)
const errorMsg = ref('')
const title = ref('')
const layout = ref({ canvas: { w: 1920, h: 1080 }, items: [] })
const chartsById = ref({})
const isFullscreen = ref(false)
const canvasRef = ref(null)
const linkState = ref(null) // 联动激活时 {key, from, responders}，未激活 null
const exporting = ref(false)

async function doExport() {
  if (exporting.value) return
  exporting.value = true
  try {
    await nextTick()
    await canvasRef.value?.exportImage(`${title.value || '数据大屏'}.png`)
  } finally {
    exporting.value = false
  }
}

watch(
  () => props.visible,
  async (v) => {
    if (!v) {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
      isFullscreen.value = false
      linkState.value = null
      return
    }
    loading.value = true
    errorMsg.value = ''
    linkState.value = null
    try {
      const res = await api.getDashboardDetail(props.dashboardId)
      title.value = res.dashboard.Title
      layout.value = {
        canvas: res.dashboard.layout.canvas || { w: 1920, h: 1080 },
        items: res.dashboard.layout.items || [],
      }
      const map = {}
      for (const c of res.charts || []) map[c.chart_id] = c
      chartsById.value = map
    } catch (err) {
      errorMsg.value = err.message || '大屏加载失败'
    } finally {
      loading.value = false
    }
  },
)

function onLinkage(st) {
  linkState.value = st
}

async function toggleFullscreen() {
  try {
    await nextTick()
    if (document.fullscreenElement) {
      await document.exitFullscreen()
      isFullscreen.value = false
    } else {
      await document.documentElement.requestFullscreen()
      isFullscreen.value = true
    }
  } catch {
    // 浏览器拒绝全屏（少见）：保持窗口内放映，不打断演示
  }
}

function onKeydown(e) {
  if (!props.visible || e.key !== 'Escape') return
  if (linkState.value) {
    // ESC 第一段：先解除联动高亮（放映中手潮了不怕，连按两下就能退出）
    canvasRef.value?.clearLinkage()
    return
  }
  if (!document.fullscreenElement) emit('close')
}
watch(
  () => props.visible,
  (v) => {
    if (v) window.addEventListener('keydown', onKeydown)
    else window.removeEventListener('keydown', onKeydown)
  },
)
</script>

<template>
  <div v-if="visible" class="viewer">
    <header class="viewer__bar">
      <span class="viewer__title">{{ title }}</span>
      <span class="badge badge--brass">放映模式</span>
      <div class="viewer__spacer" />
      <button class="btn-ghost" type="button" @click="toggleFullscreen">
        {{ isFullscreen ? '⛶ 退出全屏' : '⛶ 全屏放映' }}
      </button>
      <button class="btn-ghost" type="button" :disabled="exporting || !!errorMsg || !!loading" @click="doExport">
        {{ exporting ? '合成中…' : '⬇ 导出图片' }}
      </button>
      <button class="btn-ghost btn-ghost--brass" type="button" @click="emit('close')">
        ← 返回工作台
      </button>
    </header>

    <div class="viewer__stage">
      <div v-if="loading" class="viewer__hint">正在载入大屏…</div>
      <div v-else-if="errorMsg" class="viewer__hint viewer__hint--err">{{ errorMsg }}</div>
      <DashboardCanvas
        v-else
        ref="canvasRef"
        :layout="layout"
        :charts-by-id="chartsById"
        :linkage="true"
        @linkage="onLinkage"
      />
      <transition name="link-chip">
        <div v-if="!loading && !errorMsg" class="viewer__link" :class="{ 'is-on': linkState }">
          <template v-if="linkState">
            🔗 已联动「{{ linkState.key }}」 · {{ linkState.responders }} 块图表呼应 · 再点一次或 ESC 解除
          </template>
          <template v-else>提示：点击任意扇区 / 柱子，全大屏同维度数据联动高亮</template>
        </div>
      </transition>
    </div>
  </div>
</template>

<style scoped>
.viewer {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  flex-direction: column;
  background: var(--ink-1000);
}

.viewer__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  height: 52px;
  padding: 0 var(--sp-5);
  border-bottom: 1px solid var(--line-1);
  background: var(--bar-bg);
  backdrop-filter: blur(8px);
}

.viewer__title {
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--text-1);
}

.viewer__spacer {
  flex: 1;
}

.viewer__stage {
  flex: 1;
  min-height: 0;
  position: relative;
}

.viewer__link {
  position: absolute;
  left: 50%;
  bottom: 22px;
  transform: translateX(-50%);
  padding: 8px 16px;
  border-radius: var(--r-3);
  border: 1px solid var(--line-2);
  background: var(--ink-800);
  box-shadow: var(--shadow-panel);
  color: var(--text-3);
  font-size: var(--fs-12);
  pointer-events: none;
  white-space: nowrap;
  max-width: 90%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.viewer__link.is-on {
  color: var(--brand-text);
  border-color: var(--brand-line);
}

.link-chip-enter-active,
.link-chip-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}

.link-chip-enter-from,
.link-chip-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(6px);
}

.viewer__hint {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: var(--fs-13);
}

.viewer__hint--err {
  color: var(--danger);
}
</style>
