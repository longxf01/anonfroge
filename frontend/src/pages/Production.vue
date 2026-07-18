<template>
  <main class="production-page">
    <aside class="sidebar">
      <div class="side-top">
        <div class="brand" @click="goProject">AF</div>
        <el-tooltip content="项目" placement="right">
          <button class="nav-btn" aria-label="项目" @click="goProject">
            <el-icon><Folder /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="剧本" placement="right">
          <button class="nav-btn" aria-label="剧本" @click="goScript">
            <el-icon><Document /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="制作" placement="right">
          <button class="nav-btn active" aria-label="制作">
            <el-icon><Film /></el-icon>
          </button>
        </el-tooltip>
      </div>
      <div class="side-bottom">
        <el-tooltip content="任务" placement="right">
          <button class="nav-btn" aria-label="任务" @click="goTasks(activeJobId)">
            <el-icon><List /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="设置" placement="right">
          <button class="nav-btn" aria-label="设置" @click="settingsVisible = true">
            <el-icon><Setting /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </aside>

    <section class="production-shell">
      <header class="page-header">
        <div class="page-title">
          <h1>制作工作台</h1>
          <p>{{ currentProject?.name || '正在加载项目' }} · ProductionAgent 分镜与工作台</p>
        </div>
        <div class="header-actions">
          <el-button class="ghost-button" @click="goScript">
            <el-icon><Back /></el-icon>
            返回剧本
          </el-button>
          <el-button class="ghost-button" :loading="loading" @click="reloadAll">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </header>

      <section class="control-panel">
        <div class="control-grid">
          <label class="field">
            <span>分集</span>
            <el-select
              v-model="selectedEpisodeId"
              class="dark-select"
              popper-class="production-dark-select"
              filterable
              placeholder="选择分集"
              @change="onEpisodeChange"
            >
              <el-option
                v-for="episode in episodes"
                :key="episode.publicId"
                :label="episodeLabel(episode)"
                :value="episode.publicId"
              />
            </el-select>
          </label>

          <label class="field">
            <span>文本模型</span>
            <el-select
              v-model="generateForm.modelId"
              class="dark-select"
              popper-class="production-dark-select production-model-select"
              filterable
              placeholder="选择模型 ID"
            >
              <el-option
                v-for="model in textModels"
                :key="model.model_id"
                :label="model.name || model.model_id"
                :value="model.model_id"
              >
                <span class="model-option">
                  <span>{{ model.name || model.model_id }}</span>
                  <em>{{ model.model_id }}</em>
                </span>
              </el-option>
            </el-select>
          </label>

          <label class="field">
            <span>艺术风格</span>
            <el-select
              v-model="generateForm.artStyle"
              class="dark-select"
              popper-class="production-dark-select"
              filterable
              clearable
              placeholder="项目默认"
            >
              <el-option
                v-for="style in visualStyles"
                :key="style.style_path"
                :label="style.name || style.style_path"
                :value="style.style_path"
              />
            </el-select>
          </label>

          <label class="field">
            <span>导演风格</span>
            <el-select
              v-model="generateForm.directorStyle"
              class="dark-select"
              popper-class="production-dark-select"
              filterable
              clearable
              placeholder="项目默认"
            >
              <el-option
                v-for="manual in directorManuals"
                :key="manual.manual_path"
                :label="manual.name || manual.manual_path"
                :value="manual.manual_path"
              />
            </el-select>
          </label>
        </div>

        <div class="control-actions">
          <div class="task-status" :class="{ active: hasActiveJob }">
            <span class="status-dot"></span>
            <span>{{ activeJobLabel }}</span>
          </div>
          <el-button
            class="primary-button"
            type="primary"
            :disabled="!selectedEpisodeId || !generateForm.modelId"
            :loading="submitting"
            @click="submitGenerate"
          >
            <el-icon><VideoPlay /></el-icon>
            生成分镜
          </el-button>
        </div>
      </section>

      <section class="workbench-grid">
        <aside class="episode-panel panel">
          <div class="panel-head">
            <h2>分集</h2>
            <span>{{ episodes.length }} 集</span>
          </div>
          <div v-loading="episodesLoading" class="episode-list" element-loading-background="rgba(7, 10, 16, 0.7)">
            <button
              v-for="episode in episodes"
              :key="episode.publicId"
              class="episode-item"
              :class="{ active: selectedEpisodeId === episode.publicId }"
              @click="selectEpisode(episode.publicId)"
            >
              <strong>EP{{ pad2(episode.episodeIndex) }}</strong>
              <span>{{ episode.title || '未命名分集' }}</span>
              <em>{{ shotCountByEpisode.get(episode.publicId) || 0 }} 镜</em>
            </button>
            <el-empty v-if="!episodesLoading && episodes.length === 0" description="暂无剧本分集" />
          </div>
        </aside>

        <section class="shot-panel panel">
          <div class="panel-head">
            <h2>分镜表</h2>
            <span>{{ currentShots.length }} 镜 · {{ totalDuration }} 秒</span>
          </div>
          <div v-loading="shotsLoading" class="shot-table-wrap" element-loading-background="rgba(7, 10, 16, 0.7)">
            <el-table
              :data="currentShots"
              class="shot-table"
              height="100%"
              highlight-current-row
              row-key="publicId"
              @row-click="selectShot"
            >
              <el-table-column prop="shotIndex" label="#" width="64" />
              <el-table-column prop="sceneNumber" label="场号" width="90" />
              <el-table-column prop="shotSize" label="景别" width="90" />
              <el-table-column prop="camera" label="机位/运镜" min-width="180" show-overflow-tooltip />
              <el-table-column prop="action" label="画面动作" min-width="280" show-overflow-tooltip />
              <el-table-column prop="durationSeconds" label="秒" width="70" />
              <el-table-column label="状态" width="86">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'locked' ? 'warning' : 'info'" effect="plain">
                    {{ row.status === 'locked' ? '锁定' : '草稿' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!shotsLoading && currentShots.length === 0" description="当前分集暂无分镜" />
          </div>
        </section>

        <aside class="detail-panel panel">
          <div class="panel-head">
            <h2>镜头详情</h2>
            <span>{{ selectedShot ? `#${selectedShot.shotIndex}` : '未选择' }}</span>
          </div>
          <div v-if="selectedShot" class="shot-editor">
            <div class="editor-row two">
              <label>
                <span>场号</span>
                <el-input v-model="editForm.sceneNumber" />
              </label>
              <label>
                <span>时长</span>
                <el-input-number v-model="editForm.durationSeconds" :min="0" :max="600" controls-position="right" />
              </label>
            </div>
            <div class="editor-row two">
              <label>
                <span>景别</span>
                <el-input v-model="editForm.shotSize" />
              </label>
              <label>
                <span>状态</span>
                <el-tag :type="selectedShot.status === 'locked' ? 'warning' : 'info'" effect="plain">
                  {{ selectedShot.status === 'locked' ? '已锁定' : '草稿' }}
                </el-tag>
              </label>
            </div>
            <label>
              <span>机位与运镜</span>
              <el-input v-model="editForm.camera" />
            </label>
            <label>
              <span>画面动作</span>
              <el-input v-model="editForm.action" type="textarea" :rows="5" />
            </label>
            <label>
              <span>对白/旁白</span>
              <el-input v-model="editForm.dialogue" type="textarea" :rows="3" />
            </label>
            <label>
              <span>引用资产</span>
              <el-input v-model="editForm.assetNames" />
            </label>
            <label>
              <span>生图提示词</span>
              <el-input v-model="editForm.prompt" type="textarea" :rows="4" />
            </label>
            <div class="editor-actions">
              <el-button class="ghost-button" :loading="savingShot" :disabled="selectedShot.status === 'locked'" @click="saveShot">
                <el-icon><Check /></el-icon>
                保存
              </el-button>
              <el-button class="ghost-button" :loading="lockingShot" @click="toggleShotLock">
                <el-icon><Lock v-if="selectedShot.status !== 'locked'" /><Unlock v-else /></el-icon>
                {{ selectedShot.status === 'locked' ? '解锁' : '锁定' }}
              </el-button>
              <el-button class="danger-button" :disabled="selectedShot.status === 'locked'" @click="deleteShot">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          <div v-else class="empty-detail">
            <el-icon><Tickets /></el-icon>
            <span>选择镜头后编辑细节</span>
          </div>
        </aside>
      </section>
    </section>

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Back,
  Check,
  Delete,
  Document,
  Film,
  Folder,
  List,
  Lock,
  Refresh,
  Setting,
  Tickets,
  Unlock,
  VideoPlay,
} from '@element-plus/icons-vue'
import { listProjectEpisodesApi, type ScriptEpisodeListItem } from '@/api/script'
import {
  deleteStoryboardShotApi,
  generateStoryboardsApi,
  listStoryboardShotsApi,
  lockStoryboardShotApi,
  unlockStoryboardShotApi,
  updateStoryboardShotApi,
  type StoryboardShot,
  type StoryboardShotUpdatePayload,
} from '@/api/storyboard'
import { getTaskJobApi, type TaskJobResponse, type TaskJobStatus } from '@/api/task'
import {
  listDirectorManualsApi,
  listProjectsApi,
  listVisualStylesApi,
  type DirectorManualRecord,
  type ProjectRecord,
  type VisualStyleRecord,
} from '@/api/project'
import { listProvidersApi, type ProviderModel } from '@/api/modelProvider'
import Settings from '@/components/Settings.vue'

const ACTIVE_JOB_STATUSES: TaskJobStatus[] = ['pending', 'running', 'paused']
const POLL_ACTIVE_INTERVAL_MS = 2500

const router = useRouter()
const route = useRoute()

const resolveQueryString = (value: unknown) => {
  if (Array.isArray(value)) return String(value[0] ?? '')
  return typeof value === 'string' ? value : ''
}

const projectPublicId = ref(
  (resolveQueryString(route.query.id) || resolveQueryString(route.query.projectId)).trim(),
)
const currentProject = ref<ProjectRecord | null>(null)
const settingsVisible = ref(false)
const loading = ref(false)
const episodesLoading = ref(false)
const shotsLoading = ref(false)
const submitting = ref(false)
const savingShot = ref(false)
const lockingShot = ref(false)

const episodes = ref<ScriptEpisodeListItem[]>([])
const shots = ref<StoryboardShot[]>([])
const visualStyles = ref<VisualStyleRecord[]>([])
const directorManuals = ref<DirectorManualRecord[]>([])
const textModels = ref<ProviderModel[]>([])
const selectedEpisodeId = ref('')
const selectedShotId = ref('')
const activeJob = ref<TaskJobResponse | null>(null)
const activeJobTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const generateForm = reactive({
  modelId: '',
  artStyle: '',
  directorStyle: '',
})

const editForm = reactive({
  sceneNumber: '',
  shotSize: '',
  camera: '',
  action: '',
  dialogue: '',
  durationSeconds: 0,
  assetPublicIds: '',
  assetNames: '',
  prompt: '',
  negativePrompt: '',
})

const currentShots = computed(() =>
  shots.value
    .filter((shot) => !selectedEpisodeId.value || shot.episodePublicId === selectedEpisodeId.value)
    .sort((a, b) => a.shotIndex - b.shotIndex),
)

const selectedShot = computed(() =>
  currentShots.value.find((shot) => shot.publicId === selectedShotId.value) ?? null,
)

const totalDuration = computed(() =>
  currentShots.value.reduce((sum, shot) => sum + (Number(shot.durationSeconds) || 0), 0),
)

const shotCountByEpisode = computed(() => {
  const counts = new Map<string, number>()
  for (const shot of shots.value) {
    counts.set(shot.episodePublicId, (counts.get(shot.episodePublicId) || 0) + 1)
  }
  return counts
})

const hasActiveJob = computed(() =>
  Boolean(activeJob.value && ACTIVE_JOB_STATUSES.includes(activeJob.value.status)),
)

const activeJobId = computed(() => activeJob.value?.publicId || '')

const activeJobLabel = computed(() => {
  const job = activeJob.value
  if (!job) return '暂无分镜任务'
  const done = job.succeededCount + job.failedCount + job.canceledCount
  if (ACTIVE_JOB_STATUSES.includes(job.status)) return `生成中 ${done}/${job.totalCount}`
  if (job.status === 'succeeded') return `已完成 ${job.succeededCount}/${job.totalCount}`
  if (job.status === 'partial_failed') return `部分失败 ${job.failedCount}/${job.totalCount}`
  if (job.status === 'failed') return '生成失败'
  return job.name
})

const pad2 = (value: number) => String(value).padStart(2, '0')

const episodeLabel = (episode: ScriptEpisodeListItem) =>
  `EP${pad2(episode.episodeIndex)} ${episode.title || '未命名分集'}`

const errorDetail = (error: unknown, fallback: string) => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) return detail.map((item) => String((item as { msg?: string }).msg || '')).filter(Boolean).join('；') || fallback
  if (error instanceof Error && error.message) return error.message
  return fallback
}

