<script setup>
/**
 * 应用外壳：负责在三个页面之间切换，并在启动时恢复登录状态。
 *
 * 关于"路由"的说明：
 *   正式项目通常会用 vue-router。本项目用地址栏 # 号做极简切换
 *   （不引入新零件），刷新页面也不会丢掉当前所在页。
 *   等到第 6 阶段做"大屏分享链接"时，再评估是否换成正式路由。
 *
 * 刷新页面后为什么还是登录状态？
 *   令牌存在浏览器本地，启动时拿它去问后端"我是谁"。
 *   问得到 → 恢复会话并直接进工作台；问不到（过期/被篡改）→ 清掉，回登录页。
 */
import { onMounted, ref } from 'vue'

import { useAuth } from './composables/useAuth.js'
import { useTheme } from './composables/useTheme.js'
import LoginView from './views/LoginView.vue'
import DemoDashboardView from './views/DemoDashboardView.vue'
import ShareView from './views/ShareView.vue'
import WorkbenchView from './views/WorkbenchView.vue'

const { initTheme } = useTheme()
const { user, restore } = useAuth()

const ROUTES = {
  '#/login': 'login',
  '#/demo': 'demo',
  '#/workbench': 'workbench',
}

/** 当前路由。分享链接是动态的（#/share/<token>），需从哈希里解析出 token。 */
const route = ref(parseRoute())

function parseRoute() {
  const hash = window.location.hash
  if (hash.startsWith('#/share/')) {
    return { view: 'share', token: decodeURIComponent(hash.slice('#/share/'.length)) }
  }
  return { view: ROUTES[hash] || 'login', token: '' }
}

const username = ref('')
const booting = ref(true)

function go(next) {
  route.value = { view: next, token: '' }
  window.location.hash = `#/${next}`
  window.scrollTo({ top: 0, behavior: 'auto' })
}

function enterDemo() {
  username.value = '访客'
  go('demo')
}

function enterWorkbench(payload) {
  username.value = payload?.username || user.value?.display_name || '用户'
  go('workbench')
}

function backToLogin() {
  go('login')
}

onMounted(async () => {
  // index.html 里的"防闪白"脚本已经先定过一次皮肤，这里再同步一次，
  // 保证 Vue 里的状态与页面实际状态完全一致（比如用户中途改了系统设置）。
  initTheme()

  window.addEventListener('hashchange', () => {
    route.value = parseRoute()
  })

  // 分享页免登录：直接展示，跳过"恢复会话"那套，避免把访客弹回登录页
  if (route.value.view === 'share') {
    booting.value = false
    return
  }

  // 恢复会话：带令牌且后端认得 → 直接落在工作台
  const ok = await restore()
  if (ok && route.value.view === 'login') {
    username.value = user.value?.display_name || user.value?.username || ''
    go('workbench')
  }
  booting.value = false
})
</script>

<template>
  <!-- 恢复登录状态期间给一个极短的过渡，避免"先闪一下登录页又跳走" -->
  <div v-if="booting" class="boot" aria-label="正在恢复登录状态">
    <div class="boot__bar" />
  </div>

  <template v-else>
    <ShareView v-if="route.view === 'share'" :token="route.token" />
    <LoginView v-else-if="route.view === 'login'" @enter-demo="enterDemo" @enter-workbench="enterWorkbench" />
    <DemoDashboardView v-else-if="route.view === 'demo'" @exit="backToLogin" />
    <WorkbenchView v-else :username="username" @exit="backToLogin" @open-demo="enterDemo" />
  </template>
</template>

<style scoped>
.boot {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  background: var(--ink-1000);
}

/* 顶部一条细进度条：只提示"正在确认身份"，不做花哨的转圈 */
.boot__bar {
  margin-top: 0;
  width: 160px;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--brand-500), transparent);
  animation: boot-slide 1s ease-in-out infinite;
}

@keyframes boot-slide {
  0% {
    transform: translateX(-40%);
    opacity: 0.3;
  }
  50% {
    transform: translateX(40%);
    opacity: 1;
  }
  100% {
    transform: translateX(-40%);
    opacity: 0.3;
  }
}

@media (prefers-reduced-motion: reduce) {
  .boot__bar {
    animation: none;
    width: 100%;
    opacity: 0.6;
  }
}
</style>
