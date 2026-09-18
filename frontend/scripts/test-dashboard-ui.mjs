/**
 * 第 6 阶段：大屏组装全链路端到端测试。
 *
 * 覆盖：登录 → 备料(数据集+图表，走 API 更稳) → 打开设计器 →
 *       添加面板 → 真实鼠标拖拽移动 → 校验坐标变化 → 保存 →
 *       放映查看器渲染 → 工作台卡片出现 → 删除清理。
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

function countsOf(tc) {
  return { ds: tc['数据集'], ch: tc['图表'], db: tc['大屏'] }
}

async function apiFetch(pathName, { method = 'GET', body, token } = {}) {
  const res = await fetch(API + pathName, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await res.json().catch(() => ({}))
  return { status: res.status, json }
}

async function provisionData() {
  const { json: login } = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: { username: 'demo', password: getDemoPass() },
  })
  const token = login.token
  if (!token) throw new Error('拿不到 demo token')

  const { json: raw } = await apiFetch('/api/datasets/preview-sample', {
    method: 'POST',
    token,
    body: { filename: '电商销售_干净数据.csv' },
  })
  const { json: cleaned } = await apiFetch('/api/datasets/clean-preview', {
    method: 'POST',
    token,
    body: {
      headers: raw.data.headers,
      raw_matrix: raw.data.raw_preview_matrix,
      fill_down_merged: true,
      filter_summary_rows: true,
      filter_empty_rows: true,
      auto_convert_numbers: true,
    },
  })
  const { json: saved } = await apiFetch('/api/datasets/save', {
    method: 'POST',
    token,
    body: {
      name: '大屏E2E数据集',
      source_file_name: '电商销售_干净数据.csv',
      columns: cleaned.columns,
      rows: cleaned.preview_rows,
      cleaning_log: cleaned.cleaning_logs,
    },
  })
  const datasetId = saved.dataset_id

  const { json: chart } = await apiFetch('/api/charts/save', {
    method: 'POST',
    token,
    body: {
      dataset_id: datasetId,
      title: '大屏E2E图表',
      chart_type: 'bar',
      config: { option: { xAxis: { type: 'category', data: ['A', 'B', 'C'] }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: [3, 5, 2] }] } },
    },
  })
  return { token, datasetId, chartId: chart.chart_id }
}

let browser
const step = (n, msg) => console.log(`${n}. ${msg} ✅`)

// 基线：其它 E2E 可能各自留下（它们自己负责清），本测试只对"自己造的数据"负责。
// 快照必须在备料前抓；清场放 finally —— 中途崩了也不能漏脏数据。
const baseline = countsOf((await apiFetch('/api/health')).json.table_counts)
const snap = await snapshotIds()

try {
  console.log('=== 第 6 阶段 大屏组装端到端测试 ===')
  const { token, datasetId, chartId } = await provisionData()
  step('备料', `API 造好数据集 ${datasetId} + 图表 ${chartId}`)

  browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1600, height: 950 } })
  await context.addInitScript((tk) => {
    window.localStorage.setItem('moheng-token', tk)
  }, token)
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()) })

  await page.goto(`${BASE}/#/workbench`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(800)

  // 打开设计器
  await page.click('.wb__dash-new')
  await page.waitForSelector('.dash-dialog')
  step('设计器', '大屏设计器已弹出')

  // 图表库是异步拉取的：必须等加载结束（出现条目或空态），不能假设瞬间就位
  await page.waitForSelector('.palette-item, .palette-empty', { timeout: 8000 })
  const paletteCount = await page.locator('.palette-item').count()
  if (paletteCount < 1) throw new Error(`图表库为空（实际 ${paletteCount}）`)
  step('图表库', `侧栏列出 ${paletteCount} 张可拖入的图表`)

  // 添加两块面板
  await page.locator('.palette-add').first().click()
  await page.waitForTimeout(150)
  await page.locator('.palette-add').first().click()
  await page.waitForTimeout(150)
  const panelCount = await page.locator('.dash-stage .panel').count()
  if (panelCount !== 2) throw new Error(`画布面板数应为 2，实际 ${panelCount}`)
  step('添加面板', '两次添加，画布出现 2 块面板')

  // 真实拖拽最上层面板（两块面板瀑布式错位，.first() 被顶层遮挡会误点到 .last()，
  // 所以按 z 序取最靠上、真正落在鼠标下的那块来验证位移）
  const before = await page.locator('.dash-stage .panel').last().boundingBox()
  const box = before
  await page.mouse.move(box.x + box.width / 2, box.y + 18) // 抓头部
  await page.mouse.down()
  await page.mouse.move(box.x + 220, box.y + 140, { steps: 12 })
  await page.mouse.up()
  await page.waitForTimeout(250)
  const after = await page.locator('.dash-stage .panel').last().boundingBox()
  const moved = Math.abs(after.x - before.x) > 60 || Math.abs(after.y - before.y) > 30
  if (!moved) throw new Error(`拖拽未生效：before=(${Math.round(before.x)},${Math.round(before.y)}) after=(${Math.round(after.x)},${Math.round(after.y)})`)
  step('拖拽引擎', `面板被拖到 (${Math.round(after.x)},${Math.round(after.y)})，位移生效`)

  // 选中面板 → 右栏显示坐标
  await page.locator('.dash-stage .panel').last().click({ position: { x: 40, y: 12 } })
  await page.waitForSelector('.rail-props')
  step('属性轨', '选中面板后右侧显示 X/Y/宽/高')

  // 改个名并保存
  const dashName = `端到端测试大屏-${Date.now()%100000}`
  await page.fill('.dash-name-input', dashName)
  await page.click('.dash-footer .btn-primary')
  await page.waitForSelector('.dash-success', { timeout: 8000 })
  step('保存', await page.locator('.dash-success').innerText())

  // 弹窗自动关闭后，工作台应出现大屏卡片
  await page.waitForSelector('.dash-dialog', { state: 'hidden', timeout: 8000 })
  await page.waitForTimeout(500)
  const myCard = page.locator('.wb__dash-card').filter({ hasText: dashName })
  if (!(await myCard.count())) throw new Error(`工作台未出现名为「${dashName}」的大屏卡片`)
  step('工作台回显', `「我的大屏」区显示新卡片「${dashName}」`)

  // 打开放映查看器
  await myCard.locator('.btn-primary').click()
  await page.waitForSelector('.viewer')
  // 放映要拉"大屏+全部引用图表"的配置，校园网慢时 1.5 秒不够：等定局（有面板或报错）
  await page.waitForFunction(
    () => document.querySelector('.viewer .panel') || document.querySelector('.viewer__hint--err'),
    null,
    { timeout: 12000 },
  )
  const errHint = await page.locator('.viewer__hint--err').count()
  if (errHint) throw new Error(`放映加载报错：${await page.locator('.viewer__hint--err').innerText()}`)
  const vPanels = await page.locator('.viewer .panel').count()
  if (vPanels !== 2) throw new Error(`放映画布面板数应为 2，实际 ${vPanels}`)
  step('放映模式', `查看器渲染 ${vPanels} 块面板，${await page.locator('.viewer .panel canvas').count()} 个图表 canvas`)

  // ── 图表联动：换算柱体的屏幕坐标真点击。两个坑都要避开：
  //    ① convertToPixel 返回的是【未缩放】布局坐标，而画布被 transform:scale 整体缩放过，
  //       必须乘以 rect/getWidth 的实际缩放系数；
  //    ② 面板可能互相遮挡，用 elementFromPoint 确认候选点真的露在顶层再下手 ──
  const hit = await page.evaluate(() => {
    for (const p of document.querySelectorAll('.viewer .panel')) {
      const inst = p.__panelChart
      if (!inst) continue
      const dom = inst.getDom().getBoundingClientRect()
      const kx = dom.width / inst.getWidth()
      const ky = dom.height / inst.getHeight()
      // 本测试图表：类目 A/B，柱高 1/2 → [0,0.5]、[1,1.5] 必落在柱体内部
      for (const probe of [[0, 0.5], [1, 1.5]]) {
        const px = inst.convertToPixel({ seriesIndex: 0 }, probe)
        if (!px) continue
        const x = dom.left + px[0] * kx
        const y = dom.top + px[1] * ky
        const top = document.elementFromPoint(x, y)
        if (top && p.contains(top)) return { x, y, key: probe[0] === 0 ? 'A' : 'B' }
      }
    }
    return null
  })
  if (!hit) throw new Error('找不到一个未被遮挡、可点击的柱体坐标（__panelChart 钩子或换算异常？）')
  await page.mouse.click(hit.x, hit.y)
  await page.waitForTimeout(350)
  await page.waitForSelector('.viewer__link.is-on', { timeout: 5000 })
  const chipOn = await page.locator('.viewer__link').innerText()
  if (!chipOn.includes(`联动「${hit.key}」`) || !chipOn.includes('2 块图表')) {
    throw new Error(`联动状态条文案异常：${chipOn}`)
  }
  step('图表联动', `点击柱体「${hit.key}」后：${chipOn}`)

  // 再点一次同柱 → 解除
  await page.mouse.click(hit.x, hit.y)
  await page.waitForTimeout(350)
  if (await page.locator('.viewer__link.is-on').count()) throw new Error('二次点击未解除联动')
  step('联动解除·再点', '同一点再次点击，高亮与状态条复位')

  // 重新激活后用 ESC 解除（ESC 只退联动，不关放映）
  await page.mouse.click(hit.x, hit.y)
  await page.waitForTimeout(350)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(350)
  if (await page.locator('.viewer__link.is-on').count()) throw new Error('ESC 未解除联动')
  if (!(await page.locator('.viewer').count())) throw new Error('ESC 误关了放映窗口')
  step('联动解除·ESC', 'ESC 先退联动、放映窗口仍在（再按才退出）')

  // 关闭放映，两击删除大屏
  await page.locator('.viewer__bar .btn-ghost--brass').first().click()
  await page.waitForSelector('.viewer', { state: 'hidden' })
  await page.waitForTimeout(300)
  const delBtn = myCard.locator('.btn-ghost:has-text("删除")')
  await delBtn.click()
  await page.waitForTimeout(200)
  await delBtn.click()
  // 学校库走校园网，删除+列表刷新是两个串行往返：等"这张卡消失"这个结果，而非固定毫秒
  await myCard.waitFor({ state: 'hidden', timeout: 10000 })
  step('两击删除', `已删除大屏「${dashName}」，该卡片从工作台移除`)

  if (errors.length) {
    console.log('\n⚠️ 页面报错：\n  ' + errors.join('\n  '))
    throw new Error('存在控制台/页面错误')
  }
  console.log('\n🎉 第 6 阶段大屏组装端到端测试全部通过（且无控制台报错）！')
} catch (err) {
  console.error('\n❌ 测试失败:', err.message)
  process.exitCode = 1
} finally {
  await browser?.close()
  await cleanupNew(snap)
  const { json: health } = await apiFetch('/api/health')
  const now = countsOf(health.table_counts)
  if (now.ds !== baseline.ds || now.ch !== baseline.ch || now.db !== baseline.db) {
    console.error(`❌ 本测试数据未清干净：基线 ${JSON.stringify(baseline)} → 现在 ${JSON.stringify(now)}`)
    process.exitCode = 1
  } else {
    console.log(`🧹 数据闭环：表计数回到测试前基线 ${JSON.stringify(now)}`)
  }
}