const applyProjectDefaults = () => {
  const project = currentProject.value
  if (!project) return
  if (!generateForm.modelId) generateForm.modelId = project.text_model || ''
  if (!generateForm.artStyle) generateForm.artStyle = project.art_style || ''
  if (!generateForm.directorStyle) generateForm.directorStyle = project.director_manual || ''
}

const loadProject = async () => {
  const { data } = await listProjectsApi()
  currentProject.value = data.find((item) => item.public_id === projectPublicId.value) ?? null
  applyProjectDefaults()
}

const loadStyles = async () => {
  const [styleResult, directorResult] = await Promise.all([
    listVisualStylesApi(),
    listDirectorManualsApi(),
  ])
  visualStyles.value = styleResult.data
  directorManuals.value = directorResult.data
}

const loadModels = async () => {
  const { data } = await listProvidersApi()
  textModels.value = data
    .filter((provider) => provider.enabled)
    .flatMap((provider) => provider.models.filter((model) => model.model_type === 'text'))
  if (!generateForm.modelId && textModels.value.length > 0) {
    generateForm.modelId = textModels.value[0].model_id
  }
}

const loadEpisodes = async () => {
  if (!projectPublicId.value) return
  episodesLoading.value = true
  try {
    const { data } = await listProjectEpisodesApi(projectPublicId.value)
    episodes.value = data
    if (!selectedEpisodeId.value && data.length > 0) {
      selectedEpisodeId.value = data[0].publicId
    }
  } finally {
    episodesLoading.value = false
  }
}

