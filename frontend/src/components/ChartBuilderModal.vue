<script setup>
/**
 * 图表配置与生成工作台（第 5 阶段核心交付）。
 *
 * 核心交互：
 * 1. 数据集选择：拉取用户已入库的数据集（或提示先上传清洗）；
 * 2. 轴与指标映射：选择分类维度（如省份、品类）与数值指标（如销售额、订单量）；
 * 3. 聚合算子：选择 SUM（求和）、AVG（平均值）、COUNT（计数）、MAX/MIN；
 * 4. 图表类型切换：柱状图 (bar)、平滑折线面积图 (line)、横向排行动画条形图 (horizontal_bar)、环形饼图 (pie)；
 * 5. 实时 ECharts 渲染与保存图表到数据库。
 */
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '../api/client.js'
import { useTheme } from '../composables/useTheme.js'
import EChart from './EChart.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'saved'])

// 状态
const loading = ref(false)
const saving = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

// 数据集列表
const datasetList = ref([])
const selectedDatasetId = ref(null)
const selectedDataset = computed(() =>
  datasetList.value.find((d) => d.DatasetID === selectedDatasetId.value)
)

// 维度与指标字段列表
const dimensionColumns = ref([])
const metricColumns = ref([])

// 图表配置参数
const { chartThemeName } = useTheme()

const chartForm = ref({
  title: '数据统计图表',
  chart_type: 'bar', // 'bar' | 'line' | 'horizontal_bar' | 'pie'
  dimension: '',
  metric: '',
  agg_type: 'sum',
  sort_order: 'desc',
  limit: 10,
})

// 试算生成的 ECharts Option 与统计数据
const chartOption = ref(null)
const aggregatedRows = ref([])

// 支持的图表类型定义
const chartTypeOptions = [
  { value: 'bar', label: '柱状图', icon: '📊', desc: '分类对比' },
  { value: 'line', label: '折线图', icon: '📈', desc: '趋势与波动' },
  { value: 'horizontal_bar', label: '排行动画条形图', icon: '🏆', desc: '动态横向排名' },
  { value: 'pie', label: '环形占比图', icon: '🍩', desc: '结构份额分析' },
]

// 典型图表配置预设模板（老师一键套用示例）
const presetTemplates = [
  {
    title: '各省份销售总额柱状对比',
    desc: '维度: 省份 · 指标: 销售额 · 求和 (SUM)',
    chart_type: 'bar',
    dimension: '省份',
    metric: '销售额',
    agg_type: 'sum',
    limit: 10,
  },
  {
    title: '商品品类销售占比环形图',
    desc: '维度: 品类 · 指标: 销售额 · 占比分析',
    chart_type: 'pie',
    dimension: '品类',
    metric: '销售额',
    agg_type: 'sum',
    limit: 10,
  },
  {
    title: '全国销售业绩 TOP 10 动态榜',
    desc: '横向动态排序动画 · 视觉冲击力强',
    chart_type: 'horizontal_bar',
    dimension: '省份',
    metric: '销售额',
    agg_type: 'sum',
    limit: 10,
  },
  {
    title: '1-12月份销售走势平滑曲线',
    desc: '维度: 月份 · 指标: 销售额 · 趋势分析',
    chart_type: 'line',
    dimension: '月份',
    metric: '销售额',
    agg_type: 'sum',
    limit: 12,
  },
]

// 一键套用模板
async function applyPreset(preset) {
  chartForm.value.title = preset.title
  chartForm.value.chart_type = preset.chart_type
  chartForm.value.agg_type = preset.agg_type
  chartForm.value.limit = preset.limit

  // 尝试匹配当前数据集中的字段名
  const hasDim = dimensionColumns.value.some((c) => c.name === preset.dimension)
  if (hasDim) chartForm.value.dimension = preset.dimension

  const hasMet = metricColumns.value.some((c) => c.name === preset.metric)
  if (hasMet) chartForm.value.metric = preset.metric

  await runAggregate()
}

onMounted(async () => {
  if (props.visible) {
    await loadDatasets()
  }
})

watch(
  () => props.visible,
  async (val) => {
    if (val) {
      await loadDatasets()
    }
  }
)

async function loadDatasets() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.listMyDatasets()
    if (res.ok) {
      datasetList.value = res.datasets || []
      if (datasetList.value.length > 0) {
        // 默认选中第一个
        await selectDataset(datasetList.value[0].DatasetID)
      }
    }
  } catch (err) {
    errorMsg.value = err.message || '获取数据集失败'
  } finally {
    loading.value = false
  }
}

