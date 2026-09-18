<script setup>
/**
 * 大屏设计器 —— 第 6 阶段"组装"入口。
 *
 * 交互模型（为答辩演示刻意做到"零学习成本"）：
 *   ① 左侧「图表库」：列出我保存过的所有图表，点 ➕ 添加 落进画布；
 *   ② 中间画布：按住面板拖动摆放，拽右下角斜纹把手调大小，
 *      10px 磁吸自动对齐刻度纸，点选置顶，✕ 移出大屏（不删原图表）；
 *   ③ 保存即入库：新建走 POST /save，编辑已有大屏走 PUT /{id}。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { api } from '../api/client.js'
import DashboardCanvas from './DashboardCanvas.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  /** 传入已有大屏 ID = 编辑模式；0 = 新建 */
  dashboardId: { type: Number, default: 0 },
})
const emit = defineEmits(['close', 'saved'])

const loading = ref(false)
const saving = ref(false)
const exporting = ref(false)
const canvasRef = ref(null)
const errorMsg = ref('')
const successMsg = ref('')
const dirty = ref(false)

const dashTitle = ref('未命名数据大屏')
const layout = ref({ canvas: { w: 1920, h: 1080 }, items: [] })
/** 图表库（含配置，用于面板渲染）：{chart_id: {title, chart_type, config}} */
const chartsById = ref({})
const chartList = ref([])
const selectedId = ref('')
let addSeq = 0

const typeMeta = {
  bar: { icon: '📊', label: '柱状图' },
  line: { icon: '📈', label: '折线图' },
  horizontal_bar: { icon: '🏆', label: '排行条形' },
  pie: { icon: '🍩', label: '环形图' },
}

const panelCount = computed(() => layout.value.items.length)
const nextZ = computed(() => {
  const zs = layout.value.items.map((i) => i.z || 1)
  return (zs.length ? Math.max(...zs) : 0) + 1
})

onMounted(() => {
  if (props.visible) bootstrap()
})
watch(
  () => props.visible,
  (v) => {
    if (v) bootstrap()
  },
)

async function bootstrap() {
  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''
  dirty.value = false
  selectedId.value = ''
  addSeq = 0
  try {
    // 1. 我的全部图表（列表接口自带 ConfigJson，直接解析即可渲染）
    const res = await api.listMyCharts()
    const map = {}
    chartList.value = (res.charts || []).map((c) => {
      let config = {}
      try {
        config = JSON.parse(c.ConfigJson || '{}')
      } catch {
        config = {}
      }
      map[c.ChartID] = { chart_id: c.ChartID, title: c.Title, chart_type: c.ChartType, config }
      return { id: c.ChartID, title: c.Title, chart_type: c.ChartType }
    })
    chartsById.value = map

    // 2. 编辑模式：载入已有大屏的标题与布局
    if (props.dashboardId) {
      const d = await api.getDashboardDetail(props.dashboardId)
      dashTitle.value = d.dashboard.Title
      layout.value = {
        canvas: { w: 1920, h: 1080 },
        items: (d.dashboard.layout.items || []).map((i) => ({ ...i })),
      }
      for (const c of d.charts || []) {
        if (!chartsById.value[c.chart_id]) chartsById.value[c.chart_id] = c
      }
    } else {
      layout.value = { canvas: { w: 1920, h: 1080 }, items: [] }
      dashTitle.value = '未命名数据大屏'
    }
  } catch (err) {
    errorMsg.value = err.message || '加载图表库失败'
  } finally {
    loading.value = false
  }
}

function addChart(chartId) {
  const id = `p${Date.now()}-${addSeq}`
  addSeq += 1
  const n = panelCount.value
  layout.value.items.push({
    id,
    chart_id: chartId,
    // 瀑布式错位：每块比上一块右下挪 40px，永不完全重叠
    x: 60 + ((n * 40) % 480),
    y: 60 + ((n * 40) % 320),
    w: 720,
    h: 440,
    z: nextZ.value,
  })
  selectedId.value = id
  dirty.value = true
}

function onSelect(id) {
  selectedId.value = id
  const item = layout.value.items.find((i) => i.id === id)
  if (item) item.z = nextZ.value // 点选即置顶，叠放时不用找菜单
}

function onRemove(id) {
  layout.value.items = layout.value.items.filter((i) => i.id !== id)
  if (selectedId.value === id) selectedId.value = ''
  dirty.value = true
}

function onChange() {
  dirty.value = true
}

const selected = computed(
  () => layout.value.items.find((i) => i.id === selectedId.value) || null,
)

