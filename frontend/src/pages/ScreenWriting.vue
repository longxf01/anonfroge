<template>
  <main class="screenwriting-page">
    <div class="app-shell">
      <aside class="sidebar">
        <div class="side-top">
          <div class="brand" @click="goProject">AF</div>

          <el-tooltip content="项目" placement="right">
            <button class="nav-btn" aria-label="项目" @click="goProject">
              <el-icon><Folder /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="小说" placement="right">
            <button class="nav-btn" aria-label="小说" @click="goNovel">
              <el-icon><Reading /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="剧本创作" placement="right">
            <button class="nav-btn active" aria-label="剧本创作">
              <el-icon><EditPen /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="任务" placement="right">
            <button class="nav-btn" aria-label="任务" @click="goTasks">
              <el-icon><List /></el-icon>
            </button>
          </el-tooltip>
        </div>

        <div class="side-bottom">
          <el-tooltip content="文档" placement="right">
            <button class="nav-btn" aria-label="文档" @click="showComingSoon">
              <el-icon><Document /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="设置" placement="right">
            <button class="nav-btn" aria-label="设置" @click="settingsVisible = true">
              <el-icon><Setting /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="代码仓库" placement="right">
            <button class="nav-btn" aria-label="代码仓库" @click="showComingSoon">
              <el-icon><Connection /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </aside>

      <section class="main-panel">
        <header class="page-header">
          <div class="page-header__left">
            <h1 class="title">剧本创作</h1>
            <p class="desc">基于小说事件，与 AI Agent 协作完成故事骨架、改编策略与剧本</p>
          </div>

          <div class="page-header__right">
            <el-button class="header-action" size="large" @click="goNovel">
              <el-icon><Reading /></el-icon>
              &nbsp;返回小说
            </el-button>

            <el-button class="header-action stage-button" size="large" @click="goScriptManage">
              <el-icon><Document /></el-icon>
              &nbsp;剧本管理
            </el-button>
          </div>
        </header>

        <section class="workspace">
          <aside class="ai-chat-panel">
            <section class="assistant-shell">
              <header class="assistant-header">
                <div class="assistant-heading">
                  <span class="assistant-status-dot"></span>
                  <div>
                    <h2>剧本创作 Agent</h2>
                    <p>多轮协作 · 基于小说事件推演</p>
                  </div>
                </div>
                <span class="assistant-message-count">{{ chatMessages.length }} 条</span>
              </header>

              <div class="assistant-thread-wrap">
                <div
                  ref="assistantThreadRef"
                  class="assistant-thread"
                  aria-label="对话记录"
                  @scroll="onAssistantThreadScroll"
                >
                  <article
                    v-for="message in chatMessages"
                    :key="message.id"
                    class="assistant-message"
                    :class="`assistant-message--${message.role}`"
                  >
                    <div class="assistant-bubble">
                      <p>{{ message.content }}</p>
                      <time class="assistant-bubble__time">{{ message.time }}</time>
                    </div>
                  </article>
                </div>

                <button
                  v-if="showAssistantScrollBottom"
                  type="button"
                  class="assistant-scroll-bottom-btn"
                  aria-label="回到最新消息"
                  @click="scrollToAssistantBottom()"
                >
                  <el-icon><CaretBottom /></el-icon>
                </button>
              </div>

              <footer class="assistant-composer">
                <div class="composer-toolbar">
                  <el-tooltip content="新对话" placement="top">
                    <button type="button" class="composer-tool" aria-label="新对话" @click="startNewConversation">
                      <el-icon><Plus /></el-icon>
                    </button>
                  </el-tooltip>
                  <el-tooltip content="插入当前阶段提示" placement="top">
                    <button type="button" class="composer-tool" aria-label="插入当前阶段提示" @click="insertStagePrompt">
                      <el-icon><MagicStick /></el-icon>
                    </button>
                  </el-tooltip>
                  <el-tooltip content="引用项目小说事件" placement="top">
                    <button type="button" class="composer-tool" aria-label="引用项目小说事件" @click="showComingSoon">
                      <el-icon><Connection /></el-icon>
                    </button>
                  </el-tooltip>
                  <el-tooltip content="清空输入" placement="top">
                    <button
                      type="button"
                      class="composer-tool"
                      aria-label="清空输入"
                      :disabled="!chatInput"
                      @click="clearComposer"
                    >
                      <el-icon><Delete /></el-icon>
                    </button>
                  </el-tooltip>

                  <span class="composer-toolbar__spacer"></span>

                  <span class="composer-counter" :class="{ 'is-limit': chatInput.length >= 2000 }">
                    {{ chatInput.length }} / 2000
                  </span>
                </div>

                <el-input
                  ref="composerRef"
                  v-model="chatInput"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  resize="none"
                  maxlength="2000"
                  placeholder="描述你的创作目标，例如：先梳理前十章的主线故事骨架。"
                  @keydown.ctrl.enter.prevent="sendChatMessage"
                />

                <div class="assistant-composer__actions">
                  <span class="composer-hint">Ctrl + Enter 发送</span>
                  <el-button
                    class="assistant-send-btn"
                    type="primary"
                    :disabled="!chatInput.trim()"
                    @click="sendChatMessage"
                  >
                    <el-icon><MagicStick /></el-icon>
                    &nbsp;发送
                  </el-button>
                </div>
              </footer>
            </section>
          </aside>

          <section class="workspace-main">
            <el-tabs v-model="activeTab" class="screenwriting-tabs">
              <el-tab-pane
                v-for="tab in screenwritingTabs"
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
                    <el-button class="tab-action" type="primary" @click="startWithPrompt(tab)">
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
        </section>
      </section>
    </div>

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { InputInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import {
  CaretBottom,
  Connection,
  Delete,
  Document,
  EditPen,
  Folder,
  List,
  MagicStick,
  Plus,
  Reading,
  Setting,
  Tickets,
} from '@element-plus/icons-vue'
import Settings from '../components/Settings.vue'

interface ChatMessage {
  id: number
  role: 'assistant' | 'user'
  content: string
  time: string
}

interface ScreenwritingTab {
  name: string
  label: string
  icon: typeof Tickets
  desc: string
  action: string
  title: string
  hint: string
  starter: string
}

const router = useRouter()
const route = useRoute()

const projectPublicId = ref('')
const settingsVisible = ref(false)
const activeTab = ref('skeleton')

const chatInput = ref('')
const composerRef = ref<InputInstance | null>(null)
const assistantThreadRef = ref<HTMLElement | null>(null)
const showAssistantScrollBottom = ref(false)
let chatSeq = 2

const screenwritingTabs: ScreenwritingTab[] = [
  {
    name: 'skeleton',
    label: '故事骨架',
    icon: Tickets,
    desc: '基于已清洗的小说事件，梳理主线脉络、关键人物与核心冲突结构。',
    action: '生成故事骨架',
    title: '故事骨架尚未生成',
    hint: '在左侧与 AI Agent 对话，从已提取的小说事件中提炼主线、人物关系与章节脉络。',
    starter: '请基于本项目已提取的小说事件，梳理主线故事骨架，包含关键人物、核心冲突与章节脉络。',
  },
  {
    name: 'strategy',
    label: '改编策略',
    icon: MagicStick,
    desc: '明确改编基调、节奏取舍与表现重点，为剧本创作建立统一依据。',
    action: '制定改编策略',
    title: '改编策略待制定',
    hint: '结合故事骨架，确定整体基调、节奏安排与取舍重点，作为后续剧本创作的依据。',
    starter: '请结合故事骨架，提出本项目的改编策略，包括整体基调、节奏安排与情节取舍重点。',
  },
  {
    name: 'script',
    label: '剧本',
    icon: Document,
    desc: '在故事骨架与改编策略确认后，于此逐场景生成并打磨剧本内容。',
    action: '开始创作剧本',
    title: '剧本尚未开始',
    hint: '确认故事骨架与改编策略后，在左侧 Agent 协助下逐场景生成并编辑剧本初稿。',
    starter: '请根据故事骨架与改编策略，开始逐场景创作剧本初稿。',
  },
]

const ASSISTANT_GREETING =
  '你好，我是剧本创作 Agent。我会基于本项目已提取的小说事件，协助你完成故事骨架、改编策略与剧本。可以从右侧选择一个阶段，或直接告诉我你的创作目标。'

const chatMessages = ref<ChatMessage[]>([
  {
    id: 1,
    role: 'assistant',
    content: ASSISTANT_GREETING,
    time: '09:30',
  },
])

const resolveProjectPublicId = () => {
  const id = route.query.id
  if (Array.isArray(id)) return id[0] || ''
  return typeof id === 'string' ? id : ''
}

const formatChatTime = (date = new Date()) =>
  date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

const startWithPrompt = (tab: ScreenwritingTab) => {
  chatInput.value = tab.starter
  nextTick(() => composerRef.value?.focus?.())
}

const insertStagePrompt = () => {
  const tab = screenwritingTabs.find((item) => item.name === activeTab.value) ?? screenwritingTabs[0]
  startWithPrompt(tab)
}

const clearComposer = () => {
  chatInput.value = ''
  nextTick(() => composerRef.value?.focus?.())
}

const startNewConversation = () => {
  chatMessages.value = [
    {
      id: 1,
      role: 'assistant',
      content: ASSISTANT_GREETING,
      time: formatChatTime(),
    },
  ]
  chatSeq = 2
  chatInput.value = ''
  nextTick(() => scrollToAssistantBottom('auto'))
  ElMessage.success('已开始新的对话')
}

const isAssistantThreadAtBottom = () => {
  const el = assistantThreadRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= 24
}

const updateAssistantScrollState = () => {
  const el = assistantThreadRef.value
  if (!el) {
    showAssistantScrollBottom.value = false
    return
  }
  showAssistantScrollBottom.value = el.scrollHeight > el.clientHeight && !isAssistantThreadAtBottom()
}

const scrollToAssistantBottom = (behavior: ScrollBehavior = 'smooth') => {
  const el = assistantThreadRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior })
  showAssistantScrollBottom.value = false
}

