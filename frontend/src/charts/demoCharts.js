/**
 * 示例大屏的图表配置（纯函数：给一份数据 + 一套调色板，还一份 ECharts 配置）。
 *
 * 为什么写成"纯函数"？
 *   1. 好测试 —— 可以脱离浏览器，在 Node 里直接渲染成 SVG 做自检；
 *   2. 好复用 —— 第 5 阶段做"图表模块"时，这些配置可以直接搬过去；
 *   3. 数据与画法分离 —— 数据换成真实数据时，这里一行都不用改；
 *   4. 好换肤 —— 调色板由外部传进来，浅色/深色皮肤共用同一套画法。
 */

import { formatNumber } from '../utils/chartTheme.js'

const UNIT = '万元'

/* ---------------------------------------------------------------- 公共小工具 */

/** 省份按"全年总额"从高到低排序（固定顺序，避免每帧跳动） */
export function sortedProvinces(dataset) {
  return [...dataset.provinces].sort(
    (a, b) => sum(dataset.monthlyByProvince[b]) - sum(dataset.monthlyByProvince[a]),
  )
}

function sum(arr) {
  return arr.reduce((acc, v) => acc + v, 0)
}

/**
 * 统一的网格布局。
 * ECharts 6 已弃用 `containLabel`，官方等价写法是：
 *   { outerBoundsMode: 'same', outerBoundsContain: 'axisLabel' }
 * 含义：坐标轴标签自动纳入布局计算，不会被画到画布外面（截图时会缺字）。
 */
function gridBox(bounds) {
  return {
    ...bounds,
    outerBoundsMode: 'same',
    outerBoundsContain: 'axisLabel',
  }
}

/** 某月的各省数值 */
function provinceValuesAt(dataset, monthIndex) {
  return sortedProvinces(dataset).map((p) => dataset.monthlyByProvince[p][monthIndex])
}

/** 所有月份中的最大值（用于固定坐标轴，避免每帧缩放导致视觉抖动） */
function maxMonthlyProvinceValue(dataset) {
  let max = 0
  for (const p of dataset.provinces) {
    for (const v of dataset.monthlyByProvince[p]) max = Math.max(max, v)
  }
  return max
}

/* ------------------------------------------------------------------ 关键指标 */

export function computeKpis(dataset) {
  const totalYuan = dataset.grandTotal * 10000
  const avgOrder = totalYuan / dataset.ordersTotal
  return [
    {
      key: 'total',
      label: '总销售额',
      value: dataset.grandTotal,
      display: `${(dataset.grandTotal / 10000).toFixed(2)}`,
      displayUnit: '亿元',
      hint: `${dataset.months.length} 个月累计`,
      tone: 'brand',
      // 给"数字滚动动画"用的目标值与小数位
      animateTo: dataset.grandTotal / 10000,
      digits: 2,
    },
    {
      key: 'orders',
      label: '订单总量',
      value: dataset.ordersTotal,
      display: `${(dataset.ordersTotal / 10000).toFixed(1).replace(/\.0$/, '')}`,
      displayUnit: '万单',
      hint: '全渠道去重后',
      tone: 'brass',
      animateTo: dataset.ordersTotal / 10000,
      digits: 1,
    },
    {
      key: 'aov',
      label: '客单价',
      value: avgOrder,
      display: avgOrder.toFixed(0),
      displayUnit: '元',
      hint: '总销售额 ÷ 订单量',
      tone: 'brand',
      animateTo: avgOrder,
      digits: 0,
    },
    {
      key: 'yoy',
      label: '同比增长',
      value: dataset.yearOverYear,
      display: `${dataset.yearOverYear > 0 ? '+' : ''}${dataset.yearOverYear}`,
      displayUnit: '%',
      hint: `去年同期 ${formatNumber(dataset.lastYearTotal)} 万元`,
      tone: dataset.yearOverYear >= 0 ? 'brand' : 'danger',
      animateTo: dataset.yearOverYear,
      digits: 1,
      prefix: dataset.yearOverYear > 0 ? '+' : '',
    },
  ]
}

/* ---------------------------------------------------- 图 1：动态排名（柱状赛跑） */

