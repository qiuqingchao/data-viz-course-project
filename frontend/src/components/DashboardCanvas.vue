<script setup>
/**
 * 大屏画布（设计器与查看器共用）—— 第 6 阶段核心组件。
 *
 * 设计思想（答辩可直接讲的三个点）：
 *   1. 【固定设计坐标系】画布永远是 1920×1080，布局数据用这个坐标系存。
 *      不管屏幕多大，先按真实大小排版，再用 CSS transform 整体等比缩放适配 ——
 *      这就是电视台大屏"一处设计、处处播放"的做法。
 *   2. 【手写拖拽引擎】不引入任何第三方布局库：
 *      pointerdown 记下起点 → 移动量除以缩放系数换算回设计坐标 →
 *      10px 磁吸对齐 → 边界钳制，永远拖不出画布。
 *   3. 【一次取数，多端复用】图表配置由父级一次性传入 chartsById，
 *      editable=false 时整个画布纯只读，就是大屏放映模式。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { useTheme } from '../composables/useTheme.js'
import EChart from './EChart.vue'

const props = defineProps({
  /** {canvas:{w,h}, items:[{id,chart_id,x,y,w,h,z}]} —— 对象由父级持有，本组件就地修改 */
  layout: { type: Object, required: true },
  /** {chart_id: {title, chart_type, config:{option}}} */
  chartsById: { type: Object, required: true },
  editable: { type: Boolean, default: false },
  selectedId: { type: String, default: '' },
  /** 图表联动：放映态开启。点某面板的数据元素 → 全画布同名维度数据聚焦高亮 */
  linkage: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'remove', 'change', 'linkage'])

const { chartThemeName } = useTheme()

const CANVAS_W = 1920
const CANVAS_H = 1080
const SNAP = 10 // 磁吸网格：10 像素一档，对齐不靠手稳
const MIN_W = 160
const MIN_H = 120

const fitBox = ref(null)
const scale = ref(0.5)
const dragging = ref(false)
let ro = null

function measure() {
  const el = fitBox.value
  if (!el || !el.clientWidth) return
  const pad = 28
  scale.value = Math.max(
    0.05,
    Math.min(
      (el.clientWidth - pad) / CANVAS_W,
      (el.clientHeight - pad) / CANVAS_H,
    ),
  )
}

onMounted(() => {
  measure()
  ro = new ResizeObserver(measure)
  if (fitBox.value) ro.observe(fitBox.value)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
})

const sortedItems = computed(() =>
  [...(props.layout.items || [])].sort((a, b) => (a.z || 1) - (b.z || 1)),
)

const canvasStyle = computed(() => ({
  width: `${CANVAS_W}px`,
  height: `${CANVAS_H}px`,
  transform: `scale(${scale.value})`,
}))

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v))
}
function snap(v) {
  return Math.round(v / SNAP) * SNAP
}

/* ---------- 拖拽与缩放（手写引擎，全部原生指针事件） ---------- */
let drag = null

function onPanelDown(e, item, mode) {
  if (!props.editable || e.button !== 0) return
  if (!mode && e.target.closest('[data-no-drag]')) return
  emit('select', item.id)
  drag = {
    mode: mode || 'move',
    id: item.id,
    sx: e.clientX,
    sy: e.clientY,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h,
  }
  dragging.value = true
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  e.preventDefault() // 阻止拖拽时选中文字
}

function onMove(e) {
  if (!drag) return
  const item = (props.layout.items || []).find((i) => i.id === drag.id)
  if (!item) return
  const dx = (e.clientX - drag.sx) / scale.value // 屏幕位移换算回设计坐标系
  const dy = (e.clientY - drag.sy) / scale.value
  if (drag.mode === 'move') {
    item.x = clamp(snap(drag.x + dx), 0, CANVAS_W - item.w)
    item.y = clamp(snap(drag.y + dy), 0, CANVAS_H - item.h)
  } else {
    item.w = clamp(snap(drag.w + dx), MIN_W, CANVAS_W - item.x)
    item.h = clamp(snap(drag.h + dy), MIN_H, CANVAS_H - item.y)
  }
  emit('change')
}

function onUp() {
  drag = null
  dragging.value = false
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
}

function panelStyle(item) {
  return {
    left: `${item.x}px`,
    top: `${item.y}px`,
    width: `${item.w}px`,
    height: `${item.h}px`,
    zIndex: item.z || 1,
  }
}

