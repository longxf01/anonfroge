<template>
  <el-dialog
    :model-value="modelValue"
    :title="asset ? `配图 · ${asset.name}` : '资产配图'"
    width="min(880px, 95vw)"
    append-to-body
    class="script-asset-dialog script-asset-media-dialog"
    @update:model-value="onVisibleChange"
    @open="onOpen"
  >
    <section class="gen-config">
      <div class="gen-block">
        <div class="gen-label-row">
          <label class="gen-label">提示词</label>
          <el-button link size="small" :loading="prompting" @click="synthesizePrompt">
            <el-icon><MagicStick /></el-icon>&nbsp;生成专业提示词
          </el-button>
        </div>
        <el-input
          v-model="form.prompt"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="留空时会先调用项目绑定文本模型生成专业提示词，再提交给项目绑定图像模型"
        />
      </div>

      <div class="gen-grid">
        <div class="gen-block gen-block--select">
          <label class="gen-label">画面比例</label>
          <el-select
            v-model="form.aspectRatio"
            class="script-asset-media-select"
            popper-class="script-asset-media-select-popper"
          >
            <el-option
              v-for="ratio in RATIOS"
              :key="ratio.value"
              :label="ratio.value"
              :value="ratio.value"
            >
              <span class="media-select-option">
                <span class="ratio-box" :style="ratioBoxStyle(ratio)"></span>
                <span>{{ ratio.value }}</span>
              </span>
            </el-option>
          </el-select>
        </div>
        <div class="gen-block gen-block--select">
          <label class="gen-label">分辨率</label>
          <el-select
            v-model="form.imageSize"
            class="script-asset-media-select script-asset-media-select--small"
            popper-class="script-asset-media-select-popper"
          >
            <el-option v-for="size in SIZES" :key="size" :label="size" :value="size" />
          </el-select>
        </div>
        <div class="gen-block gen-block--select">
          <label class="gen-label">数量</label>
          <el-select
            v-model="form.count"
            class="script-asset-media-select script-asset-media-select--small"
            popper-class="script-asset-media-select-popper"
          >
            <el-option v-for="n in COUNTS" :key="n" :label="String(n)" :value="n" />
          </el-select>
        </div>
        <div class="gen-block gen-block--actions">
          <el-button class="media-refresh-button" :loading="loading" @click="() => loadMedia()">
            <el-icon><Refresh /></el-icon>&nbsp;刷新
          </el-button>
          <el-button type="primary" :loading="generating" @click="generate">
            <el-icon><MagicStick /></el-icon>&nbsp;生成配图
          </el-button>
        </div>
      </div>
    </section>

    <section class="media-gallery">
      <template v-if="loading && medias.length === 0 && pendingCount === 0">
        <div
          v-for="n in 4"
          :key="`sk${n}`"
          class="media-card media-card--skeleton"
          :style="{ aspectRatio: cardAspect }"
        />
      </template>
      <template v-else>
        <div
          v-for="n in pendingCount"
          :key="`pd${n}`"
          class="media-card media-card--pending"
          :style="{ aspectRatio: cardAspect }"
        >
          <el-icon class="pending-spin"><Loading /></el-icon>
          <span>生成中…</span>
        </div>

        <el-empty
          v-if="medias.length === 0 && pendingCount === 0"
          class="media-empty"
          :image-size="80"
          description="暂无配图，调整参数后点击「生成配图」"
        />

        <figure
          v-for="(media, idx) in medias"
          :key="media.publicId"
          class="media-card"
          :class="{ 'is-cover': media.mediaRole === 'final' }"
          :style="{ aspectRatio: mediaAspect(media) }"
        >
          <img
            :src="media.url"
            :alt="asset?.name || ''"
            loading="lazy"
            @click="openPreview(idx)"
          />
          <span v-if="media.mediaRole === 'final'" class="cover-ribbon">封面</span>
          <div class="media-overlay">
            <el-button circle size="small" title="放大预览" @click="openPreview(idx)">
              <el-icon><ZoomIn /></el-icon>
            </el-button>
            <el-button
              circle
              size="small"
              :disabled="media.mediaRole === 'final'"
              title="设为封面"
              @click="setCover(media)"
            >
              <el-icon><Star /></el-icon>
            </el-button>
            <el-button circle size="small" type="danger" title="删除" @click="remove(media)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </figure>
      </template>
    </section>
  </el-dialog>

  <el-image-viewer
    v-if="previewVisible"
    :url-list="previewUrls"
    :initial-index="previewIndex"
    hide-on-click-modal
    teleported
    @close="previewVisible = false"
  />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Loading, MagicStick, Refresh, Star, ZoomIn } from '@element-plus/icons-vue'
