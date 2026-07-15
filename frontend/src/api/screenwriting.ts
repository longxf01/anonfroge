import request from '@/request'


export type ScreenwritingActiveTab = 'skeleton' | 'strategy' | 'script'

export interface ScreenwritingChatTurn {
  role: 'user' | 'assistant'
  content: string
  time: string
}

export interface ScreenwritingChatPayload {
  message: string
  conversationId: string
  activeTab: ScreenwritingActiveTab
  messages: ScreenwritingChatTurn[]
  reset?: boolean
}

export interface ScreenwritingChatResponse {
  conversationId: string
  isolationKey: string
  modelId: string
  activeTab: ScreenwritingActiveTab
  content: string
  messages: ScreenwritingChatTurn[]
  runtime: Record<string, unknown>
}

export interface ScreenwritingStreamEvent {
  type: string
  content: string
  conversationId: string
  isolationKey: string
  modelId: string
  activeTab: ScreenwritingActiveTab
  data?: Record<string, unknown>
}

const projectNovelPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/novels`
)

export const chatScreenwritingApi = (
  projectPublicId: string,
  payload: ScreenwritingChatPayload,
) => (
  request.post<ScreenwritingChatResponse>(
    `${projectNovelPath(projectPublicId)}/screenwriting/chat`,
    payload,
    { timeout: 300000 },
  )
)

export const chatScreenwritingStreamUrl = (projectPublicId: string) => (
  `/api${projectNovelPath(projectPublicId)}/screenwriting/chat/stream`
)