async function selectDataset(datasetId) {
  selectedDatasetId.value = datasetId
  const ds = selectedDataset.value
  if (!ds) return

  try {
    const cols = JSON.parse(ds.ColumnsJson || '[]')
    dimensionColumns.value = cols.filter((c) => c.type === 'string' || c.is_dimension)
    metricColumns.value = cols.filter((c) => c.type === 'number' || c.is_metric)

    // 如果分类不明显，则全部作为维度，且全部作为指标
    if (dimensionColumns.value.length === 0) dimensionColumns.value = cols
    if (metricColumns.value.length === 0) metricColumns.value = cols

    // 默认赋值
    chartForm.value.dimension = dimensionColumns.value[0]?.name || ''
    chartForm.value.metric = metricColumns.value[0]?.name || ''
    chartForm.value.title = `${ds.Name} - ${chartForm.value.metric}分析`

    await runAggregate()
  } catch (err) {
    console.error('解析数据集字段失败:', err)
  }
}

// 监听参数变化重新试算图表
watch(
  () => [
    chartForm.value.chart_type,
    chartForm.value.dimension,
    chartForm.value.metric,
    chartForm.value.agg_type,
    chartForm.value.sort_order,
    chartForm.value.limit,
  ],
  async () => {
    if (selectedDatasetId.value && chartForm.value.dimension) {
      await runAggregate()
    }
  }
)

async function runAggregate() {
  if (!selectedDatasetId.value || !chartForm.value.dimension) return

  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.aggregateChart({
      dataset_id: selectedDatasetId.value,
      dimension: chartForm.value.dimension,
      metric: chartForm.value.metric,
      agg_type: chartForm.value.agg_type,
      sort_order: chartForm.value.sort_order,
      limit: chartForm.value.limit,
      chart_type: chartForm.value.chart_type,
      title: chartForm.value.title,
    })
    if (res.ok) {
      chartOption.value = res.option
      aggregatedRows.value = res.aggregated_data || []
    }
  } catch (err) {
    errorMsg.value = err.message || '图表聚合计算失败'
  } finally {
    loading.value = false
  }
}