import {
  deleteAssetMediaApi,
  generateAssetImagesApi,
  listAssetMediaApi,
  setAssetMediaCoverApi,
  synthesizeAssetImagePromptApi,
  type AssetManageItem,
  type AssetMediaItem,
} from '@/api/asset'
import { getTaskJobApi, type TaskJobResponse } from '@/api/task'

const props = defineProps<{
  modelValue: boolean
  projectPublicId: string
  asset: AssetManageItem | null
  textModelId?: string
  imageModelId?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'changed'): void
}>()

interface RatioOption {
  value: string
  w: number
  h: number
}

const RATIOS: RatioOption[] = [
  { value: '1:1', w: 1, h: 1 },
  { value: '4:3', w: 4, h: 3 },
  { value: '3:4', w: 3, h: 4 },
  { value: '16:9', w: 16, h: 9 },
  { value: '9:16', w: 9, h: 16 },
  { value: '3:2', w: 3, h: 2 },
  { value: '2:3', w: 2, h: 3 },
  { value: '5:4', w: 5, h: 4 },
  { value: '4:5', w: 4, h: 5 },
  { value: '21:9', w: 21, h: 9 },
]
const SIZES = ['1K', '2K', '4K']
const COUNTS = [1, 2, 3, 4]
const PROMPT_CACHE_PREFIX = 'script:asset-media-prompt:'
const MEDIA_POLL_INTERVAL_MS = 4000
const MEDIA_MAX_POLL_ATTEMPTS = 120

const form = reactive({
  prompt: '',
  aspectRatio: '3:4',
  imageSize: '2K',
  count: 1,
})

const loading = ref(false)
const generating = ref(false)
const prompting = ref(false)
const medias = ref<AssetMediaItem[]>([])
const pendingCount = ref(0)

const cardAspect = computed(() => form.aspectRatio.replace(':', ' / '))

const ratioBoxStyle = (ratio: RatioOption) => {
  const max = 16
  const longSide = Math.max(ratio.w, ratio.h)
  return {
    width: `${(ratio.w / longSide) * max}px`,
    height: `${(ratio.h / longSide) * max}px`,
  }
}

const mediaAspect = (media: AssetMediaItem) =>
  media.width > 0 && media.height > 0 ? `${media.width} / ${media.height}` : cardAspect.value

const promptCacheKey = () => {
  const assetId = props.asset?.publicId || ''
  const projectId = props.projectPublicId || ''
  return assetId && projectId ? `${PROMPT_CACHE_PREFIX}${projectId}:${assetId}` : ''
}

const readCachedPrompt = () => {
  const key = promptCacheKey()
  if (!key) return ''
  try {
    return localStorage.getItem(key) || ''
  } catch {
    return ''
  }
}

const cachePrompt = (prompt: string) => {
  const key = promptCacheKey()
  const value = prompt.trim()
  if (!key || !value) return
  try {
    localStorage.setItem(key, value)
  } catch {
    // 本地缓存不可用不影响后续生图；生成完成后提示词仍会随媒体入库。
  }
}

const loadMedia = async (options: { silent?: boolean } = {}) => {
  if (!props.asset) return
  if (!options.silent) loading.value = true
  try {
    const { data } = await listAssetMediaApi(props.projectPublicId, props.asset.publicId)
    medias.value = data
  } catch (error) {
    if (!options.silent) {
      ElMessage.error((error as Error)?.message || '加载配图失败')
    }
  } finally {
    if (!options.silent) loading.value = false
  }
}

