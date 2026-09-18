/**
 * 第 7 阶段 导出与分享 端到端测试。
 *
 * 覆盖：工作台开分享 → 复制 → 匿名访客打开分享页（免登录）→ 联动可用
 *       → 放映/分享页各导出一次 PNG（真下载、校验体积）
 *       → 作者关闭分享 → 访客重开链接立即作废 → API 清理回基线。
 * 与大屏 E2E 同一套自清理纪律：snapshotIds + finally cleanupNew。
 */
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
import { snapshotIds, cleanupNew } from './_e2e-cleanup.mjs'

const BASE = 'http://127.0.0.1:5173'
const API = 'http://127.0.0.1:8000'

function getDemoPass() {
  const envPath = path.resolve('../backend/.env')
  for (const l of fs.readFileSync(envPath, 'utf-8').split('\n')) {
    if (l.startsWith('DEMO_PASSWORD=')) return l.split('=')[1].trim()
  }
  return ''
}

async function apiFetch(p, opts = {}) {
  const r = await fetch(API + p, {
    method: opts.method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  return { status: r.status, json: await r.json().catch(() => ({})) }
}

async function provision() {
  const { json: login } = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: { username: 'demo', password: getDemoPass() },
  })
  const token = login.token
  const raw = await apiFetch('/api/datasets/preview-sample', {
    method: 'POST', token, body: { filename: '电商销售_干净数据.csv' },
  })
  const d = raw.json.data
  const cl = await apiFetch('/api/datasets/clean-preview', {
    method: 'POST', token,
    body: {
      headers: d.headers, raw_matrix: d.raw_preview_matrix,
      fill_down_merged: true, filter_summary_rows: true,
      filter_empty_rows: true, auto_convert_numbers: true,
    },
  })
  const sv = await apiFetch('/api/datasets/save', {
    method: 'POST', token,
    body: {
      name: '分享E2E数据集', source_file_name: '电商销售_干净数据.csv',
      columns: cl.json.columns, rows: cl.json.preview_rows, cleaning_log: cl.json.cleaning_logs,
    },
  })
  const ch = await apiFetch('/api/charts/save', {
    method: 'POST', token,
    body: {
      dataset_id: sv.json.dataset_id, title: '分享E2E图表', chart_type: 'bar',
      // 刻意用构建器真实存法：config = 裸 ECharts option（不包 {option:…}），
      // 与 test-dashboard-ui 的包裹形态形成双覆盖，防契约再次漂移
      config: { xAxis: { type: 'category', data: ['甲', '乙'] }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: [3, 5] }] },
    },
  })
  const name = `分享E2E大屏-${Date.now() % 100000}`
  const db = await apiFetch('/api/dashboards/save', {
    method: 'POST', token,
    body: {
      title: name,
      layout: { canvas: { w: 1920, h: 1080 }, items: [
        { id: 'p1', chart_id: ch.json.chart_id, x: 60, y: 60, w: 860, h: 500, z: 1 },
        { id: 'p2', chart_id: ch.json.chart_id, x: 1000, y: 60, w: 860, h: 500, z: 2 },
      ] },
    },
  })
  return { token, datasetId: sv.json.dataset_id, chartId: ch.json.chart_id, dashId: db.json.dashboard_id, name }
}

const step = (n, msg) => console.log(`${n}. ${msg} ✅`)

const errors = []
let browser
let snap

