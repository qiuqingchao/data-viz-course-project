<script setup>
/**
 * 工作台（第 3 阶段起接入了真实账号）。
 *
 * 三件事：
 *   1. 显示"你是谁"（来自后端的真实身份，不是前端随便写的字符串）；
 *   2. 显示"你有多少数据"（数据集/图表/大屏的条数，真实从数据库查的）；
 *   3. 把开发进度如实摆在页面上 —— 做了就是做了，没做就是没做，
 *      避免演示时被问"这个功能在哪"却答不上来。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import BrandMark from '../components/BrandMark.vue'
import ChartBuilderModal from '../components/ChartBuilderModal.vue'
import DashboardDesignerModal from '../components/DashboardDesignerModal.vue'
import DashboardViewerModal from '../components/DashboardViewerModal.vue'
import DataUploaderModal from '../components/DataUploaderModal.vue'
import PanelCard from '../components/PanelCard.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import StatCard from '../components/StatCard.vue'
import { useAuth } from '../composables/useAuth.js'
import { api } from '../api/client.js'

const props = defineProps({
  username: { type: String, default: '访客' },
})

const emit = defineEmits(['exit', 'open-demo'])

const { user, displayName, logout, fetchOverview } = useAuth()

/** 上传弹窗与图表构建器显隐 */
const uploaderVisible = ref(false)
const chartBuilderVisible = ref(false)

/** 大屏：设计器 / 放映查看器 / 我的大屏列表 */
const designerVisible = ref(false)
const editingDashId = ref(0)
const viewerVisible = ref(false)
const viewingDashId = ref(0)
const dashboards = ref([])
const dashError = ref('')
/** 两击确认删除：第一次点击进入"确认删除？"状态，4 秒无操作自动撤销 */
const pendingDeleteId = ref(0)
let pendingDeleteTimer = null

/** 数据概况：null=还没拿到 */
const counts = ref(null)
const loadError = ref('')

/** 优先显示后端返回的真实身份，退回路由传来的名字 */
const who = computed(() => displayName.value || props.username)

onMounted(async () => {
  try {
    const info = await fetchOverview()
    counts.value = info.counts
  } catch (err) {
    loadError.value = err.message
  }
  refreshDashboards()
})

async function refreshDashboards() {
  try {
    const res = await api.listMyDashboards()
    dashboards.value = res.dashboards || []
    dashError.value = ''
  } catch (err) {
    dashError.value = err.message || '大屏列表加载失败'
  }
}

function openDesigner(id = 0) {
  editingDashId.value = id
  designerVisible.value = true
}

function openViewer(id) {
  viewingDashId.value = id
  viewerVisible.value = true
}

/* ---------- 只读分享（第 7 阶段） ----------
 * 交互刻意做"笨"：点分享 → 出链接 → 复制走人；点关闭 → 链接立刻作废。
 * 链接是"钥匙"不是权限系统：token 由后端 secrets 随机生成，关闭即失效。 */
const shareOpenId = ref(0) // 当前展开分享面板的大屏 ID（0 = 收起）
const shareLink = ref('')
const shareBusy = ref(false)
const shareCopied = ref(false)
let copyTipTimer = 0

async function toggleShare(id) {
  if (shareOpenId.value === id) {
    shareOpenId.value = 0
    return
  }
  shareBusy.value = true
  try {
    const res = await api.shareDashboard(id)
    shareLink.value = `${window.location.origin}${res.share_path}`
    shareOpenId.value = id
    // 乐观点亮徽标：本地先改，再异步和后端对齐 —— 免得列表往返期间徽标慢半拍
    const local = dashboards.value.find((d) => d.DashboardID === id)
    if (local) local.IsPublic = true
    await refreshDashboards() // 让"已公开"徽标与后端权威状态保持一致
  } catch (err) {
    dashError.value = err.message || '开启分享失败'
  } finally {
    shareBusy.value = false
  }
}

async function copyShareLink() {
  try {
    await navigator.clipboard.writeText(shareLink.value)
  } catch {
    // 剪贴板 API 在非 https/旧内核会被拒：临时输入框 + execCommand 兜底
    const t = document.createElement('textarea')
    t.value = shareLink.value
    document.body.appendChild(t)
    t.select()
    document.execCommand('copy')
    t.remove()
  }
  shareCopied.value = true
  clearTimeout(copyTipTimer)
  copyTipTimer = setTimeout(() => (shareCopied.value = false), 1800)
}