const synthesizePrompt = async () => {
  if (!props.asset) return ''
  if (!(props.textModelId || '').trim()) {
    ElMessage.warning('请先在项目设置中选择文本模型，再生成专业提示词')
    return ''
  }
  if (!(props.imageModelId || '').trim()) {
    ElMessage.warning('请先在项目设置中选择图像模型，再生成专业提示词')
    return ''
  }
  prompting.value = true
  try {
    const { data } = await synthesizeAssetImagePromptApi(props.projectPublicId, props.asset.publicId)
    form.prompt = data.prompt || ''
    cachePrompt(form.prompt)
    return form.prompt
  } catch (error) {
    ElMessage.error((error as Error)?.message || '生成专业提示词失败')
    return ''
  } finally {
    prompting.value = false
  }
}

// 异步生成可见化：提交后插入占位卡，按任务状态轮询，并在终态刷新媒体列表。
let pollTimer: ReturnType<typeof setTimeout> | undefined
let pollTries = 0
let pollingJobPublicId = ''

const stopPolling = () => {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = undefined
  pollingJobPublicId = ''
}

const isTerminalJob = (job: TaskJobResponse) => (
  job.status === 'succeeded' ||
  job.status === 'partial_failed' ||
  job.status === 'failed' ||
  job.status === 'canceled'
)

const pendingFromJob = (job: TaskJobResponse, expected: number) => {
  const active = job.pendingCount + job.runningCount + job.pausedCount
  const unfinished = Math.max(
    0,
    job.totalCount - job.succeededCount - job.failedCount - job.canceledCount,
  )
  return Math.min(expected, Math.max(active, unfinished))
}

const startPolling = (jobPublicId: string, expected: number) => {
  stopPolling()
  const baseline = medias.value.length
  pendingCount.value = expected
  pollTries = 0
  pollingJobPublicId = jobPublicId
  const tick = async () => {
    if (!pollingJobPublicId) return
    pollTries += 1
    try {
      const { data: job } = await getTaskJobApi(props.projectPublicId, jobPublicId)
      await loadMedia({ silent: true })
      pendingCount.value = pendingFromJob(job, expected)
      if (medias.value.length > baseline || job.succeededCount > 0) emit('changed')
      if (isTerminalJob(job)) {
        pendingCount.value = 0
        stopPolling()
        if (job.failedCount > 0 || job.canceledCount > 0) {
          ElMessage.warning('配图任务已结束，部分图片未生成成功，可在任务中心查看详情')
        }
        return
      }
    } catch {
      await loadMedia({ silent: true })
      const produced = Math.max(0, medias.value.length - baseline)
      pendingCount.value = Math.max(0, expected - produced)
      if (produced >= expected) {
        emit('changed')
        pendingCount.value = 0
        stopPolling()
        return
      }
    }
    if (pollTries >= MEDIA_MAX_POLL_ATTEMPTS) {
      stopPolling()
      pendingCount.value = 0
      await loadMedia({ silent: true })
      ElMessage.warning('配图任务仍在后台执行，可稍后手动刷新查看结果')
      return
    }
    pollTimer = setTimeout(tick, MEDIA_POLL_INTERVAL_MS)
  }
  pollTimer = setTimeout(tick, MEDIA_POLL_INTERVAL_MS)
}

const generate = async () => {
  if (!props.asset) return
  const modelId = (props.imageModelId || '').trim()
  if (!modelId) {
    ElMessage.warning('请先在项目设置中选择图像模型，再生成配图')
    return
  }
  generating.value = true
  try {
    if (!form.prompt.trim()) {
      const synthesized = await synthesizePrompt()
      if (!synthesized.trim()) return
    }
    cachePrompt(form.prompt)
    const { data: job } = await generateAssetImagesApi(props.projectPublicId, {
      modelId,
      assetPublicIds: [props.asset.publicId],
      prompt: form.prompt.trim(),
      aspectRatio: form.aspectRatio,
      imageSize: form.imageSize,
      count: form.count,
    })
    ElMessage.success('已提交配图生成任务，正在等待出图…')
    startPolling(job.publicId, form.count)
  } catch (error) {
    ElMessage.error((error as Error)?.message || '提交配图任务失败')
  } finally {
    generating.value = false
  }
}

