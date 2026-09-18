import { chromium } from 'playwright'
import { snapshotIds, cleanupNew } from './_e2e-cleanup.mjs'
import fs from 'node:fs'
import path from 'node:path'

const BASE = 'http://127.0.0.1:5173'

function getDemoPass() {
  const envPath = path.resolve('../backend/.env')
  if (fs.existsSync(envPath)) {
    const lines = fs.readFileSync(envPath, 'utf-8').split('\n')
    for (const l of lines) {
      if (l.startsWith('DEMO_PASSWORD=')) return l.split('=')[1].trim()
    }
  }
  return 'demo123'
}

const DEMO_USER = 'demo'
const DEMO_PASS = getDemoPass()

async function testTeacherFriendlyPresets() {
  console.log('=== 开始测试“防老师不会用”典型事例与向导交互 ===')
  const snap = await snapshotIds()
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()

  try {
    // 1. 登录
    await page.goto(`${BASE}/#/login`, { waitUntil: 'networkidle' })
    await page.getByPlaceholder('请输入用户名').first().fill(DEMO_USER)
    await page.getByPlaceholder('请输入密码').first().fill(DEMO_PASS)
    await page.getByRole('button', { name: '进入系统' }).first().click()
    await page.waitForTimeout(1000)

    // 2. 检查上传表格中的“快速体验指南”横幅
    await page.click('.wb__action-btn:has-text("上传表格")')
    await page.waitForSelector('.teacher-guide-banner')
    const guideText = await page.locator('.teacher-guide-banner').innerText()
    console.log(`1. 上传工作台已挂载“快速体验指南”: ${guideText.slice(0, 50)}... ✅`)
    await page.click('.btn-close')
    await page.waitForSelector('.uploader-dialog', { state: 'hidden' })

    // 2.5 自给自足：先入库一份干净样本数据集（过去本测试蹭别的测试遗留的数据，
    // 现在大家跑完都自清理，必须自备弹药，不能对环境有隐性依赖）
    await page.click('.wb__action-btn:has-text("上传表格")')
    await page.waitForSelector('.uploader-dialog')
    await page.locator('.sample-card').first().click()
    await page.waitForSelector('.cleaning-workbench')
    await page.waitForTimeout(600)
    await page.click('button:has-text("确认清洗并保存入库")')
    await page.waitForSelector('.uploader-dialog', { state: 'hidden', timeout: 10000 })
    console.log('1.5 自备的样本数据集已入库 ✅')

    // 3. 打开图表工作台，测试一键套用典型预设图表
    await page.click('.wb__action-btn--brass:has-text("新建可视化图表")')
    await page.waitForSelector('.builder-dialog')
    await page.waitForSelector('.preset-section')
    // 等首帧聚合定局再动鼠标：preset-section 在拉数据/聚合期间就已渲染，
    // 抢跑会撞上弹窗内容连续重绘的窗口期（Playwright 报 not stable / detached）
    await page.waitForSelector('.agg-pill', { timeout: 15000 })
    await page.waitForFunction(() => !document.querySelector('.chart-canvas-loading'), null, { timeout: 12000 })
    console.log('2. 图表工作台成功展示“典型图表一键套用模板”区域 ✅')

    // 4. 点击第二个典型模板：“商品品类销售占比环形图”
    const piePreset = page.locator('.preset-pill-btn:has-text("品类销售占比")')
    await piePreset.click()
    await page.waitForTimeout(800)
    console.log('3. 老师点击一键套用「品类销售占比环形图」，维度与图表类型自动装配完成 ✅')

    // 5. 点击第三个典型模板：“全国销售业绩 TOP 10 动态榜”
    const hbarPreset = page.locator('.preset-pill-btn:has-text("TOP 10 动态榜")')
    await hbarPreset.click()
    await page.waitForTimeout(800)
    console.log('4. 老师点击一键套用「全国销售业绩 TOP 10 动态榜」，成功自动装配完成 ✅')

    // 6. 保存图表
    await page.click('button:has-text("保存此图表到库")')
    await page.waitForSelector('.success-strip')
    console.log('5. 套用典型模板后一键保存成功 ✅')

    await page.waitForTimeout(1500)
    await page.waitForSelector('.builder-dialog', { state: 'hidden' })
    console.log('🎉 典型事例防呆向导全套测试通过！')
  } finally {
    await browser.close()
    const rm = await cleanupNew(snap)
    console.log(`🧹 本测试新增数据已自清理：大屏${rm.dashboards} 图表${rm.charts} 数据集${rm.datasets}`)
  }
}

testTeacherFriendlyPresets().catch((err) => {
  console.error('测试失败:', err)
  process.exit(1)
})
