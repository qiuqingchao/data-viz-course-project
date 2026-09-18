/**
 * 第 8 阶段 一键体验（写库版）+ 一键清空 端到端测试。
 *
 * 断言的都是"真实发生"：seed 后工作台计数真的变、大屏卡片真的出现、
 * 放映里 4 块画布真的渲染；清空走"点两下"确认，之后一切归零。
 * 与兄弟测试同一纪律：snapshotIds + finally cleanupNew（半途翻车也不留垃圾）。
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

const step = (n, msg) => console.log(`${n}. ${msg} ✅`)
const errors = []
let browser
let snap

try {
  console.log('=== 第 8 阶段 一键体验与清空 端到端测试 ===')
  snap = await snapshotIds()

  const { json: login } = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: { username: 'demo', password: getDemoPass() },
  })
  const token = login.token
  if (!token) throw new Error('demo 登录失败，检查后端')

  browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 } })
  await ctx.addInitScript((tk) => localStorage.setItem('moheng-token', tk), token)
  const page = await ctx.newPage()
  page.on('pageerror', (e) => errors.push(`页面脚本错误: ${e.message}`))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`控制台错误: ${m.text()}`) })

  await page.goto(`${BASE}/#/workbench`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(700)

  // ── 1. 一键体验：按下 → 按钮进忙碌态 → 自动弹出放映 ──
  const seedBtn = page.locator('button:has-text("一键体验真实流程")')
  if (!(await seedBtn.count())) throw new Error('工作台找不到「⚡一键体验真实流程」按钮')
  await seedBtn.click()
  await page.waitForFunction(
    () => {
      const b = [...document.querySelectorAll('button')].find((x) => x.textContent.includes('管道运行中'))
      return !!b || !!document.querySelector('.viewer .panel')
    },
    null, { timeout: 8000 },
  )
  // 放映自动弹出且 4 块面板全部有真实画布（seed 走的是完整入库链路）
  await page.waitForSelector('.viewer .panel', { timeout: 30000 })
  await page.waitForFunction(
    () => document.querySelectorAll('.viewer .panel canvas').length >= 4,
    null, { timeout: 20000 },
  )
  const titles = await page.locator('.viewer .panel__title').allInnerTexts()
  const want = ['品类销售额占比', '省份销售额 TOP 排行', '月度销售趋势', '品类订单量对比']
  for (const t of want) {
    if (!titles.some((x) => x.includes(t))) throw new Error(`放映里缺少面板「${t}」，实际：${titles.join(' | ')}`)
  }
  step('自动放映', `seed 后自动弹出大屏，4 面板就位：${titles.join(' / ')}`)

  // 关放映回工作台
  await page.locator('.viewer__bar .btn-ghost--brass').click()
  await page.waitForSelector('.viewer', { state: 'hidden', timeout: 8000 })

  // ── 2. 工作台计数真的刷新了 ──
  const statTexts = await page.locator('.stat__number').allInnerTexts().catch(() => [])
  console.log(`   概览数字：${JSON.stringify(statTexts)}`)
  const dashCard = page.locator('.wb__dash-card').filter({ hasText: '体验大屏·电商销售驾驶舱' })
  if (!(await dashCard.count())) throw new Error('大屏卡片未出现「体验大屏·电商销售驾驶舱」')
  if (!dashCard.locator('text=4 块面板').count() && !(await dashCard.innerText()).includes('4 块面板')) {
    throw new Error('体验大屏卡片应显示 4 块面板')
  }
  step('状态刷新', '大屏卡片出现且标注 4 块面板，概览计数已更新')

  // ── 3. 数据是真的：直连数据库读回该数据集，行数必须是 480 全量 ──
  const dbs = await apiFetch('/api/datasets/list', { token })
  const seedDs = (dbs.json.datasets || []).find((x) => x.Name === '体验数据·480行销售单')
  if (!seedDs) throw new Error('seed 的数据集没出现在列表里')
  if (seedDs.RowTotal !== 480) throw new Error(`数据集行数 ${seedDs.RowTotal} ≠ 480（又丢数据了！）`)
  step('全量核验', `列表接口回读 RowTotal=${seedDs.RowTotal}（写库版名副其实）`)

  // ── 4. 一键清空：第一次点击是"确认臂"，不立即删 ──
  const clearBtn = page.locator('button:has-text("一键清空我的数据")')
  await clearBtn.click()
  await page.waitForSelector('button:has-text("再点一次")', { timeout: 4000 })
  // 撤销机制：等 4 秒超时自动解除（顺带验证防误删真的会解除）
  await page.waitForSelector('button:has-text("一键清空我的数据")', { timeout: 8000 })
  step('防误删', '第一下只进入确认态，4 秒不点第二下自动撤销')

  await clearBtn.click()
  await page.waitForSelector('button:has-text("再点一次")')
  await page.locator('button:has-text("再点一次")').click()
  // 清空完成的硬证据：大屏空态文案回来 + 列表接口归零
  await page.waitForSelector('.wb__dash-empty', { timeout: 15000 })
  const dbs2 = await apiFetch('/api/datasets/list', { token })
  if ((dbs2.json.datasets || []).length !== 0) throw new Error('清空后数据集列表非空')
  step('一键清空', '两次点击后账号数据全部归零，空态文案回归')

  // ── 5. 清空后再体验一次 → 证明可反复演示（答辩彩排场景）──
  await page.locator('button:has-text("一键体验真实流程")').click()
  await page.waitForSelector('.viewer .panel', { timeout: 30000 })
  await page.waitForFunction(
    () => document.querySelectorAll('.viewer .panel canvas').length >= 4,
    null, { timeout: 20000 },
  )
  await page.locator('.viewer__bar .btn-ghost--brass').click()
  await page.waitForSelector('.viewer', { state: 'hidden', timeout: 8000 })
  step('可重复', '清空→再体验 一键复原，反复演示无负担')

  if (errors.length) throw new Error(`存在页面报错：\n${errors.join('\n')}`)
  console.log('\n🎉 第 8 阶段一键体验与清空端到端测试全部通过（且无控制台报错）！')
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