async function revokeShare(id) {
  shareBusy.value = true
  try {
    await api.unshareDashboard(id)
    shareOpenId.value = 0
    const local = dashboards.value.find((d) => d.DashboardID === id)
    if (local) local.IsPublic = false
    await refreshDashboards()
  } catch (err) {
    dashError.value = err.message || '关闭分享失败'
  } finally {
    shareBusy.value = false
  }
}

/* ---------- 一键体验（写库版）与一键清空（第 8 阶段） ----------
 * seed 是一次 HTTP 调用，但后端真的跑完整条管道（清洗→聚合→4 图→大屏）并入库，
 * 生成完立刻自动放映 —— "30 秒走完整个产品"就是给答辩现场准备的。
 * reset 是全局破坏性操作：沿用"点两下"防误删交互，4 秒不确认自动撤销。 */
const demoBusy = ref(false)
const demoArmed = ref(false)
let demoArmTimer = 0

async function refreshAll() {
  const info = await fetchOverview()
  counts.value = info.counts
  await refreshDashboards()
}

async function runDemoSeed() {
  if (demoBusy.value) return
  demoBusy.value = true
  try {
    const res = await api.seedDemo()
    await refreshAll()
    ElMessage.success(res.message || '体验数据已生成')
    openViewer(res.dashboard_id) // 生成即放映：一气呵成
  } catch (err) {
    ElMessage.error(err.message || '体验数据生成失败')
  } finally {
    demoBusy.value = false
  }
}

function askDemoReset() {
  if (demoArmed.value) {
    doDemoReset()
    return
  }
  demoArmed.value = true
  clearTimeout(demoArmTimer)
  demoArmTimer = setTimeout(() => (demoArmed.value = false), 4000)
}

async function doDemoReset() {
  demoArmed.value = false
  clearTimeout(demoArmTimer)
  if (demoBusy.value) return
  demoBusy.value = true
  try {
    const res = await api.resetDemoData()
    shareOpenId.value = 0
    await refreshAll()
    ElMessage.success(res.message || '已清空当前账号数据')
  } catch (err) {
    ElMessage.error(err.message || '清空失败')
  } finally {
    demoBusy.value = false
  }
}

function askDelete(id) {
  if (pendingDeleteId.value === id) {
    doDelete(id)
    return
  }
  pendingDeleteId.value = id
  clearTimeout(pendingDeleteTimer)
  pendingDeleteTimer = setTimeout(() => (pendingDeleteId.value = 0), 4000)
}

async function doDelete(id) {
  pendingDeleteId.value = 0
  clearTimeout(pendingDeleteTimer)
  try {
    await api.deleteDashboard(id)
    await refreshDashboards()
    const info = await fetchOverview()
    counts.value = info.counts
  } catch (err) {
    dashError.value = err.message || '大屏删除失败'
  }
}

async function onDashSaved() {
  await refreshDashboards()
  try {
    const info = await fetchOverview()
    counts.value = info.counts
  } catch (err) {
    console.error('刷新概况失败:', err)
  }
}

async function doLogout() {
  await logout()
  emit('exit')
}

// 数据集保存成功后刷新概况
async function onDatasetSaved() {
  try {
    const info = await fetchOverview()
    counts.value = info.counts
  } catch (err) {
    console.error('刷新概况失败:', err)
  }
}

// 图表保存成功后刷新概况
async function onChartSaved() {
  try {
    const info = await fetchOverview()
    counts.value = info.counts
  } catch (err) {
    console.error('刷新概况失败:', err)
  }
}

const roadmap = [
  { phase: '第 1 阶段', title: '骨架与前后端握手', status: 'done' },
  { phase: '第 2 阶段', title: '视觉方案（双皮肤）+ 一键体验', status: 'done' },
  { phase: '第 3 阶段', title: '接入数据库 + 账号与数据隔离', status: 'done' },
  { phase: '第 4 阶段', title: '数据处理（上传 / 清洗 / 筛选 / 聚合）', status: 'done' },
  { phase: '第 5 阶段', title: '图表模块（常规图 + 创意图）', status: 'done' },
  { phase: '第 6 阶段', title: '大屏组装（拖拽 + 联动）', status: 'done' },
  { phase: '第 7 阶段', title: '导出与分享（PNG / 只读链接）', status: 'done' },
  { phase: '第 8 阶段', title: '一键体验（写库版）+ 一键清空', status: 'done' },
]

const statusText = {
  done: '已完成',
  doing: '进行中',
  todo: '未开始',
}
</script>

