<script setup>
/**
 * 登录页。
 *
 * 第 3 阶段起，这里的登录和注册都是**真的**：
 *   密码送到后端，用 scrypt 校验，成功后签发令牌，令牌存在浏览器本地。
 *   页面上会显示后端与数据库的真实状态，不假装在线。
 *
 * 另外保留一条"不依赖服务器的路"：一键体验。
 * 它读的是前端内置数据，后端挂了、断网了都照常能演示。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import BrandMark from '../components/BrandMark.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import { api } from '../api/client.js'
import { useAuth } from '../composables/useAuth.js'

const emit = defineEmits(['enter-demo', 'enter-workbench'])

const { login, register } = useAuth()

const activeTab = ref('login')
const submitting = ref(false)

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', confirm: '', displayName: '' })

/** 后端状态：null=检测中。分"通不通"和"数据库通不通"两件事，分开显示更有用。 */
const backendOnline = ref(null)
const dbOnline = ref(null)

onMounted(async () => {
  try {
    const info = await api.health()
    backendOnline.value = true
    dbOnline.value = !!info?.database?.connected
  } catch {
    backendOnline.value = false
    dbOnline.value = false
  }
})

async function submitLogin() {
  if (!loginForm.username.trim() || !loginForm.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  submitting.value = true
  try {
    const u = await login(loginForm.username.trim(), loginForm.password)
    ElMessage.success(`欢迎回来，${u.display_name || u.username}`)
    loginForm.password = ''
    emit('enter-workbench', { username: u.display_name || u.username })
  } catch (err) {
    // 后端返回的是人话（例如"用户名或密码不正确"），直接显示
    ElMessage.error(err.message)
  } finally {
    submitting.value = false
  }
}

async function submitRegister() {
  if (!registerForm.username.trim() || !registerForm.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  if (registerForm.password !== registerForm.confirm) {
    ElMessage.error('两次输入的密码不一致')
    return
  }
  submitting.value = true
  try {
    const u = await register(
      registerForm.username.trim(),
      registerForm.password,
      registerForm.displayName.trim(),
    )
    ElMessage.success(`注册成功，已自动登录：${u.username}`)
    registerForm.password = ''
    registerForm.confirm = ''
    emit('enter-workbench', { username: u.display_name || u.username })
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login">
    <!-- 右上角：主题切换（大家习惯在这里找） -->
    <div class="login__theme">
      <ThemeToggle />
    </div>

    <!-- 左：品牌区 -->
    <aside class="login__brand">
      <BrandMark />

      <div class="login__headline">
        <h1 class="login__title">数据可视化平台</h1>
        <p class="login__desc">
          从上传数据到组装大屏，一条流水线走完。<br />
          为课堂演示而做：稳定、离线可跑、开箱即用。
        </p>
      </div>

      <div class="tick-rule login__rule" />

      <ul class="login__points">
        <li>
          <span class="login__dot" />
          <div>
            <strong>一键体验</strong>
            <span>无需注册、无需数据库，直接看到完整大屏</span>
          </div>
        </li>
        <li>
          <span class="login__dot login__dot--brass" />
          <div>
            <strong>断网兜底</strong>
            <span>示例数据内置在前端，服务器挂了也能演示</span>
          </div>
        </li>
        <li>
          <span class="login__dot" />
          <div>
            <strong>数据隔离</strong>
            <span>每个账号只看得到自己的数据</span>
          </div>
        </li>
      </ul>

      <div class="login__status">
        <span class="badge" :class="{ 'badge--brand': backendOnline === true }">
          <span
            class="login__led"
            :class="{
              'login__led--ok': backendOnline === true,
              'login__led--off': backendOnline === false,
            }"
          />
          后端{{ backendOnline === null ? '检测中' : backendOnline ? '在线' : '离线' }}
        </span>
        <span class="badge" :class="{ 'badge--brand': dbOnline === true }">
          <span
            class="login__led"
            :class="{
              'login__led--ok': dbOnline === true,
              'login__led--off': dbOnline === false,
            }"
          />
          数据库{{ dbOnline === null ? '检测中' : dbOnline ? '已就绪' : '不可用' }}
        </span>
      </div>
    </aside>

    <!-- 右：表单区 -->
    <main class="login__panel">
      <div class="login__card">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="登录" name="login">
            <el-form label-position="top" @submit.prevent="submitLogin">
              <el-form-item label="用户名">
                <el-input v-model="loginForm.username" placeholder="请输入用户名" size="large" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input
                  v-model="loginForm.password"
                  type="password"
                  show-password
                  placeholder="请输入密码"
                  size="large"
                  @keyup.enter="submitLogin"
                />
              </el-form-item>
              <el-button
                type="primary"
                size="large"
                class="login__submit"
                :loading="submitting"
                @click="submitLogin"
              >
                进入系统
              </el-button>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="注册" name="register">
            <el-form label-position="top" @submit.prevent="submitRegister">
              <el-form-item label="用户名">
                <el-input
                  v-model="registerForm.username"
                  placeholder="3~32 位字母、数字、下划线"
                  size="large"
                />
              </el-form-item>
              <el-form-item label="显示名（可留空）">
                <el-input
                  v-model="registerForm.displayName"
                  placeholder="例如：张三"
                  size="large"
                />
              </el-form-item>
              <el-form-item label="密码">
                <el-input
                  v-model="registerForm.password"
                  type="password"
                  show-password
                  placeholder="设置密码（将加密存储）"
                  size="large"
                />
              </el-form-item>
              <el-form-item label="确认密码">
                <el-input
                  v-model="registerForm.confirm"
                  type="password"
                  show-password
                  placeholder="再次输入密码"
                  size="large"
                  @keyup.enter="submitRegister"
                />
              </el-form-item>
              <el-button
                type="primary"
                size="large"
                class="login__submit"
                :loading="submitting"
                @click="submitRegister"
              >
                注册账号
              </el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>

        <div class="login__divider"><span>或</span></div>

        <button class="demo-entry" type="button" @click="emit('enter-demo')">
          <div class="demo-entry__text">
            <strong>一键体验</strong>
            <span>打开示例大屏 · 不用注册 · 不依赖服务器</span>
          </div>
          <span class="badge badge--brass">推荐</span>
        </button>

        <div class="notice login__notice">
          <span class="notice__key">关于账号</span>
          <span>
            登录与注册已接入数据库：密码以 <strong>scrypt 加密</strong>后存储，
            后端永远拿不到明文；每个账号只能看到<strong>自己的数据</strong>。
            若不想注册，直接点上面的「一键体验」。
          </span>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.login {
  min-height: 100%;
  display: grid;
  grid-template-columns: minmax(360px, 1fr) minmax(420px, 520px);
  gap: var(--sp-10);
  align-items: center;
  padding: var(--sp-10) var(--sp-12);
  max-width: 1280px;
  margin: 0 auto;
}

/* ---------------- 左侧品牌区 ---------------- */
.login__theme {
  position: fixed;
  top: var(--sp-4);
  right: var(--sp-5);
  z-index: var(--z-sticky);
}

.login__brand {
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
  max-width: 520px;
}

.login__title {
  font-size: var(--fs-36);
  line-height: 1.25;
  margin-bottom: var(--sp-3);
  letter-spacing: 0.02em;
}

.login__desc {
  color: var(--text-2);
  font-size: var(--fs-14);
  line-height: 1.9;
}

.login__rule {
  width: 220px;
}

.login__points {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.login__points li {
  display: flex;
  gap: var(--sp-3);
  align-items: flex-start;
}

.login__points strong {
  display: block;
  font-size: var(--fs-14);
  font-weight: 600;
  color: var(--text-1);
}

.login__points span {
  font-size: var(--fs-13);
  color: var(--text-3);
}

.login__dot {
  width: 6px;
  height: 6px;
  margin-top: 8px;
  border-radius: 1px;
  background: var(--brand-500);
  flex: none;
}

.login__dot--brass {
  background: var(--brass-500);
}

.login__status {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.login__led {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-4);
  flex: none;
}

.login__led--ok {
  background: var(--ok);
}

.login__led--off {
  background: var(--danger);
}

/* ---------------- 右侧表单区 ---------------- */
.login__panel {
  display: flex;
  justify-content: flex-end;
}

.login__card {
  width: 100%;
  padding: var(--sp-8);
  background: var(--ink-850);
  border: 1px solid var(--line-2);
  border-radius: var(--r-4);
  box-shadow: var(--shadow-card);
}

.login__submit {
  width: 100%;
  margin-top: var(--sp-2);
}

.login__divider {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin: var(--sp-5) 0;
  color: var(--text-3);
  font-size: var(--fs-12);
}

.login__divider::before,
.login__divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--line-1);
}

/* 一键体验：全页最显眼的入口 */
.demo-entry {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-4) var(--sp-5);
  background: var(--brass-soft);
  border: 1px solid var(--brass-line);
  border-radius: var(--r-2);
  color: var(--text-1);
  cursor: pointer;
  text-align: left;
  transition: background-color var(--dur-1) var(--ease),
    border-color var(--dur-1) var(--ease), transform var(--dur-1) var(--ease);
}

.demo-entry:hover {
  background: rgba(216, 162, 74, 0.18);
  border-color: var(--brass-500);
  transform: translateY(-1px);
}

.demo-entry__text strong {
  display: block;
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--brass-text);
}

.demo-entry__text span {
  font-size: var(--fs-12);
  color: var(--text-3);
}

.login__notice {
  margin-top: var(--sp-5);
}

/* ---------------- 窄屏：改为上下排列 ---------------- */
@media (max-width: 980px) {
  .login {
    grid-template-columns: 1fr;
    padding: var(--sp-8) var(--sp-5);
    gap: var(--sp-8);
  }

  .login__panel {
    justify-content: stretch;
  }

  .login__title {
    font-size: var(--fs-28);
  }
}
</style>