function chartOf(item) {
  return props.chartsById[item.chart_id] || null
}

/**
 * 取出面板要渲染的 ECharts option —— 兼容两种存储形态：
 *   1) 构建器真实存法：config 本身就是裸 option（{title,xAxis,series...}）；
 *   2) 早期/测试存法：config = {option:{...}} 包一层。
 * 顶层有 .option 就是包好的，否则 config 即 option。放映/分享/设计三处共用，
 * 一处归一，避免"建图能存、上大屏却渲染空白"的契约错位。
 */
function panelOption(item) {
  const c = chartOf(item)?.config
  if (!c) return null
  return c.option || c
}

/* ---------- 图表联动（放映态专属） ----------
 * 交互模型（简单到老师一学就会，答辩演示效果拉满）：
 *   点任意面板的扇区/柱子/折线点 → 取出该数据点的"维度名"（如"零食"），
 *   在所有含同名数据的面板上 dispatchAction 聚焦高亮：
 *   命中项发光、其余自动变淡（ECharts 原生 blur 状态，跨图表各自生效）；
 *   再点一次同一目标 / 点画布空白 / ESC（父级调 clearLinkage）解除。
 * 为什么不做"真过滤联动"（点饼图扇区其他图只显示该品类明细）：
 *   那要求每张图都带原始数据、同维度对齐——配置期一次性烘焙的静态图表做不到，
 *   硬做会把课程项目拖进后端重查询。高亮呼应是这套架构下最有演示价值的联动。 */
const chartInsts = new Map() // item.id -> ECharts 实例（换肤重建后经 ready 自动更新）
const panelEls = new Map() // item.id -> 面板 DOM（测试钩子 __panelChart 挂这里）
const linkState = ref(null) // { key, from, responders } | null

function onChartReady(id, inst) {
  chartInsts.set(id, inst)
  const el = panelEls.get(id)
  if (el) el.__panelChart = inst // 自动化测试定位/换算坐标用，无副作用
  inst.off('click')
  inst.on('click', (p) => onChartDataClick(id, p))
}

/** 在一张图的最终 option 里找名为 key 的数据项（支持柱/线/散点的类目轴 + 饼/环） */
function findMatches(opt, key) {
  const out = []
  const axes = Array.isArray(opt.xAxis) ? opt.xAxis : opt.xAxis ? [opt.xAxis] : []
  const seriesArr = Array.isArray(opt.series) ? opt.series : opt.series ? [opt.series] : []
  seriesArr.forEach((s, si) => {
    if (!s) return
    if (s.type === 'pie' || s.type === 'funnel') {
      (s.data || []).forEach((d, di) => {
        if (d && d.name === key) out.push({ si, di })
      })
      return
    }
    const axis = axes[s.xAxisIndex || 0]
    const cats = axis && axis.data
    if (Array.isArray(cats)) {
      const di = cats.findIndex((c) => (c && typeof c === 'object' ? c.value : c) === key)
      if (di >= 0) out.push({ si, di })
    }
    if (Array.isArray(s.data)) {
      s.data.forEach((d, di) => {
        if (d && typeof d === 'object' && d.name === key && !out.some((m) => m.si === si && m.di === di)) {
          out.push({ si, di })
        }
      })
    }
  })
  return out
}

function seriesCount(inst) {
  const opt = inst.getOption()
  return (Array.isArray(opt.series) ? opt.series : opt.series ? [opt.series] : []).length
}

function downplayAll(inst) {
  const n = seriesCount(inst)
  for (let si = 0; si < n; si++) inst.dispatchAction({ type: 'downplay', seriesIndex: si })
}

function onChartDataClick(fromId, p) {
  if (!props.linkage) return
  const key = p && (p.name || (p.data && p.data.name))
  if (!key) return
  if (linkState.value && linkState.value.key === key && linkState.value.from === fromId) {
    clearLinkage()
    return
  }
  let responders = 0
  for (const [, inst] of chartInsts) {
    if (!inst || inst.isDisposed()) continue
    downplayAll(inst)
    const matches = findMatches(inst.getOption(), key)
    if (!matches.length) continue
    responders += 1
    // 连源面板自己一起聚焦：blurScope=global 让同图其他项变淡，形成"呼应"
    for (const m of matches) {
      inst.dispatchAction({ type: 'highlight', seriesIndex: m.si, dataIndex: m.di, blurScope: 'global' })
    }
  }
  linkState.value = { key, from: fromId, responders }
  emit('linkage', linkState.value)
}

