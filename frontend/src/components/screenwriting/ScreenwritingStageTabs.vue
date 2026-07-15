<template>
  <section class="workspace-main">
    <el-tabs v-model="tabValue" class="screenwriting-tabs">
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.name"
        :name="tab.name"
        :label="tab.label"
      >
        <div class="tab-panel">
          <div class="tab-panel__toolbar">
            <div class="tab-panel__heading">
              <h3>{{ tab.label }}</h3>
              <p>{{ tab.desc }}</p>
            </div>
            <el-button class="tab-action" type="primary" @click="emit('start', tab)">
              <el-icon><MagicStick /></el-icon>
              &nbsp;{{ tab.action }}
            </el-button>
          </div>

          <div class="tab-panel__body">
            <div class="tab-empty">
              <el-icon class="tab-empty__icon"><component :is="tab.icon" /></el-icon>
              <strong>{{ tab.title }}</strong>
              <p>{{ tab.hint }}</p>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import type { ScreenwritingActiveTab } from '@/api/novel'
import type { ScreenwritingTab } from './types'

const props = defineProps<{
  activeTab: ScreenwritingActiveTab
  tabs: ScreenwritingTab[]
}>()

const emit = defineEmits<{
  'update:activeTab': [value: ScreenwritingActiveTab]
  start: [tab: ScreenwritingTab]
}>()

const tabValue = computed({
  get: () => props.activeTab,
  set: (value) => emit('update:activeTab', value as ScreenwritingActiveTab),
})
</script>

<style scoped>
.workspace-main {
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(8, 12, 18, 0.62);
  padding: 14px 16px 16px;
}

.screenwriting-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.screenwriting-tabs :deep(.el-tabs__header) {
  margin: 0 0 14px;
}

.screenwriting-tabs :deep(.el-tabs__nav-wrap)::after {
  height: 1px;
  background-color: rgba(255, 255, 255, 0.06);
}

.screenwriting-tabs :deep(.el-tabs__item) {
  height: 42px;
  padding: 0 18px;
  color: #8b949e;
  font-size: 14px;
  font-weight: 600;
}

.screenwriting-tabs :deep(.el-tabs__item:hover) {
  color: #e6edf3;
}

.screenwriting-tabs :deep(.el-tabs__item.is-active) {
  color: #dbeafe;
}

.screenwriting-tabs :deep(.el-tabs__active-bar) {
  height: 3px;
  border-radius: 3px;
  background: linear-gradient(90deg, #2563eb 0%, #60a5fa 100%);
}

.screenwriting-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
}

.screenwriting-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.tab-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.tab-panel__toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.tab-panel__heading h3 {
  margin: 0;
  color: #f2f4f8;
  font-size: 17px;
  font-weight: 750;
}

.tab-panel__heading p {
  margin: 5px 0 0;
  max-width: 540px;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.6;
}

.tab-action {
  flex-shrink: 0;
  height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  background: #2563eb;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
}

.tab-action :deep(.el-icon) {
  margin-right: 0;
  font-size: 15px;
}

.tab-action:hover,
.tab-action:focus {
  background: #1d4ed8;
  transform: translateY(-1px);
}

.tab-panel__body {
  flex: 1;
  min-height: 0;
  display: flex;
  border: 1px dashed rgba(255, 255, 255, 0.1);
  border-radius: 14px;
  background: rgba(4, 8, 14, 0.36);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.tab-panel__body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.tab-panel__body::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.tab-empty {
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 32px 24px;
  text-align: center;
}

.tab-empty__icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.12);
  font-size: 28px;
}

.tab-empty strong {
  color: #e6edf3;
  font-size: 15px;
  font-weight: 700;
}

.tab-empty p {
  max-width: 420px;
  margin: 0;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.7;
}

@media (max-width: 920px) {
  .workspace-main {
    overflow: visible;
    min-height: 520px;
  }
}
</style>
