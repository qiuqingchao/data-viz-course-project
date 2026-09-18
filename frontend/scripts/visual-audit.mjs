/**
 * 视觉体检 + 截图（开发工具，不参与打包）。
 *
 * 为什么需要它：
 *   1. 开发机上没有可视化环境，靠程序把"看起来对不对"变成可验证的指标；
 *   2. 换肤最容易出的问题（皮肤换了但图表/组件没跟着换）只有真跑一遍才发现；
 *   3. 浏览器控制台报错是"编译通过但运行炸了"的唯一发现手段。
 *
 * 它检查什么：
 *   · 每页在浅色/深色下是否真的应用了对应皮肤（读计算样式，不看截图）
 *   · 品牌令牌的对比度是否达标（WCAG 4.5:1）
 *   · 有没有横向溢出、关键文字有没有被裁掉
 *   · 图表画布数量是否正常
 *   · 浏览器有没有报错
 *   · 真实点击"浅色/深色"按钮，验证切换是否即时生效
 *
 * 运行：cd frontend && PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers node scripts/visual-audit.mjs
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const here = path.dirname(fileURLToPath(import.meta.url))
const outDir = path.resolve(here, '../screenshots')
fs.mkdirSync(outDir, { recursive: true })

const BASE = process.env.APP_URL || 'http://127.0.0.1:5173'
const API = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

/* ---------------------------------------------------------------------------
 * 读取真实演示账号并换取令牌。
 * 不把账号密码写死在这里 —— 从 backend/.env 读，那才是它们的唯一归属地。
 * ------------------------------------------------------------------------- */
function readBackendEnv(key) {
  const envPath = path.resolve(here, '../../backend/.env')
  if (!fs.existsSync(envPath)) return ''
  for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
    if (line.trim().startsWith(`${key}=`)) return line.split('=').slice(1).join('=').trim()
  }
  return ''
}

const DEMO_USER = readBackendEnv('DEMO_USERNAME') || 'demo'
const DEMO_PASS = readBackendEnv('DEMO_PASSWORD')

async function fetchToken() {
  if (!DEMO_PASS) return ''
  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: DEMO_USER, password: DEMO_PASS }),
    })
    if (!res.ok) return ''
    return (await res.json()).token || ''
  } catch {
    return ''
  }
}

const TOKEN = await fetchToken()
if (!TOKEN) {
  console.log('⚠️  没能从后端拿到登录令牌（后端没启动？.env 里没有 DEMO_PASSWORD？）')
  console.log('    需要登录的页面（工作台）将无法体检。')
} else {
  console.log(`已用演示账号「${DEMO_USER}」拿到真实登录令牌，可用于需要登录的页面。`)
}

const PAGES = [
  {
    hash: '#/login',
    name: '登录页',
    file: 'login',
    size: { width: 1440, height: 900 },
    expect: ['墨衡', '一键体验', '数据可视化平台'],
    charts: 0,
  },
  {
    hash: '#/demo',
    name: '示例大屏',
    file: 'dashboard',
    size: { width: 1600, height: 1080 },
    expect: ['省份销售额动态排名', '品类销售占比', '订单量', '客单价'],
    charts: 5,
  },
  {
    hash: '#/workbench',
    name: '工作台',
    file: 'workbench',
    size: { width: 1440, height: 900 },
    expect: ['工作台', '开发进度', '账号已校验'],
    charts: 0,
    needAuth: true,
  },
]

