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
            :rag-warmup="ragWarmup"
            @send="sendChatMessage"
            @new-conversation="startNewConversation"
            @open-history="historyDialogVisible = true"
            @insert-stage-prompt="insertStagePrompt"
            @quote-events="showComingSoon"
            @clear-composer="clearComposer"
          />

          <ScreenwritingStageTabs
            ref="stageTabsRef"
            v-model:active-tab="activeTab"
            :tabs="screenwritingTabs"
            :workspace="workspace"
            :saving="isSavingWorkspace"
            @start="startWithPrompt"
            @save="saveWorkspace"
          />
        </section>
      </section>
    </div>

    <ScreenwritingHistoryDialog
      v-model="historyDialogVisible"
      :history-entries="historyEntries"
      :tab-label="screenwritingTabLabel"
      :restoring="isRestoringHistory"
      :deleting-history-id="deletingHistoryId"
      :busy="isSendingChat || isResettingConversation"
      @restore="restoreHistory"
      @delete-history="deleteHistory"
    />

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { AxiosError } from 'axios'
import {
  Document,
  MagicStick,
  Tickets,
} from '@element-plus/icons-vue'
import {
  chatScreenwritingStreamUrl,
  deleteScreenwritingHistoryApi,
  getScreenwritingStateApi,
  resetScreenwritingStateApi,
  restoreScreenwritingHistoryApi,
  updateScreenwritingWorkspaceApi,
  warmupScreenwritingRagIndexApi,
  type ScreenwritingActiveTab,
  type ScreenwritingHistoryEntry,
  type ScreenwritingState,
  type ScreenwritingStreamEvent,
  type ScreenwritingWorkspace,
} from '@/api/screenwriting'
import { fetchWithAuthRetry } from '@/request'
import { readNdjsonStream } from '@/utils/ndjsonStream'
import ScreenwritingAssistantPanel from '@/components/screenwriting/ScreenwritingAssistantPanel.vue'
import ScreenwritingHistoryDialog from '@/components/screenwriting/ScreenwritingHistoryDialog.vue'
import ScreenwritingPageHeader from '@/components/screenwriting/ScreenwritingPageHeader.vue'
import ScreenwritingSidebar from '@/components/screenwriting/ScreenwritingSidebar.vue'
import ScreenwritingStageTabs from '@/components/screenwriting/ScreenwritingStageTabs.vue'
import type { AgentActionEntry, ChatMessage, ScreenwritingRagWarmupViewState, ScreenwritingTab } from '@/components/screenwriting/types'
import Settings from '../components/Settings.vue'

interface AssistantPanelExpose {
  focusComposer: () => void
  followOutput: () => Promise<void>
  resetAutoScroll: () => void
  scrollToBottom: (behavior?: ScrollBehavior) => void
}

interface StageTabsExpose {
  finishEdit: () => void
  scrollTabToBottom: (tab: ScreenwritingActiveTab) => void
}

const router = useRouter()
const route = useRoute()

const projectPublicId = ref('')
const settingsVisible = ref(false)
const activeTab = ref<ScreenwritingActiveTab>('skeleton')

const chatInput = ref('')
const assistantPanelRef = ref<AssistantPanelExpose | null>(null)
const stageTabsRef = ref<StageTabsExpose | null>(null)
const isSendingChat = ref(false)
const isSavingWorkspace = ref(false)
const isResettingConversation = ref(false)
const conversationId = ref('')
const connectedModelId = ref('')
const streamingAssistantMessageId = ref<number | null>(null)
const ragWarmup = ref<ScreenwritingRagWarmupViewState>({ status: 'idle', label: '' })
const workspace = ref<ScreenwritingWorkspace>({ skeleton: '', strategy: '', script: '' })
const historyEntries = ref<ScreenwritingHistoryEntry[]>([])
const historyDialogVisible = ref(false)
const isRestoringHistory = ref(false)
const deletingHistoryId = ref('')
let chatSeq = 2
let chatStreamController: AbortController | null = null
let ragWarmupPollTimer: number | null = null

const ASSISTANT_REVEAL_CHUNK_SIZE = 1
const ASSISTANT_REVEAL_INTERVAL_MS = 18
const RAG_WARMUP_POLL_INTERVAL_MS = 1400

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