const onAssistantThreadScroll = () => {
  updateAssistantScrollState()
}

const sendChatMessage = () => {
  const content = chatInput.value.trim()
  if (!content) {
    ElMessage.warning('请输入对话内容')
    return
  }

  chatMessages.value.push({
    id: chatSeq++,
    role: 'user',
    content,
    time: formatChatTime(),
  })
  chatInput.value = ''

  chatMessages.value.push({
    id: chatSeq++,
    role: 'assistant',
    content: `已收到你的需求：“${content}”。我会结合本项目已提取的小说事件，在「${activeTabLabel()}」阶段继续多轮推演，并将结果同步到右侧选项卡。`,
    time: formatChatTime(),
  })
  nextTick(() => scrollToAssistantBottom())
}

const activeTabLabel = () =>
  screenwritingTabs.find((tab) => tab.name === activeTab.value)?.label ?? '故事骨架'

const goProject = () => {
  router.push('/project')
}

const goNovel = () => {
  router.push({
    path: '/novel',
    query: projectPublicId.value ? { id: projectPublicId.value } : {},
  })
}

const goScriptManage = () => {
  router.push({
    path: '/script',
    query: projectPublicId.value ? { id: projectPublicId.value } : {},
  })
}

const goTasks = () => {
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  router.push({
    path: '/tasks',
    query: {
      id: projectPublicId.value,
      type: 'novel',
      from: route.fullPath,
    },
  })
}

