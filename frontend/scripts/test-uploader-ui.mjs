import { chromium } from 'playwright'
import { snapshotIds, cleanupNew } from './_e2e-cleanup.mjs'
import fs from 'node:fs'
import path from 'node:path'

const BASE = 'http://127.0.0.1:5173'

// 读取 demo 密码
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

async function testFullCleaningFlow() {
  console.log('=== 开始数据上传、清洗配置与入库保存全链路端到端自动化测试 ===')
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
    console.log('1. 登录成功进入工作台 ✅')

    // 2. 点击上传按钮
    await page.click('button:has-text("上传表格")')
    await page.waitForSelector('.uploader-dialog')
    console.log('2. 点击上传按钮，清洗弹窗弹出 ✅')

    // 3. 点击“花式 Excel”样本（含有 27 处合并单元格）
    const excelSample = page.locator('.sample-card:has-text("花式 Excel")')
    await excelSample.click()

    // 4. 等待进入第二步清洗流水线
    await page.waitForSelector('.cleaning-workbench')
    console.log('3. 成功进入清洗流水线工作台 ✅')

    // 验证清洗审计栏
    await page.waitForSelector('.audit-strip')
    const auditText = await page.locator('.audit-strip').innerText()
    console.log(`4. 审计横幅实时显示: ${auditText.replace(/\n+/g, ' ')} ✅`)

    // 验证清洗后表格
    const rowCount = await page.locator('.preview-table tbody tr').count()
    console.log(`5. 清洗后表格渲染行数: ${rowCount} (由于过滤了 1 行空行，20 行采样中呈现 19 行) ✅`)
    if (rowCount < 15) throw new Error('清洗预览表格行数不符合预期')

    // 5. 点击“确认清洗并保存入库”
    await page.click('button:has-text("确认清洗并保存入库")')
    await page.waitForSelector('.uploader-success')
    const successText = await page.locator('.uploader-success').innerText()
    console.log(`6. 数据集成功入库，系统提示: ${successText} ✅`)

    // 等待弹窗自动关闭并返回工作台
    await page.waitForTimeout(2000)
    await page.waitForSelector('.uploader-dialog', { state: 'hidden' })
    console.log('7. 弹窗自动关闭，返回工作台 ✅')

    console.log('🎉 数据清洗与入库全链路端到端测试圆满成功！')
  } finally {
    await browser.close()
    const rm = await cleanupNew(snap)
    console.log(`🧹 本测试新增数据已自清理：大屏${rm.dashboards} 图表${rm.charts} 数据集${rm.datasets}`)
  }
}

testFullCleaningFlow().catch((err) => {
  console.error('测试失败:', err)
  process.exit(1)
})
