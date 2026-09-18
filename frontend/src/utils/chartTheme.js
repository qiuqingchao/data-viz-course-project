/**
 * 墨衡 · 图表主题（浅色 / 深色两套）
 *
 * ⚠️ 重要约定：ECharts 读不到 CSS 变量，所以这里的色值必须与
 *    styles/tokens.css 手动保持一致。这是全项目唯一允许"重复写色值"的地方。
 *    改配色时两处一起改。
 */

/** 深色皮肤「夜墨」——对应 tokens.css 的 html.dark */
const DARK = {
  name: '夜墨',
  ink1000: '#070b12',
  ink900: '#0b111a',
  ink850: '#0f1621',
  ink800: '#121a26',
  ink600: '#243040',
  line1: 'rgba(255,255,255,0.07)',
  line2: 'rgba(255,255,255,0.12)',
  text1: '#e9eff7',
  text2: '#a8b6c8',
  text3: '#7d8ca0',
  text4: '#5f6f83',
  brand400: '#2ad3bf',
  brand500: '#17b8a6',
  brass400: '#edbb6a',
  brass500: '#d8a24a',
  ok: '#3fb27f',
  warn: '#e0a93b',
  danger: '#e0605a',
  info: '#5b8fd9',
  data: ['#17b8a6', '#d8a24a', '#6c8ae4', '#d9707f', '#8fbf5a', '#7a8ca3'],
  // 面积图填充的不透明度：深底上可以厚一点
  areaOpacity: 0.22,
}

/** 浅色皮肤「宣纸」——对应 tokens.css 的 :root 默认值 */
const LIGHT = {
  name: '宣纸',
  ink1000: '#f6f4ef',
  ink900: '#eeece5',
  ink850: '#ffffff',
  ink800: '#ffffff',
  ink600: '#ddd8ca',
  line1: 'rgba(26,30,36,0.10)',
  line2: 'rgba(26,30,36,0.16)',
  text1: '#14191f',
  text2: '#4b5563',
  text3: '#666e7c',
  text4: '#848c97',
  brand400: '#2ec4b0',
  brand500: '#12a696',
  brass400: '#a97a1f',
  brass500: '#c08a2a',
  ok: '#1f8f5f',
  warn: '#b9821a',
  danger: '#c0392f',
  info: '#3a6fbf',
  data: ['#0f9c8c', '#c08a2a', '#3f63c9', '#c04a5c', '#5f8f2f', '#6b7c93'],
  // 浅底上同样的透明度会显得脏，所以调低
  areaOpacity: 0.16,
}

export const PALETTES = { dark: DARK, light: LIGHT }

/** ECharts 注册主题时用的名字 */
export const ECHARTS_THEME = { dark: 'moheng-dark', light: 'moheng-light' }

const FONT =
  '"PingFang SC","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC",-apple-system,"Segoe UI",Roboto,Arial,sans-serif'

/**
 * 根据皮肤生成 ECharts 主题。
 * 主题只负责"默认值"（图例字色、坐标轴、提示框等）；
 * 具体每张图的颜色由 demoCharts.js 从 palette 里取，两者配合才能换肤彻底。
 */
export function buildChartTheme(p) {
  return {
    color: p.data,
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT, color: p.text2 },

    title: {
      textStyle: { color: p.text1, fontSize: 15, fontWeight: 600 },
      subtextStyle: { color: p.text3, fontSize: 12 },
    },

    legend: {
      textStyle: { color: p.text2, fontSize: 12 },
      inactiveColor: p.text4,
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 16,
    },

    tooltip: {
      backgroundColor: p.ink800,
      borderColor: p.line2,
      borderWidth: 1,
      textStyle: { color: p.text1, fontSize: 12, fontFamily: FONT },
      extraCssText: 'box-shadow: 0 8px 24px rgba(0,0,0,0.18); border-radius: 6px;',
      axisPointer: {
        lineStyle: { color: p.text4 },
        crossStyle: { color: p.text4 },
        shadowStyle: { color: p.line1 },
      },
    },

    categoryAxis: {
      axisLine: { lineStyle: { color: p.line2 } },
      axisTick: { show: false },
      axisLabel: { color: p.text3, fontSize: 11 },
      splitLine: { show: false },
    },

    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: p.text3, fontSize: 11 },
      // 只保留水平细网格线：像仪器的标尺，不喧宾夺主
      splitLine: { lineStyle: { color: p.line1, type: 'solid' } },
    },

    line: { symbolSize: 5, smooth: false, lineStyle: { width: 2 } },
    bar: { barMaxWidth: 26, itemStyle: { borderRadius: [2, 2, 0, 0] } },
    // 扇区之间留一条与卡片同色的缝，而不是画一圈深色描边
    pie: { itemStyle: { borderColor: p.ink850, borderWidth: 2 } },
  }
}

/** 统一的数字格式：千分位，图表与卡片共用 */
export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** 大数字压缩显示：367282 → 36.73 亿 */
export function formatCompact(value, unit = '') {
  const n = Number(value) || 0
  if (Math.abs(n) >= 100000000) {
    return `${(n / 100000000).toFixed(2).replace(/\.00$/, '')} 亿${unit}`
  }
  if (Math.abs(n) >= 10000) {
    return `${(n / 10000).toFixed(1).replace(/\.0$/, '')} 万${unit}`
  }
  return `${formatNumber(n)}${unit}`
}
