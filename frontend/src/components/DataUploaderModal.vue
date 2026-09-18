<script setup>
/**
 * 上传与数据清洗工作台（第 4 阶段完整交付）。
 *
 * 功能链路：
 * 1. 步骤 1：选择/上传文件（内置 4 典型样本或本地文件拖拽）；
 * 2. 步骤 2：智能嗅探与清洗规则配置（开关：向下填充合并单元格、过滤汇总行、过滤空行、格式规范化）；
 * 3. 步骤 3：实时试算对比预览（展示清洗后前 20 行，展示字段推断类型，展示清洗审计日志）；
 * 4. 步骤 4：一键保存入库（正式写入 Datasets 表，与用户绑定）。
 */
import { ref, onMounted, computed, watch } from 'vue'
import { api } from '../api/client.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'saved'])

// 当前阶段步骤：1=选择文件, 2=清洗配置与预览对比, 3=确认入库
const step = ref(1)

// 加载与提示
const loading = ref(false)
const saving = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

// 步骤 1 状态
const activeTab = ref('samples') // 'samples' | 'upload'
const samplesList = ref([])
const currentFile = ref(null)
const previewFilename = ref('')
const selectedSheet = ref('')

// 步骤 2 状态：原始嗅探结果
const rawParsedResult = ref(null)

// 清洗规则开关
const cleanRules = ref({
  fill_down_merged: true,
  filter_summary_rows: true,
  filter_empty_rows: true,
  auto_convert_numbers: true,
})

// 清洗后试算结果
const cleanedResult = ref(null)

// 保存数据集表单
const datasetName = ref('')

onMounted(async () => {
  await loadSamples()
})

async function loadSamples() {
  try {
    const res = await api.listSamples()
    if (res.ok) {
      samplesList.value = res.samples || []
    }
  } catch (err) {
    console.error('加载样本列表失败:', err)
  }
}

// 监听开关变动，自动重新试算清洗结果
watch(
  () => [cleanRules.value.fill_down_merged, cleanRules.value.filter_summary_rows, cleanRules.value.filter_empty_rows, cleanRules.value.auto_convert_numbers],
  async () => {
    if (step.value >= 2 && rawParsedResult.value) {
      await runCleanPreview()
    }
  }
)

// 快速预览内置样本
async function handleSelectSample(sample) {
  loading.value = true
  errorMsg.value = ''
  currentFile.value = null
  previewFilename.value = sample.filename
  try {
    const res = await api.previewSample(sample.filename)
    if (res.ok) {
      rawParsedResult.value = res.data
      selectedSheet.value = res.data.current_sheet || ''
      datasetName.value = sample.title.split('（')[0] || sample.filename.replace(/\.[^/.]+$/, '')
      step.value = 2
      await runCleanPreview()
    }
  } catch (err) {
    errorMsg.value = err.message || '样本解析失败'
  } finally {
    loading.value = false
  }
}

// 本地文件上传
async function handleFileChange(event) {
  const file = event.target.files?.[0]
  if (!file) return
  await processUploadedFile(file)
}

function handleDrop(event) {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  processUploadedFile(file)
}

function handleDragOver(event) {
  event.preventDefault()
}

async function processUploadedFile(file) {
  const name = file.name.toLowerCase()
  if (!name.endsWith('.csv') && !name.endsWith('.xlsx') && !name.endsWith('.txt')) {
    errorMsg.value = '仅支持 .csv、.xlsx 或 .txt 格式的表格文件'
    return
  }

  loading.value = true
  errorMsg.value = ''
  currentFile.value = file
  previewFilename.value = file.name

  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await api.previewDataset(formData)
    if (res.ok) {
      rawParsedResult.value = res.data
      selectedSheet.value = res.data.current_sheet || ''
      datasetName.value = file.name.replace(/\.[^/.]+$/, '')
      step.value = 2
      await runCleanPreview()
    }
  } catch (err) {
    errorMsg.value = err.message || '文件解析失败'
  } finally {
    loading.value = false
  }
}