try {
  console.log('=== 第 7 阶段 导出与分享 端到端测试 ===')
  snap = await snapshotIds()
  const prov = await provision()
  if (!prov.dashId) throw new Error('备料失败：大屏未建出来')
  step('备料', `API 建好 图表${prov.chartId} + 大屏${prov.dashId}「${prov.name}」`)

  browser = await chromium.launch({ headless: true })

  // ── 作者端：登录 → 分享 → 复制链接 ──
  const ownerCtx = await browser.newContext({ viewport: { width: 1600, height: 950 } })
  await ownerCtx.addInitScript((tk) => localStorage.setItem('moheng-token', tk), prov.token)
  const owner = await ownerCtx.newPage()
  owner.on('pageerror', (e) => errors.push(`作者页脚本错误: ${e.message}`))
  owner.on('console', (m) => { if (m.type() === 'error') errors.push(`作者页控制台: ${m.text()}`) })
  await owner.goto(`${BASE}/#/workbench`, { waitUntil: 'networkidle' })
  await owner.waitForTimeout(800)

  const card = owner.locator('.wb__dash-card').filter({ hasText: prov.name })
  if (!(await card.count())) throw new Error('工作台找不到目标大屏卡片')
  await card.locator('.btn-ghost:has-text("分享")').click()
  await owner.waitForSelector('.wb__share-input')
  const shareUrl = await owner.locator('.wb__share-input').inputValue()
  if (!shareUrl.includes(`/#/share/`) || shareUrl.length < 40) throw new Error(`分享链接异常：${shareUrl}`)
  step('开启分享', `链接已生成：${shareUrl.slice(0, 46)}…`)

  await card.locator('.wb__dash-share .btn-ghost:has-text("复制")').click()
  await owner.waitForSelector('.wb__dash-share .btn-ghost:has-text("已复制")', { timeout: 4000 })
  step('复制链接', '点击复制 → 按钮变「✓ 已复制」')

  if (!(await owner.locator('.badge:has-text("已公开")').count())) throw new Error('卡片未出现"已公开"徽标')
  step('分享徽标', '卡片显示 🔗 已公开')

  // ── 作者放映页导出 PNG（真实下载事件）──
  const dl1p = owner.waitForEvent('download', { timeout: 20000 })
  await card.locator('.btn-primary').click()
  await owner.waitForSelector('.viewer .panel')
  await owner.click('.viewer__bar .btn-ghost:has-text("导出图片")')
  const dl1 = await dl1p
  const f1 = await dl1.path()
  const sz1 = fs.statSync(f1).size
  if (sz1 < 50000) throw new Error(`放映页导出 PNG 体积异常仅 ${sz1}B（疑似空白图）`)
  step('放映导出', `下载「${dl1.suggestedFilename()}」 ${(sz1 / 1024).toFixed(0)}KB`)
  await owner.locator('.viewer__bar .btn-ghost--brass').click()
  await owner.waitForSelector('.viewer', { state: 'hidden' })

  // ── 匿名访客：全新无登录态上下文 ──
  const guestCtx = await browser.newContext({ viewport: { width: 1600, height: 950 } })
  const guest = await guestCtx.newPage()
  guest.on('pageerror', (e) => errors.push(`访客页脚本错误: ${e.message}`))
  guest.on('console', (m) => { if (m.type() === 'error') errors.push(`访客页控制台: ${m.text()}`) })
  await guest.goto(shareUrl, { waitUntil: 'networkidle' })
  await guest.waitForSelector('.share__bar', { timeout: 10000 })
  await guest.waitForFunction(
    () => document.querySelector('.share__stage .panel') || document.querySelector('.share__invalid'),
    null, { timeout: 12000 },
  )
  if (await guest.locator('.share__invalid').count()) {
    throw new Error(`访客打开分享页被判无效：${await guest.locator('.share__invalid-msg').innerText()}`)
  }
  const gPanels = await guest.locator('.share__stage .panel').count()
  if (gPanels !== 2) throw new Error(`分享画面板数应为 2，实际 ${gPanels}`)
  const hasToken = await guest.evaluate(() => !!localStorage.getItem('moheng-token'))
  if (hasToken) throw new Error('访客上下文竟带有登录令牌')
  step('匿名访问', `免登录渲染 ${gPanels} 块面板，访客上下文零令牌`)

  // ── 访客也能联动（坐标换算 + 缩放系数 + 遮挡检测）──
  const hit = await guest.evaluate(() => {
    for (const p of document.querySelectorAll('.share__stage .panel')) {
      const inst = p.__panelChart
      if (!inst) continue
      const dom = inst.getDom().getBoundingClientRect()
      const kx = dom.width / inst.getWidth()
      const ky = dom.height / inst.getHeight()
      for (const probe of [[0, 1.5], [1, 2.5]]) {
        const px = inst.convertToPixel({ seriesIndex: 0 }, probe)
        if (!px) continue
        const x = dom.left + px[0] * kx
        const y = dom.top + px[1] * ky
        const top = document.elementFromPoint(x, y)
        if (top && p.contains(top)) return { x, y, key: probe[0] === 0 ? '甲' : '乙' }
      }
    }
    return null
  })
  if (!hit) throw new Error('访客页找不到可点击柱体')
  await guest.mouse.click(hit.x, hit.y)
  await guest.waitForSelector('.share__link.is-on', { timeout: 5000 })
  const chip = await guest.locator('.share__link').innerText()
  if (!chip.includes(hit.key) || !chip.includes('2 块图表')) throw new Error(`访客联动文案异常：${chip}`)
  step('访客联动', `点柱体「${hit.key}」→ ${chip}`)

  // ── 访客导出 PNG（分享页也提供）──
  const dl2p = guest.waitForEvent('download', { timeout: 20000 })
  await guest.click('.share__bar .btn-ghost:has-text("导出图片")')
  const dl2 = await dl2p
  const sz2 = fs.statSync(await dl2.path()).size
  if (sz2 < 50000) throw new Error(`分享页导出 PNG 体积异常仅 ${sz2}B`)
  step('访客导出', `下载「${dl2.suggestedFilename()}」 ${(sz2 / 1024).toFixed(0)}KB`)
  await guestCtx.close()

  // ── 作者关闭分享 → 访客旧链接立即作废 ──
  await card.locator('.wb__dash-share .wb__share-off').click()
  await owner.waitForSelector('.wb__share-input', { state: 'hidden', timeout: 8000 })
  if (await owner.locator(`.wb__dash-card:has-text("${prov.name}") .badge:has-text("已公开")`).count()) {
    throw new Error('关闭分享后"已公开"徽标未消失')
  }
  step('关闭分享', '链接面板收起，徽标消失')

  const guest2 = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const g2 = await guest2.newPage()
  await g2.goto(shareUrl, { waitUntil: 'networkidle' })
  await g2.waitForSelector('.share__invalid', { timeout: 10000 })
  const invMsg = await g2.locator('.share__invalid-msg').innerText()
  if (!invMsg.includes('无效') && !invMsg.includes('关闭')) throw new Error(`作废提示不明确：${invMsg}`)
  step('链接作废', `旧链接访客所见：「${invMsg}」`)
  await guest2.close()

  if (errors.length) throw new Error(`存在页面报错：\n${errors.join('\n')}`)
  console.log('\n🎉 第 7 阶段导出与分享端到端测试全部通过（且无控制台报错）！')
} catch (err) {
  console.error('\n❌ 测试失败:', err.message)
  process.exitCode = 1
} finally {
  await browser?.close()
  if (snap) {
    await cleanupNew(snap)
    console.log('🧹 本测试新增数据已自清理')
  }
}
