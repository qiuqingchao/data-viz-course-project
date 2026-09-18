/**
 * ECharts 统一入口。
 *
 * 为什么不用 `import * as echarts from 'echarts'`？
 *   整包引入会把所有图表类型都打包进来（体积大、启动慢）。
 *   这里只登记项目真正用到的图表与组件，属于"实用主义"的取舍：
 *   以后要用新图表，只需在下面补一行。
 *
 * 注意：所有用到 ECharts 的地方都必须从这个文件引入，
 *      否则会出现"两个互不相识的 echarts 实例"，图表会莫名其妙不显示。
 */

import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  GraphicComponent,
  DatasetComponent,
  MarkLineComponent,
} from 'echarts/components'
import { LabelLayout, UniversalTransition } from 'echarts/features'
import { CanvasRenderer, SVGRenderer } from 'echarts/renderers'

// 注意：纯 JS 模块之间的引用一律写全 .js 后缀
// （浏览器打包器不需要，但 Node 需要 —— 这样同一份代码才能在两边都跑）
import { ECHARTS_THEME, PALETTES, buildChartTheme } from './chartTheme.js'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  GraphicComponent,
  DatasetComponent,
  MarkLineComponent,
  LabelLayout,
  UniversalTransition,
  CanvasRenderer,
  // SVG 渲染器：浏览器里用不到，但让"无浏览器自检"和将来的矢量导出成为可能
  SVGRenderer,
])

// 两套皮肤各注册一个主题，靠 echarts.init(dom, 主题名) 选择
echarts.registerTheme(ECHARTS_THEME.dark, buildChartTheme(PALETTES.dark))
echarts.registerTheme(ECHARTS_THEME.light, buildChartTheme(PALETTES.light))

export { ECHARTS_THEME }
export default echarts