// 切换 Excel 工作表
async function handleSheetChange(newSheet) {
  if (!newSheet || newSheet === rawParsedResult.value?.current_sheet) return
  loading.value = true
  errorMsg.value = ''

  try {
    let res
    if (currentFile.value) {
      const formData = new FormData()
      formData.append('file', currentFile.value)
      formData.append('sheet_name', newSheet)
      res = await api.previewExcelSheet(formData)
    } else {
      res = await api.previewSample(previewFilename.value, newSheet)
    }
    if (res?.ok) {
      rawParsedResult.value = res.data
      selectedSheet.value = res.data.current_sheet || ''
      await runCleanPreview()
    }
  } catch (err) {
    errorMsg.value = err.message || '工作表切换失败'
  } finally {
    loading.value = false
  }
}

// 执行清洗试算
async function runCleanPreview() {
  if (!rawParsedResult.value) return
  try {
    const res = await api.cleanPreview({
      headers: rawParsedResult.value.headers,
      // 送全量矩阵清洗（后端已回传 raw_matrix）；缺失时退回预览矩阵，绝不比原来更差
      raw_matrix: rawParsedResult.value.raw_matrix ?? rawParsedResult.value.raw_preview_matrix,
      ...cleanRules.value,
    })
    if (res.ok) {
      cleanedResult.value = res
    }
  } catch (err) {
    console.error('清洗试算失败:', err)
  }
}

// 保存入库
async function handleSaveToDatabase() {
  if (!datasetName.value.trim()) {
    errorMsg.value = '请输入数据集名称'
    return
  }
  if (!cleanedResult.value) return

  saving.value = true
  errorMsg.value = ''

  try {
    const res = await api.saveDataset({
      name: datasetName.value.trim(),
      source_file_name: previewFilename.value,
      source_sheet: selectedSheet.value || null,
      columns: cleanedResult.value.columns,
      // 入库用清洗后【全量】行（clean-preview 现回传 rows）；老响应无 rows 才退回 preview
      rows: cleanedResult.value.rows ?? cleanedResult.value.preview_rows,
      cleaning_log: cleanedResult.value.cleaning_logs,
    })
    if (res.ok) {
      successMsg.value = res.message
      emit('saved', res)
      setTimeout(() => {
        handleReset()
        emit('close')
      }, 1500)
    }
  } catch (err) {
    errorMsg.value = err.message || '保存入库失败'
  } finally {
    saving.value = false
  }
}

function handleReset() {
  step.value = 1
  rawParsedResult.value = null
  cleanedResult.value = null
  previewFilename.value = ''
  currentFile.value = null
  errorMsg.value = ''
  successMsg.value = ''
}
</script>