const setCover = async (media: AssetMediaItem) => {
  try {
    await setAssetMediaCoverApi(props.projectPublicId, media.publicId)
    ElMessage.success('已设为封面')
    await loadMedia()
    emit('changed')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '设置封面失败')
  }
}

const remove = async (media: AssetMediaItem) => {
  try {
    await ElMessageBox.confirm('确认删除这张配图？', '删除配图', {
      type: 'warning',
      customClass: 'script-asset-messagebox',
    })
  } catch {
    return
  }
  try {
    await deleteAssetMediaApi(props.projectPublicId, media.publicId)
    ElMessage.success('已删除')
    await loadMedia()
    emit('changed')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '删除失败')
  }
}

const previewVisible = ref(false)
const previewUrls = ref<string[]>([])
const previewIndex = ref(0)
const openPreview = (index: number) => {
  previewUrls.value = medias.value.map((media) => media.url).filter(Boolean)
  previewIndex.value = index
  previewVisible.value = true
}

const onOpen = () => {
  form.prompt = readCachedPrompt()
  pendingCount.value = 0
  void loadMedia()
}

const onVisibleChange = (value: boolean) => {
  if (!value) {
    stopPolling()
    pendingCount.value = 0
  }
  emit('update:modelValue', value)
}

onBeforeUnmount(stopPolling)
</script>

<style>
/* 资产配图弹窗：深色，复用 .script-asset-dialog 暗色外壳；以唯一类前缀避免泄漏。 */
.script-asset-media-dialog .gen-config {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px 16px;
  margin-bottom: 16px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.07);
}
.script-asset-media-dialog .gen-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.script-asset-media-dialog .gen-block--select {
  min-width: 128px;
}
.script-asset-media-dialog .gen-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.script-asset-media-dialog .gen-label {
  font-size: 12px;
  font-weight: 600;
  color: #8b949e;
  letter-spacing: 0.02em;
}
.script-asset-media-dialog .gen-grid {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 18px;
}
.script-asset-media-dialog .gen-block--actions {
  margin-left: auto;
  flex-direction: row;
  gap: 8px;
}
.script-asset-media-dialog .script-asset-media-select {
  width: 142px;
}
.script-asset-media-dialog .script-asset-media-select--small {
  width: 96px;
}
.script-asset-media-dialog .script-asset-media-select .el-select__wrapper {
  min-height: 40px;
  background: #0c1015;
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: none;
  border-radius: 8px;
}
.script-asset-media-dialog .script-asset-media-select .el-select__wrapper:hover {
  background: #111820;
  border-color: rgba(255, 255, 255, 0.24);
}
.script-asset-media-dialog .script-asset-media-select .el-select__wrapper.is-focused {
  border-color: rgba(37, 99, 235, 0.7);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14);
}
.script-asset-media-dialog .script-asset-media-select .el-select__selected-item,
.script-asset-media-dialog .script-asset-media-select .el-select__placeholder {
  color: #e6edf3;
}
.script-asset-media-dialog .script-asset-media-select .el-select__caret {
  color: #8b949e;
}
.script-asset-media-dialog .media-refresh-button {
  min-height: 40px;
  color: #c5cdd6;
  background: #0c1015;
  border-color: rgba(255, 255, 255, 0.14);
  box-shadow: none;
}
.script-asset-media-dialog .media-refresh-button:hover,
.script-asset-media-dialog .media-refresh-button:focus {
  color: #ffffff;
  background: #111820;
  border-color: rgba(255, 255, 255, 0.28);
}
.script-asset-media-dialog .el-textarea__inner {
  background: #0c1015;
  color: #e6edf3;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border-radius: 8px;
}
.script-asset-media-dialog .el-textarea__inner::placeholder {
  color: #6e7681;
}
.script-asset-media-dialog .el-textarea__inner:focus {
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.55) inset, 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.script-asset-media-dialog .ratio-box {
  display: inline-block;
  border-radius: 2px;
  background: currentColor;
  opacity: 0.85;
}

.script-asset-media-dialog .media-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  align-items: start;
  gap: 12px;
  min-height: 180px;
  max-height: 52vh;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}
