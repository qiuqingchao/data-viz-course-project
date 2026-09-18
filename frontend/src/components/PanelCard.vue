<script setup>
/**
 * 统一面板：全站所有的"卡片"都用它，保证圆角、描边、标题样式前后一致。
 * 标题左侧的黄铜短横是全局统一的"章节标记"。
 */
defineProps({
  title: { type: String, default: '' },
  note: { type: String, default: '' },
  /** 面板体是否去掉内边距（图表类通常需要贴边） */
  flush: { type: Boolean, default: false },
})
</script>

<template>
  <section class="panel">
    <header v-if="title || $slots.extra" class="panel__head">
      <div class="panel__title-wrap">
        <div class="section-title">{{ title }}</div>
        <span v-if="note" class="panel__note">{{ note }}</span>
      </div>
      <div class="panel__extra">
        <slot name="extra" />
      </div>
    </header>
    <div class="tick-rule panel__rule" />
    <div class="panel__body" :class="{ 'panel__body--flush': flush }">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  background: var(--ink-850);
  border: 1px solid var(--line-1);
  border-radius: var(--r-3);
  /* 浅色皮肤下靠极淡的阴影把白卡片从纸底上"托起来"；深色皮肤为 none */
  box-shadow: var(--shadow-panel);
  overflow: hidden;
  transition: border-color var(--dur-1) var(--ease);
}

.panel:hover {
  border-color: var(--line-2);
}

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-4) var(--sp-5) var(--sp-3);
}

.panel__title-wrap {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  min-width: 0;
}

.panel__note {
  font-size: var(--fs-12);
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.panel__extra {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: none;
}

.panel__rule {
  margin: 0 var(--sp-5);
  opacity: 0.35;
}

.panel__body {
  padding: var(--sp-4) var(--sp-5) var(--sp-5);
  flex: 1;
  min-height: 0;
}

.panel__body--flush {
  padding: var(--sp-3) var(--sp-3) var(--sp-3);
}
</style>