<template>
  <div v-if="visible" class="uploader-modal">
    <div class="uploader-overlay" @click="emit('close')" />

    <div class="uploader-dialog rise">
      <!-- 弹窗顶栏 -->
      <header class="uploader-header">
        <div class="uploader-title-group">
          <h3 class="uploader-title">数据清洗与导入工作台</h3>
          <span class="badge badge--brand">第 4 阶段 · 全功能</span>
        </div>
        <div class="step-indicator">
          <span :class="{ 'is-active': step === 1 }">1. 选择文件</span>
          <span class="step-sep">→</span>
          <span :class="{ 'is-active': step === 2 }">2. 智能清洗与对比</span>
        </div>
        <button class="btn-close" type="button" @click="emit('close')">✕</button>
      </header>

      <div class="uploader-body">
        <!-- 课设答辩/新手向导贴士条 -->
        <div class="teacher-guide-banner">
          <span class="guide-badge">💡 快速体验指南</span>
          <span class="guide-text">
            老师/评委无需自备文件：直接点击下方<strong>推荐样本卡片</strong>，系统会自动模拟“乱码修复”、“26处合并单元格自动填充”与“全空行过滤”的全过程！
          </span>
        </div>

        <!-- 步骤 1：文件选择 -->
        <div v-if="step === 1" class="uploader-selector">
          <div class="uploader-tabs">
            <button
              class="tab-btn"
              :class="{ 'is-active': activeTab === 'samples' }"
              type="button"
              @click="activeTab = 'samples'"
            >
              一键使用课设预置样本（推荐）
            </button>
            <button
              class="tab-btn"
              :class="{ 'is-active': activeTab === 'upload' }"
              type="button"
              @click="activeTab = 'upload'"
            >
              上传本地文件 (.csv / .xlsx)
            </button>
          </div>

          <!-- 预置样本 -->
          <div v-if="activeTab === 'samples'" class="samples-grid">
            <div
              v-for="s in samplesList"
              :key="s.filename"
              class="sample-card"
              @click="handleSelectSample(s)"
            >
              <div class="sample-card__head">
                <span class="sample-card__title">{{ s.title }}</span>
                <span class="badge badge--brass">{{ s.badge }}</span>
              </div>
              <p class="sample-card__desc">{{ s.description }}</p>
              <div class="sample-card__foot">
                <span class="sample-card__meta">{{ s.filename }} · {{ (s.size_bytes / 1024).toFixed(1) }} KB</span>
                <span class="sample-card__action">进入清洗流水线 →</span>
              </div>
            </div>
          </div>

          <!-- 本地拖拽上传 -->
          <div
            v-if="activeTab === 'upload'"
            class="upload-dropzone"
            @dragover="handleDragOver"
            @drop="handleDrop"
          >
            <div class="dropzone-icon">📁</div>
            <p class="dropzone-title">拖拽文件到这里，或点击选择文件</p>
            <p class="dropzone-hint">
              支持 <strong>.csv</strong>（自动修复 GBK 乱码）与 <strong>.xlsx</strong>（自动探测多 Sheet 与合并单元格），单文件 ≤ 5MB
            </p>
            <label class="btn-primary dropzone-btn">
              选择本地表格
              <input
                type="file"
                accept=".csv,.xlsx,.txt"
                class="file-input-hidden"
                @change="handleFileChange"
              />
            </label>
          </div>

          <div v-if="loading" class="uploader-loading">
            <span class="loading-spinner" /> 正在智能嗅探文件格式与字符编码...
          </div>
          <div v-if="errorMsg" class="uploader-error">
            ⚠️ {{ errorMsg }}
          </div>
        </div>

        <!-- 步骤 2：清洗规则配置与对比预览 -->
        <div v-else-if="step === 2 && rawParsedResult" class="cleaning-workbench">
          <!-- 顶部元数据与工作表切换 -->
          <div class="meta-strip">
            <div class="meta-tags">
              <span class="meta-file">📄 <strong>{{ previewFilename }}</strong></span>
              <span class="badge">{{ rawParsedResult.file_type.toUpperCase() }}</span>
              <span class="badge badge--brand">编码: {{ rawParsedResult.encoding }}</span>
              <span class="badge badge--brass">原始 {{ rawParsedResult.total_rows }} 行 · {{ rawParsedResult.total_columns }} 列</span>
            </div>

            <div v-if="rawParsedResult.sheets?.length > 1" class="sheet-switch">
              <span>工作表:</span>
              <select :value="selectedSheet" class="sheet-dropdown" @change="handleSheetChange($event.target.value)">
                <option v-for="sh in rawParsedResult.sheets" :key="sh" :value="sh">{{ sh }}</option>
              </select>
            </div>

            <button class="btn-ghost btn-sm" type="button" @click="handleReset">重新选择文件</button>
          </div>

          <!-- 清洗规则控制栏 -->
          <div class="cleaning-controls">
            <div class="controls-title">⚙️ 智能清洗规则配置（点击开关实时试算）：</div>
            <div class="rules-grid">
              <label class="rule-toggle">
                <input v-model="cleanRules.fill_down_merged" type="checkbox" />
                <span class="toggle-box" />
                <span class="rule-label">
                  <strong>向下填充合并单元格</strong>
                  <small>修复 Excel 跨行合并导致的下方空白</small>
                </span>
              </label>

              <label class="rule-toggle">
                <input v-model="cleanRules.filter_summary_rows" type="checkbox" />
                <span class="toggle-box" />
                <span class="rule-label">
                  <strong>剔除合计/汇总行</strong>
                  <small>过滤总计、合计行，防止图表统计膨胀</small>
                </span>
              </label>

              <label class="rule-toggle">
                <input v-model="cleanRules.filter_empty_rows" type="checkbox" />
                <span class="toggle-box" />
                <span class="rule-label">
                  <strong>过滤全空行</strong>
                  <small>移除非法空行数据</small>
                </span>
              </label>

              <label class="rule-toggle">
                <input v-model="cleanRules.auto_convert_numbers" type="checkbox" />
                <span class="toggle-box" />
                <span class="rule-label">
                  <strong>数值规范化与编号保留</strong>
                  <small>剥离千分位/货币符，保留学号前导0</small>
                </span>
              </label>
            </div>
          </div>

          <!-- 清洗审计日志展示 -->
          <div v-if="cleanedResult?.cleaning_logs?.length" class="audit-strip">
            <div class="audit-head">📋 清洗效果实时审计（已自动处理）：</div>
            <div class="audit-badges">
              <span
                v-for="(log, idx) in cleanedResult.cleaning_logs"
                :key="idx"
                class="audit-pill"
              >
                ✅ {{ log.title }}: {{ log.desc }}
              </span>
            </div>
          </div>

          <!-- 清洗后数据表格预览 -->
          <div class="table-card">
            <div class="table-card__head">
              <span>清洗后数据预览（共 {{ cleanedResult?.total_rows ?? '…' }} 行 · 展示前 20 行）：</span>
              <span class="table-legend">
                <span class="legend-dot is-metric" /> 数值指标
                <span class="legend-dot is-dim" /> 文本维度
              </span>
            </div>

            <div class="preview-table-container">
              <table v-if="cleanedResult" class="preview-table">
                <thead>
                  <tr>
                    <th class="col-index">#</th>
                    <th
                      v-for="col in cleanedResult.columns"
                      :key="col.name"
                      class="col-header"
                      :class="{ 'is-metric-head': col.is_metric, 'is-dim-head': col.is_dimension }"
                    >
                      <div class="th-content">
                        <span>{{ col.name }}</span>
                        <span class="col-type-tag">{{ col.type === 'number' ? '123 数值' : 'Aa 文本' }}</span>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in cleanedResult.preview_rows" :key="idx">
                    <td class="col-index num">{{ idx + 1 }}</td>
                    <td
                      v-for="col in cleanedResult.columns"
                      :key="col.name"
                      :class="{ 'is-metric-cell': col.is_metric }"
                    >
                      {{ row[col.name] !== '' && row[col.name] !== null ? row[col.name] : '-' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 底部确认入库表单 -->
          <div class="save-footer">
            <div class="save-input-group">
              <label for="ds-name">保存为数据集：</label>
              <input
                id="ds-name"
                v-model="datasetName"
                type="text"
                class="save-input"
                placeholder="请输入数据集名称（如：2024电商销售表）"
              />
            </div>
            <div class="save-actions">
              <button class="btn-ghost" type="button" @click="handleReset">重新选择文件</button>
              <button
                class="btn-primary"
                type="button"
                :disabled="saving"
                @click="handleSaveToDatabase"
              >
                <span v-if="saving" class="loading-spinner" />
                <span v-else>确认清洗并保存入库 💾</span>
              </button>
            </div>
          </div>

          <div v-if="errorMsg" class="uploader-error">
            ⚠️ {{ errorMsg }}
          </div>
          <div v-if="successMsg" class="uploader-success">
            🎉 {{ successMsg }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.uploader-modal {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-4);
}

.uploader-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(4px);
}

.uploader-dialog {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1040px;
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  background: var(--ink-850);
  border: 1px solid var(--line-1);
  border-radius: var(--r-3);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.uploader-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--line-1);
}