const applyServerState = (state: ScreenwritingState) => {
  conversationId.value = state.conversationId
  if (state.modelId) {
    connectedModelId.value = state.modelId
  }
  activeTab.value = state.activeTab
  workspace.value = { ...state.workspace }
  historyEntries.value = [...state.history]
  const messages = state.messages.filter((turn) => turn.content.trim())
  chatSeq = 1
  chatMessages.value = messages.length
    ? messages.map((turn) => ({
        id: chatSeq++,
        role: turn.role,
        content: turn.content,
        time: turn.time,
      }))
    : [
        {
          id: chatSeq++,
          role: 'assistant',
          content: ASSISTANT_GREETING,
          time: formatChatTime(),
        },
      ]
}

const loadScreenwritingState = async () => {
  if (!projectPublicId.value) return
  try {
    const { data: state } = await getScreenwritingStateApi(projectPublicId.value)
    applyServerState(state)
    nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
  } catch (error) {
    ElMessage.error(`加载创作会话失败：${getErrorMessage(error)}`)
  }
}

const startNewConversation = async () => {
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  if (isResettingConversation.value) return
  stopChatStream()
  isResettingConversation.value = true
  try {
    const { data: state } = await resetScreenwritingStateApi(projectPublicId.value)
    assistantPanelRef.value?.resetAutoScroll()
    applyServerState(state)
    chatInput.value = ''
    nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
    ElMessage.success('已开始新的对话')
  } catch (error) {
    ElMessage.error(`开始新对话失败：${getErrorMessage(error)}`)
  } finally {
    isResettingConversation.value = false
  }
}

const screenwritingTabLabel = (tab: ScreenwritingActiveTab) =>
  screenwritingTabs.find((item) => item.name === tab)?.label ?? '故事骨架'

const restoreHistory = async (historyId: string) => {
  if (!projectPublicId.value || isRestoringHistory.value) return
  isRestoringHistory.value = true
  try {
    const { data: state } = await restoreScreenwritingHistoryApi(projectPublicId.value, historyId)
    assistantPanelRef.value?.resetAutoScroll()
    applyServerState(state)
    historyDialogVisible.value = false
    nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
    ElMessage.success('已恢复创作历史')
  } catch (error) {
    ElMessage.error(`恢复创作历史失败：${getErrorMessage(error)}`)
  } finally {
    isRestoringHistory.value = false
  }
}

const deleteHistory = async (historyId: string) => {
  if (!projectPublicId.value || deletingHistoryId.value) return
  deletingHistoryId.value = historyId
  try {
    const { data: state } = await deleteScreenwritingHistoryApi(projectPublicId.value, historyId)
    historyEntries.value = [...state.history]
    ElMessage.success('已删除创作历史')
  } catch (error) {
    ElMessage.error(`删除创作历史失败：${getErrorMessage(error)}`)
  } finally {
    deletingHistoryId.value = ''
  }
}

const saveWorkspace = async (tab: ScreenwritingActiveTab, content: string) => {
  if (!projectPublicId.value) {
    ElMessage.warning('项目信息尚未加载完成，请稍候再试')
    return
  }
  if (isSavingWorkspace.value) return
  isSavingWorkspace.value = true
  try {
    const { data: state } = await updateScreenwritingWorkspaceApi(projectPublicId.value, {
      activeTab: tab,
      content,
    })
    workspace.value = { ...state.workspace }
    activeTab.value = state.activeTab
    stageTabsRef.value?.finishEdit()
    ElMessage.success('工作区内容已保存')
  } catch (error) {
    ElMessage.error(`保存工作区失败：${getErrorMessage(error)}`)
  } finally {
    isSavingWorkspace.value = false
  }
}

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

const readAssistantFinalContent = (event: ScreenwritingStreamEvent) => {
  if (event.content?.trim()) return event.content
  const assistantMessage = event.data?.assistantMessage
  if (typeof assistantMessage === 'string' && assistantMessage.trim()) {
    return assistantMessage
  }
  const messages = event.data?.messages
  if (Array.isArray(messages)) {
    const finalAssistantMessage = [...messages]
      .reverse()
      .find((message) => message.role === 'assistant' && message.content.trim())
    return finalAssistantMessage?.content ?? ''
  }
  return ''
}

const normalizeWorkspaceTab = (value: unknown): ScreenwritingActiveTab | null => {
  const tab = String(value ?? '').trim()
  return tab === 'skeleton' || tab === 'strategy' || tab === 'script'
    ? (tab as ScreenwritingActiveTab)
    : null
}

