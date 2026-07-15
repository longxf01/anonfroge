<template>
  <main class="screenwriting-page">
    <div class="app-shell">
      <ScreenwritingSidebar
        @project="goProject"
        @novel="goNovel"
        @tasks="goTasks"
        @documents="showComingSoon"
        @settings="settingsVisible = true"
        @repository="showComingSoon"
      />

      <section class="main-panel">
        <ScreenwritingPageHeader
          @back-novel="goNovel"
          @script-manage="goScriptManage"
        />

        <section class="workspace">
          <ScreenwritingAssistantPanel
            ref="assistantPanelRef"
            v-model="chatInput"
            :messages="chatMessages"
            :connected-model-id="connectedModelId"
            :is-sending="isSendingChat"
            :streaming-message-id="streamingAssistantMessageId"
            @send="sendChatMessage"
            @new-conversation="startNewConversation"
            @insert-stage-prompt="insertStagePrompt"
            @quote-events="showComingSoon"
            @clear-composer="clearComposer"
          />

          <ScreenwritingStageTabs
            v-model:active-tab="activeTab"
            :tabs="screenwritingTabs"
            @start="startWithPrompt"
          />
        </section>
      </section>
    </div>

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Document,
  MagicStick,
  Tickets,
} from '@element-plus/icons-vue'
import {
  chatScreenwritingStreamUrl,
  type ScreenwritingActiveTab,
  type ScreenwritingChatTurn,
  type ScreenwritingStreamEvent,
} from '@/api/novel'
import { fetchWithAuthRetry } from '@/request'
import { readNdjsonStream } from '@/utils/ndjsonStream'
import ScreenwritingAssistantPanel from '@/components/screenwriting/ScreenwritingAssistantPanel.vue'
import ScreenwritingPageHeader from '@/components/screenwriting/ScreenwritingPageHeader.vue'
import ScreenwritingSidebar from '@/components/screenwriting/ScreenwritingSidebar.vue'
import ScreenwritingStageTabs from '@/components/screenwriting/ScreenwritingStageTabs.vue'
import type { ChatMessage, ScreenwritingTab } from '@/components/screenwriting/types'
import Settings from '../components/Settings.vue'

interface AssistantPanelExpose {
  focusComposer: () => void
  followOutput: () => Promise<void>
  resetAutoScroll: () => void
  scrollToBottom: (behavior?: ScrollBehavior) => void
}

const router = useRouter()
const route = useRoute()

const projectPublicId = ref('')
const settingsVisible = ref(false)
const activeTab = ref<ScreenwritingActiveTab>('skeleton')

const chatInput = ref('')
const assistantPanelRef = ref<AssistantPanelExpose | null>(null)
const isSendingChat = ref(false)
const conversationId = ref('')
const connectedModelId = ref('')
const streamingAssistantMessageId = ref<number | null>(null)
let chatSeq = 2
let chatStreamController: AbortController | null = null

const ASSISTANT_REVEAL_CHUNK_SIZE = 1
const ASSISTANT_REVEAL_INTERVAL_MS = 18

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
  '你好，我是剧本创作助理。我会基于本项目已提取的小说事件，协助你完成故事骨架、改编策略与剧本。可以从右侧选择一个阶段，或直接告诉我你的创作目标。'

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

