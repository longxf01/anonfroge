import request from '@/request'

export type EventState = -1 | 0 | 1

export interface NovelChapterRecord {
  id: number
  publicId: string
  projectId: number
  chapterIndex: number
  reel: string
  chapter: string
  chapterData: string
  event: string
  eventState: EventState
  errorReason: string | null
  crawlSourceKey: string
  crawlNovelDirid: string
  crawlChapterId: number | null
  crawlTime: string
  crawlMd5: string
  sortOrder: number
  createdAt: string
  updatedAt: string
  disabledAt: string | null
}

export interface NovelChapterPage {
  data: NovelChapterRecord[]
  total: number
  page: number
  limit: number
}

export interface NovelChapterListParams {
  page: number
  limit: number
  search?: string
}

export interface NovelChapterPayload {
  chapterIndex: number
  reel: string
  chapter: string
  chapterData: string
  event?: string
}

export interface NovelChapterBatchPayload {
  ids: number[]
}

export interface NovelChapterBatchResult {
  affected: number
}

export interface NovelChapterImportPayload {
  rawText: string
}

export const listNovelChaptersApi = (
  projectPublicId: string,
  params: NovelChapterListParams,
) => (
  request.get<NovelChapterPage>(`${projectNovelPath(projectPublicId)}`, { params })
)

export const createNovelChapterApi = (
  projectPublicId: string,
  payload: NovelChapterPayload,
) => (
  request.post<NovelChapterRecord>(`${projectNovelPath(projectPublicId)}`, payload)
)

export const importNovelChaptersApi = (
  projectPublicId: string,
  payload: NovelChapterImportPayload,
) => (
  request.post<NovelChapterRecord[]>(`${projectNovelPath(projectPublicId)}/import`, payload, { timeout: 120000 })
)

export const updateNovelChapterApi = (
  projectPublicId: string,
  chapterId: number,
  payload: Partial<NovelChapterPayload>,
) => (
  request.put<NovelChapterRecord>(`${projectNovelPath(projectPublicId)}/${chapterId}`, payload)
)

export const deleteNovelChapterApi = (
  projectPublicId: string,
  chapterId: number,
) => (
  request.delete<void>(`${projectNovelPath(projectPublicId)}/${chapterId}`)
)

export const batchDeleteNovelChaptersApi = (
  projectPublicId: string,
  payload: NovelChapterBatchPayload,
) => (
  request.post<NovelChapterBatchResult>(`${projectNovelPath(projectPublicId)}/batch-delete`, payload)
)

export const cleanNovelChapterApi = (
  projectPublicId: string,
  chapterId: number,
) => (
  request.post<NovelChapterRecord>(`${projectNovelPath(projectPublicId)}/${chapterId}/clean`, undefined, { timeout: 120000 })
)

export const batchCleanNovelChaptersApi = (
  projectPublicId: string,
  payload: NovelChapterBatchPayload,
) => (
  request.post<NovelChapterBatchResult>(`${projectNovelPath(projectPublicId)}/batch-clean`, payload, { timeout: 120000 })
)

const projectNovelPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/novels`
)