const readWorkspacePayload = (value: unknown): ScreenwritingWorkspace | null => {
  if (!isRecord(value)) return null
  return {
    skeleton: String(value.skeleton ?? ''),
    strategy: String(value.strategy ?? ''),
    script: String(value.script ?? ''),
  }
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

  const thinkingStartedAt = performance.now()
  const clientRequestStartedAtMs = Date.now()
  assistantPanelRef.value?.resetAutoScroll()
  chatMessages.value.push({
    id: chatSeq++,
    role: 'user',
    content,
    time: formatChatTime(),
  })
  chatInput.value = ''

  const assistantMessageId = chatSeq++
  chatMessages.value.push({
    id: assistantMessageId,
    role: 'assistant',
    content: '',
    time: formatChatTime(),
    thinkingElapsedMs: 0,
  })
  const getAssistantMessage = () => (
    chatMessages.value.find((message) => message.id === assistantMessageId)
  )
  const updateAssistantMessage = (updater: (message: ChatMessage) => void) => {
    const message = getAssistantMessage()
    if (message) updater(message)
  }
  streamingAssistantMessageId.value = assistantMessageId
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

  const updateThinkingElapsed = (serverElapsedMs?: number) => {
    const localElapsedMs = Math.max(0, Math.floor(performance.now() - thinkingStartedAt))
    const normalizedServerElapsedMs = Number.isFinite(serverElapsedMs)
      ? Math.max(0, Math.floor(serverElapsedMs ?? 0))
      : 0
    updateAssistantMessage((message) => {
      message.thinkingElapsedMs = Math.max(
        message.thinkingElapsedMs ?? 0,
        localElapsedMs,
        normalizedServerElapsedMs,
      )
    })
  }

  const thinkingTimer = window.setInterval(() => {
    updateThinkingElapsed()
  }, 250)

  const revealQueuedAssistantContent = async () => {
    while (!assistantRevealCanceled && !controller.signal.aborted && assistantRevealQueue.length) {
      const chunk = assistantRevealQueue.splice(0, ASSISTANT_REVEAL_CHUNK_SIZE).join('')
      updateAssistantMessage((message) => {
        message.content += chunk
      })
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
        activeTab: activeTab.value,
        message: content,
        clientRequestStartedAtMs,
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
      updateThinkingElapsed(event.data?.thinkingElapsedMs)
      if (event.conversationId) {
        conversationId.value = event.conversationId
      }
      if (event.modelId) {
        connectedModelId.value = event.modelId
      }
      if (event.data?.rag) {
        updateAssistantMessage((message) => {
          message.rag = event.data?.rag
        })
      }
      if (event.data?.serverTimings) {
        updateAssistantMessage((message) => {
          message.serverTimings = event.data?.serverTimings
        })
      }
      if (event.type === 'error') {
        throw new Error(readStreamError(event))
      }
      if (event.type === 'agent.action') {
        const entry: AgentActionEntry = {
          phase: String(event.data?.phase ?? ''),
          message: String(event.data?.message ?? ''),
          detail: typeof event.data?.detail === 'string' ? event.data.detail : undefined,
          targetTab: typeof event.data?.targetTab === 'string' ? event.data.targetTab : undefined,
        }
        if (entry.message) {
          updateAssistantMessage((message) => {
            message.actions = [...(message.actions ?? []), entry]
          })
          await assistantPanelRef.value?.followOutput()
        }
        return
      }
      if (event.type === 'workspace.delta') {
        const targetTab = normalizeWorkspaceTab(event.data?.targetTab)
        if (targetTab) {
          const fullWorkspace = readWorkspacePayload(event.data?.workspace)
          if (fullWorkspace) {
            workspace.value = fullWorkspace
          } else {
            workspace.value = {
              ...workspace.value,
              [targetTab]: String(event.data?.workspaceContent ?? ''),
            }
          }
          if (activeTab.value !== targetTab) {
            activeTab.value = targetTab
          }
          stageTabsRef.value?.scrollTabToBottom(targetTab)
        }
        return
      }
      if (event.type === 'message.delta' && event.content) {
        enqueueAssistantContent(event.content, 'delta')
      }
      if (event.type === 'done') {
        const doneWorkspace = readWorkspacePayload(event.data?.workspace)
        if (doneWorkspace) {
          workspace.value = doneWorkspace
        }
        const doneStage = normalizeWorkspaceTab(event.data?.stage)
        if (doneStage) {
          activeTab.value = doneStage
        }
        const finalContent = readAssistantFinalContent(event)
        if (finalContent) {
          enqueueAssistantContent(finalContent, 'final')
        }
      }
    })
    await waitForAssistantReveal()

    if (!receivedContent && !getAssistantMessage()?.content.trim()) {
      updateAssistantMessage((message) => {
        message.content = '本轮没有返回可展示内容，请稍后重试。'
      })
      await assistantPanelRef.value?.followOutput()
    }
  } catch (error) {
    if (isAbortError(error)) return
    assistantRevealCanceled = true
    assistantRevealQueue = []
    const errorMessage = `对话失败：${getErrorMessage(error)}`
    updateAssistantMessage((message) => {
      message.content = errorMessage
    })
    ElMessage.error(errorMessage)
  } finally {
    window.clearInterval(thinkingTimer)
    updateThinkingElapsed()
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
  const axiosError = isRecord(error) ? (error as unknown as AxiosError<{ detail?: unknown; message?: unknown }>) : null
  const responseMessage =
    formatErrorDetail(axiosError?.response?.data?.detail) ||
    formatErrorDetail(axiosError?.response?.data?.message)
  if (responseMessage) return responseMessage
  if (axiosError?.response?.status) {
    const statusText = axiosError.response.statusText ? ` ${axiosError.response.statusText}` : ''
    return `请求失败：HTTP ${axiosError.response.status}${statusText}`
  }
  if (axiosError?.code === 'ECONNABORTED') return '请求超时'
  if (error instanceof Error) return error.message
  return formatErrorDetail(error) || '未知错误'
}