/* 键盘 Delete 移除选中面板（输入框里打字不触发） */
function onKeydown(e) {
  if (!props.visible) return
  const tag = e.target?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
  if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId.value) {
    onRemove(selectedId.value)
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

async function doExport() {
  if (exporting.value) return
  exporting.value = true
  try {
    await canvasRef.value?.exportImage(`${dashTitle.value.trim() || '大屏草稿'}.png`)
  } finally {
    exporting.value = false
  }
}

async function doSave() {
  if (saving.value) return
  const t = dashTitle.value.trim()
  if (!t) {
    errorMsg.value = '请先给大屏起个名字'
    return
  }
  if (panelCount.value === 0) {
    errorMsg.value = '大屏还是空的 —— 从左侧图表库点「➕ 添加」放一块图进来'
    return
  }
  saving.value = true
  errorMsg.value = ''
  try {
    const payload = { title: t, layout: layout.value }
    if (props.dashboardId) {
      await api.updateDashboard(props.dashboardId, payload)
    } else {
      await api.saveDashboard(payload)
    }
    dirty.value = false
    successMsg.value = `🎉 大屏「${t}」已保存（${panelCount.value} 块面板）`
    emit('saved')
    setTimeout(() => emit('close'), 1300)
  } catch (err) {
    errorMsg.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="visible" class="dash-modal">
    <div class="dash-overlay" @click="emit('close')" />

    <div class="dash-dialog rise">
      <header class="dash-header">
        <div class="dash-header__left">
          <h3 class="dash-title">数据大屏设计器</h3>
          <span class="badge badge--brand">第 6 阶段 · 拖拽组装</span>
        </div>
        <input
          v-model="dashTitle"
          class="dash-name-input"
          maxlength="128"
          placeholder="大屏名称"
          @input="dirty = true"
        />
        <button class="btn-close" type="button" @click="emit('close')">✕</button>
      </header>

      <div v-if="loading" class="dash-loading">正在载入图表库与布局…</div>

      <div v-else class="dash-body">
        <!-- 左：图表库 -->
        <aside class="dash-palette">
          <div class="palette-title">我的图表库（{{ chartList.length }} 张）</div>
          <div v-if="chartList.length === 0" class="palette-empty">
            还没有已保存的图表。<br />
            先去工作台「新建可视化图表」保存几张，再来组装大屏。
          </div>
          <div v-else class="palette-list">
            <div v-for="c in chartList" :key="c.id" class="palette-item">
              <span class="palette-icon">{{ typeMeta[c.chart_type]?.icon || '📈' }}</span>
              <div class="palette-info">
                <span class="palette-name">{{ c.title }}</span>
                <span class="palette-type">{{ typeMeta[c.chart_type]?.label || c.chart_type }}</span>
              </div>
              <button class="palette-add" type="button" title="添加到画布" @click="addChart(c.id)">
                ➕ 添加
              </button>
            </div>
          </div>
        </aside>

        <!-- 中：画布 -->
        <main class="dash-stage">
          <DashboardCanvas
            ref="canvasRef"
            :layout="layout"
            :charts-by-id="chartsById"
            editable
            :selected-id="selectedId"
            @select="onSelect"
            @remove="onRemove"
            @change="onChange"
          />
        </main>

        <!-- 右：属性与操作提示 -->
        <aside class="dash-rail">
          <div class="rail-section">
            <div class="rail-title">当前大屏</div>
            <div class="rail-stat num">{{ panelCount }} 块面板 / 上限 30</div>
          </div>
          <div class="rail-section">
            <div class="rail-title">选中面板</div>
            <div v-if="selected" class="rail-props num">
              <span>X {{ Math.round(selected.x) }} · Y {{ Math.round(selected.y) }}</span>
              <span>宽 {{ Math.round(selected.w) }} · 高 {{ Math.round(selected.h) }}</span>
            </div>
            <div v-else class="rail-hint">点选画布中任意面板查看坐标</div>
          </div>
          <div class="rail-section">
            <div class="rail-title">操作说明</div>
            <ul class="rail-tips">
              <li>按住面板<em>拖动</em>摆放位置</li>
              <li>拽右下角<em>斜纹把手</em>调大小</li>
              <li>自动<em>10px 磁吸</em>对齐刻度</li>
              <li><em>Delete 键</em>移除选中面板</li>
              <li>✕ 仅移出大屏，<em>不删原图表</em></li>
              <li>放映时点<em>扇区/柱子</em>跨图联动高亮</li>
            </ul>
          </div>
        </aside>
      </div>

      <footer class="dash-footer">
        <span v-if="errorMsg" class="dash-error">{{ errorMsg }}</span>
        <span v-else-if="successMsg" class="dash-success">{{ successMsg }}</span>
        <span v-else class="dash-foot-hint">
          {{ dirty ? '布局有未保存的改动' : '画布坐标系 1920×1080，放映时自动等比缩放' }}
        </span>
        <button
          class="btn-ghost"
          type="button"
          :disabled="exporting || loading || !panelCount"
          @click="doExport"
        >
          {{ exporting ? '合成中…' : '⬇ 导出图片' }}
        </button>
        <button
          class="btn-primary"
          type="button"
          :disabled="saving || loading"
          @click="doSave"
        >
          {{ saving ? '保存中…' : '保存大屏 🖥️' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.dash-modal {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-3);
}

.dash-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(4px);
}

.dash-dialog {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1400px;
  height: 92vh;
  display: flex;
  flex-direction: column;
  background: var(--ink-850);
  border: 1px solid var(--line-1);
  border-radius: var(--r-3);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.dash-header {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-3) var(--sp-5);
  border-bottom: 1px solid var(--line-1);
  flex: none;
}

.dash-header__left {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.dash-title {
  margin: 0;
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
}

.dash-name-input {
  flex: 1;
  max-width: 420px;
  padding: 6px var(--sp-3);
  border-radius: var(--r-2);
  border: 1px solid var(--line-2);
  background: var(--ink-900);
  color: var(--text-1);
  font-size: var(--fs-13);
  font-weight: 600;
}

.dash-name-input:focus {
  outline: none;
  border-color: var(--brand-500);
}

.btn-close {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--text-3);
  font-size: var(--fs-14);
  cursor: pointer;
  padding: 4px 8px;
}

.btn-close:hover {
  color: var(--danger);
}

.dash-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: var(--fs-13);
}

.dash-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

/* ── 左侧图表库 ── */
.dash-palette {
  width: 250px;
  flex: none;
  border-right: 1px solid var(--line-1);
  background: var(--ink-900);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.palette-title {
  padding: var(--sp-3) var(--sp-3) var(--sp-2);
  font-size: var(--fs-12);
  font-weight: 600;
  color: var(--text-2);
  flex: none;
}

.palette-empty {
  padding: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--text-3);
  line-height: 1.7;
}

.palette-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--sp-2) var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.palette-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2);
  background: var(--ink-850);
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
}

