<template>
  <el-drawer
    :model-value="modelValue"
    title="资产管理"
    direction="rtl"
    size="min(1080px, 96vw)"
    append-to-body
    class="script-asset-drawer"
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
    @open="loadAssets"
  >
    <template #header>
      <div class="asset-drawer-head">
        <span class="asset-drawer-title">资产管理</span>
        <span class="asset-drawer-sub">父子资产结构 · 分页筛选 · 批量操作 · 剧本引用识别</span>
      </div>
    </template>

    <section class="asset-manage-toolbar">
      <el-input
        v-model="filters.keyword"
        class="asset-manage-search"
        clearable
        size="small"
        placeholder="搜索资产名称 / 关键词 / 标签"
        @keyup.enter="reloadFirstPage"
        @clear="reloadFirstPage"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>

      <div class="asset-manage-filters">
        <el-select v-model="filters.assetType" size="small" class="asset-manage-filter" placeholder="资产类型" popper-class="script-dark-select" @change="reloadFirstPage">
          <el-option label="全部类型" value="" />
          <el-option v-for="type in allAssetTypes" :key="type" :label="assetTypeLabel(type)" :value="type" />
        </el-select>

        <el-select v-model="filters.status" size="small" class="asset-manage-filter" placeholder="状态" popper-class="script-dark-select" @change="reloadFirstPage">
          <el-option label="全部状态" value="" />
          <el-option label="草稿" value="draft" />
          <el-option label="已锁定" value="locked" />
        </el-select>

        <el-select v-model="filters.referenced" size="small" class="asset-manage-filter" placeholder="正文引用" popper-class="script-dark-select" @change="reloadFirstPage">
          <el-option label="全部引用" value="" />
          <el-option label="已被引用" value="with" />
          <el-option label="未被引用" value="without" />
        </el-select>

        <div class="asset-manage-actions">
          <el-button size="small" :loading="loading" @click="loadAssets">
            <el-icon><Refresh /></el-icon>&nbsp;刷新
          </el-button>
          <el-button type="primary" size="small" @click="openCreate">
            <el-icon><Plus /></el-icon>&nbsp;新增资产
          </el-button>
        </div>
      </div>
    </section>

    <section class="asset-batch-bar" :class="{ 'is-active': selectedIds.length > 0 }">
      <div class="asset-batch-info">
        <el-checkbox
          :model-value="isPageSelected"
          :indeterminate="isPageIndeterminate"
          @change="toggleCurrentPage"
        />
        <span>已选择 {{ selectedIds.length }} 项</span>
      </div>
      <div class="asset-batch-actions">
        <el-button size="small" :disabled="selectedIds.length === 0" @click="batchOperate('lock')">批量锁定</el-button>
        <el-button size="small" :disabled="selectedIds.length === 0" @click="batchOperate('unlock')">批量解锁</el-button>
        <el-button size="small" :disabled="selectedIds.length === 0" @click="autocompleteSelected">
          <el-icon><MagicStick /></el-icon>&nbsp;描述补全
        </el-button>
        <el-button size="small" type="danger" plain :disabled="selectedIds.length === 0" @click="batchOperate('delete')">
          批量删除
        </el-button>
      </div>
    </section>

    <section
      v-loading="loading"
      class="asset-manage-body"
      element-loading-background="rgba(13, 17, 23, 0.62)"
    >
      <el-empty v-if="!loading && assets.length === 0" description="暂无匹配资产">
        <el-button type="primary" size="small" @click="openCreate">新增资产</el-button>
      </el-empty>

      <article
        v-for="asset in assets"
        :key="asset.publicId"
        class="asset-manage-row"
        :class="{ 'is-locked': asset.status === 'locked', 'is-selected': selectedIds.includes(asset.publicId) }"
      >
        <el-checkbox
          :model-value="selectedIds.includes(asset.publicId)"
          class="asset-row-checkbox"
          @change="(value: unknown) => toggleAsset(asset.publicId, !!value)"
        />
        <div class="asset-row-thumb">
          <img v-if="asset.thumbnailUrl" :src="asset.thumbnailUrl" alt="" />
          <el-icon v-else class="asset-row-thumb-icon"><Picture /></el-icon>
        </div>
        <div class="asset-row-main">
          <div class="asset-row-title">
            <span :class="`asset-type-pill asset-type-pill--${asset.assetType}`">{{ assetTypeLabel(asset.assetType) }}</span>
            <strong>{{ asset.name }}</strong>
            <span v-if="asset.status === 'locked'" class="asset-status-pill">已锁定</span>
            <span v-if="asset.references.length > 0" class="asset-reference-pill">已引用 {{ asset.references.length }}</span>
          </div>
          <p class="asset-row-desc">{{ asset.summary || '暂无概述' }}</p>
          <div v-if="asset.references.length" class="asset-row-meta">
            正文引用：{{ asset.references.map((ref) => `EP${pad2(ref.episodeIndex)}`).join('、') }}
          </div>

          <div v-for="child in asset.children" :key="child.publicId" class="asset-child-row">
            <el-checkbox
              :model-value="selectedIds.includes(child.publicId)"
              @change="(value: unknown) => toggleAsset(child.publicId, !!value)"
            />
            <div class="asset-child-thumb">
              <img v-if="child.thumbnailUrl" :src="child.thumbnailUrl" alt="" />
              <el-icon v-else><Picture /></el-icon>
            </div>
            <span :class="`asset-type-pill asset-type-pill--${child.assetType}`">{{ assetTypeLabel(child.assetType) }}</span>
            <strong>{{ child.name }}</strong>
            <span v-if="child.status === 'locked'" class="asset-status-pill">已锁定</span>
            <span class="asset-child-actions">
              <el-button link size="small" @click="openEdit(child)">编辑</el-button>
              <el-button link size="small" @click="toggleLock(child)">{{ child.status === 'locked' ? '解锁' : '锁定' }}</el-button>
              <el-button link size="small" type="danger" @click="removeAsset(child)">删除</el-button>
            </span>
          </div>
        </div>
        <div class="asset-row-actions">
          <el-button link size="small" @click="openEdit(asset)"><el-icon><Edit /></el-icon>&nbsp;编辑</el-button>
          <el-button link size="small" @click="toggleLock(asset)">
            <el-icon><component :is="asset.status === 'locked' ? Unlock : Lock" /></el-icon>
            &nbsp;{{ asset.status === 'locked' ? '解锁' : '锁定' }}
          </el-button>
          <el-button link size="small" type="danger" @click="removeAsset(asset)"><el-icon><Delete /></el-icon>&nbsp;删除</el-button>
        </div>
      </article>
    </section>

    <template #footer>
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        small
        background
        @current-change="loadAssets"
      />
    </template>
  </el-drawer>

  <el-dialog
    v-model="formVisible"
    :title="editingPublicId ? '编辑资产' : '新增资产'"
    width="min(640px, 94vw)"
    append-to-body
    class="script-asset-dialog"
  >
    <el-form label-width="86px" label-position="right">
      <el-form-item label="资产类型">
        <el-select v-if="!editingPublicId" v-model="form.assetType" placeholder="选择类型" popper-class="script-dark-select">
          <el-option v-for="type in creatableAssetTypes" :key="type" :label="assetTypeLabel(type)" :value="type" />
        </el-select>
        <span v-else class="asset-form-static">{{ assetTypeLabel(form.assetType) }}</span>
      </el-form-item>
      <el-form-item label="名称"><el-input v-model="form.name" maxlength="200" placeholder="资产名称" /></el-form-item>
      <el-form-item label="变体标签"><el-input v-model="form.variantLabel" maxlength="100" placeholder="如：受伤状态、少年" /></el-form-item>
      <el-form-item label="关键词"><el-input v-model="form.keyword" maxlength="500" placeholder="风格关键词" /></el-form-item>
      <el-form-item label="色彩"><el-input v-model="form.colors" maxlength="1000" placeholder="主色调 / 配色" /></el-form-item>
      <el-form-item label="概述"><el-input v-model="form.summary" type="textarea" :rows="3" placeholder="可直接用于制作的整体概述" /></el-form-item>
      <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="3" placeholder="结构化描述（可留空，交由抽取或补全生成）" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="formVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitAssetForm">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Lock, MagicStick, Picture, Plus, Refresh, Search, Unlock } from '@element-plus/icons-vue'