const loadShots = async () => {
  if (!projectPublicId.value) return
  shotsLoading.value = true
  try {
    const { data } = await listStoryboardShotsApi(projectPublicId.value)
    shots.value = data
    if (selectedShotId.value && !data.some((shot) => shot.publicId === selectedShotId.value)) {
      selectedShotId.value = ''
    }
    if (!selectedShotId.value && currentShots.value.length > 0) {
      selectedShotId.value = currentShots.value[0].publicId
    }
  } finally {
    shotsLoading.value = false
  }
}

const reloadAll = async () => {
  loading.value = true
  try {
    await Promise.all([loadProject(), loadStyles(), loadModels(), loadEpisodes()])
    await loadShots()
  } catch (error) {
    ElMessage.error(errorDetail(error, '加载制作工作台失败'))
  } finally {
    loading.value = false
  }
}

const selectEpisode = async (episodeId: string) => {
  selectedEpisodeId.value = episodeId
  selectedShotId.value = ''
  if (currentShots.value.length > 0) {
    selectedShotId.value = currentShots.value[0].publicId
  }
}

const onEpisodeChange = () => {
  void selectEpisode(selectedEpisodeId.value)
}

const selectShot = (shot: StoryboardShot) => {
  selectedShotId.value = shot.publicId
}

