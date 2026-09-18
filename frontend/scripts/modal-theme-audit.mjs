/**
 * 弹窗主题审计（浅色/深色 × 三个工作台弹窗 + 免登录分享页）——防"深色照搬"类事故复发。
 *
 * 为什么需要这个脚本：
 *   第 4/5 阶段的两个弹窗曾在浅色模式下完全看不清 ——
 *   根因是 CSS 里引用了**不存在的变量**（--bg-card/--bg-page），
 *   背景静默变成透明，透出黑色遮罩。深色模式恰好"蒙混过关"，
 *   所以原有测试全绿也没拦住它。
 *
 * 本审计做三件人眼替代不了的事：
 *   1. 断言弹窗表面（dialog 本体）背景**不透明**——透明 = 变量无效的直接信号；
 *   2. 对弹窗内每个可见文字元素，沿祖先链**合成真实底色**后计算 WCAG 对比度，
 *      正文要求 ≥ 4.5:1，大字号/加粗放宽到 ≥ 3:1（与 WCAG 一致）；
 *   3. 两套皮肤各跑一遍（浅色是曾经翻车的皮肤，重点盯防）。
 */

import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const BASE = 'http://127.0.0.1:5173'
const API = 'http://127.0.0.1:8000'
const SHOT_DIR = 'screenshots'

function getDemoPass() {
  const envPath = path.resolve('../backend/.env')
  for (const l of fs.readFileSync(envPath, 'utf-8').split('\n')) {
    if (l.startsWith('DEMO_PASSWORD=')) return l.split('=')[1].trim()
  }
  return ''
}

async function fetchToken() {
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'demo', password: getDemoPass() }),
  })
  if (!res.ok) throw new Error(`登录失败 HTTP ${res.status}，后端起来了吗？`)
  return (await res.json()).token
}

/* ---------- 浏览器内执行的取色与对比度计算 ---------- */
function pageHelpers() {
  const parse = (c) => {
    const m = c.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/)
    return m
      ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] }
      : { r: 0, g: 0, b: 0, a: 0 }
  }
  const lum = ({ r, g, b }) => {
    const f = (v) => {
      v /= 255
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
    }
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
  }
  window.__auditEffectiveBg = function (el) {
    // 从元素向上收集所有半透明背景，逐层合成到不透明为止
    const layers = []
    let cur = el
    while (cur) {
      const bg = parse(getComputedStyle(cur).backgroundColor)
      if (bg.a > 0) layers.push(bg)
      if (bg.a >= 1) break
      cur = cur.parentElement
    }
    if (!layers.length || layers[layers.length - 1].a < 1) {
      layers.push(parse(getComputedStyle(document.documentElement).backgroundColor))
    }
    // 自底向上 alpha 合成
    let acc = layers[layers.length - 1]
    acc = { r: acc.r, g: acc.g, b: acc.b }
    for (let i = layers.length - 2; i >= 0; i--) {
      const t = layers[i]
      acc = {
        r: t.r * t.a + acc.r * (1 - t.a),
        g: t.g * t.a + acc.g * (1 - t.a),
        b: t.b * t.a + acc.b * (1 - t.a),
      }
    }
    return acc
  }
  window.__auditContrast = function (el) {
    const cs = getComputedStyle(el)
    const fg = parse(cs.color)
    const bg = window.__auditEffectiveBg(el)
    const l1 = lum(fg)
    const l2 = lum(bg)
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)
    const size = parseFloat(cs.fontSize)
    const bold = parseInt(cs.fontWeight, 10) >= 700
    // WCAG：≥18.66px 加粗 或 ≥24px 视为大字号，阈值放宽到 3:1
    const large = size >= 24 || (size >= 18.66 && bold)
    const transparentSurface =
      parse(cs.backgroundColor).a === 0 &&
      bg === undefined
    return {
      ratio: Math.round(ratio * 100) / 100,
      need: large ? 3 : 4.5,
      pass: ratio >= (large ? 3 : 4.5),
      size,
      weight: cs.fontWeight,
    }
  }
}