export function buildRaceOption(dataset, monthIndex, p) {
  const provinces = sortedProvinces(dataset)
  const ceiling = Math.ceil((maxMonthlyProvinceValue(dataset) * 1.18) / 500) * 500

  return {
    // 动画交给"数据更新"来做，而不是初始化动画，才能形成连续赛跑
    animationDuration: 0,
    animationDurationUpdate: 720,
    animationEasingUpdate: 'linear',
    grid: gridBox({ left: 8, right: 78, top: 46, bottom: 8 }),
    xAxis: {
      max: ceiling,
      type: 'value',
      axisLabel: { formatter: (v) => formatNumber(v) },
      splitLine: { lineStyle: { color: p.line1 } },
    },
    yAxis: {
      type: 'category',
      data: provinces,
      inverse: true,
      max: provinces.length - 1,
      animationDuration: 240,
      animationDurationUpdate: 240,
      axisLabel: { color: p.text2, fontSize: 12 },
      axisLine: { show: false },
    },
    series: [
      {
        type: 'bar',
        realtimeSort: true,
        barMaxWidth: 20,
        data: provinceValuesAt(dataset, monthIndex),
        itemStyle: {
          borderRadius: [0, 2, 2, 0],
          // 最后一名弱化处理，把注意力留给头部名次
          color: (params) =>
            params.dataIndex === provinces.length - 1 ? p.ink600 : p.brand500,
        },
        label: {
          show: true,
          position: 'right',
          distance: 8,
          color: p.text1,
          fontFamily: 'ui-monospace, Consolas, monospace',
          fontSize: 12,
          formatter: (params) => formatNumber(params.value),
        },
      },
    ],
    // 右下角的月份"仪表读数"
    graphic: [
      {
        type: 'text',
        right: 10,
        bottom: 4,
        silent: true,
        style: {
          text: dataset.months[monthIndex],
          fill: p.brass400,
          fontSize: 30,
          fontWeight: 600,
          fontFamily: '"PingFang SC","Microsoft YaHei",sans-serif',
          opacity: 0.55,
        },
      },
    ],
  }
}

/* ------------------------------------------------------ 图 2：月度趋势（堆叠面积） */

export function buildTrendOption(dataset, p) {
  return {
    grid: gridBox({ left: 8, right: 16, top: 44, bottom: 8 }),
    legend: { top: 0, left: 0, icon: 'roundRect' },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => `${formatNumber(v)} ${UNIT}`,
    },
    xAxis: { type: 'category', boundaryGap: false, data: dataset.months },
    yAxis: { type: 'value', axisLabel: { formatter: (v) => formatNumber(v) } },
    series: dataset.categories.map((name, i) => ({
      name,
      type: 'line',
      stack: '总量',
      smooth: false,
      symbol: 'circle',
      symbolSize: 4,
      showSymbol: false,
      lineStyle: { width: 1.5 },
      areaStyle: { opacity: p.areaOpacity },
      emphasis: { focus: 'series' },
      itemStyle: { color: p.data[i % p.data.length] },
      data: dataset.monthlyByCategory[name],
    })),
  }
}

/* -------------------------------------------------------- 图 3：品类占比（环形） */

export function buildPieOption(dataset, p) {
  const rows = dataset.categories
    .map((name, i) => ({
      name,
      value: sum(dataset.monthlyByCategory[name]),
      itemStyle: { color: p.data[i % p.data.length] },
    }))
    .sort((a, b) => b.value - a.value)

  const total = rows.reduce((acc, r) => acc + r.value, 0)

  return {
    tooltip: {
      trigger: 'item',
      valueFormatter: (v) => `${formatNumber(v)} ${UNIT}`,
    },
    legend: {
      bottom: 0,
      left: 'center',
      icon: 'roundRect',
      formatter: (name) => {
        const row = rows.find((r) => r.name === name)
        return `${name}  ${((row.value / total) * 100).toFixed(1)}%`
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['46%', '68%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        padAngle: 1,
        itemStyle: { borderRadius: 3, borderColor: p.ink850, borderWidth: 2 },
        label: { show: false },
        emphasis: {
          scaleSize: 4,
          label: {
            show: true,
            formatter: '{b}\n{d}%',
            color: p.text1,
            fontSize: 13,
            lineHeight: 20,
          },
        },
        data: rows,
      },
    ],
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '34%',
        silent: true,
        style: {
          text: String(dataset.categories.length),
          fill: p.text1,
          fontSize: 30,
          fontWeight: 600,
          fontFamily: 'ui-monospace, Consolas, monospace',
          textAlign: 'center',
        },
      },
      {
        type: 'text',
        left: 'center',
        top: '46%',
        silent: true,
        style: {
          text: '个品类',
          fill: p.text3,
          fontSize: 12,
          textAlign: 'center',
        },
      },
    ],
  }
}