const syncEditForm = () => {
  const shot = selectedShot.value
  if (!shot) return
  editForm.sceneNumber = shot.sceneNumber
  editForm.shotSize = shot.shotSize
  editForm.camera = shot.camera
  editForm.action = shot.action
  editForm.dialogue = shot.dialogue
  editForm.durationSeconds = shot.durationSeconds
  editForm.assetPublicIds = shot.assetPublicIds
  editForm.assetNames = shot.assetNames
  editForm.prompt = shot.prompt
  editForm.negativePrompt = shot.negativePrompt
}

const submitGenerate = async () => {
  if (!projectPublicId.value || !selectedEpisodeId.value || !generateForm.modelId) {
    ElMessage.warning('请先选择分集和文本模型')
    return
  }
  submitting.value = true
  try {
    const { data } = await generateStoryboardsApi(projectPublicId.value, {
      modelId: generateForm.modelId,
      episodePublicIds: [selectedEpisodeId.value],
      artStyle: generateForm.artStyle,
      directorStyle: generateForm.directorStyle,
    })
    activeJob.value = data
    ElMessage.success('分镜生成任务已提交')
    startJobPolling(data.publicId)
  } catch (error) {
    ElMessage.error(errorDetail(error, '分镜生成任务提交失败'))
  } finally {
    submitting.value = false
  }
}

