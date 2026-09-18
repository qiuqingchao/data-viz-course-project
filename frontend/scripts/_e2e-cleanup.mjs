/**
 * E2E 共用清理助手：保证"测试落库的数据，测试自己收尾"。
 *
 * 背景：上传/图表/防呆模板这几个 UI 测试为了走通"保存"这一步，会真的往学校库
 * 写数据集/图表。历史版本没做收尾，导致库里越积越多脏数据。
 *
 * 用法（前后夹一次即可，与并发运行的其它测试互不误伤）：
 *   const before = await snapshotIds();   // 测试开始前
 *   ...跑 UI 测试、造数据...
 *   await cleanupNew(before);             // 只删"本次新增"的数据集/图表/大屏
 *
 * 为什么按"基线差集"删，而不是清空：
 *   多个 E2E 可能先后/并行跑，各自造各自的数据。整体清空会误删别人的，
 *   按"开始前没有、结束后多出来"的 ID 删，才是各自负责各自的。
 */
import fs from 'node:fs'
import path from 'node:path'

const API = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

function demoPass() {
  const envPath = path.resolve('backend/.env')
  const alt = path.resolve('../backend/.env')
  const p = fs.existsSync(envPath) ? envPath : alt
  for (const l of fs.readFileSync(p, 'utf-8').split('\n')) {
    if (l.startsWith('DEMO_PASSWORD=')) return l.split('=')[1].trim()
  }
  return ''
}

async function api(pathName, method = 'GET', body, token) {
  const r = await fetch(API + pathName, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await r.json().catch(() => ({}))
  return { status: r.status, json }
}

async function demoToken() {
  const { json } = await api('/api/auth/login', 'POST', {
    username: 'demo',
    password: demoPass(),
  })
  if (!json.token) throw new Error('清理助手：demo 登录失败')
  return json.token
}

/** 抓一份当前 demo 名下 数据集/图表/大屏 的 ID 快照 */
export async function snapshotIds(token) {
  const tk = token || (await demoToken())
  const ds = (await api('/api/datasets/list', 'GET', null, tk)).json
  const ch = (await api('/api/charts/list', 'GET', null, tk)).json
  const db = (await api('/api/dashboards/list', 'GET', null, tk)).json
  return {
    token: tk,
    datasets: new Set((ds.datasets || []).map((d) => d.DatasetID)),
    charts: new Set((ch.charts || []).map((c) => c.ChartID)),
    dashboards: new Set((db.dashboards || []).map((d) => d.DashboardID)),
  };
}

/**
 * 删除 snapshot 之后新增的数据：先删大屏、再删图表、最后删数据集
 * （数据集被图表引用时删除会 409，逆序天然规避）。
 * 返回本次删掉的条数，便于测试打印。
 */
export async function cleanupNew(before) {
  const after = await snapshotIds(before.token)
  let removed = { dashboards: 0, charts: 0, datasets: 0 }

  for (const id of after.dashboards) {
    if (!before.dashboards.has(id)) {
      await api(`/api/dashboards/${id}`, 'DELETE', null, before.token)
      removed.dashboards += 1
    }
  }
  for (const id of after.charts) {
    if (!before.charts.has(id)) {
      await api(`/api/charts/${id}`, 'DELETE', null, before.token)
      removed.charts += 1
    }
  }
  for (const id of after.datasets) {
    if (!before.datasets.has(id)) {
      const r = await api(`/api/datasets/${id}`, 'DELETE', null, before.token)
      if (r.status === 200) removed.datasets += 1
    }
  }
  return removed
}