function clearLinkage() {
  for (const [, inst] of chartInsts) {
    if (!inst || inst.isDisposed()) continue
    downplayAll(inst)
  }
  linkState.value = null
  emit('linkage', null)
}

function setPanelRef(id, el) {
  if (el) {
    panelEls.set(id, el)
    const inst = chartInsts.get(id)
    if (inst) el.__panelChart = inst
  } else {
    panelEls.delete(id)
  }
}

/* ---------- 导出 PNG（第 7 阶段） ----------
 * 不引 html2canvas 之类第三方"DOM 转图片"库，直接从设计坐标系重绘：
 *   画布底色、面板底色/描边/头栏/标题 —— 全部 getComputedStyle 现场采样，
 *   所以导出图自动跟皮肤走（深色皮肤导出深色图）；
 *   图表本体用 ECharts 自带的 getDataURL 拿高清位图（pixelRatio 2），贴回面板内容区。
 * 整图输出 3840×2160（2 倍设计分辨率），投打印/贴报告都够清晰。 */
const canvasSpaceEl = ref(null)

function roundRectPath(ctx, x, y, w, h, r) {
  ctx.beginPath()
  if (ctx.roundRect) ctx.roundRect(x, y, w, h, r)
  else ctx.rect(x, y, w, h) // 极老浏览器降级：直角
}

async function exportImage(filename = '大屏.png') {
  const S = 2
  const out = document.createElement('canvas')
  out.width = CANVAS_W * S
  out.height = CANVAS_H * S
  const ctx = out.getContext('2d')
  ctx.scale(S, S)

  const space = canvasSpaceEl.value
  if (space) {
    ctx.fillStyle = getComputedStyle(space).backgroundColor
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H)
  }

  for (const item of sortedItems.value) {
    const pEl = panelEls.get(item.id)
    if (!pEl) continue
    const cs = getComputedStyle(pEl)

    ctx.save()
    roundRectPath(ctx, item.x, item.y, item.w, item.h, 8)
    ctx.fillStyle = cs.backgroundColor
    ctx.fill()
    ctx.strokeStyle = cs.borderColor
    ctx.lineWidth = 1
    ctx.stroke()
    roundRectPath(ctx, item.x, item.y, item.w, item.h, 8)
    ctx.clip() // 后续所有绘制裁进圆角面板内

    // 头栏：高度、底色、下边线全部现采（改设计不用同步导出代码）
    const headEl = pEl.querySelector('.panel__head')
    const hh = headEl ? headEl.offsetHeight : 36
    if (headEl) {
      const hcs = getComputedStyle(headEl)
      ctx.fillStyle = hcs.backgroundColor
      ctx.fillRect(item.x, item.y, item.w, hh)
      ctx.strokeStyle = hcs.borderBottomColor
      ctx.beginPath()
      ctx.moveTo(item.x, item.y + hh + 0.5)
      ctx.lineTo(item.x + item.w, item.y + hh + 0.5)
      ctx.stroke()
    }

    // 标题（超宽手动省略号）
    const tEl = pEl.querySelector('.panel__title')
    if (tEl) {
      const tcs = getComputedStyle(tEl)
      ctx.fillStyle = tcs.color
      ctx.font = `${tcs.fontWeight} ${parseFloat(tcs.fontSize)}px ${tcs.fontFamily}`
      ctx.textBaseline = 'middle'
      let s = tEl.textContent || ''
      const maxW = item.w - 24
      if (ctx.measureText(s).width > maxW) {
        while (s.length > 1 && ctx.measureText(s + '…').width > maxW) s = s.slice(0, -1)
        s += '…'
      }
      ctx.fillText(s, item.x + 12, item.y + hh / 2)
    }

    // 图表位图：ECharts 实例直出，透明底贴进内容区
    const inst = chartInsts.get(item.id)
    if (inst && !inst.isDisposed()) {
      try {
        const dataUrl = inst.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: 'transparent' })
        const img = new Image()
        await new Promise((ok, no) => {
          img.onload = ok
          img.onerror = no
          img.src = dataUrl
        })
        const pad = 4
        ctx.drawImage(img, item.x + pad, item.y + hh + pad, item.w - pad * 2, item.h - hh - pad * 2)
      } catch {
        /* 个别图表拿不到位图就跳过它，导出不整体失败 */
      }
    } else if (!chartOf(item)) {
      ctx.fillStyle = '#e5484d'
      ctx.font = '12px sans-serif'
      ctx.textBaseline = 'middle'
      ctx.fillText('引用失效', item.x + 12, item.y + hh + 20)
    }
    ctx.restore()
  }

  const a = document.createElement('a')
  a.href = out.toDataURL('image/png')
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