import {
  autocompleteAssetsApi,
  batchAssetsApi,
  createAssetApi,
  deleteAssetApi,
  listManagedAssetsApi,
  lockAssetApi,
  unlockAssetApi,
  updateAssetApi,
  type AssetListQuery,
  type AssetManageItem,
  type AssetType,
} from '@/api/asset'
import './ScriptAssetDrawer.css'

const props = defineProps<{
  modelValue: boolean
  projectPublicId: string
  textModelId?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'changed'): void
}>()

const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  role: '人物',
  faction: '势力',
  prop: '道具',
  scene: '场景',
}
const allAssetTypes: AssetType[] = ['role', 'faction', 'prop', 'scene']
const creatableAssetTypes: AssetType[] = ['role', 'faction', 'prop', 'scene']
const assetTypeLabel = (type: AssetType) => ASSET_TYPE_LABELS[type] ?? type
const pad2 = (value: number) => String(value).padStart(2, '0')

const loading = ref(false)
const submitting = ref(false)
const assets = ref<AssetManageItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const selectedIds = ref<string[]>([])

const filters = reactive<{ keyword: string; assetType: AssetType | ''; status: 'draft' | 'locked' | ''; referenced: 'with' | 'without' | '' }>({
  keyword: '',
  assetType: '',
  status: '',
  referenced: '',
})

const visibleIds = computed(() =>
  assets.value.flatMap((asset) => [asset.publicId, ...asset.children.map((child) => child.publicId)]),
)
const isPageSelected = computed(
  () => visibleIds.value.length > 0 && visibleIds.value.every((id) => selectedIds.value.includes(id)),
)
const isPageIndeterminate = computed(
  () => selectedIds.value.length > 0 && !isPageSelected.value,
)