const createConversationId = () => (
  `conv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
)

const startWithPrompt = (tab: ScreenwritingTab) => {
  chatInput.value = tab.starter
  nextTick(() => assistantPanelRef.value?.focusComposer())
}

const insertStagePrompt = () => {
  const tab = screenwritingTabs.find((item) => item.name === activeTab.value) ?? screenwritingTabs[0]
  startWithPrompt(tab)
}

const clearComposer = () => {
  chatInput.value = ''
  nextTick(() => assistantPanelRef.value?.focusComposer())
}

const startNewConversation = () => {
  stopChatStream()
  assistantPanelRef.value?.resetAutoScroll()
  chatMessages.value = [
    {
      id: 1,
      role: 'assistant',
      content: ASSISTANT_GREETING,
      time: formatChatTime(),
    },
  ]
  chatSeq = 2
  conversationId.value = createConversationId()
  chatInput.value = ''
  nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
  ElMessage.success('已开始新的对话')
}

const toChatTurn = (message: ChatMessage): ScreenwritingChatTurn => ({
  role: message.role,
  content: message.content,
  time: message.time,
})

const waitForAssistantRevealFrame = () => (
  new Promise<void>((resolve) => {
    window.setTimeout(resolve, ASSISTANT_REVEAL_INTERVAL_MS)
  })
)

const getMissingAssistantContent = (currentContent: string, incomingContent: string) => {
  if (!incomingContent) return ''
  if (!currentContent) return incomingContent
  if (incomingContent.startsWith(currentContent)) {
    return incomingContent.slice(currentContent.length)
  }
  if (currentContent.includes(incomingContent)) {
    return ''
  }
  return incomingContent
}

const sendChatMessage = async () => {
  const content = chatInput.value.trim()
  if (!content) {
    ElMessage.warning('请输入对话内容')
    return
  }
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  if (isSendingChat.value) {
    ElMessage.warning('上一轮对话仍在生成中')
    return
  }

  assistantPanelRef.value?.resetAutoScroll()
  const history = chatMessages.value
    .map(toChatTurn)
    .filter((message) => message.content.trim())
  chatMessages.value.push({
    id: chatSeq++,
    role: 'user',
    content,
    time: formatChatTime(),
  })
  chatInput.value = ''

  const assistantMessage: ChatMessage = {
    id: chatSeq++,
    role: 'assistant',
    content: '',
    time: formatChatTime(),
  }
  chatMessages.value.push(assistantMessage)
  streamingAssistantMessageId.value = assistantMessage.id
  await nextTick()
  assistantPanelRef.value?.scrollToBottom()

  const controller = new AbortController()
  chatStreamController = controller
  isSendingChat.value = true
  let receivedContent = false
  let targetAssistantContent = ''
  let assistantRevealCanceled = false
  let assistantRevealQueue: string[] = []
  let assistantRevealTask: Promise<void> | null = null

  const revealQueuedAssistantContent = async () => {
    while (!assistantRevealCanceled && !controller.signal.aborted && assistantRevealQueue.length) {
      const chunk = assistantRevealQueue.splice(0, ASSISTANT_REVEAL_CHUNK_SIZE).join('')
      assistantMessage.content += chunk
      await assistantPanelRef.value?.followOutput()
      await waitForAssistantRevealFrame()
    }
  }

  const ensureAssistantRevealTask = () => {
    if (!assistantRevealTask) {
      assistantRevealTask = revealQueuedAssistantContent().finally(() => {
        assistantRevealTask = null
        if (!assistantRevealCanceled && !controller.signal.aborted && assistantRevealQueue.length) {
          ensureAssistantRevealTask()
        }
      })
    }
  }

  const waitForAssistantReveal = async () => {
    while (assistantRevealTask) {
      await assistantRevealTask
    }
  }

  const enqueueAssistantContent = (incomingContent: string, mode: 'delta' | 'final') => {
    const chunk = mode === 'final'
      ? getMissingAssistantContent(targetAssistantContent, incomingContent)
      : incomingContent
    if (!chunk) return

    targetAssistantContent += chunk
    receivedContent = true
    assistantRevealQueue.push(...Array.from(chunk))
    ensureAssistantRevealTask()
  }

  try {
    const response = await fetchWithAuthRetry(chatScreenwritingStreamUrl(projectPublicId.value), {
      method: 'POST',
      headers: {
        Accept: 'application/x-ndjson',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        conversationId: conversationId.value,
        activeTab: activeTab.value,
        message: content,
        messages: history,
      }),
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(await readFetchError(response))
    }
    if (!response.body) {
      throw new Error('当前浏览器不支持读取 AI 对话流')
    }

    await readNdjsonStream<ScreenwritingStreamEvent>(response.body, async (event) => {
      if (event.conversationId) {
        conversationId.value = event.conversationId
      }
      if (event.modelId) {
        connectedModelId.value = event.modelId
      }
      if (event.type === 'error') {
        throw new Error(readStreamError(event))
      }
      if (event.type === 'message.delta' && event.content) {
        enqueueAssistantContent(event.content, 'delta')
      }
      if (event.type === 'done' && event.content) {
        enqueueAssistantContent(event.content, 'final')
      }
    })
    await waitForAssistantReveal()

    if (!receivedContent && !assistantMessage.content.trim()) {
      assistantMessage.content = '本轮没有返回可展示内容，请稍后重试。'
      await assistantPanelRef.value?.followOutput()
    }
  } catch (error) {
    if (isAbortError(error)) return
    assistantRevealCanceled = true
    assistantRevealQueue = []
    assistantMessage.content = `对话失败：${getErrorMessage(error)}`
    ElMessage.error(assistantMessage.content)
  } finally {
    assistantRevealCanceled = true
    if (chatStreamController === controller) {
      chatStreamController = null
    }
    isSendingChat.value = false
    streamingAssistantMessageId.value = null
    await assistantPanelRef.value?.followOutput()
  }
}

const readStreamError = (event: ScreenwritingStreamEvent) => {
  const detail = event.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  return event.content || 'AI 对话流返回错误'
}

const readFetchError = async (response: Response) => {
  const text = await response.text()
  try {
    const payload = JSON.parse(text)
    if (typeof payload?.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim()
    }
  } catch {
    // 非 JSON 错误响应继续读取纯文本。
  }
  return text.trim() || `请求失败：HTTP ${response.status}`
}

const getErrorMessage = (error: unknown) => {
  if (error instanceof Error) return error.message
  return String(error || '未知错误')
}

const isAbortError = (error: unknown) => (
  error instanceof DOMException && error.name === 'AbortError'
)

const stopChatStream = () => {
  chatStreamController?.abort()
  chatStreamController = null
  isSendingChat.value = false
  streamingAssistantMessageId.value = null
}

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
  conversationId.value = createConversationId()
  nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
})

onBeforeUnmount(() => {
  stopChatStream()
})
</script>

<style scoped>
.screenwriting-page {
  box-sizing: border-box;
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

.workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: clamp(368px, 24vw, 432px) minmax(0, 1fr);
  gap: 8px;
  overflow: hidden;
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

  .workspace {
    grid-template-columns: 1fr;
    overflow-y: auto;
    align-content: start;
  }
}
</style>