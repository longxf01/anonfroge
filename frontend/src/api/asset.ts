import request from '@/request'
import { toTaskJob, type BackendTaskJobDetail, type TaskJobResponse } from '@/api/task'

export type AssetType = 'role' | 'faction' | 'prop' | 'scene' | 'lens'

export interface AssetItem {
  publicId: string
  assetType: AssetType
  name: string
  summary: string
  description: string
  status: 'draft' | 'locked'
  createdAt: string
  updatedAt: string
}

export interface AssetExtractPayload {
  modelId: string
  episodePublicIds?: string[]
}

export interface AssetAssociationPayload {
  episodePublicId: string
  assetPublicIds: string[]
}

export interface AssetAssociationResult {
  affected: number
  assets: AssetItem[]
}

const projectAssetPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/assets`
)

// 资产抽取只提交异步任务，真正的模型调用由 Worker 执行。
export const extractAssetsApi = (
  projectPublicId: string,
  payload: AssetExtractPayload,
) => (
  request
    .post<BackendTaskJobDetail>(`${projectAssetPath(projectPublicId)}/extract`, payload)
    .then((response) => ({
      ...response,
      data: toTaskJob(response.data, projectPublicId, response.data.items),
    } as typeof response & { data: TaskJobResponse }))
)

export const listAssetsApi = (projectPublicId: string, assetType = '') => {
  const params = assetType ? { assetType } : undefined
  return request.get<AssetItem[]>(projectAssetPath(projectPublicId), params ? { params } : undefined)
}

export const setEpisodeAssetsApi = (
  projectPublicId: string,
  payload: AssetAssociationPayload,
) => request.post<AssetAssociationResult>(`${projectAssetPath(projectPublicId)}/associations`, payload)