<template>
  <div class="wb">
    <header class="appbar">
      <BrandMark compact :show-tagline="false" />
      <div class="appbar__sep" />
      <div class="appbar__title">工作台</div>
      <span class="badge badge--brand">账号已校验</span>
      <span v-if="user?.role" class="badge">{{ user.role === 'demo' ? '演示账号' : '普通账号' }}</span>

      <div class="appbar__spacer" />

      <span class="wb__user">
        当前用户：<strong>{{ who }}</strong>
      </span>
      <ThemeToggle />
      <button class="btn-ghost btn-ghost--brass" type="button" @click="emit('open-demo')">
        打开示例大屏
      </button>
      <button class="btn-ghost" type="button" @click="doLogout">退出登录</button>
    </header>

    <div class="wb__body">
      <PanelCard class="rise" style="--i: 0" title="欢迎回来" :note="`${who}，你已通过数据库校验登录`">
        <p class="wb__lead">
          账号与密码已存在数据库中（密码经 <strong>scrypt 加密</strong>，明文不落盘），
          你创建的每一个数据集、图表、大屏都会记在<strong>你自己的账号</strong>名下，
          其他人看不到。
        </p>

        <div class="wb__stats">
          <StatCard
            label="数据集"
            :display="counts ? String(counts.datasets) : '—'"
            display-unit="个"
            hint="上传并清洗后的数据"
            tone="brand"
          />
          <StatCard
            label="图表"
            :display="counts ? String(counts.charts) : '—'"
            display-unit="张"
            hint="由数据集生成"
            tone="brass"
          />
          <StatCard
            label="大屏"
            :display="counts ? String(counts.dashboards) : '—'"
            display-unit="块"
            hint="拖拽组装而成"
            tone="brand"
          />
        </div>

        <p v-if="loadError" class="wb__lead wb__lead--warn">
          数据概况读取失败：{{ loadError }}
        </p>
        <p v-else-if="counts && counts.datasets === 0" class="wb__lead wb__lead--hint">
          还没有数据 —— 点下方按钮<strong>上传表格 / 智能清洗</strong>，或直接「⚡ 一键体验真实流程」，
          让系统替你把整条管道跑一遍并写进数据库。
        </p>

        <div class="wb__action-row">
          <button class="btn-primary wb__action-btn" type="button" @click="uploaderVisible = true">
            <span class="btn-icon">📤</span>
            <span>上传表格 / 智能清洗</span>
          </button>
          <button
            class="btn-primary wb__action-btn wb__action-btn--brass"
            type="button"
            @click="chartBuilderVisible = true"
          >
            <span class="btn-icon">📊</span>
            <span>新建可视化图表</span>
          </button>
          <button class="wb__cta" type="button" @click="emit('open-demo')">
            <span class="wb__cta-main">一键体验示例大屏</span>
            <span class="wb__cta-sub">8 个省份 · 5 个品类 · 12 个月 · 含动态排名动画</span>
          </button>

          <!-- 第 8 阶段：写库版真实流程体验 + 一键清空（答辩演示专用工具条） -->
          <div class="wb__demo-row">
            <button class="btn-ghost wb__demo-btn" type="button" :disabled="demoBusy" @click="runDemoSeed">
              {{ demoBusy ? '⏳ 管道运行中：清洗 → 建图 → 组屏…' : '⚡ 一键体验真实流程（自动写库 · 约 5 秒）' }}
            </button>
            <button
              class="btn-ghost wb__demo-btn"
              :class="{ 'wb__demo-btn--armed': demoArmed }"
              type="button"
              :disabled="demoBusy"
              @click="askDemoReset"
            >
              {{ demoArmed ? '⚠️ 再点一次：清空本账号全部数据' : '🧹 一键清空我的数据' }}
            </button>
          </div>
          <p class="wb__demo-note">
            体验按钮会在你的账号下<strong>真实生成</strong> 480 行数据集 + 4 张图表 + 1 块大屏并自动放映；
            清空会把本账号数据一并删除（含手工建的），演示完一键复原。
          </p>
        </div>
      </PanelCard>

      <PanelCard class="rise" style="--i: 1" title="我的大屏" note="把已保存的图表拖进 1920×1080 画布组装成大屏，支持全屏放映">
        <div class="wb__dash-head">
          <button class="btn-primary wb__dash-new" type="button" @click="openDesigner(0)">
            <span class="btn-icon">🖥️</span>
            <span>新建数据大屏</span>
          </button>
          <span v-if="dashError" class="wb__dash-err">{{ dashError }}</span>
        </div>

        <div v-if="dashboards.length === 0" class="wb__dash-empty">
          还没有大屏 —— 先保存几张图表，再点上方按钮，10 秒拖出一块能全屏放映的数据大屏。
        </div>
        <div v-else class="wb__dash-grid">
          <div v-for="d in dashboards" :key="d.DashboardID" class="wb__dash-card">
            <div class="wb__dash-card-top">
              <span class="wb__dash-name">{{ d.Title }}</span>
              <span v-if="d.IsPublic" class="badge badge--brass">🔗 已公开</span>
              <span class="badge">{{ d.ItemCount }} 块面板</span>
            </div>
            <div class="wb__dash-meta num">更新 {{ d.UpdatedAt || d.CreatedAt || '—' }}</div>
            <div class="wb__dash-actions">
              <button class="btn-primary btn-sm" type="button" @click="openViewer(d.DashboardID)">
                ▶ 放映
              </button>
              <button class="btn-ghost" type="button" @click="openDesigner(d.DashboardID)">
                编辑
              </button>
              <button
                class="btn-ghost"
                type="button"
                :disabled="shareBusy"
                @click="toggleShare(d.DashboardID)"
              >
                {{ shareOpenId === d.DashboardID ? '收起分享' : '🔗 分享' }}
              </button>
              <button
                class="btn-ghost"
                :class="{ 'wb__dash-del--armed': pendingDeleteId === d.DashboardID }"
                type="button"
                @click="askDelete(d.DashboardID)"
              >
                {{ pendingDeleteId === d.DashboardID ? '确认删除？' : '删除' }}
              </button>
            </div>
            <div v-if="shareOpenId === d.DashboardID" class="wb__dash-share">
              <input class="wb__share-input" readonly :value="shareLink" @focus="$event.target.select()" />
              <button class="btn-ghost" type="button" @click="copyShareLink">
                {{ shareCopied ? '✓ 已复制' : '复制' }}
              </button>
              <button class="btn-ghost wb__share-off" type="button" :disabled="shareBusy" @click="revokeShare(d.DashboardID)">
                关闭分享
              </button>
            </div>
          </div>
        </div>
      </PanelCard>

      <PanelCard class="rise" style="--i: 2" title="开发进度" note="如实标记，未完成的功能不会假装完成">
        <ol class="wb__roadmap">
          <li v-for="item in roadmap" :key="item.phase" :class="`is-${item.status}`">
            <span class="wb__phase num">{{ item.phase }}</span>
            <span class="wb__name">{{ item.title }}</span>
            <span class="wb__status">{{ statusText[item.status] }}</span>
          </li>
        </ol>
      </PanelCard>
    </div>

    <!-- 数据上传与嗅探预览弹窗 -->
    <DataUploaderModal
      :visible="uploaderVisible"
      @close="uploaderVisible = false"
      @saved="onDatasetSaved"
    />

    <!-- 图表构建工作台弹窗 -->
    <ChartBuilderModal
      :visible="chartBuilderVisible"
      @close="chartBuilderVisible = false"
      @saved="onChartSaved"
    />

    <!-- 大屏设计器（dashboard-id>0 为编辑已有大屏） -->
    <DashboardDesignerModal
      :visible="designerVisible"
      :dashboard-id="editingDashId"
      @close="designerVisible = false"
      @saved="onDashSaved"
    />

    <!-- 大屏放映查看器 -->
    <DashboardViewerModal
      :visible="viewerVisible"
      :dashboard-id="viewingDashId"
      @close="viewerVisible = false"
    />
  </div>
