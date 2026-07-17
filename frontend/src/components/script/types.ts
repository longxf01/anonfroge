import type { Component } from 'vue'

export type ExtractState = -1 | 0 | 1 | 2
export type AssetType = 'role' | 'faction' | 'prop' | 'scene' | 'lens'

export interface ScriptAsset {
  publicId: string
  name: string
  description: string
  assetType: AssetType
  episodes: string
}

export interface ScriptRecord {
  id: string
  planPublicId: string
  planTitle: string
  episodeIndex: number
  episodeTitle: string
  name: string
  intro: string
  content: string
  extractState: ExtractState
  errorReason: string | null
  relatedAssets: ScriptAsset[]
  isLocked: boolean
  version: number
  createdAt: string
}

export interface ScriptEditForm {
  name: string
  content: string
  relatedAssetIds: string[]
}

export type SortField = 'id' | 'createdAt' | 'name' | 'extractState' | 'assetCount'
export type SortOrder = 'asc' | 'desc'

export interface SortOption {
  value: SortField
  label: string
}

export interface ImportScriptDraft {
  key: number
  name: string
  detail: string
  content: string
}

export interface ImportSplitPreset {
  key: string
  label: string
  description: string
  titlePattern: string
  titleFlagsList: string[]
}

export interface PreviewEditDraft {
  name: string
  content: string
  detail: string
}

export interface SidebarNavItem {
  key: string
  label: string
  icon: Component
}