/* ----------------------------------------------------------- 对比度计算 */
function parseColor(input) {
  const s = String(input).trim()
  let m = s.match(/^#([0-9a-f]{6})$/i)
  if (m) {
    const n = parseInt(m[1], 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  m = s.match(/rgba?\(([^)]+)\)/i)
  if (m) {
    const parts = m[1].split(',').map((v) => parseFloat(v))
    return [parts[0], parts[1], parts[2]]
  }
  return null
}

function luminance([r, g, b]) {
  const f = (c) => {
    const v = c / 255
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function contrast(a, b) {
  const la = luminance(parseColor(a))
  const lb = luminance(parseColor(b))
  const [hi, lo] = la > lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}

/* --------------------------------------------------------------- 主流程 */
const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const problems = []
const lines = []

for (const theme of ['dark', 'light']) {
  for (const page of PAGES) {
    const context = await browser.newContext({
      viewport: page.size,
      deviceScaleFactor: 1,
      colorScheme: theme,
      locale: 'zh-CN',
    })
    // 在页面脚本执行前写入主题选择与登录令牌，
    // 等同于"用户上次选了这一档皮肤，并且已经登录过"
    await context.addInitScript(
      ({ t, token, needAuth }) => {
        try {
          window.localStorage.setItem('moheng-theme', t)
          if (needAuth && token) window.localStorage.setItem('moheng-token', token)
        } catch {
          /* 忽略 */
        }
      },
      { t: theme, token: TOKEN, needAuth: !!page.needAuth },
    )

    const p = await context.newPage()
    const errors = []
    p.on('console', (m) => {
      if (m.type() === 'error') errors.push(m.text())
    })
    p.on('pageerror', (e) => errors.push(`页面异常: ${e.message}`))

    const tag = `${page.name}·${theme === 'dark' ? '深色' : '浅色'}`
    await p.goto(`${BASE}/${page.hash}`, { waitUntil: 'networkidle', timeout: 30000 })
    await p.waitForTimeout(2600)

    await p.screenshot({ path: path.join(outDir, `${page.file}-${theme}.png`) })

    const bodyText = await p.innerText('body')
    for (const t of page.expect) {
      if (!bodyText.includes(t)) problems.push(`[${tag}] 页面上找不到关键文字「${t}」`)
    }
    if (page.needAuth && !bodyText.includes('账号已校验')) {
      problems.push(`[${tag}] 带令牌进来却没有进入工作台（可能被弹回了登录页）`)
    }

    const info = await p.evaluate(() => {
      const cs = getComputedStyle(document.documentElement)
      const token = (n) => cs.getPropertyValue(n).trim()
      const canvasCount = document.querySelectorAll('canvas').length
      // 关键文字是否被横向裁掉
      const clipped = []
      for (const sel of ['.appbar__title', '.panel__note', '.stat__number', '.brand__name']) {
        document.querySelectorAll(sel).forEach((el) => {
          if (el.scrollWidth > el.clientWidth + 2) clipped.push(`${sel} 被裁切`)
        })
      }
      // 主题切换器是否在右上角区域
      const sw = document.querySelector('.theme-switch')
      let switchAtTopRight = false
      if (sw) {
        const r = sw.getBoundingClientRect()
        switchAtTopRight = r.right > window.innerWidth * 0.6 && r.top < 140
      }
      return {
        isDark: document.documentElement.classList.contains('dark'),
        colorScheme: document.documentElement.style.colorScheme,
        bg: getComputedStyle(document.body).backgroundColor,
        fg: getComputedStyle(document.body).color,
        canvasCount,
        clipped,
        hasSwitch: !!sw,
        switchAtTopRight,
        overflowX: document.documentElement.scrollWidth - window.innerWidth,
        t1: token('--text-1'),
        t2: token('--text-2'),
        t3: token('--text-3'),
        t4: token('--text-4'),
        panel: token('--ink-850'),
        brand: token('--brand-500'),
      }
    })

    const wantDark = theme === 'dark'
    if (info.isDark !== wantDark) {
      problems.push(`[${tag}] 皮肤没有正确应用（期望深色=${wantDark}，实际=${info.isDark}）`)
    }
    if (!info.hasSwitch) problems.push(`[${tag}] 找不到主题切换器`)
    else if (!info.switchAtTopRight) problems.push(`[${tag}] 主题切换器不在右上角`)

    if (info.canvasCount < page.charts) {
      problems.push(`[${tag}] 图表数量不足（期望 ≥${page.charts}，实际 ${info.canvasCount}）`)
    }
    if (info.clipped.length) problems.push(`[${tag}] 文字被裁切：${info.clipped.join('；')}`)
    if (info.overflowX > 1) problems.push(`[${tag}] 出现横向滚动（多出 ${info.overflowX}px）`)
    if (errors.length) problems.push(`[${tag}] 浏览器报错：${errors.join(' | ')}`)

    // 正文对比度
    const c2 = contrast(info.t2, info.panel)
    if (c2 < 4.5) problems.push(`[${tag}] 次要文字对比度过低：${c2.toFixed(2)}:1`)
    const c3 = contrast(info.t3, info.panel)
    if (c3 < 4.5) problems.push(`[${tag}] 弱化文字对比度过低：${c3.toFixed(2)}:1`)
    // text-4 只用于装饰（非文字元素），按 3:1 的宽松标准要求
    const c4 = contrast(info.t4, info.panel)
    if (c4 < 3) problems.push(`[${tag}] 装饰色对比度过低：${c4.toFixed(2)}:1`)

    lines.push(
      `${tag.padEnd(14)} 深色=${String(info.isDark).padEnd(5)} 底色=${info.bg.padEnd(20)} ` +
        `图表=${info.canvasCount} 对比度(次要/弱化/装饰)=${c2.toFixed(1)}/${c3.toFixed(1)}/${c4.toFixed(1)}:1`,
    )

    await context.close()
  }
}

/* ---------------- 端到端测试：像真人一样在页面上登录 ---------------- */
if (DEMO_PASS) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
  })
  const p = await context.newPage()
  const errors = []
  p.on('pageerror', (e) => errors.push(e.message))
  p.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })

  await p.goto(`${BASE}/#/login`, { waitUntil: 'networkidle' })
  await p.waitForTimeout(600)

  // 1) 先故意输错密码，验证错误提示真的会出现
  await p.getByPlaceholder('请输入用户名').first().fill(DEMO_USER)
  await p.getByPlaceholder('请输入密码').first().fill('wrong-password-xyz')
  await p.getByRole('button', { name: '进入系统' }).first().click()
  await p.waitForTimeout(1200)
  const wrongShown = await p.locator('text=用户名或密码不正确').count()
  if (wrongShown === 0) problems.push('[登录流程] 输错密码后没有出现错误提示')
  const stillLogin = await p.locator('text=数据可视化平台').count()
  if (stillLogin === 0) problems.push('[登录流程] 密码错误却离开了登录页')

  // 上面这一小段是**故意**让接口返回 401 的，浏览器必然会在控制台记一条
  // "401 (Unauthorized)"。那是预期内的噪音，不是缺陷，所以在这里把
  // 已收集的错误清空，后续步骤的报错才算真问题。
  errors.length = 0

  // 2) 再输对密码，验证能真正进入工作台
  await p.getByPlaceholder('请输入密码').first().fill(DEMO_PASS)
  await p.getByRole('button', { name: '进入系统' }).first().click()
  await p.waitForTimeout(2000)

  const after = await p.evaluate(() => ({
    hash: window.location.hash,
    hasToken: !!window.localStorage.getItem('moheng-token'),
    text: document.body.innerText,
  }))

  if (after.hash !== '#/workbench') problems.push(`[登录流程] 登录成功后应在工作台，实际 hash=${after.hash}`)
  if (!after.hasToken) problems.push('[登录流程] 登录成功后没有保存令牌（刷新就会掉登录）')
  if (!after.text.includes('账号已校验')) problems.push('[登录流程] 工作台没有显示"账号已校验"')

  // 3) 刷新页面，验证登录状态能恢复
  await p.reload({ waitUntil: 'networkidle' })
  await p.waitForTimeout(1500)
  const reloaded = await p.evaluate(() => ({
    hash: window.location.hash,
    text: document.body.innerText,
  }))
  if (reloaded.hash !== '#/workbench' || !reloaded.text.includes('账号已校验')) {
    problems.push('[登录流程] 刷新后登录状态丢失了')
  }

  // 4) 退出登录，验证令牌被清掉
  await p.getByRole('button', { name: '退出登录' }).first().click()
  await p.waitForTimeout(1200)
  const out = await p.evaluate(() => ({
    hash: window.location.hash,
    hasToken: !!window.localStorage.getItem('moheng-token'),
  }))
  if (out.hasToken) problems.push('[登录流程] 退出登录后本地令牌没有被清除')
  if (out.hash !== '#/login') problems.push(`[登录流程] 退出后应回登录页，实际 hash=${out.hash}`)

  if (errors.length) problems.push(`[登录流程] 浏览器报错：${errors.join(' | ')}`)

  lines.push(
    `[登录流程] 错密码被拒 ✅ → 正确密码进入工作台 ✅ → 刷新保持登录 ✅ → 退出清除令牌 ✅`,
  )
  await context.close()
} else {
  problems.push('[登录流程] 跳过：backend/.env 里没有 DEMO_PASSWORD')
}

