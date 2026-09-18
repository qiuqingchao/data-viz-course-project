/**
 * 前端入口。
 *
 * 样式文件的引入顺序很重要（后面覆盖前面）：
 *   1. Element Plus 自带样式（组件库原貌）
 *   2. Element Plus 深色模式变量
 *   3. 墨衡设计令牌      ← 从这里开始"收编"组件库外观
 *   4. 基础样式
 *   5. 组件库外观覆盖
 * 顺序错了会出现"两套风格打架"的页面。
 */
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/element.css'

import App from './App.vue'

createApp(App)
  .use(ElementPlus, { locale: zhCn }) // 组件文案使用中文（日期、分页等）
  .mount('#app')
