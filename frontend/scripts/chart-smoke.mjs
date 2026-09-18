/**
 * 无浏览器自检：把所有示例图表在 Node 里渲染成 SVG 字符串。
 *
 * 为什么需要它？
 *   1. 图表配置是否真的能出图（语法、数据、ECharts 版本兼容性）；
 *   2. **两套皮肤是否真的换了颜色** —— 这是换肤最容易骗过自己的地方：
 *      皮肤换了，图表却还是原来的颜色。
 *
 * 运行：cd frontend && node scripts/chart-smoke.mjs
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import echarts, { ECHARTS_THEME } from '../src/utils/echarts.js'
import { PALETTES } from '../src/utils/chartTheme.js'
import { allDemoCharts, computeKpis } from '../src/charts/demoCharts.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const dataset = JSON.parse(
  fs.readFileSync(path.resolve(here, '../src/data/demo-sales.json'), 'utf8'),
)

const outDir = path.resolve(here, '../.chart-preview')
fs.mkdirSync(outDir, { recursive: true })

const SKINS = ['dark', 'light']

/** 一套皮肤里"应该出现在图上"的颜色（系列色 + 品牌色 + 弱化图形色） */
function expectedColors(p) {
  return [...p.data, p.brand500, p.brass500, p.ink600]
}

let failed = 0
const rows = []

for (const skin of SKINS) {
  const other = skin === 'dark' ? 'light' : 'dark'
  const p = PALETTES[skin]

  for (const chart of allDemoCharts(dataset, p)) {
    const label = `${chart.title}（${skin === 'dark' ? '深色' : '浅色'}）`
    try {
      const option = chart.build()
      const instance = echarts.init(null, ECHARTS_THEME[skin], {
        renderer: 'svg',
        ssr: true,
        width: 900,
        height: 420,
      })
      instance.setOption(option)
      const svg = instance.renderToSVGString()
      instance.dispose()

      fs.writeFileSync(path.join(outDir, `${chart.id}-${skin}.svg`), svg, 'utf8')

      const problems = []
      if (!svg.startsWith('<svg')) problems.push('输出不是 SVG')
      if (svg.length < 2000) problems.push(`输出过小(${svg.length} 字节)，可能没画出内容`)
      if (svg.includes('NaN')) problems.push('输出里出现 NaN（数据或配置有问题）')
      if (!svg.includes('<path') && !svg.includes('<rect')) problems.push('没有找到任何图形元素')

      // 换肤是否真的生效：必须用到本皮肤的颜色
      if (!expectedColors(p).some((c) => svg.includes(c))) {
        problems.push('没有使用本皮肤的任何配色')
      }

      // 反向验证：不应出现"只有另一套皮肤才有的系列色"
      const foreign = PALETTES[other].data.filter((c) => !p.data.includes(c))
      const leaked = foreign.filter((c) => svg.includes(c))
      if (leaked.length) problems.push(`混入了另一套皮肤的颜色：${leaked.join(', ')}`)

      rows.push({
        label,
        size: svg.length,
        ok: problems.length === 0,
        detail: problems.join('；'),
      })
      if (problems.length) failed += 1
    } catch (err) {
      rows.push({ label, size: 0, ok: false, detail: `渲染抛异常：${err.message}` })
      failed += 1
    }
  }
}

/* ---------- 关键指标自检：数字必须自洽 ---------- */
const kpis = computeKpis(dataset)
const kpiProblems = []
for (const k of kpis) {
  if (Number.isNaN(Number(String(k.display).replace('+', '')))) {
    kpiProblems.push(`${k.label} 数值异常`)
  }
  if (Number.isNaN(Number(k.animateTo))) kpiProblems.push(`${k.label} 缺少动画目标值`)
}
const avgCheck = (dataset.grandTotal * 10000) / dataset.ordersTotal
if (Math.abs(avgCheck - kpis.find((k) => k.key === 'aov').value) > 1) {
  kpiProblems.push('客单价与总销售额/订单量对不上')
}

/* ---------- 打印结果 ---------- */
console.log('图表自检（ECharts 服务端渲染 · 双皮肤）')
console.log('─'.repeat(78))
for (const r of rows) {
  console.log(
    r.label.padEnd(30) + String(r.size).padEnd(10) + (r.ok ? '✅ 通过' : `❌ ${r.detail}`),
  )
}
console.log('─'.repeat(78))
console.log('关键指标：')
for (const k of kpis) {
  console.log(`  ${k.label.padEnd(8)} ${k.display} ${k.displayUnit}   （${k.hint}）`)
}
console.log('─'.repeat(78))

const kpiOk = kpiProblems.length === 0
console.log(`图表：${rows.length - failed}/${rows.length} 通过`)
console.log(`指标自洽：${kpiOk ? '✅ 通过' : `❌ ${kpiProblems.join('；')}`}`)
console.log(`SVG 预览已输出到：${outDir}`)

process.exit(failed === 0 && kpiOk ? 0 : 1)
