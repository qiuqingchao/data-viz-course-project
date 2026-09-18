/**
 * 一分钟流程彩排（答辩前一键自查 + 留关键帧截图）。
 *
 * 按演讲稿里的演示手顺真实走一遍：
 *   深色皮肤登录 → ⚡一键体验（写库）→ 自动放映 → 点扇区联动 → ⬇导出 PNG（真下载校验）
 *   → 无痕视角看分享 → 🧹一键清空归零。
 * 全程计时，最后告诉你"总耗时是否 ≤ 60 秒"，并打印每步耗时。
 *
 * 用法（需前后端都在运行，且 backend/.env 里有 DEMO_PASSWORD）：
 *   cd frontend && PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers node scripts/rehearse-one-minute.mjs
 * 截图落在 ../screenshots/rehearsal-*.png。跑完自动把数据库清回基线。
 */
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
import { snapshotIds, cleanupNew } from './_e2e-cleanup.mjs'

const BASE = 'http://127.0.0.1:5173'
const API = 'http://127.0.0.1:8000'
const SHOT = path.resolve('../screenshots')
fs.mkdirSync(SHOT, { recursive: true })

function getDemoPass() {
  const envPath = path.resolve('../backend/.env')
  for (const l of fs.readFileSync(envPath, 'utf-8').split('\n')) {
    if (l.startsWith('DEMO_PASSWORD=')) return l.split('=')[1].trim()
  }
  return ''
}
async function api(p, o = {}) {
  const r = await fetch(API + p, {
    method: o.method || 'GET',
    headers: { 'Content-Type': 'application/json', ...(o.token ? { Authorization: `Bearer ${o.token}` } : {}) },
    body: o.body ? JSON.stringify(o.body) : undefined,
  })
  return r.json().catch(() => ({}))
}

const T0 = Date.now()
const mark = (s) => console.log(`  ⏱ ${((Date.now() - T0) / 1000).toFixed(1)}s  ${s}`)
let browser
let snap

try {
  console.log('=== 一分钟流程彩排 ===')
  snap = await snapshotIds()
  const login = await api('/api/auth/login', { method: 'POST', body: { username: 'demo', password: getDemoPass() } })
  if (!login.token) throw new Error('demo 登录失败，检查后端与 DEMO_PASSWORD')
  mark('demo 令牌签发')

  browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 } })
  await ctx.addInitScript((tk) => {
    localStorage.setItem('moheng-theme', 'dark') // 答辩机预设深色皮肤
    localStorage.setItem('moheng-token', tk)
  }, login.token)
  const page = await ctx.newPage()
  await page.goto(`${BASE}/#/workbench`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(700)
  await page.screenshot({ path: `${SHOT}/rehearsal-1-workbench.png` })
  mark('工作台（深色）就位')

  // ⚡ 一键体验
  await page.click('button:has-text("一键体验真实流程")')
  await page.waitForSelector('.viewer .panel', { timeout: 30000 })
  await page.waitForFunction(() => document.querySelectorAll('.viewer .panel canvas').length >= 4, null, { timeout: 20000 })
  await page.waitForTimeout(900)
  await page.screenshot({ path: `${SHOT}/rehearsal-2-viewer.png` })
  mark('体验生成 + 自动放映（4 面板画布就位）')

  // 联动：点饼图第一个扇区（极坐标取样，含缩放系数）
  const hit = await page.evaluate(() => {
    for (const p of document.querySelectorAll('.viewer .panel')) {
      const inst = p.__panelChart
      if (!inst) continue
      const series = inst.getOption().series || []
      const pieIdx = series.findIndex((s) => s && s.type === 'pie')
      if (pieIdx < 0) continue
      const names = (series[pieIdx].data || []).map((d) => d && d.name).filter(Boolean)
      if (!names.length) continue
      const name = names[0]
      const dom = inst.getDom().getBoundingClientRect()
      const kx = dom.width / inst.getWidth()
      const ky = dom.height / inst.getHeight()
      const pt = inst.convertToPixel({ seriesIndex: pieIdx }, [0, 0]) || [dom.width / 2, dom.height / 2]
      const cx = pt[0], cy = pt[1]
      const r = Math.min(inst.getWidth(), inst.getHeight()) * 0.28
      const ang = Math.PI / 4
      const x = dom.left + (cx + r * Math.cos(ang)) * kx
      const y = dom.top + (cy - r * Math.sin(ang)) * ky
      const top = document.elementFromPoint(x, y)
      if (top && p.contains(top)) return { x, y, name }
    }
    return null
  })
  if (hit) {
    await page.mouse.click(hit.x, hit.y)
    await page.waitForSelector('.viewer__link.is-on', { timeout: 5000 }).catch(() => {})
    const chip = await page.locator('.viewer__link').innerText().catch(() => '')
    await page.screenshot({ path: `${SHOT}/rehearsal-3-linkage.png` })
    mark(`联动演示：${chip.trim() || '（未点亮，扇区坐标需再校准）'}`)
    await page.keyboard.press('Escape')
  } else {
    mark('联动演示：未找到饼图面板（跳过）')
  }

  // ⬇ 导出 PNG（真实下载）
  const dlp = page.waitForEvent('download', { timeout: 20000 })
  await page.click('.viewer__bar .btn-ghost:has-text("导出图片")')
  const dl = await dlp
  mark(`导出 PNG：「${dl.suggestedFilename()}」 ${(fs.statSync(await dl.path()).size / 1024).toFixed(0)}KB`)
  await page.locator('.viewer__bar .btn-ghost--brass').click()
  await page.waitForSelector('.viewer', { state: 'hidden', timeout: 8000 })

  // 分享：开链接
  await page.click('.wb__dash-card .btn-ghost:has-text("分享")')
  await page.waitForSelector('.wb__share-input', { timeout: 8000 })
  const shareUrl = await page.locator('.wb__share-input').inputValue()
  mark(`分享链接生成：${shareUrl.slice(0, 44)}…`)
  // 访客无痕视角
  const guest = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const gp = await guest.newPage()
  await gp.goto(shareUrl, { waitUntil: 'networkidle' })
  await gp.waitForFunction(() => document.querySelectorAll('.share__stage .panel').length >= 4, null, { timeout: 15000 })
  await gp.waitForTimeout(700)
  await gp.screenshot({ path: `${SHOT}/rehearsal-4-share-guest.png` })
  mark('访客免登录打开分享页（4 面板渲染）')
  await guest.close()

  // 🧹 一键清空（两下）
  await page.click('button:has-text("一键清空我的数据")')
  await page.waitForSelector('button:has-text("再点一次")', { timeout: 5000 })
  await page.click('button:has-text("再点一次")')
  await page.waitForSelector('.wb__dash-empty', { timeout: 15000 })
  const health = await api('/api/health')
  await page.screenshot({ path: `${SHOT}/rehearsal-5-cleared.png` })
  mark(`一键清空归零：${JSON.stringify(health.table_counts)}`)

  const secs = (Date.now() - T0) / 1000
  console.log(`\n总耗时 ${secs.toFixed(1)} 秒 —— ${secs <= 60 ? '一分钟流程达标 ✅' : '超过 60 秒 ❌（彩排未通过）'}`)
  if (secs > 60) process.exitCode = 1
} catch (err) {
  console.error('\n❌ 彩排中断:', err.message)
  process.exitCode = 1
} finally {
  await browser?.close()
  if (snap) {
    await cleanupNew(snap)
    console.log('🧹 彩排数据已清回基线')
  }
}