.palette-item:hover {
  border-color: var(--brand-line);
}

.palette-icon {
  font-size: 16px;
  flex: none;
}

.palette-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.palette-name {
  font-size: var(--fs-12);
  color: var(--text-1);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.palette-type {
  font-size: 10px;
  color: var(--text-3);
}

.palette-add {
  flex: none;
  border: 1px solid var(--brand-line);
  background: var(--brand-soft);
  color: var(--brand-text);
  font-size: var(--fs-11);
  border-radius: var(--r-1);
  padding: 3px 7px;
  cursor: pointer;
  white-space: nowrap;
}

.palette-add:hover {
  border-color: var(--brand-500);
}

/* ── 中间画布 ── */
.dash-stage {
  flex: 1;
  min-width: 0;
  padding: var(--sp-3);
}

/* ── 右侧属性轨 ── */
.dash-rail {
  width: 200px;
  flex: none;
  border-left: 1px solid var(--line-1);
  background: var(--ink-900);
  padding: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  overflow-y: auto;
}

.rail-title {
  font-size: var(--fs-11);
  font-weight: 600;
  color: var(--text-3);
  margin-bottom: var(--sp-1);
}

.rail-stat {
  font-size: var(--fs-13);
  color: var(--text-1);
}

.rail-props {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: var(--fs-12);
  color: var(--text-2);
}

.rail-hint {
  font-size: var(--fs-11);
  color: var(--text-3);
}

.rail-tips {
  margin: 0;
  padding-left: var(--sp-4);
  font-size: var(--fs-11);
  color: var(--text-3);
  line-height: 1.9;
}

.rail-tips em {
  font-style: normal;
  color: var(--brand-text);
  font-weight: 600;
}

/* ── 底部 ── */
.dash-footer {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-5);
  border-top: 1px solid var(--line-1);
  background: var(--ink-900);
}

.dash-foot-hint {
  flex: 1;
  font-size: var(--fs-12);
  color: var(--text-3);
}

.dash-error {
  flex: 1;
  font-size: var(--fs-12);
  color: var(--danger);
}

.dash-success {
  flex: 1;
  font-size: var(--fs-12);
  color: var(--ok);
  font-weight: 600;
}
</style>