.script-asset-media-dialog .media-empty {
  grid-column: 1 / -1;
}
.script-asset-media-dialog .media-card {
  position: relative;
  margin: 0;
  align-self: start;
  border-radius: 10px;
  overflow: hidden;
  background: #0c1015;
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}
.script-asset-media-dialog .media-card:hover {
  border-color: rgba(255, 255, 255, 0.2);
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
}
.script-asset-media-dialog .media-card.is-cover {
  border-color: rgba(37, 99, 235, 0.7);
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.4);
}
.script-asset-media-dialog .media-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  cursor: zoom-in;
}
.script-asset-media-dialog .cover-ribbon {
  position: absolute;
  top: 8px;
  left: 8px;
  font-size: 11px;
  padding: 1px 9px;
  border-radius: 999px;
  color: #fff;
  background: #2563eb;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}
.script-asset-media-dialog .media-overlay {
  position: absolute;
  inset: auto 0 0 0;
  display: flex;
  justify-content: center;
  gap: 8px;
  padding: 8px;
  background: linear-gradient(to top, rgba(6, 9, 13, 0.86), rgba(6, 9, 13, 0));
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.script-asset-media-dialog .media-card:hover .media-overlay,
.script-asset-media-dialog .media-card:focus-within .media-overlay {
  opacity: 1;
  transform: translateY(0);
}
.script-asset-media-dialog .media-card--skeleton {
  background: linear-gradient(100deg, #0c1015 30%, #161b22 50%, #0c1015 70%);
  background-size: 200% 100%;
  animation: media-shimmer 1.3s ease-in-out infinite;
}
.script-asset-media-dialog .media-card--pending {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #8b949e;
  font-size: 12px;
  border-style: dashed;
}
.script-asset-media-dialog .pending-spin {
  font-size: 22px;
  color: #2563eb;
  animation: media-spin 1s linear infinite;
}
@keyframes media-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}
@keyframes media-spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .script-asset-media-dialog .media-card,
  .script-asset-media-dialog .media-overlay,
  .script-asset-media-dialog .media-card--skeleton,
  .script-asset-media-dialog .pending-spin {
    transition: none;
    animation: none;
  }
}
</style>

<style>
/* 下拉浮层会 teleport 到 body，需使用全局类保持配图弹窗的暗色控件一致性。 */
.script-asset-media-select-popper.el-popper {
  background: #111820 !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}
.script-asset-media-select-popper .el-select-dropdown {
  background: #111820;
  border: none;
}
.script-asset-media-select-popper .el-select-dropdown__wrap,
.script-asset-media-select-popper .el-scrollbar,
.script-asset-media-select-popper .el-scrollbar__wrap,
.script-asset-media-select-popper .el-scrollbar__view {
  background: #111820;
}
.script-asset-media-select-popper .el-select-dropdown__list {
  padding: 6px 4px;
}
.script-asset-media-select-popper .el-select-dropdown__item {
  margin: 2px 4px;
  border-radius: 8px;
  color: #c5cdd6;
  transition: background-color 0.18s ease, color 0.18s ease;
}
.script-asset-media-select-popper .el-select-dropdown__item:hover,
.script-asset-media-select-popper .el-select-dropdown__item.hover,
.script-asset-media-select-popper .el-select-dropdown__item.is-hovering {
  background: rgba(255, 255, 255, 0.06);
  color: #ffffff;
}
.script-asset-media-select-popper .el-select-dropdown__item.selected,
.script-asset-media-select-popper .el-select-dropdown__item.is-selected {
  color: #7aa2f7;
  background: rgba(37, 99, 235, 0.16);
  font-weight: 600;
}
.script-asset-media-select-popper .el-select-dropdown__item.is-disabled {
  color: #4d5560;
  background: transparent;
}
.script-asset-media-select-popper .el-select-dropdown__wrap::-webkit-scrollbar {
  width: 6px;
}
.script-asset-media-select-popper .el-select-dropdown__wrap::-webkit-scrollbar-track {
  background: transparent;
}
.script-asset-media-select-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.3);
  border-radius: 999px;
}
.script-asset-media-select-popper .el-select-dropdown__wrap::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.5);
}
.script-asset-media-select-popper .el-popper__arrow::before {
  background: #111820 !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
}
.script-asset-media-select-popper .media-select-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-variant-numeric: tabular-nums;
}
</style>