const startJobPolling = (jobId: string) => {
  stopJobPolling()
  const tick = async () => {
    if (!projectPublicId.value || !jobId) return
    try {
      const { data } = await getTaskJobApi(projectPublicId.value, jobId)
      activeJob.value = data
      if (ACTIVE_JOB_STATUSES.includes(data.status)) {
        activeJobTimer.value = setTimeout(tick, POLL_ACTIVE_INTERVAL_MS)
        return
      }
      await loadShots()
      if (data.status === 'succeeded') ElMessage.success('分镜生成完成')
      else if (data.status === 'failed') ElMessage.error('分镜生成失败，请查看任务详情')
      else if (data.status === 'partial_failed') ElMessage.warning('分镜生成部分失败，请查看任务详情')
    } catch (error) {
      console.error('轮询分镜任务失败', error)
      activeJobTimer.value = setTimeout(tick, POLL_ACTIVE_INTERVAL_MS)
    }
  }
  activeJobTimer.value = setTimeout(tick, POLL_ACTIVE_INTERVAL_MS)
}

const stopJobPolling = () => {
  if (activeJobTimer.value) {
    clearTimeout(activeJobTimer.value)
    activeJobTimer.value = null
  }
}

const saveShot = async () => {
  const shot = selectedShot.value
  if (!shot) return
  const payload: StoryboardShotUpdatePayload = {
    sceneNumber: editForm.sceneNumber,
    shotSize: editForm.shotSize,
    camera: editForm.camera,
    action: editForm.action,
    dialogue: editForm.dialogue,
    durationSeconds: editForm.durationSeconds,
    assetPublicIds: editForm.assetPublicIds,
    assetNames: editForm.assetNames,
    prompt: editForm.prompt,
    negativePrompt: editForm.negativePrompt,
  }
  savingShot.value = true
  try {
    const { data } = await updateStoryboardShotApi(projectPublicId.value, shot.publicId, payload)
    replaceShot(data)
    ElMessage.success('分镜已保存')
  } catch (error) {
    ElMessage.error(errorDetail(error, '保存分镜失败'))
  } finally {
    savingShot.value = false
  }
}