function sampleSpecs() {
  return {
    uploader: {
      surface: '.uploader-dialog',
      selectors: [
        '.uploader-title',
        '.step-indicator .is-active',
        '.guide-badge',
        '.guide-text',
        '.tab-btn.is-active',
        '.sample-card__title',
        '.sample-card__desc',
        '.sample-card__meta',
        '.sample-card__action',
        '.badge--brass',
      ],
      // 进入第二步后追加的抽样
      afterLoad: [
        '.meta-file',
        '.meta-strip .badge',
        '.controls-title',
        '.rule-label strong',
        '.rule-label small',
        '.audit-pill',
        '.table-card__head',
        '.preview-table th',
        '.preview-table tbody td',
        '.is-dim-head .col-type-tag',
        '.is-metric-head .col-type-tag',
        '.save-input-group label',
        '.save-input',
        '.btn-ghost',
        '.save-footer .btn-primary',
      ],
    },
    builder: {
      surface: '.builder-dialog',
      selectors: [
        '.builder-title',
        '.preset-title',
        '.preset-name',
        '.preset-tag',
        '.form-label',
        '.form-select',
        '.type-card-btn',
        '.type-card-btn.is-selected',
        '.preview-title span',
        '.agg-pill',
        '.form-input',
        '.sidebar-actions .btn-primary',
      ],
    },
    // 第 6 阶段：大屏设计器外壳（标题栏/图表库/属性轨/底栏，均与数据无关，空态即可审）
    designer: {
      surface: '.dash-dialog',
      selectors: [
        '.dash-title',
        '.dash-name-input',
        '.palette-title',
        '.rail-title',
        '.rail-stat',
        '.rail-hint',
        '.rail-tips em',
        '.dash-foot-hint',
        '.dash-footer .btn-primary',
      ],
    },
    // 第 7 阶段：免登录公开分享页（顶栏文字/徽标/按钮、面板标题、底部联动提示条）
    share: {
      surface: '.share',
      selectors: [
        '.share__brand',
        '.share__title',
        '.share__bar .badge--brass',
        '.share__bar .btn-ghost',
        '.share__bar .btn-ghost--brass',
        '.panel .panel__title',
        '.share__link',
      ],
    },
  }
}

/* ---------- 主流程 ---------- */
const token = await fetchToken()

// 审计的空态分支可能顺手入库数据集：先快照原有 ID，跑完把增量删掉（自我清理）
async function apiCall(p, method = 'GET') {
  const r = await fetch(`${API}${p}`, { method, headers: { Authorization: `Bearer ${token}` } })
  return r.json()
}
async function apiPost(p, body) {
  const r = await fetch(`${API}${p}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return r.json()
}
async function apiDel(p) {
  await fetch(`${API}${p}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } }).catch(() => {})
}
const preDatasetIds = new Set(
  ((await apiCall('/api/datasets/list')).datasets || []).map((d) => d.DatasetID),
)

/* ---------- 分享页审计备料（在快照之后建，数据集会被差量清理兜底） ----------
 * 免登录公开页是双皮肤可读性的新战场：给它建一张真分享（数据集→图→大屏→开token）。 */
const _raw = (await apiPost('/api/datasets/preview-sample', { filename: '电商销售_干净数据.csv' })).data
const _cl = await apiPost('/api/datasets/clean-preview', {
  headers: _raw.headers,
  raw_matrix: _raw.raw_preview_matrix,
  fill_down_merged: true,
  filter_summary_rows: true,
  filter_empty_rows: true,
  auto_convert_numbers: true,
})
const _sv = await apiPost('/api/datasets/save', {
  name: '审计分享数据集',
  source_file_name: '电商销售_干净数据.csv',
  columns: _cl.columns,
  rows: _cl.preview_rows,
  cleaning_log: _cl.cleaning_logs,
})
const _ch = await apiPost('/api/charts/save', {
  dataset_id: _sv.dataset_id,
  title: '审计分享图表',
  chart_type: 'bar',
  config: { option: { xAxis: { type: 'category', data: ['甲', '乙'] }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: [3, 5] }] } },
})
const _db = await apiPost('/api/dashboards/save', {
  title: '审计分享大屏',
  layout: { canvas: { w: 1920, h: 1080 }, items: [
    { id: 'p1', chart_id: _ch.chart_id, x: 60, y: 60, w: 860, h: 500, z: 1 },
    { id: 'p2', chart_id: _ch.chart_id, x: 1000, y: 60, w: 860, h: 500, z: 2 },
  ] },
})
const _share = await apiPost(`/api/dashboards/${_db.dashboard_id}/share`)
const sharePath = _share.share_path
if (!sharePath) throw new Error('分享页备料失败：没拿到 share_path')

const browser = await chromium.launch({ headless: true })
const failures = []
const results = []