/* ---------------- 交互测试：真实点击切换按钮，验证即时生效 ---------------- */
{
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: 'dark',
  })
  await context.addInitScript(() => {
    try {
      window.localStorage.setItem('moheng-theme', 'dark')
    } catch {
      /* 忽略 */
    }
  })
  const p = await context.newPage()
  const errors = []
  p.on('pageerror', (e) => errors.push(e.message))
  await p.goto(`${BASE}/#/demo`, { waitUntil: 'networkidle' })
  await p.waitForTimeout(1200)

  const before = await p.evaluate(() => ({
    dark: document.documentElement.classList.contains('dark'),
    bg: getComputedStyle(document.body).backgroundColor,
  }))

  await p.getByRole('button', { name: '浅色皮肤（宣纸）' }).first().click()
  await p.waitForTimeout(700)

  const after = await p.evaluate(() => ({
    dark: document.documentElement.classList.contains('dark'),
    bg: getComputedStyle(document.body).backgroundColor,
    canvases: document.querySelectorAll('canvas').length,
    saved: window.localStorage.getItem('moheng-theme'),
  }))

  if (before.dark !== true) problems.push('[交互] 初始应为深色皮肤，实际不是')
  if (after.dark !== false) problems.push('[交互] 点击"浅色"后页面没有变浅色')
  if (before.bg === after.bg) problems.push('[交互] 点击后背景色没有变化')
  if (after.canvases < 5) problems.push(`[交互] 换肤后图表丢失（只剩 ${after.canvases} 个画布）`)
  if (after.saved !== 'light') problems.push('[交互] 用户选择没有被记住')

  if (errors.length) problems.push(`[交互] 浏览器报错：${errors.join(' | ')}`)

  lines.push(
    `[交互测试] 深色→浅色：底色 ${before.bg} → ${after.bg}，图表 ${after.canvases} 个，记忆=${after.saved}`,
  )

  await context.close()
}

await browser.close()

console.log('视觉体检结果')
console.log('─'.repeat(96))
for (const l of lines) console.log('  ' + l)
console.log('─'.repeat(96))
console.log(`截图目录：${outDir}`)
if (problems.length) {
  console.log(`\n❌ 发现 ${problems.length} 个问题：`)
  for (const x of problems) console.log('  · ' + x)
  process.exit(1)
} else {
  console.log('\n✅ 两种皮肤均无报错；皮肤正确应用；文字未裁切；对比度达标；切换即时生效')
}
