<script setup>
/**
 * 一键体验 · 示例大屏。
 *
 * 这是整套系统的"兜底王牌"：数据全部来自内置 JSON，
 * 即使后端停机、学校数据库断网，这一页依然完整可用。
 *
 * 皮肤：图表颜色来自 useTheme 提供的调色板，切换浅色/深色时会跟着换。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import BrandMark from '../components/BrandMark.vue'
import EChart from '../components/EChart.vue'
import PanelCard from '../components/PanelCard.vue'
import StatCard from '../components/StatCard.vue'
import ThemeToggle from '../components/ThemeToggle.vue'

import dataset from '../data/demo-sales.json'
import {
  buildOrdersOption,
  buildPieOption,
  buildProvinceOption,
  buildRaceOption,
  buildTrendOption,
  computeKpis,
} from '../charts/demoCharts.js'
import { formatNumber } from '../utils/chartTheme.js'
import { useTheme } from '../composables/useTheme.js'

const emit = defineEmits(['exit'])

const { palette, chartThemeName } = useTheme()

/* ----------------------------------------------------------- 关键指标 */
const kpis = computed(() => computeKpis(dataset))

/* --------------------------------------------------- 动态排名（柱状赛跑） */
const monthIndex = ref(0)
const playing = ref(true)
let raceTimer = null

const raceOption = computed(() => buildRaceOption(dataset, monthIndex.value, palette.value))

/** 系统若开启了"减少动效"，则默认不自动播放（尊重使用者的偏好） */
const prefersReducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function startRace() {
  stopRace()
  raceTimer = window.setInterval(() => {
    monthIndex.value = (monthIndex.value + 1) % dataset.months.length
  }, 900)
}

function stopRace() {
  if (raceTimer) {
    window.clearInterval(raceTimer)
    raceTimer = null
  }
}

function toggleRace() {
  playing.value = !playing.value
  if (playing.value) startRace()
  else stopRace()
}

function replayRace() {
  monthIndex.value = 0
  playing.value = true
  startRace()
}

/* --------------------------------------------------------------- 时钟 */
const now = ref(new Date())
let clockTimer = null

const clockText = computed(() => {
  const d = now.value
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
    d.getMinutes(),
  )}:${p(d.getSeconds())}`
})

/* ------------------------------------------------------------ 生命周期 */
onMounted(() => {
  if (!prefersReducedMotion) {
    playing.value = true
    startRace()
  } else {
    playing.value = false
    monthIndex.value = dataset.months.length - 1
  }
  clockTimer = window.setInterval(() => {
    now.value = new Date()
  }, 1000)
})

onBeforeUnmount(() => {
  stopRace()
  if (clockTimer) window.clearInterval(clockTimer)
})

/* ------------------------------------------------------------- 其它图表 */
const trendOption = computed(() => buildTrendOption(dataset, palette.value))
const pieOption = computed(() => buildPieOption(dataset, palette.value))
const provinceOption = computed(() => buildProvinceOption(dataset, palette.value))
const ordersOption = computed(() => buildOrdersOption(dataset, palette.value))

const totalText = formatNumber(dataset.grandTotal)
</script>

<template>
  <div class="dash">
    <header class="appbar">
      <BrandMark compact :show-tagline="false" />
      <div class="appbar__sep" />
      <div class="appbar__title">{{ dataset.meta.title }}</div>
      <span class="badge badge--brass">数据源：本地内置</span>
      <span class="badge">断网可用</span>

      <div class="appbar__spacer" />

      <span class="dash__clock num">{{ clockText }}</span>
      <ThemeToggle />
      <button class="btn-ghost" type="button" @click="emit('exit')">返回登录</button>
    </header>

    <div class="dash__body">
      <!-- 关键指标：数字从 0 滚到目标值，四张卡依次错峰 -->
      <div class="dash__kpis">
        <StatCard
          v-for="(k, i) in kpis"
          :key="k.key"
          class="rise"
          :style="{ '--i': i }"
          :label="k.label"
          :display="k.display"
          :display-unit="k.displayUnit"
          :hint="k.hint"
          :tone="k.tone"
          :animate-to="k.animateTo"
          :digits="k.digits"
          :prefix="k.prefix || ''"
          :delay="i * 90"
        />
      </div>

      <!-- 图表区 -->
      <div class="dash__grid">
        <PanelCard
          class="col-8 rise"
          style="--i: 4"
          title="省份销售额动态排名"
          :note="`${dataset.months[monthIndex]} · 每 0.9 秒推进`"
        >
          <template #extra>
            <button class="btn-ghost" type="button" @click="toggleRace">
              {{ playing ? '暂停' : '播放' }}
            </button>
            <button class="btn-ghost btn-ghost--brass" type="button" @click="replayRace">
              重新播放
            </button>
          </template>
          <EChart :option="raceOption" :theme-name="chartThemeName" height="376px" />
        </PanelCard>

        <PanelCard
          class="col-4 rise"
          style="--i: 5"
          title="品类销售占比"
          :note="`全年 ${totalText} 万元`"
        >
          <EChart :option="pieOption" :theme-name="chartThemeName" height="376px" />
        </PanelCard>

        <PanelCard
          class="col-12 rise"
          style="--i: 6"
          title="月度销售趋势（按品类堆叠）"
          note="2 月春节回落，6 月与 11 月为两次大促高峰"
        >
          <EChart :option="trendOption" :theme-name="chartThemeName" height="300px" />
        </PanelCard>

        <PanelCard class="col-6 rise" style="--i: 7" title="省份销售额排行" note="冠军以黄铜色标出">
          <EChart :option="provinceOption" :theme-name="chartThemeName" height="300px" />
        </PanelCard>

        <PanelCard
          class="col-6 rise"
          style="--i: 8"
          title="订单量与客单价"
          note="柱=订单量 · 线=客单价"
        >
          <EChart :option="ordersOption" :theme-name="chartThemeName" height="300px" />
        </PanelCard>
      </div>

      <footer class="dash__foot">
        <span>{{ dataset.meta.note }}</span>
        <span class="appbar__sep" />
        <span>{{ dataset.meta.source }}</span>
        <span class="appbar__sep" />
        <span>金额单位：{{ dataset.meta.unit }}</span>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.dash {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.dash__body {
  padding: var(--sp-5);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  max-width: 1680px;
  width: 100%;
  margin: 0 auto;
}

.dash__clock {
  font-size: var(--fs-13);
  color: var(--text-2);
  letter-spacing: 0.02em;
}

/* 12 栅格：小于 1280px 自动堆叠，保证投影仪分辨率下不挤压 */
.dash__kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-4);
}

.dash__grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: var(--sp-4);
}

.col-4 {
  grid-column: span 4;
}
.col-6 {
  grid-column: span 6;
}
.col-8 {
  grid-column: span 8;
}
.col-12 {
  grid-column: span 12;
}

.dash__foot {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
  padding: var(--sp-3) 0 var(--sp-2);
  font-size: var(--fs-12);
  color: var(--text-3);
}

@media (max-width: 1280px) {
  .dash__kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .col-4,
  .col-8 {
    grid-column: span 12;
  }
}

@media (max-width: 900px) {
  .dash__kpis {
    grid-template-columns: minmax(0, 1fr);
  }
  .col-6 {
    grid-column: span 12;
  }
  .dash__body {
    padding: var(--sp-4) var(--sp-3);
  }
}
</style>