async function handleSaveChart() {
  if (!chartForm.value.title.trim()) {
    errorMsg.value = '请输入图表标题'
    return
  }
  if (!chartOption.value) return

  saving.value = true
  errorMsg.value = ''
  try {
    const res = await api.saveChart({
      dataset_id: selectedDatasetId.value,
      title: chartForm.value.title.trim(),
      chart_type: chartForm.value.chart_type,
      config: chartOption.value,
    })
    if (res.ok) {
      successMsg.value = `图表「${chartForm.value.title}」保存成功！`
      emit('saved', res)
      setTimeout(() => {
        emit('close')
      }, 1400)
    }
  } catch (err) {
    errorMsg.value = err.message || '保存图表失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="visible" class="builder-modal">
    <div class="builder-overlay" @click="emit('close')" />

    <div class="builder-dialog rise">
      <header class="builder-header">
        <div class="header-title-group">
          <h3 class="builder-title">图表可视化工作台</h3>
          <span class="badge badge--brand">第 5 阶段 · 图表构建器</span>
        </div>
        <button class="btn-close" type="button" @click="emit('close')">✕</button>
      </header>

      <div class="builder-body">
        <!-- 无数据集引导 -->
        <div v-if="datasetList.length === 0 && !loading" class="no-data-hint">
          <div class="hint-icon">📂</div>
          <h4>您名下暂无可用的数据集</h4>
          <p>请先在工作台点击「上传表格 / 智能嗅探预览」，清洗并入库一份数据后再来创建图表。</p>
          <button class="btn-primary" type="button" @click="emit('close')">知道了，先去清洗数据</button>
        </div>

        <div v-else class="builder-layout">
          <!-- 左侧：参数控制面板 -->
          <div class="builder-sidebar">
            <!-- 典型预设模板（老师一键套用） -->
            <div class="preset-section">
              <div class="preset-title">💡 老师/小白一键套用典型图表：</div>
              <div class="preset-buttons">
                <button
                  v-for="(p, idx) in presetTemplates"
                  :key="idx"
                  class="preset-pill-btn"
                  type="button"
                  @click="applyPreset(p)"
                >
                  <span class="preset-name">{{ p.title }}</span>
                  <span class="preset-tag">{{ p.chart_type === 'pie' ? '环形图' : p.chart_type === 'horizontal_bar' ? '动态榜' : p.chart_type === 'line' ? '走势图' : '对比图' }}</span>
                </button>
              </div>
            </div>

            <!-- 1. 选择数据集 -->
            <div class="form-group">
              <label class="form-label">选择数据源：</label>
              <select
                :value="selectedDatasetId"
                class="form-select"
                @change="selectDataset(Number($event.target.value))"
              >
                <option v-for="d in datasetList" :key="d.DatasetID" :value="d.DatasetID">
                  {{ d.Name }} ({{ d.RowTotal }} 行)
                </option>
              </select>
            </div>

            <!-- 2. 选择图表类型 -->
            <div class="form-group">
              <label class="form-label">图表类型：</label>
              <div class="chart-type-grid">
                <button
                  v-for="opt in chartTypeOptions"
                  :key="opt.value"
                  class="type-card-btn"
                  :class="{ 'is-selected': chartForm.chart_type === opt.value }"
                  type="button"
                  @click="chartForm.chart_type = opt.value"
                >
                  <span class="type-icon">{{ opt.icon }}</span>
                  <span class="type-name">{{ opt.label }}</span>
                </button>
              </div>
            </div>

            <!-- 3. 维度与指标选择 -->
            <div class="form-group">
              <label class="form-label">分类维度（X 轴 / 扇区分组）：</label>
              <select v-model="chartForm.dimension" class="form-select">
                <option v-for="c in dimensionColumns" :key="c.name" :value="c.name">
                  Aa {{ c.name }}
                </option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">数值指标（Y 轴 / 扇区大小）：</label>
              <select v-model="chartForm.metric" class="form-select">
                <option v-for="c in metricColumns" :key="c.name" :value="c.name">
                  123 {{ c.name }}
                </option>
              </select>
            </div>

            <!-- 4. 聚合算法与排序 -->
            <div class="form-row">
              <div class="form-group flex-1">
                <label class="form-label">聚合算子：</label>
                <select v-model="chartForm.agg_type" class="form-select">
                  <option value="sum">求和 (SUM)</option>
                  <option value="avg">平均值 (AVG)</option>
                  <option value="count">计数 (COUNT)</option>
                  <option value="max">最大值 (MAX)</option>
                  <option value="min">最小值 (MIN)</option>
                </select>
              </div>

              <div class="form-group flex-1">
                <label class="form-label">排行筛选：</label>
                <select v-model="chartForm.limit" class="form-select">
                  <option :value="5">Top 5</option>
                  <option :value="10">Top 10</option>
                  <option :value="20">Top 20</option>
                  <option :value="0">全量显示</option>
                </select>
              </div>
            </div>

            <!-- 图表标题 -->
            <div class="form-group">
              <label class="form-label">图表标题：</label>
              <input v-model="chartForm.title" type="text" class="form-input" placeholder="输入标题" />
            </div>

            <div class="sidebar-actions">
              <button
                class="btn-primary btn-block"
                type="button"
                :disabled="saving"
                @click="handleSaveChart"
              >
                <span v-if="saving" class="loading-spinner" />
                <span v-else>保存此图表到库 📊</span>
              </button>
            </div>

            <div v-if="errorMsg" class="error-strip">⚠️ {{ errorMsg }}</div>
            <div v-if="successMsg" class="success-strip">🎉 {{ successMsg }}</div>
          </div>

          <!-- 右侧：实时图表画板与预览 -->
          <div class="builder-preview-panel">
            <div class="preview-panel-head">
              <div class="preview-title">
                <strong>画布预览：</strong>
                <span>{{ chartForm.title }}</span>
              </div>
              <span class="badge badge--brass">墨衡双皮肤适配</span>
            </div>

            <div class="chart-canvas-area">
              <div v-if="loading" class="chart-canvas-loading">
                <span class="loading-spinner" /> 正在根据维度与指标实时聚合计算...
              </div>
              <EChart
                v-else-if="chartOption"
                class="builder-chart-instance"
                :option="chartOption"
                :theme-name="chartThemeName"
              />
              <div v-else class="chart-canvas-empty">
                请在左侧选定分类维度与指标生成图表
              </div>
            </div>

            <!-- 聚合结果前置预览表 -->
            <div v-if="aggregatedRows.length > 0" class="agg-data-summary">
              <span class="agg-summary-title">聚合计算明细数据（前 {{ aggregatedRows.length }} 项）：</span>
              <div class="agg-tags-scroll">
                <span
                  v-for="(row, idx) in aggregatedRows"
                  :key="idx"
                  class="agg-pill"
                >
                  <strong>{{ row.dimension }}</strong>: {{ row.value }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.builder-modal {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-4);
}

.builder-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(4px);
}

.builder-dialog {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1100px;
  height: 88vh;
  display: flex;
  flex-direction: column;
  background: var(--ink-850);
  border: 1px solid var(--line-1);
  border-radius: var(--r-3);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.builder-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--line-1);
}

.header-title-group {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.builder-title {
  margin: 0;
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--text-1);
}

.btn-close {
  background: transparent;
  border: none;
  font-size: var(--fs-16);
  color: var(--text-3);
  cursor: pointer;
  padding: var(--sp-1) var(--sp-2);
  border-radius: var(--r-1);
}
.btn-close:hover {
  color: var(--text-1);
  background: var(--line-1);
}

.builder-body {
  flex: 1;
  overflow: hidden;
  display: flex;
}

.no-data-hint {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-3);
  text-align: center;
  padding: var(--sp-6);
}