.uploader-title-group {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.uploader-title {
  margin: 0;
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--text-1);
}

.teacher-guide-banner {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  background: var(--brand-soft);
  border: 1px solid var(--brand-line);
  border-radius: var(--r-2);
  margin-bottom: var(--sp-4);
  font-size: var(--fs-12);
  color: var(--text-2);
}

.guide-badge {
  background: var(--brand-fill);
  color: var(--on-brand);
  padding: 1px 6px;
  border-radius: var(--r-1);
  font-weight: 600;
  font-size: 11px;
  white-space: nowrap;
}

.guide-text strong {
  color: var(--brand-text);
}

.step-indicator {
  font-size: var(--fs-13);
  color: var(--text-3);
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.step-indicator .is-active {
  color: var(--brand-text);
  font-weight: 600;
}

.step-sep {
  color: var(--text-3);
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

.uploader-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-5);
}

/* Tabs */
.uploader-tabs {
  display: flex;
  gap: var(--sp-2);
  border-bottom: 1px solid var(--line-1);
  margin-bottom: var(--sp-5);
}

.tab-btn {
  padding: var(--sp-2) var(--sp-4);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-3);
  font-size: var(--fs-14);
  cursor: pointer;
  font-weight: 500;
  transition: all var(--dur-1) var(--ease);
}