</template>

<style scoped>
.wb {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.wb__body {
  padding: var(--sp-6) var(--sp-5);
  max-width: 1080px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.wb__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-4);
  margin: var(--sp-4) 0;
}

.wb__lead--hint {
  color: var(--text-3);
}

.wb__lead--warn {
  color: var(--danger);
}

@media (max-width: 900px) {
  .wb__stats {
    grid-template-columns: minmax(0, 1fr);
  }
}

.wb__user {
  font-size: var(--fs-13);
  color: var(--text-3);
}

.wb__user strong {
  color: var(--text-1);
  font-weight: 600;
}

.wb__lead {
  color: var(--text-2);
  font-size: var(--fs-14);
  line-height: 1.9;
  margin-bottom: var(--sp-5);
}

.wb__lead strong {
  color: var(--brass-text);
}

.wb__action-row {
  display: flex;
  gap: var(--sp-4);
  align-items: stretch;
}

@media (max-width: 760px) {
  .wb__action-row {
    flex-direction: column;
  }
}

/* ── 我的大屏区块 ── */
.wb__dash-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}

.wb__dash-new {
  white-space: nowrap;
}

.wb__dash-err {
  font-size: var(--fs-12);
  color: var(--danger);
}

.wb__dash-empty {
  padding: var(--sp-4);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-2);
  text-align: center;
  font-size: var(--fs-12);
  color: var(--text-3);
  line-height: 1.8;
}