const showComingSoon = () => {
  ElMessage.info('功能开发中')
}

onMounted(() => {
  projectPublicId.value = resolveProjectPublicId()
  nextTick(() => scrollToAssistantBottom('auto'))
})

onBeforeUnmount(() => {
  showAssistantScrollBottom.value = false
})
</script>

<style scoped>
.screenwriting-page {
  height: 100vh;
  height: 100dvh;
  min-height: 760px;
  overflow: hidden;
  padding: 16px;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  background:
    radial-gradient(circle at top, rgba(100, 116, 139, 0.18) 0%, rgba(11, 13, 16, 0) 32%),
    linear-gradient(180deg, #0d1117 0%, #0b0d10 100%);
}

.app-shell {
  height: calc(100vh - 32px);
  height: calc(100dvh - 32px);
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 16px;
}

.sidebar {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.side-top,
.side-bottom {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.brand {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: #0a0a0a;
  font-size: 20px;
  font-weight: 800;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, #f3d96b, #c4b5fd);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 6px 18px rgba(243, 217, 107, 0.18);
  transition: transform 0.2s ease;
}

.brand:hover {
  transform: translateY(-1px);
}

.nav-btn {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 16px;
  color: #8b949e;
  background: transparent;
  cursor: pointer;
  font-size: 22px;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.nav-btn :deep(.el-icon) {
  font-size: 22px;
}

.nav-btn:hover {
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.05);
  transform: translateY(-1px);
}

.nav-btn.active {
  color: #dbeafe;
  border-color: rgba(37, 99, 235, 0.32);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.22), rgba(37, 99, 235, 0.12));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.main-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 24px 28px 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
  flex-shrink: 0;
}

.page-header__left {
  min-width: 0;
}

.page-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  margin: 0;
  font-size: 32px;
  line-height: 1.1;
  font-weight: 800;
  background: linear-gradient(180deg, #ffffff 0%, #93a1b3 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.desc {
  margin: 6px 0 0;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.4;
}

.header-action {
  height: 38px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #c5cdd6;
  background-color: rgba(255, 255, 255, 0.04);
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.header-action :deep(.el-icon) {
  margin-right: 0;
  font-size: 16px;
}

.header-action:hover,
.header-action:focus {
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.18);
  background-color: rgba(255, 255, 255, 0.08);
  transform: translateY(-1px);
}

.stage-button {
  border-color: rgba(96, 165, 250, 0.28);
  color: #bfdbfe;
  background-color: rgba(37, 99, 235, 0.12);
}

.stage-button:hover,
.stage-button:focus {
  color: #ffffff;
  border-color: rgba(147, 197, 253, 0.42);
  background-color: rgba(37, 99, 235, 0.2);
}

.workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: clamp(368px, 24vw, 432px) minmax(0, 1fr);
  gap: 8px;
  overflow: hidden;
}