defineExpose({ clearLinkage, exportImage })
</script>

<template>
  <div ref="fitBox" class="canvas-fit" :class="{ 'is-edit': editable, 'is-dragging': dragging }">
    <div ref="canvasSpaceEl" class="canvas-space" :style="canvasStyle" @pointerdown.self="linkage && clearLinkage()">
      <div
        v-for="item in sortedItems"
        :key="item.id"
        class="panel"
        :ref="(el) => setPanelRef(item.id, el)"
        :class="{
          'is-selected': editable && selectedId === item.id,
          'is-missing': !chartOf(item),
        }"
        :style="panelStyle(item)"
        @pointerdown="onPanelDown($event, item)"
      >
        <div class="panel__head">
          <span class="panel__title">{{ chartOf(item)?.title || '（图表已被删除）' }}</span>
          <button
            v-if="editable"
            class="panel__remove"
            type="button"
            data-no-drag
            title="从大屏移除该面板"
            @click="emit('remove', item.id)"
          >
            ✕
          </button>
        </div>
        <div class="panel__body">
          <EChart
            v-if="panelOption(item)"
            :option="panelOption(item)"
            :theme-name="chartThemeName"
            height="100%"
            :transition="false"
            @ready="(inst) => onChartReady(item.id, inst)"
          />
          <div v-else-if="!chartOf(item)" class="panel__ghost">引用失效</div>
        </div>
        <div
          v-if="editable"
          class="panel__resize"
          title="拖拽调整大小"
          data-no-drag
          @pointerdown.stop="onPanelDown($event, item, 'resize')"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.canvas-fit {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--ink-900);
}

.canvas-fit.is-edit .canvas-space {
  /* 编辑态铺"刻度纸"：网格挂在缩放空间内部，与 10px 磁吸同源、拖到哪都对得齐 */
  background-image:
    linear-gradient(var(--line-1) 1px, transparent 1px),
    linear-gradient(90deg, var(--line-1) 1px, transparent 1px),
    radial-gradient(ellipse 120% 90% at 50% -10%, var(--brand-soft), transparent 60%);
  background-size: 40px 40px, 40px 40px, 100% 100%;
}

.canvas-fit.is-dragging {
  user-select: none;
  cursor: grabbing;
}

.canvas-space {
  position: relative;
  flex: none;
  transform-origin: center center;
  background:
    radial-gradient(ellipse 120% 90% at 50% -10%, var(--brand-soft), transparent 60%),
    var(--ink-850);
  border: 1px solid var(--line-2);
  box-shadow: var(--shadow-card);
}

.panel {
  position: absolute;
  display: flex;
  flex-direction: column;
  background: var(--ink-800);
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
  overflow: hidden;
  box-shadow: var(--shadow-panel);
}

.is-edit .panel {
  cursor: move;
  border-color: var(--line-2);
}

.is-edit .panel:hover {
  border-color: var(--brand-line);
}

.panel.is-selected {
  outline: 2px solid var(--brand-500);
  outline-offset: 1px;
}

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: none;
  height: 36px;
  padding: 0 var(--sp-3);
  border-bottom: 1px solid var(--line-1);
  background: var(--ink-750);
}

.panel__title {
  font-size: var(--fs-13);
  font-weight: 600;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel__remove {
  border: none;
  background: transparent;
  color: var(--text-3);
  font-size: var(--fs-12);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--r-1);
  flex: none;
}

.panel__remove:hover {
  color: var(--danger);
  background: var(--ink-700);
}

.panel__body {
  flex: 1;
  min-height: 0;
  padding: 4px;
}

.panel__ghost {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--danger);
  font-size: var(--fs-12);
}

.panel__resize {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background: linear-gradient(
    135deg,
    transparent 0 50%,
    var(--brand-line) 50% 60%,
    transparent 60% 70%,
    var(--brand-line) 70% 80%,
    transparent 80%
  );
}

.panel.is-missing .panel__title {
  color: var(--danger);
}
</style>