.wb__dash-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--sp-3);
}

.wb__dash-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3);
  background: var(--ink-900);
  border: 1px solid var(--line-1);
  border-radius: var(--r-2);
}

.wb__dash-card:hover {
  border-color: var(--brand-line);
}

.wb__dash-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}

.wb__dash-name {
  font-size: var(--fs-13);
  font-weight: 600;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb__dash-meta {
  font-size: var(--fs-11);
  color: var(--text-3);
}

.wb__dash-actions {
  display: flex;
  gap: var(--sp-2);
  margin-top: 2px;
}

.wb__dash-del--armed {
  color: var(--danger);
  border-color: var(--danger);
}

.wb__dash-share {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border: 1px dashed var(--brand-line);
  border-radius: var(--r-2);
  background: var(--ink-850);
}

.wb__share-input {
  flex: 1;
  min-width: 0;
  padding: 5px 8px;
  font-size: var(--fs-11);
  font-family: var(--font-mono, ui-monospace, Consolas, monospace);
  color: var(--brand-text);
  background: var(--ink-900);
  border: 1px solid var(--line-2);
  border-radius: var(--r-1);
  cursor: text;
}

.wb__share-off {
  color: var(--danger);
}

.wb__action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-5);
  font-size: var(--fs-14);
  font-weight: 600;
  border-radius: var(--r-2);
  cursor: pointer;
  white-space: nowrap;
}

.wb__action-btn--brass {
  background: var(--brass-fill);
}

.wb__action-btn--brass:hover {
  background: var(--brass-fill-hover);
}

.wb__cta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: var(--sp-4) var(--sp-5);
  text-align: left;
  cursor: pointer;
  border-radius: var(--r-2);
  border: 1px solid var(--brand-line);
  background: var(--brand-soft);
  transition: background-color var(--dur-1) var(--ease),
    border-color var(--dur-1) var(--ease);
}

.wb__cta:hover {
  background: rgba(23, 184, 166, 0.18);
  border-color: var(--brand-500);
}

.wb__cta-main {
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--brand-text);
}

.wb__cta-sub {
  font-size: var(--fs-12);
  color: var(--text-3);
}

/* ---------------- 演示工具条（第 8 阶段：写库体验 / 一键清空） ---------------- */
.wb__demo-row {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
  margin-top: var(--sp-3);
}

.wb__demo-btn {
  flex: 1;
  min-width: 200px;
  font-size: var(--fs-12);
}

.wb__demo-btn--armed {
  color: var(--danger);
  border-color: var(--danger);
  animation: demo-armed-pulse 1s ease-in-out infinite;
}

@keyframes demo-armed-pulse {
  50% {
    background: rgba(229, 72, 77, 0.12);
  }
}

.wb__demo-note {
  margin: var(--sp-2) 0 0;
  font-size: var(--fs-11);
  line-height: 1.6;
  color: var(--text-3);
}

.wb__demo-note strong {
  color: var(--text-2);
  font-weight: 600;
}

/* ---------------- 进度看板 ---------------- */
.wb__roadmap {
  list-style: none;
  margin: 0;
  padding: 0;
}

.wb__roadmap li {
  display: grid;
  grid-template-columns: 84px 1fr 72px;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-3) 0;
  border-bottom: 1px dashed var(--line-1);
  font-size: var(--fs-13);
}

.wb__roadmap li:last-child {
  border-bottom: none;
}

.wb__phase {
  color: var(--text-3);
  font-size: var(--fs-12);
}

.wb__name {
  color: var(--text-3);
}

.wb__status {
  text-align: right;
  font-size: var(--fs-12);
  color: var(--text-3);
}

.is-done .wb__name {
  color: var(--text-1);
}
.is-done .wb__status {
  color: var(--ok);
}
.is-doing .wb__name {
  color: var(--text-1);
  font-weight: 600;
}
.is-doing .wb__status {
  color: var(--brass-text);
}

@media (max-width: 760px) {
  .wb__roadmap li {
    grid-template-columns: 74px 1fr;
  }
  .wb__status {
    grid-column: 2;
    text-align: left;
  }
}
</style>