.ai-chat-panel,
.workspace-main {
  min-height: 0;
}

.ai-chat-panel {
  overflow: hidden;
}

.workspace-main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(8, 12, 18, 0.62);
  padding: 14px 16px 16px;
}

/* ===== AI Agent 多轮对话 ===== */
.assistant-shell {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background:
    radial-gradient(circle at 20% 0%, rgba(37, 99, 235, 0.14), transparent 34%),
    linear-gradient(180deg, rgba(15, 22, 32, 0.92), rgba(7, 11, 17, 0.96));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 22px 52px rgba(0, 0, 0, 0.42);
  overflow: hidden;
}

.assistant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 50px;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.01)),
    rgba(9, 14, 22, 0.86);
}

.assistant-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.assistant-status-dot {
  position: relative;
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow:
    0 0 0 4px rgba(34, 197, 94, 0.12),
    0 0 18px rgba(34, 197, 94, 0.32);
}

.assistant-heading h2 {
  margin: 0;
  color: #f2f4f8;
  font-size: 16px;
  line-height: 1.25;
  font-weight: 750;
}

.assistant-heading p {
  margin: 3px 0 0;
  color: #7e8893;
  font-size: 12px;
  line-height: 1.35;
}

.assistant-message-count {
  flex-shrink: 0;
  min-width: 54px;
  padding: 5px 9px;
  border-radius: 999px;
  color: #93c5fd;
  border: 1px solid rgba(96, 165, 250, 0.22);
  background: rgba(37, 99, 235, 0.12);
  text-align: center;
  font-size: 12px;
  font-weight: 700;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.assistant-thread-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  background: rgba(4, 8, 14, 0.24);
}

.assistant-thread {
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 12px 16px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.assistant-thread::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.assistant-thread::-webkit-scrollbar-track {
  background: transparent;
}

.assistant-thread::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.assistant-thread::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.assistant-scroll-bottom-btn {
  position: absolute;
  right: 16px;
  bottom: 14px;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(96, 165, 250, 0.38);
  border-radius: 50%;
  color: #dbeafe;
  background: rgba(13, 18, 27, 0.92);
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.34);
  cursor: pointer;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.assistant-scroll-bottom-btn :deep(.el-icon) {
  font-size: 18px;
}

.assistant-scroll-bottom-btn:hover,
.assistant-scroll-bottom-btn:focus {
  color: #ffffff;
  border-color: rgba(96, 165, 250, 0.65);
  background: rgba(37, 99, 235, 0.72);
  transform: translateY(-1px);
}

.assistant-scroll-bottom-btn:active {
  transform: translateY(0);
}

.assistant-message {
  display: flex;
  align-items: flex-start;
}

.assistant-message--user {
  justify-content: flex-end;
}

.assistant-message--user .assistant-bubble {
  max-width: 86%;
  border-color: rgba(96, 165, 250, 0.36);
  background:
    linear-gradient(180deg, rgba(37, 99, 235, 0.28), rgba(37, 99, 235, 0.16)),
    rgba(13, 18, 27, 0.86);
}

.assistant-bubble {
  min-width: 0;
  max-width: 92%;
  display: grid;
  gap: 6px;
  padding: 11px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.012)),
    rgba(15, 22, 32, 0.88);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.18);
}