/* ------------------------------------------------------ 图 4：省份排行（横向柱） */

export function buildProvinceOption(dataset, p) {
  const provinces = sortedProvinces(dataset)
  const totals = provinces.map((name) => sum(dataset.monthlyByProvince[name]))

  return {
    grid: gridBox({ left: 8, right: 60, top: 16, bottom: 8 }),
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${formatNumber(v)} ${UNIT}` },
    xAxis: { type: 'value', axisLabel: { formatter: (v) => formatNumber(v) } },
    yAxis: {
      type: 'category',
      inverse: true,
      data: provinces,
      axisLine: { show: false },
      axisLabel: { color: p.text2, fontSize: 12 },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 16,
        data: totals.map((v, i) => ({
          value: v,
          // 冠军用黄铜色点出，其余用松石：一眼看出"第一名"
          itemStyle: { color: i === 0 ? p.brass500 : p.brand500 },
        })),
        label: {
          show: true,
          position: 'right',
          color: p.text2,
          fontSize: 11,
          fontFamily: 'ui-monospace, Consolas, monospace',
          formatter: (params) => formatNumber(params.value),
        },
      },
    ],
  }
}

/* -------------------------------------------- 图 5：订单量 × 客单价（双轴） */

export function buildOrdersOption(dataset, p) {
  const monthlyTotals = dataset.months.map((_, i) =>
    sum(dataset.provinces.map((name) => dataset.monthlyByProvince[name][i])),
  )
  const ordersInWan = dataset.ordersByMonth.map((v) => Number((v / 10000).toFixed(2)))
  const aov = dataset.ordersByMonth.map((orders, i) =>
    Number(((monthlyTotals[i] * 10000) / orders).toFixed(0)),
  )

  return {
    grid: gridBox({ left: 8, right: 8, top: 44, bottom: 8 }),
    legend: { top: 0, left: 0, icon: 'roundRect' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dataset.months },
    yAxis: [
      {
        type: 'value',
        name: '订单量(万单)',
        nameTextStyle: { color: p.text3, fontSize: 11 },
        axisLabel: { formatter: (v) => formatNumber(v) },
      },
      {
        type: 'value',
        name: '客单价(元)',
        nameTextStyle: { color: p.text3, fontSize: 11 },
        axisLabel: { formatter: (v) => formatNumber(v) },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '订单量',
        type: 'bar',
        barMaxWidth: 18,
        itemStyle: { color: p.ink600, borderRadius: [2, 2, 0, 0] },
        data: ordersInWan,
        tooltip: { valueFormatter: (v) => `${formatNumber(v, 2)} 万单` },
      },
      {
        name: '客单价',
        type: 'line',
        yAxisIndex: 1,
        smooth: false,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: p.brass500, width: 2 },
        itemStyle: { color: p.brass500 },
        data: aov,
        tooltip: { valueFormatter: (v) => `${formatNumber(v)} 元` },
      },
    ],
  }
}

/**
 * 大屏上所有图表的清单（顺序即布局顺序），供"自检"脚本统一遍历。
 * 注意每个图表都接收调色板 p，因此同一份清单可以在两套皮肤下分别渲染验证。
 */
export function allDemoCharts(dataset, p) {
  return [
    { id: 'race', title: '省份销售额动态排名', build: () => buildRaceOption(dataset, 0, p) },
    { id: 'trend', title: '月度销售趋势（按品类）', build: () => buildTrendOption(dataset, p) },
    { id: 'pie', title: '品类销售占比', build: () => buildPieOption(dataset, p) },
    { id: 'province', title: '省份销售额排行', build: () => buildProvinceOption(dataset, p) },
    { id: 'orders', title: '订单量与客单价', build: () => buildOrdersOption(dataset, p) },
  ]
}
