import type { Component } from 'vue'
import type { ScreenwritingActiveTab, ScreenwritingRagPayload, ScreenwritingServerTimings } from '@/api/screenwriting'

export interface ChatMessage {
  id: number
  role: 'assistant' | 'user'
  content: string
  time: string
  rag?: ScreenwritingRagPayload
  thinkingElapsedMs?: number
  serverTimings?: ScreenwritingServerTimings
}

export type ScreenwritingRagWarmupStatus = 'idle' | 'starting' | 'running' | 'ready' | 'failed'

export interface ScreenwritingRagWarmupViewState {
  status: ScreenwritingRagWarmupStatus
  label: string
  detail?: string
}

export interface ScreenwritingTab {
  name: ScreenwritingActiveTab
  label: string
  icon: Component
  desc: string
  action: string
  title: string
  hint: string
  starter: string
}
