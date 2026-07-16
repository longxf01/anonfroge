import request from '@/request'

export interface ScriptScene {
  number: string
  title: string
  location: string
  dayNight: string
  interiorExterior: string
}

export interface ScriptEpisode {
  publicId: string
  episodeIndex: number
  title: string
  summary: string
  body: string
  scenes: ScriptScene[]
  version: number
  isLocked: boolean
}

export interface ScriptPlanSummary {
  publicId: string
  title: string
  totalEpisodes: string
  episodeDuration: string
  status: string
  updatedAt: string
}

export interface ScriptPlanDetail extends ScriptPlanSummary {
  sourceRange: string
  platformSpec: string
  style: string
  paywall: string
  episodes: ScriptEpisode[]
}

const projectScriptPath = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/scripts`
)

export const listScriptPlansApi = (projectPublicId: string) => (
  request.get<ScriptPlanSummary[]>(`${projectScriptPath(projectPublicId)}/plans`)
)

export const getScriptPlanApi = (projectPublicId: string, planPublicId: string) => (
  request.get<ScriptPlanDetail>(
    `${projectScriptPath(projectPublicId)}/plans/${encodeURIComponent(planPublicId)}`,
  )
)

export const syncScriptPlanApi = (projectPublicId: string, title = '') => (
  request.post<ScriptPlanDetail>(
    `${projectScriptPath(projectPublicId)}/sync`,
    { title },
    { timeout: 60000 },
  )
)