const loadAssets = async () => {
  if (!props.projectPublicId) return
  loading.value = true
  try {
    const query: AssetListQuery = {
      keyword: filters.keyword.trim(),
      assetType: filters.assetType,
      status: filters.status,
      referenced: filters.referenced,
      page: page.value,
      pageSize: pageSize.value,
    }
    const { data } = await listManagedAssetsApi(props.projectPublicId, query)
    assets.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error((error as Error)?.message || '加载资产失败')
  } finally {
    loading.value = false
  }
}

const reloadFirstPage = () => {
  page.value = 1
  void loadAssets()
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => filters.keyword,
  () => {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(reloadFirstPage, 300)
  },
)

const toggleAsset = (publicId: string, checked: boolean) => {
  const next = new Set(selectedIds.value)
  if (checked) next.add(publicId)
  else next.delete(publicId)
  selectedIds.value = Array.from(next)
}

const toggleCurrentPage = (checked: unknown) => {
  if (checked) {
    selectedIds.value = Array.from(new Set([...selectedIds.value, ...visibleIds.value]))
  } else {
    const remove = new Set(visibleIds.value)
    selectedIds.value = selectedIds.value.filter((id) => !remove.has(id))
  }
}

const batchOperate = async (operation: 'lock' | 'unlock' | 'delete') => {
  if (selectedIds.value.length === 0) return
  if (operation === 'delete') {
    try {
      await ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.length} 项资产？子资产将一并删除。`, '批量删除', {
        type: 'warning',
        customClass: 'script-asset-messagebox',
      })
    } catch {
      return
    }
  }
  try {
    const { data } = await batchAssetsApi(props.projectPublicId, {
      assetPublicIds: selectedIds.value,
      operation,
    })
    ElMessage.success(`已处理 ${data.affected} 项`)
    selectedIds.value = []
    await loadAssets()
    emit('changed')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '批量操作失败')
  }
}

const autocompleteSelected = async () => {
  if (selectedIds.value.length === 0) return
  const modelId = (props.textModelId || '').trim()
  if (!modelId) {
    ElMessage.warning('请先在项目设置中选择文本模型，再进行描述补全')
    return
  }
  try {
    await autocompleteAssetsApi(props.projectPublicId, {
      modelId,
      assetPublicIds: selectedIds.value,
    })
    ElMessage.success('已提交描述补全任务，完成后请刷新查看')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '提交补全任务失败')
  }
}

const formVisible = ref(false)
const editingPublicId = ref('')
const form = reactive({
  assetType: 'role' as AssetType,
  name: '',
  variantLabel: '',
  keyword: '',
  colors: '',
  summary: '',
  description: '',
})

const resetForm = () => {
  form.assetType = 'role'
  form.name = ''
  form.variantLabel = ''
  form.keyword = ''
  form.colors = ''
  form.summary = ''
  form.description = ''
}

const openCreate = () => {
  editingPublicId.value = ''
  resetForm()
  formVisible.value = true
}

const openEdit = (asset: AssetManageItem) => {
  editingPublicId.value = asset.publicId
  form.assetType = asset.assetType
  form.name = asset.name
  form.variantLabel = asset.variantLabel
  form.keyword = asset.keyword
  form.colors = asset.colors
  form.summary = asset.summary
  form.description = asset.description
  formVisible.value = true
}

const submitAssetForm = async () => {
  if (!form.name.trim()) {
    ElMessage.warning('请填写资产名称')
    return
  }
  submitting.value = true
  try {
    if (editingPublicId.value) {
      await updateAssetApi(props.projectPublicId, editingPublicId.value, {
        name: form.name.trim(),
        variantLabel: form.variantLabel.trim(),
        keyword: form.keyword.trim(),
        colors: form.colors.trim(),
        summary: form.summary,
        description: form.description,
      })
    } else {
      await createAssetApi(props.projectPublicId, {
        assetType: form.assetType,
        name: form.name.trim(),
        variantLabel: form.variantLabel.trim(),
        keyword: form.keyword.trim(),
        colors: form.colors.trim(),
        summary: form.summary,
        description: form.description,
      })
    }
    ElMessage.success('保存成功')
    formVisible.value = false
    await loadAssets()
    emit('changed')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '保存失败')
  } finally {
    submitting.value = false
  }
}

const toggleLock = async (asset: AssetManageItem) => {
  try {
    if (asset.status === 'locked') await unlockAssetApi(props.projectPublicId, asset.publicId)
    else await lockAssetApi(props.projectPublicId, asset.publicId)
    await loadAssets()
    emit('changed')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '操作失败')
  }
}

const removeAsset = async (asset: AssetManageItem) => {
  try {
    await ElMessageBox.confirm(`确认删除资产「${asset.name}」？子资产将一并删除。`, '删除资产', {
      type: 'warning',
      customClass: 'script-asset-messagebox',
    })
  } catch {
    return
  }
  try {
    await deleteAssetApi(props.projectPublicId, asset.publicId)
    ElMessage.success('已删除')
    selectedIds.value = selectedIds.value.filter((id) => id !== asset.publicId)
    await loadAssets()
    emit('changed')
  } catch (error) {
    ElMessage.error((error as Error)?.message || '删除失败')
  }
}
</script>