.tab-btn.is-active {
  color: var(--brand-text);
  border-bottom-color: var(--brand-500);
}

/* 预置样本卡片网格 */
.samples-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-4);
}

@media (max-width: 640px) {
  .samples-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.sample-card {
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
  padding: var(--sp-4);
  background: var(--ink-900);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  transition: border-color var(--dur-1) var(--ease), transform var(--dur-1) var(--ease);
}

.sample-card:hover {
  border-color: var(--brand-500);
  transform: translateY(-2px);
}

.sample-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sample-card__title {
  font-size: var(--fs-14);
  font-weight: 600;
  color: var(--text-1);
}

.sample-card__desc {
  font-size: var(--fs-12);
  color: var(--text-3);
  line-height: 1.6;
  flex: 1;
  margin: 0;
}

.sample-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
}

.sample-card__meta {
  color: var(--text-3);
}

.sample-card__action {
  color: var(--brand-text);
  font-weight: 500;
}

/* 拖拽上传 */
.upload-dropzone {
  border: 2px dashed var(--line-2);
  border-radius: var(--r-3);
  padding: var(--sp-8) var(--sp-4);
  text-align: center;
  background: var(--ink-900);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
}

.dropzone-icon {
  font-size: 3rem;
}

.dropzone-title {
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--text-1);
  margin: 0;
}

.dropzone-hint {
  font-size: var(--fs-13);
  color: var(--text-3);
  max-width: 500px;
  line-height: 1.6;
  margin: 0;
}

.file-input-hidden {
  display: none;
}

.dropzone-btn {
  margin-top: var(--sp-2);
  cursor: pointer;
}

.uploader-loading {
  margin-top: var(--sp-4);
  text-align: center;
  font-size: var(--fs-13);
  color: var(--brand-text);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
}

.uploader-error {
  margin-top: var(--sp-4);
  padding: var(--sp-3);
  border-radius: var(--r-1);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid var(--danger);
  color: var(--danger);
  font-size: var(--fs-13);
}

.uploader-success {
  margin-top: var(--sp-4);
  padding: var(--sp-3);
  border-radius: var(--r-1);
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid var(--ok);
  color: var(--ok);
  font-size: var(--fs-13);
}

/* 清洗工作台控制栏 */
.meta-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  background: var(--ink-900);
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
  margin-bottom: var(--sp-3);
}

.meta-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  font-size: var(--fs-13);
}

.meta-file {
  color: var(--text-1);
}

.sheet-switch {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-13);
  color: var(--text-2);
}