const toggleShotLock = async () => {
  const shot = selectedShot.value
  if (!shot) return
  lockingShot.value = true
  try {
    const request = shot.status === 'locked' ? unlockStoryboardShotApi : lockStoryboardShotApi
    const { data } = await request(projectPublicId.value, shot.publicId)
    replaceShot(data)
  } catch (error) {
    ElMessage.error(errorDetail(error, '更新锁定状态失败'))
  } finally {
    lockingShot.value = false
  }
}

const deleteShot = async () => {
  const shot = selectedShot.value
  if (!shot) return
  try {
    await ElMessageBox.confirm('确定删除当前分镜镜头吗？', '删除分镜', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'production-dark-messagebox',
    })
    await deleteStoryboardShotApi(projectPublicId.value, shot.publicId)
    shots.value = shots.value.filter((item) => item.publicId !== shot.publicId)
    selectedShotId.value = currentShots.value[0]?.publicId || ''
    ElMessage.success('分镜已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorDetail(error, '删除分镜失败'))
  }
}

const replaceShot = (shot: StoryboardShot) => {
  const index = shots.value.findIndex((item) => item.publicId === shot.publicId)
  if (index >= 0) shots.value.splice(index, 1, shot)
  else shots.value.push(shot)
  selectedShotId.value = shot.publicId
}

const goProject = () => router.push('/project')

const goScript = () => {
  if (!projectPublicId.value) return router.push('/script')
  return router.push({ path: '/script', query: { id: projectPublicId.value } })
}

const goTasks = (jobPublicId: string | null | undefined = '') => {
  if (!projectPublicId.value) return
  const resolvedJobPublicId = String(jobPublicId || '').trim()
  router.push({
    path: '/tasks',
    query: {
      id: projectPublicId.value,
      type: 'storyboard',
      from: route.fullPath,
      ...(resolvedJobPublicId ? { job: resolvedJobPublicId } : {}),
    },
  })
}

watch(selectedShot, syncEditForm)

onMounted(() => {
  void reloadAll()
})

onBeforeUnmount(stopJobPolling)
</script>

<style scoped>
.production-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  color: #e6edf3;
  background:
    linear-gradient(180deg, rgba(37, 99, 235, 0.08), transparent 32%),
    #070a10;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 18px 12px;
  box-sizing: border-box;
  background: #0d1117;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.side-top,
.side-bottom {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}

.brand,
.nav-btn {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: grid;
  place-items: center;
}

.brand {
  color: #fff;
  font-weight: 800;
  background: #2563eb;
  cursor: pointer;
}

.nav-btn {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: #8b949e;
  cursor: pointer;
}

.nav-btn:hover,
.nav-btn.active {
  color: #fff;
  background: rgba(37, 99, 235, 0.18);
  border-color: rgba(96, 165, 250, 0.45);
}

.production-shell {
  min-width: 0;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-header,
.control-panel,
.panel {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(13, 17, 23, 0.86);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.28);
}

.page-header {
  min-height: 86px;
  border-radius: 16px;
  padding: 18px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-title h1 {
  margin: 0;
  font-size: 24px;
  line-height: 1.25;
}

.page-title p {
  margin: 6px 0 0;
  color: #8b949e;
  font-size: 13px;
}

.header-actions,
.control-actions,
.editor-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.control-panel {
  border-radius: 16px;
  padding: 16px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: end;
}

.control-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 14px;
}

.field,
.shot-editor label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.field > span,
.shot-editor label > span {
  font-size: 12px;
  color: #8b949e;
  font-weight: 700;
}

.task-status {
  height: 36px;
  padding: 0 12px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #8b949e;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  white-space: nowrap;
}

