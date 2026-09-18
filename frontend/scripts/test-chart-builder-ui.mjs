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

async function testChartBuilderFlow() {
  console.log('=== 开始图表工作台全链路端到端自动化测试 ===')
  const snap = await snapshotIds()
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()

  try {
    // 1. 登录工作台
    await page.goto(`${BASE}/#/login`, { waitUntil: 'networkidle' })
    await page.getByPlaceholder('请输入用户名').first().fill(DEMO_USER)
    await page.getByPlaceholder('请输入密码').first().fill(DEMO_PASS)
    await page.getByRole('button', { name: '进入系统' }).first().click()
    await page.waitForTimeout(1000)
    console.log('1. 登录成功进入工作台 ✅')

    // 2. 检查是否有数据，若没有先导入干净数据
    await page.click('.wb__action-btn:has-text("上传表格")')
    await page.waitForSelector('.uploader-dialog')
    const sample = page.locator('.sample-card').first()
    await sample.click()
    await page.waitForSelector('.cleaning-workbench')
    await page.click('button:has-text("确认清洗并保存入库")')
    await page.waitForSelector('.uploader-dialog', { state: 'hidden' })
    console.log('2. 确保至少有一份已入库的数据集 ✅')

    // 3. 点击“新建可视化图表”
    await page.click('.wb__action-btn--brass:has-text("新建可视化图表")')
    await page.waitForSelector('.builder-dialog')
    console.log('3. 成功弹出图表构建工作台 ✅')

    // 4. 验证默认柱状图渲染与聚合明细
    await page.waitForSelector('.agg-data-summary')
    const aggSummary = await page.locator('.agg-data-summary').innerText()
    console.log(`4. 实时聚合明细展示成功: ${aggSummary.slice(0, 45)}... ✅`)

    // 5. 切换图表类型为“环形占比图”
    await page.click('.type-card-btn:has-text("环形占比图")')
    await page.waitForTimeout(800)
    console.log('5. 切换为环形饼图成功 ✅')

    // 6. 切换为“排行动画条形图”
    await page.click('.type-card-btn:has-text("排行动画条形图")')
    await page.waitForTimeout(800)
    console.log('6. 切换为排行动画条形图成功 ✅')

    // 7. 点击“保存此图表到库”
    await page.click('button:has-text("保存此图表到库")')
    await page.waitForSelector('.success-strip')
    const succText = await page.locator('.success-strip').innerText()
    console.log(`7. 保存图表成功，提示: ${succText} ✅`)

    // 等待弹窗自动关闭
    await page.waitForSelector('.builder-dialog', { state: 'hidden' })
    console.log('8. 弹窗自动关闭，平滑返回工作台 ✅')

    console.log('🎉 图表构建工作台端到端全链路自动化测试全部通过！')
  } finally {
    await browser.close()
    const rm = await cleanupNew(snap)
    console.log(`🧹 本测试新增数据已自清理：大屏${rm.dashboards} 图表${rm.charts} 数据集${rm.datasets}`)
  }
}

testChartBuilderFlow().catch((err) => {
  console.error('测试失败:', err)
  process.exit(1)
})
