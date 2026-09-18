<script setup>
/**
 * 分享页 —— 第 7 阶段"只读链接"的落地页。
 *
 * 特点（答辩可讲的三点）：
 *   1. 免登录：只凭地址里的 token 拉数据，调的是 /api/share 公开接口；
 *      后端只在 IsPublic=1 且 token 合法时返回，作者随时可关闭使链接失效。
 *   2. 只读但可交互：画布 editable=false（没有网格/把手/删除键），
 *      但图表联动照常工作 —— 看的人点扇区也能高亮呼应。
 *   3. 复用同一块 DashboardCanvas：放映/分享/设计共用一个渲染核心，
 *      "一处设计、处处播放"在这里体现为"一套组件、多种场合"。
 */
import { onMounted, ref } from 'vue'

import { api } from '../api/client.js'
import { useTheme } from '../composables/useTheme.js'
import DashboardCanvas from '../components/DashboardCanvas.vue'
import ThemeToggle from '../components/ThemeToggle.vue'

const props = defineProps({
  token: { type: String, default: '' },
})

const { chartThemeName } = useTheme()

const loading = ref(true)
const errorMsg = ref('')
const title = ref('')
const layout = ref({ canvas: { w: 1920, h: 1080 }, items: [] })
const chartsById = ref({})
const linkState = ref(null)
const canvasRef = ref(null)
const exporting = ref(false)

async function load() {
  loading.value = true
  errorMsg.value = ''
  if (!props.token) {
    errorMsg.value = '链接不完整，请向分享者索取完整地址'
    loading.value = false
    return
  }
  try {
    const res = await api.getSharedDashboard(props.token)
    title.value = res.dashboard.Title
    layout.value = {
      canvas: res.dashboard.layout.canvas || { w: 1920, h: 1080 },
      items: res.dashboard.layout.items || [],
    }
    const map = {}
    for (const c of res.charts || []) map[c.chart_id] = c
    chartsById.value = map
  } catch (err) {
    errorMsg.value = err.message || '分享链接无效或已被作者关闭'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function doExport() {
  if (exporting.value) return
  exporting.value = true
  try {
    await canvasRef.value?.exportImage(`${title.value || '数据大屏'}.png`)
  } finally {
    exporting.value = false
  }
}

function goHome() {
  window.location.hash = '#/login'
}
</script>

<template>
  <div class="share">
    <header class="share__bar">
      <span class="share__brand">墨衡 · 数据大屏</span>
      <span class="share__title">{{ title }}</span>
      <span class="badge badge--brass">只读分享</span>
      <div class="share__spacer" />
      <ThemeToggle />
      <button class="btn-ghost" type="button" :disabled="loading || !!errorMsg || exporting" @click="doExport">
        {{ exporting ? '合成中…' : '⬇ 导出图片' }}
      </button>
      <button class="btn-ghost btn-ghost--brass" type="button" @click="goHome">
        我也做一个 →
      </button>
    </header>

    <div class="share__stage">
      <div v-if="loading" class="share__hint">正在载入分享的看板…</div>
      <div v-else-if="errorMsg" class="share__invalid">
        <div class="share__invalid-icon">🔒</div>
        <div class="share__invalid-title">这份看板看不到</div>
        <div class="share__invalid-msg">{{ errorMsg }}</div>
        <button class="btn-primary" type="button" @click="goHome">前往登录 / 体验演示</button>
      </div>
      <template v-else>
        <DashboardCanvas
          ref="canvasRef"
          :layout="layout"
          :charts-by-id="chartsById"
          :linkage="true"
          @linkage="(st) => (linkState = st)"
        />
        <div class="share__link" :class="{ 'is-on': linkState }">
          <template v-if="linkState">
            🔗 已联动「{{ linkState.key }}」 · {{ linkState.responders }} 块图表呼应 · 点空白处解除
          </template>
          <template v-else>提示：点击任意扇区 / 柱子可跨图表联动高亮 · 数据为作者保存时的快照</template>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.share {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: var(--ink-1000);
}

.share__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  height: 56px;
  padding: 0 var(--sp-5);
  border-bottom: 1px solid var(--line-1);
  background: var(--bar-bg);
  backdrop-filter: blur(8px);
}

.share__brand {
  font-size: var(--fs-14);
  font-weight: 700;
  color: var(--brand-text);
  letter-spacing: 0.04em;
}

.share__title {
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--text-1);
  max-width: 40vw;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.share__spacer {
  flex: 1;
}

.share__stage {
  flex: 1;
  min-height: 0;
  position: relative;
}

.share__hint {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: var(--fs-13);
}

.share__invalid {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-4);
  text-align: center;
}

.share__invalid-icon {
  font-size: 44px;
}

.share__invalid-title {
  font-size: var(--fs-18);
  font-weight: 700;
  color: var(--text-1);
}

.share__invalid-msg {
  font-size: var(--fs-13);
  color: var(--text-3);
  max-width: 420px;
}

.share__link {
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

.share__link.is-on {
  color: var(--brand-text);
  border-color: var(--brand-line);
}
</style>