.assistant-bubble__time {
  justify-self: end;
  color: #7e8893;
  font-size: 11px;
  line-height: 1;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.assistant-bubble p {
  margin: 0;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.68;
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-composer {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent),
    rgba(9, 14, 22, 0.92);
}

.composer-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.composer-toolbar__spacer {
  flex: 1;
}

.composer-tool {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
  color: #8b949e;
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: color 0.18s ease, background-color 0.18s ease, border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.composer-tool :deep(.el-icon) {
  font-size: 16px;
}

.composer-tool:hover:not(:disabled) {
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.42);
  background: rgba(37, 99, 235, 0.14);
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.18);
}

.composer-tool:focus-visible {
  outline: none;
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.55);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
}

.composer-tool:active:not(:disabled) {
  transform: translateY(0) scale(0.94);
  background: rgba(37, 99, 235, 0.2);
}

.composer-tool:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.composer-counter {
  flex-shrink: 0;
  color: #6e7681;
  font-size: 12px;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

.composer-counter.is-limit {
  color: #fca5a5;
}

.composer-hint {
  color: #6e7681;
  font-size: 12px;
  line-height: 1.45;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.assistant-composer :deep(.el-textarea__inner) {
  padding: 10px 13px;
  border: none;
  border-radius: 10px;
  color: #e6edf3;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  font-size: 13px;
  line-height: 1.6;
}

.assistant-composer :deep(.el-textarea__inner:hover) {
  background-color: #0f151d;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.2) inset;
}

.assistant-composer :deep(.el-textarea__inner:focus) {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.assistant-composer :deep(.el-textarea__inner::placeholder) {
  color: #7e8893;
}

.assistant-composer :deep(.el-input__count) {
  color: #6e7681 !important;
  background: transparent !important;
  background-color: transparent !important;
}

.assistant-composer__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.assistant-composer__actions span {
  min-width: 0;
  color: #6e7681;
  font-size: 12px;
  line-height: 1.45;
}

.assistant-send-btn {
  --el-button-disabled-bg-color: rgba(255, 255, 255, 0.04);
  --el-button-disabled-border-color: rgba(255, 255, 255, 0.08);
  --el-button-disabled-text-color: #4d5560;
  flex-shrink: 0;
  height: 36px;
  min-width: 86px;
  padding: 0 16px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
}

.assistant-send-btn:hover,
.assistant-send-btn:focus {
  transform: translateY(-1px);
}

.assistant-send-btn :deep(.el-icon) {
  margin-right: 0;
  font-size: 15px;
}

/* ===== 右侧选项卡 ===== */
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

@media (max-width: 1180px) {
  .workspace {
    grid-template-columns: minmax(320px, 0.8fr) minmax(0, 1fr);
  }
}

@media (max-width: 920px) {
  .screenwriting-page {
    min-height: 920px;
  }

  .app-shell {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .sidebar {
    flex-direction: row;
    padding: 12px 14px;
  }

  .side-top,
  .side-bottom {
    width: auto;
    flex-direction: row;
    gap: 10px;
  }

  .page-header,
  .page-header__right {
    flex-direction: column;
    align-items: stretch;
  }

  .workspace {
    grid-template-columns: 1fr;
    overflow-y: auto;
    align-content: start;
  }

  .ai-chat-panel,
  .workspace-main {
    overflow: visible;
  }

  .assistant-shell {
    min-height: 560px;
  }

  .workspace-main {
    min-height: 520px;
  }
}
</style>