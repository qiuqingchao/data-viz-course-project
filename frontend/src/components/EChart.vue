<script setup>
/**
 * 图表容器：把 ECharts 的"生命周期杂活"统一收在这里。
 *   · 挂载时初始化、卸载时销毁（防止内存泄漏，反复切页面也不会卡）
 *   · 用 ResizeObserver 监听容器尺寸变化并自适应（拖窗口、改布局都不会变形）
 *   · 配置或皮肤变化时自动重绘
 *
 * 关于换皮肤：ECharts 的主题是在 init 的那一刻"烘焙"进实例的，
 * 事后没法替换。所以换皮肤时必须销毁旧实例、用新主题重建。
 */
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import echarts from '../utils/echarts.js'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '320px' },
  /** ECharts 主题名（由 useTheme 提供，随皮肤变化） */
  themeName: { type: String, default: '' },
  /** 是否在数据更新时做过渡动画（动态排名需要 true） */
  transition: { type: Boolean, default: true },
})
/** ready：每次（含换肤重建后）实例就位都通知一次，供外层绑定交互（如大屏联动） */
const emit = defineEmits(['ready'])

const box = ref(null)
const instance = shallowRef(null)
let observer = null

function createInstance() {
  if (instance.value) {
    instance.value.dispose()
    instance.value = null
  }
  instance.value = echarts.init(box.value, props.themeName, { renderer: 'canvas' })
  instance.value.setOption(props.option, { notMerge: true, silent: true })
  emit('ready', instance.value)
}

function render() {
  if (!instance.value) return
  instance.value.setOption(props.option, {
    notMerge: false,
    lazyUpdate: false,
    silent: true,
  })
}

onMounted(() => {
  createInstance()
  observer = new ResizeObserver(() => instance.value?.resize())
  observer.observe(box.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  instance.value?.dispose()
  instance.value = null
})

// 皮肤变了：重建实例
watch(
  () => props.themeName,
  () => {
    if (instance.value) createInstance()
  },
)

// 数据/配置变了：就地更新（保留过渡动画）
watch(
  () => props.option,
  () => {
    if (!props.transition && instance.value) {
      instance.value.setOption({ animationDurationUpdate: 0 }, { silent: true })
    }
    render()
  },
  { deep: true },
)

// 把实例暴露出去，方便将来导出图片、做图表联动
defineExpose({
  getInstance: () => instance.value,
})
</script>

<template>
  <div ref="box" class="chart" :style="{ height }" />
</template>

<style scoped>
.chart {
  width: 100%;
  min-height: 120px;
}
</style>