const formatErrorDetail = (detail: unknown): string => {
  if (!detail) return ''
  if (typeof detail === 'string') return detail.trim()
  if (Array.isArray(detail)) {
    return detail.map(formatErrorDetail).filter(Boolean).join('；')
  }
  if (isRecord(detail)) {
    const message =
      formatErrorDetail(detail.msg) ||
      formatErrorDetail(detail.message) ||
      formatErrorDetail(detail.detail)
    const location = Array.isArray(detail.loc) ? detail.loc.map(String).join('.') : ''
    if (message) return location ? `${location}: ${message}` : message
    try {
      return JSON.stringify(detail)
    } catch {
      return String(detail)
    }
  }
  return String(detail)
}

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null
)

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

const clearRagWarmupPoll = () => {
  if (ragWarmupPollTimer === null) return
  window.clearTimeout(ragWarmupPollTimer)
  ragWarmupPollTimer = null
}

const scheduleRagWarmupPoll = () => {
  clearRagWarmupPoll()
  ragWarmupPollTimer = window.setTimeout(() => {
    void warmupRagIndex({ silent: true })
  }, RAG_WARMUP_POLL_INTERVAL_MS)
}

const warmupRagIndex = async (options: { silent?: boolean } = {}) => {
  if (!projectPublicId.value) return
  if (!options.silent) {
    clearRagWarmupPoll()
    ragWarmup.value = {
      status: 'starting',
      label: '正在启动资料索引预热',
      detail: '首次进入当前项目时开始构建 RAG 检索索引。',
    }
  }
  try {
    const { data: result } = await warmupScreenwritingRagIndexApi(projectPublicId.value)
    if (result.status === 'ready') {
      clearRagWarmupPoll()
      ragWarmup.value = {
        status: 'ready',
        label: '资料索引预热完成',
        detail: '现在可以使用章节、项目与小说资料进行检索。',
      }
      return
    }
    ragWarmup.value = {
      status: 'running',
      label: result.status === 'started' ? '资料索引预热已开始' : '资料索引预热进行中',
      detail: result.status === 'running'
        ? '同项目已有构建任务在运行，正在等待完成。'
        : '正在异步构建当前项目的向量索引。',
    }
    scheduleRagWarmupPoll()
  } catch (error) {
    clearRagWarmupPoll()
    const errorMessage = getErrorMessage(error)
    ragWarmup.value = {
      status: 'failed',
      label: '资料索引预热失败',
      detail: `错误：${errorMessage}。仍可继续对话，系统会在问答时尝试检索。`,
    }
    console.warn('Screenwriting RAG warmup failed', {
      projectPublicId: projectPublicId.value,
      errorMessage,
      error,
    })
  }
}

onMounted(() => {
  projectPublicId.value = resolveProjectPublicId()
  void loadScreenwritingState()
  void warmupRagIndex()
  nextTick(() => assistantPanelRef.value?.scrollToBottom('auto'))
})

onBeforeUnmount(() => {
  clearRagWarmupPoll()
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