.task-status.active {
  color: #bfdbfe;
  border-color: rgba(96, 165, 250, 0.35);
  background: rgba(37, 99, 235, 0.14);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #6b7280;
}

.task-status.active .status-dot {
  background: #60a5fa;
  box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.16);
}

.workbench-grid {
  min-height: 0;
  height: calc(100vh - 214px);
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 380px;
  gap: 18px;
}

.panel {
  min-height: 0;
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-head {
  min-height: 54px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.panel-head h2 {
  margin: 0;
  font-size: 15px;
}

.panel-head span {
  color: #8b949e;
  font-size: 12px;
}

.episode-list,
.shot-table-wrap,
.shot-editor {
  min-height: 0;
  flex: 1;
}

.episode-list {
  overflow: auto;
  padding: 10px;
}

.episode-item {
  width: 100%;
  min-height: 74px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid transparent;
  background: transparent;
  color: #c5cdd6;
  text-align: left;
  cursor: pointer;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 10px;
  align-items: baseline;
}

.episode-item:hover,
.episode-item.active {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(96, 165, 250, 0.34);
}

.episode-item strong {
  color: #93c5fd;
  font-size: 12px;
}

.episode-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.episode-item em {
  grid-column: 2;
  font-style: normal;
  color: #6e7681;
  font-size: 12px;
}

.shot-table-wrap {
  position: relative;
}

.shot-editor {
  overflow: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.editor-row.two {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 120px;
  gap: 12px;
}

.empty-detail {
  flex: 1;
  display: grid;
  place-items: center;
  color: #6e7681;
  gap: 10px;
}

.empty-detail .el-icon {
  font-size: 32px;
}

.ghost-button,
.danger-button,
.primary-button {
  border-radius: 10px;
}

.ghost-button {
  color: #c5cdd6;
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
}

.ghost-button:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
}

.danger-button {
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.24);
}

.primary-button {
  background: #2563eb;
  border-color: #2563eb;
}

.model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.model-option em {
  color: #8b949e;
  font-style: normal;
  font-size: 12px;
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner),
:deep(.el-input-number .el-input__wrapper),
:deep(.el-select__wrapper) {
  background-color: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: none;
}

:deep(.el-input__inner),
:deep(.el-textarea__inner),
:deep(.el-select__placeholder),
:deep(.el-select__selected-item) {
  color: #e6edf3;
}

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.035);
  --el-table-row-hover-bg-color: rgba(37, 99, 235, 0.12);
  --el-table-current-row-bg-color: rgba(37, 99, 235, 0.18);
  --el-table-text-color: #c5cdd6;
  --el-table-header-text-color: #8b949e;
  --el-table-border-color: rgba(255, 255, 255, 0.08);
}

@media (max-width: 1280px) {
  .control-panel {
    grid-template-columns: minmax(0, 1fr);
  }

  .control-grid {
    grid-template-columns: repeat(2, minmax(160px, 1fr));
  }

  .workbench-grid {
    height: auto;
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .detail-panel {
    grid-column: 1 / -1;
    min-height: 520px;
  }
}
</style>

<style>
.production-dark-select.el-popper {
  background-color: #14181f;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #e6edf3;
}

.production-dark-select.el-popper .el-select-dropdown__item {
  color: #c5cdd6;
}

.production-dark-select.el-popper .el-select-dropdown__item.is-hovering,
.production-dark-select.el-popper .el-select-dropdown__item:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.06);
}

.production-dark-select.el-popper .el-select-dropdown__item.is-selected {
  color: #93c5fd;
  background: rgba(37, 99, 235, 0.16);
}

.production-dark-select.el-popper .el-popper__arrow::before {
  background: #14181f;
  border-color: rgba(255, 255, 255, 0.08);
}

.production-dark-messagebox {
  background: #14181f;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
}

.production-dark-messagebox .el-message-box__title,
.production-dark-messagebox .el-message-box__message {
  color: #e6edf3;
}
</style>