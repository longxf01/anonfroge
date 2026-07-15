import request from '@/request'

export interface ScreenwritingPreflightCheck {
  key: string
  label: string
  passed: boolean
  detail: string
}

export interface ScreenwritingPreflightResult {
  ready: boolean
  requiredEventCount: number
  eventReadyCount: number
  textModel: string
  checks: ScreenwritingPreflightCheck[]
}

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
  clientRequestStartedAtMs?: number
}

export type ScreenwritingRagWarmupApiStatus = 'started' | 'running' | 'ready'

export interface ScreenwritingRagWarmupResponse {
  status: ScreenwritingRagWarmupApiStatus
  ragIsolationKey: string
}

export interface ScreenwritingRagRuntimeMetadata {
  assetsReady?: boolean
  vectorReady?: boolean
  retrievalMode?: string
  retrievalStrategy?: string
  failureReason?: string | null
  hitCount?: number
  minVectorScore?: number
  indexCacheHit?: boolean
  [key: string]: unknown
}

export interface ScreenwritingRagHit {
  sourceId: string
  sourceType: string
  title: string
  score: number
}

export interface ScreenwritingRagPayload {
  runtime: ScreenwritingRagRuntimeMetadata
  hitCount: number
  documentCount: number
  hits: ScreenwritingRagHit[]
}

export interface ScreenwritingServerTimingStage {
  name: string
  durationMs: number
  startedAtMs?: number
  endedAtMs?: number
}

export interface ScreenwritingServerTimings {
  totalMs: number
  clientToServerMs?: number | null
  stages: ScreenwritingServerTimingStage[]
}

export interface ScreenwritingChatRuntime {
  agent?: string
  conversation?: string
  rag?: ScreenwritingRagPayload
  thinkingElapsedMs?: number
  serverTimings?: ScreenwritingServerTimings
  [key: string]: unknown
}

export interface ScreenwritingChatResponse {
  conversationId: string
  isolationKey: string
  modelId: string
  activeTab: ScreenwritingActiveTab
  content: string
  messages: ScreenwritingChatTurn[]
  runtime: ScreenwritingChatRuntime
}

export interface ScreenwritingStreamEventData {
  rag?: ScreenwritingRagPayload
  detail?: string
  errorType?: string
  thinkingElapsedMs?: number
  serverTimings?: ScreenwritingServerTimings
  assistantMessage?: string
  messages?: ScreenwritingChatTurn[]
  [key: string]: unknown
}

export interface ScreenwritingStreamEvent {
  type: string
  content: string
  conversationId: string
  isolationKey: string
  modelId: string
  activeTab: ScreenwritingActiveTab
  data?: ScreenwritingStreamEventData
}

export const getScreenwritingPreflightApi = (
  projectPublicId: string,
) => (
  request.get<ScreenwritingPreflightResult>(
    `${projectScreenwritingPath(projectPublicId)}/preflight`,
  )
)

export const warmupScreenwritingRagIndexApi = (
  projectPublicId: string,
) => (
  request.post<ScreenwritingRagWarmupResponse>(
    `${projectScreenwritingPath(projectPublicId)}/rag/warmup`,
  )
)

export const chatScreenwritingApi = (
  projectPublicId: string,
  payload: ScreenwritingChatPayload,
) => (
  request.post<ScreenwritingChatResponse>(
    `${projectScreenwritingPath(projectPublicId)}/chat`,
    payload,
    { timeout: 300000 },
  )
)

export const chatScreenwritingStreamUrl = (projectPublicId: string) => (
  `/api${projectScreenwritingPath(projectPublicId)}/chat/stream`
)

const projectScreenwritingPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/novels/screenwriting`
)