.hint-icon {
  font-size: 3.5rem;
}

.no-data-hint h4 {
  margin: 0;
  font-size: var(--fs-16);
  color: var(--text-1);
}

.no-data-hint p {
  color: var(--text-3);
  font-size: var(--fs-13);
  max-width: 420px;
  line-height: 1.6;
}

/* 左右分栏 */
.builder-layout {
  flex: 1;
  display: flex;
  height: 100%;
  overflow: hidden;
}

.builder-sidebar {
  width: 340px;
  background: var(--ink-900);
  border-right: 1px solid var(--line-1);
  padding: var(--sp-4);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.preset-section {
  background: var(--brand-soft);
  border: 1px solid var(--brand-line);
  border-radius: var(--r-2);
  padding: var(--sp-2) var(--sp-3);
}

.preset-title {
  font-size: var(--fs-11);
  font-weight: 600;
  color: var(--brand-text);
  margin-bottom: var(--sp-2);
}

.preset-buttons {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preset-pill-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px var(--sp-2);
  background: var(--ink-850);
  border: 1px solid var(--line-1);
  border-radius: var(--r-1);
  cursor: pointer;
  text-align: left;
  transition: all var(--dur-1) var(--ease);
}

.preset-pill-btn:hover {
  border-color: var(--brand-500);
  transform: translateX(2px);
}

.preset-name {
  font-size: var(--fs-11);
  color: var(--text-1);
  font-weight: 500;
}

.preset-tag {
  font-size: 10px;
  color: var(--brass-text);
  background: var(--brass-soft);
  padding: 1px 4px;
  border-radius: 2px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.form-row {
  display: flex;
  gap: var(--sp-2);
}

.flex-1 {
  flex: 1;
}

.form-label {
  font-size: var(--fs-12);
  color: var(--text-2);
  font-weight: 500;
}

.form-select,
.form-input {
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  background: var(--ink-850);
  border: 1px solid var(--line-2);
  border-radius: var(--r-1);
  color: var(--text-1);
  font-size: var(--fs-13);
}

.form-select:focus,
.form-input:focus {
  outline: none;
  border-color: var(--brand-500);
}

/* 图表类型按钮卡片 */
.chart-type-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-2);
}

.type-card-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--line-1);
  background: var(--ink-850);
  border-radius: var(--r-1);
  cursor: pointer;
  color: var(--text-2);
  font-size: var(--fs-12);
  transition: all var(--dur-1) var(--ease);
}

.type-card-btn:hover {
  border-color: var(--brand-text);
}

.type-card-btn.is-selected {
  border-color: var(--brand-500);
  background: var(--brand-soft);
  color: var(--brand-text);
  font-weight: 600;
}

.type-icon {
  font-size: 1.1rem;
}

.sidebar-actions {
  margin-top: var(--sp-3);
}

.btn-block {
  width: 100%;
  padding: var(--sp-3);
  font-size: var(--fs-14);
}

.error-strip {
  font-size: var(--fs-12);
  color: var(--danger);
  background: rgba(239, 68, 68, 0.1);
  padding: var(--sp-2);
  border-radius: var(--r-1);
}

.success-strip {
  font-size: var(--fs-12);
  color: var(--ok);
  background: rgba(16, 185, 129, 0.1);
  padding: var(--sp-2);
  border-radius: var(--r-1);
}

/* 右侧画板 */
.builder-preview-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: var(--sp-4);
  background: var(--ink-850);
  overflow: hidden;
}

.preview-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-3);
  padding-bottom: var(--sp-2);
  border-bottom: 1px solid var(--line-1);
}

.preview-title {
  font-size: var(--fs-14);
  color: var(--text-1);
}

.preview-title strong {
  color: var(--text-3);
}

.chart-canvas-area {
  flex: 1;
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
  background: var(--ink-900);
  position: relative;
  overflow: hidden;
}

.builder-chart-instance {
  width: 100%;
  height: 100%;
}

.chart-canvas-loading,
.chart-canvas-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: var(--fs-13);
  gap: var(--sp-2);
}

/* 聚合数据摘要条 */
.agg-data-summary {
  margin-top: var(--sp-3);
  padding-top: var(--sp-2);
  border-top: 1px solid var(--line-1);
}

.agg-summary-title {
  font-size: var(--fs-11);
  color: var(--text-3);
  margin-bottom: var(--sp-1);
  display: block;
}

.agg-tags-scroll {
  display: flex;
  gap: var(--sp-2);
  overflow-x: auto;
  white-space: nowrap;
}

.agg-pill {
  font-size: var(--fs-11);
  padding: 2px var(--sp-2);
  border: 1px solid var(--line-1);
  background: var(--ink-900);
  border-radius: var(--r-1);
  color: var(--text-2);
}

.agg-pill strong {
  color: var(--text-1);
}
</style>