.sheet-dropdown {
  background: var(--ink-850);
  border: 1px solid var(--line-1);
  color: var(--text-1);
  border-radius: var(--r-1);
  padding: 2px 8px;
  font-size: var(--fs-12);
}

.btn-sm {
  padding: var(--sp-1) var(--sp-3);
  font-size: var(--fs-12);
}

/* 规则开关网格 */
.cleaning-controls {
  padding: var(--sp-3) var(--sp-4);
  background: var(--ink-900);
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
  margin-bottom: var(--sp-3);
}

.controls-title {
  font-size: var(--fs-13);
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: var(--sp-3);
}

.rules-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
}

@media (max-width: 680px) {
  .rules-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.rule-toggle {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  cursor: pointer;
  user-select: none;
}

.rule-toggle input {
  display: none;
}

.toggle-box {
  width: 18px;
  height: 18px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-1);
  background: var(--ink-850);
  margin-top: 2px;
  flex-shrink: 0;
  position: relative;
  transition: all var(--dur-1) var(--ease);
}

.rule-toggle input:checked + .toggle-box {
  background: var(--brand-fill);
  border-color: var(--brand-fill);
}

.rule-toggle input:checked + .toggle-box::after {
  content: '✓';
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--on-brand);
  font-size: 11px;
  font-weight: bold;
}

.rule-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rule-label strong {
  font-size: var(--fs-13);
  color: var(--text-1);
}

.rule-label small {
  font-size: var(--fs-11);
  color: var(--text-3);
}

/* 审计条目 */
.audit-strip {
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: var(--r-2);
  padding: var(--sp-3) var(--sp-4);
  margin-bottom: var(--sp-3);
}

.audit-head {
  font-size: var(--fs-12);
  font-weight: 600;
  color: var(--ok);
  margin-bottom: var(--sp-2);
}

.audit-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}

.audit-pill {
  font-size: var(--fs-12);
  color: var(--text-1);
  background: var(--ink-850);
  padding: 2px var(--sp-2);
  border-radius: var(--r-1);
  border: 1px solid var(--line-1);
}

/* 表格卡片 */
.table-card {
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
  overflow: hidden;
  background: var(--ink-900);
  margin-bottom: var(--sp-4);
}

.table-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-2) var(--sp-4);
  border-bottom: 1px solid var(--line-1);
  font-size: var(--fs-12);
  color: var(--text-2);
}

.table-legend {
  display: flex;
  gap: var(--sp-3);
}

.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.legend-dot.is-metric {
  background: var(--brass-400);
}
.legend-dot.is-dim {
  background: var(--brand-400);
}

.preview-table-container {
  overflow-x: auto;
  max-height: 360px;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-12);
  white-space: nowrap;
}

.preview-table th,
.preview-table td {
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--line-1);
  border-right: 1px solid var(--line-1);
  text-align: left;
}

.preview-table th {
  background: var(--ink-800);
  color: var(--text-2);
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
}

.th-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}

.col-type-tag {
  font-size: 10px;
  font-weight: normal;
  padding: 1px 4px;
  border-radius: 2px;
  background: var(--line-1);
}

.is-metric-head .col-type-tag {
  color: var(--brass-text);
  background: rgba(245, 158, 11, 0.15);
}

.is-dim-head .col-type-tag {
  color: var(--brand-text);
  background: var(--brand-soft);
}

.is-metric-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--brass-text);
}

.col-index {
  width: 40px;
  text-align: center;
  color: var(--text-3);
}

/* 底部入库表单 */
.save-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-3);
  padding: var(--sp-4);
  background: var(--ink-900);
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
}

.save-input-group {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-13);
  color: var(--text-1);
  flex: 1;
}

.save-input {
  flex: 1;
  max-width: 320px;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--line-2);
  border-radius: var(--r-1);
  background: var(--ink-850);
  color: var(--text-1);
  font-size: var(--fs-13);
}

.save-input:focus {
  border-color: var(--brand-500);
  outline: none;
}

.save-actions {
  display: flex;
  gap: var(--sp-2);
}
</style>
