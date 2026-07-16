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
            <div class="tab-panel__actions">
              <template v-if="editingTab === tab.name">
                <el-button
                  class="tab-action tab-action--ghost"
                  :disabled="saving"
                  @click="cancelEdit"
                >
                  取消
                </el-button>
                <el-button
                  class="tab-action"
                  type="primary"
                  :loading="saving"
                  @click="saveEdit(tab.name)"
                >
                  保存
                </el-button>
              </template>
              <template v-else>
                <el-button
                  class="tab-action tab-action--ghost"
                  @click="startEdit(tab.name)"
                >
                  <el-icon><EditPen /></el-icon>
                  &nbsp;{{ workspaceContent(tab.name) ? '编辑' : '手动撰写' }}
                </el-button>
                <el-button class="tab-action" type="primary" @click="emit('start', tab)">
                  <el-icon><MagicStick /></el-icon>
                  &nbsp;{{ tab.action }}
                </el-button>
              </template>
            </div>
          </div>

          <div class="tab-panel__body" :class="{ 'tab-panel__body--filled': editingTab === tab.name || workspaceContent(tab.name) }">
            <el-input
              v-if="editingTab === tab.name"
              v-model="draftContent"
              class="tab-editor"
              type="textarea"
              :autosize="false"
              resize="none"
              :placeholder="`在此撰写${tab.label}内容，支持 Markdown 格式`"
            />
            <MdPreview
              v-else-if="workspaceContent(tab.name)"
              :id="`screenwriting-workspace-${tab.name}`"
              class="workspace-markdown-preview"
              :model-value="workspaceContent(tab.name)"
              theme="dark"
              preview-theme="github"
              code-theme="github"
            />
            <div v-else class="tab-empty">
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
import { computed, ref } from 'vue'
import { EditPen, MagicStick } from '@element-plus/icons-vue'
import { MdPreview } from 'md-editor-v3'
import type { ScreenwritingActiveTab, ScreenwritingWorkspace } from '@/api/screenwriting'
import type { ScreenwritingTab } from './types'

const props = defineProps<{
  activeTab: ScreenwritingActiveTab
  tabs: ScreenwritingTab[]
  workspace: ScreenwritingWorkspace
  saving?: boolean
}>()

const emit = defineEmits<{
  'update:activeTab': [value: ScreenwritingActiveTab]
  start: [tab: ScreenwritingTab]
  save: [tab: ScreenwritingActiveTab, content: string]
}>()

const editingTab = ref<ScreenwritingActiveTab | null>(null)
const draftContent = ref('')

const tabValue = computed({
  get: () => props.activeTab,
  set: (value) => emit('update:activeTab', value as ScreenwritingActiveTab),
})

const workspaceContent = (tab: ScreenwritingActiveTab) => props.workspace[tab] ?? ''

const startEdit = (tab: ScreenwritingActiveTab) => {
  editingTab.value = tab
  draftContent.value = workspaceContent(tab)
}

const cancelEdit = () => {
  editingTab.value = null
  draftContent.value = ''
}

const saveEdit = (tab: ScreenwritingActiveTab) => {
  emit('save', tab, draftContent.value)
}

defineExpose({
  /** 保存成功后由父组件调用以退出编辑态。 */
  finishEdit: cancelEdit,
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

.tab-panel__actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0;
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

.tab-action--ghost {
  color: #c9d1d9;
  background: rgba(255, 255, 255, 0.06);
  box-shadow: none;
}

.tab-action--ghost:hover,
.tab-action--ghost:focus {
  color: #f2f4f8;
  background: rgba(255, 255, 255, 0.12);
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

.tab-panel__body--filled {
  border-style: solid;
  border-color: rgba(255, 255, 255, 0.08);
}

.tab-panel__body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.tab-panel__body::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.tab-editor {
  flex: 1;
  display: flex;
}

.tab-editor :deep(.el-textarea__inner) {
  height: 100%;
  min-height: 100%;
  padding: 16px 18px;
  color: #e6edf3;
  font-size: 13.5px;
  line-height: 1.8;
  font-family: "JetBrains Mono", Consolas, "PingFang SC", monospace;
  background: transparent;
  border: none;
  box-shadow: none;
}

.workspace-markdown-preview {
  flex: 1;
  min-width: 0;
  background: transparent;
}

.workspace-markdown-preview :deep(.md-editor-preview-wrapper),
.workspace-markdown-preview :deep(.md-editor-preview) {
  padding: 16px 18px;
  background: transparent;
  color: #dbe4ec;
}

.workspace-markdown-preview :deep(.md-editor-preview) {
  font-size: 13.5px;
  line-height: 1.85;
  word-break: break-word;
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