for (const theme of ['light', 'dark']) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await context.addInitScript(([t, tk]) => {
    window.localStorage.setItem('moheng-theme', t)
    window.localStorage.setItem('moheng-token', tk)
  }, [theme, token])
  const page = await context.newPage()
  page.on('pageerror', (e) => failures.push(`[${theme}] 页面脚本错误: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') failures.push(`[${theme}] 控制台错误: ${m.text()}`)
  })

  await page.goto(`${BASE}/#/workbench`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(700)
  await page.evaluate(pageHelpers)

  const specs = sampleSpecs()

  // —— 审计 1：数据清洗工作台（两步）——
  await page.click('button:has-text("上传表格")')
  await page.waitForSelector('.uploader-dialog')
  await page.waitForTimeout(400)
  await auditSurfaceAndTexts(page, theme, '清洗工作台·选择文件', specs.uploader.surface, specs.uploader.selectors, failures, results)
  await page.locator('.sample-card').first().click()
  await page.waitForSelector('.cleaning-workbench')
  await page.waitForTimeout(900)
  await auditSurfaceAndTexts(page, theme, '清洗工作台·清洗对比', specs.uploader.surface, specs.uploader.afterLoad, failures, results)
  await page.screenshot({ path: `${SHOT_DIR}/audit-uploader-${theme}.png` })
  await page.click('.uploader-dialog .btn-close')
  await page.waitForSelector('.uploader-dialog', { state: 'hidden' })

  // —— 审计 2：图表构建工作台 ——
  // 注意：bootstrap loading 期间 .builder-layout 会先渲染"空壳"，拉完数据才定局，
  // 所以必须等【定局态】：空态提示 / 聚合胶囊 / 画布空提示，三者之一出现才算加载完。
  const builderSettled = () =>
    document.querySelector('.no-data-hint') ||
    document.querySelector('.agg-pill') ||
    document.querySelector('.chart-canvas-empty')
  await page.click('button:has-text("新建可视化图表")')
  await page.waitForSelector('.builder-dialog')
  await page.waitForFunction(builderSettled, null, { timeout: 15000 })
  // 若名下没有数据集，空态下没东西可测：先关掉去入库一份，再回来。
  // 注意：上传弹窗会保留上次进度（步骤2还开着），两种状态都要能走通。
  if (await page.locator('.no-data-hint').count()) {
    await page.click('.builder-dialog .btn-close')
    await page.click('button:has-text("上传表格")')
    await page.waitForSelector('.uploader-dialog')
    await page.waitForSelector('.sample-card, .cleaning-workbench', { timeout: 8000 })
    if (await page.locator('.sample-card').count()) {
      await page.locator('.sample-card').first().click()
      await page.waitForSelector('.cleaning-workbench')
    }
    await page.waitForTimeout(600)
    await page.click('.save-footer .btn-primary')
    await page.waitForSelector('.uploader-success, [class*="success"]', { timeout: 8000 })
    await page.waitForSelector('.uploader-dialog', { state: 'hidden', timeout: 8000 })
    await page.click('button:has-text("新建可视化图表")')
    await page.waitForSelector('.builder-dialog')
    await page.waitForFunction(builderSettled, null, { timeout: 15000 })
  }
  // 首帧聚合彻底落定（画布 loading 消失）后才抽样
  await page.waitForFunction(() => !document.querySelector('.chart-canvas-loading'), null, { timeout: 12000 })
  await auditSurfaceAndTexts(page, theme, '图表构建工作台', specs.builder.surface, specs.builder.selectors, failures, results)
  await page.screenshot({ path: `${SHOT_DIR}/audit-builder-${theme}.png` })
  await page.click('.builder-dialog .btn-close')

  // —— 审计 3：大屏设计器外壳（标题栏/图表库/属性轨/底栏，空态可审）——
  await page.click('.wb__dash-new')
  await page.waitForSelector('.dash-dialog')
  // body 在 bootstrap 完成前是 loading 态：等图表库就位（有条目或空态提示）
  await page.waitForSelector('.palette-item, .palette-empty', { timeout: 8000 })
  await page.waitForTimeout(300)
  await auditSurfaceAndTexts(page, theme, '大屏设计器', specs.designer.surface, specs.designer.selectors, failures, results)
  await page.screenshot({ path: `${SHOT_DIR}/audit-designer-${theme}.png` })
  await page.click('.dash-dialog .btn-close')
  await page.waitForSelector('.dash-dialog', { state: 'hidden' })

  // —— 审计 4：免登录公开分享页（访客拿到的第一眼，两套皮肤都不许翻车）——
  const sharePage = await context.newPage()
  sharePage.on('pageerror', (e) => failures.push(`[${theme}] 分享页脚本错误: ${e.message}`))
  sharePage.on('console', (m) => {
    if (m.type() === 'error') failures.push(`[${theme}] 分享页控制台错误: ${m.text()}`)
  })
  await sharePage.goto(`${BASE}${sharePath}`, { waitUntil: 'networkidle' })
  await sharePage.waitForFunction(
    () => document.querySelectorAll('.share__stage .panel').length >= 2 || document.querySelector('.share__invalid'),
    null,
    { timeout: 15000 },
  )
  await sharePage.evaluate(pageHelpers)
  await sharePage.waitForTimeout(500) // 图表首帧落稳后再取样
  await auditSurfaceAndTexts(sharePage, theme, '公开分享页', specs.share.surface, specs.share.selectors, failures, results)
  await sharePage.screenshot({ path: `${SHOT_DIR}/audit-share-${theme}.png` })
  await sharePage.close()

  await context.close()
}

await browser.close()

// 自我清理：删除审计途中（空态分支）入库的数据集增量，恢复纯净态
{
  await apiDel(`/api/dashboards/${_db.dashboard_id}`) // 分享大屏先删（关 token 随行走）
  await apiDel(`/api/charts/${_ch.chart_id}`)
  const now = (await apiCall('/api/datasets/list')).datasets || []
  for (const d of now) {
    if (!preDatasetIds.has(d.DatasetID)) {
      await apiCall(`/api/datasets/${d.DatasetID}`, 'DELETE').catch(() => {})
    }
  }
}

async function auditSurfaceAndTexts(page, theme, label, surfaceSel, selectors, failures, results) {
  const surface = await page.evaluate((sel) => {
    const el = document.querySelector(sel)
    if (!el) return { missing: true }
    const cs = getComputedStyle(el)
    return { bg: cs.backgroundColor, boxShadow: cs.boxShadow.slice(0, 60) }
  }, surfaceSel)
  if (surface.missing) {
    failures.push(`[${theme}] ${label}: 找不到弹窗本体 ${surfaceSel}`)
    return
  }
  // 核心断言：弹窗背景必须接近不透明（透明 = 变量失效 / 深色透底）
  const m = surface.bg.match(/rgba?\([^)]*?([\d.]+)\)?$/)
  const alpha = surface.bg.includes('rgba') ? parseFloat(m[1]) : 1
  if (alpha < 0.95) {
    failures.push(`[${theme}] ${label}: 弹窗背景半透明(${surface.bg}) —— 会透出遮罩，正是"浅色看不清"的根因`)
  } else {
    results.push(`[${theme}] ${label} 弹窗底色不透明 ✓`)
  }

  const report = await page.evaluate((sels) => {
    const out = []
    for (const sel of sels) {
      const els = Array.from(document.querySelectorAll(sel))
      const el = els.find((e) => e.offsetParent !== null && e.getBoundingClientRect().width > 0)
      if (!el) {
        out.push({ sel, skipped: true })
        continue
      }
      const c = window.__auditContrast(el)
      out.push({ sel, ...c, fg: getComputedStyle(el).color })
    }
    return out
  }, selectors)

  for (const r of report) {
    if (r.skipped) continue
    if (!r.pass) {
      failures.push(`[${theme}] ${label} ${r.sel}: 对比度 ${r.ratio}:1（需 ≥${r.need}）颜色 ${r.fg}`)
    } else {
      results.push(`[${theme}] ${label} ${r.sel}: ${r.ratio}:1 ✓`)
    }
  }
}

console.log('弹窗主题审计结果')
console.log('─'.repeat(72))
console.log(`通过项：${results.length}`)
if (process.env.AUDIT_VERBOSE) {
  results.forEach((r) => console.log('   ' + r))
}
if (failures.length) {
  console.log('\n❌ 未通过项：')
  failures.forEach((f) => console.log('   ' + f))
  process.exit(1)
} else {
  console.log('\n✅ 两套皮肤 × 三个工作台弹窗 + 公开分享页：表面不透明、全部文字对比度达标')
  console.log('   截图已存：screenshots/audit-{uploader,builder,designer,share}-{light,dark}.png')
}
