<template>
  <main class="novel-page">
    <div class="app-shell">
      <aside class="sidebar">
        <div class="side-top">
          <div class="brand" @click="goProject">AF</div>

          <el-tooltip content="项目" placement="right">
            <button class="nav-btn" aria-label="项目" @click="goProject">
              <el-icon><Folder /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="小说" placement="right">
            <button class="nav-btn active" aria-label="小说">
              <el-icon><Reading /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="任务" placement="right">
            <button class="nav-btn" aria-label="任务" @click="showComingSoon">
              <el-icon><List /></el-icon>
            </button>
          </el-tooltip>
        </div>

        <div class="side-bottom">
          <el-tooltip content="文档" placement="right">
            <button class="nav-btn" aria-label="文档" @click="showComingSoon">
              <el-icon><Document /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="设置" placement="right">
            <button class="nav-btn" aria-label="设置" @click="settingsVisible = true">
              <el-icon><Setting /></el-icon>
            </button>
          </el-tooltip>

          <el-tooltip content="代码仓库" placement="right">
            <button class="nav-btn" aria-label="代码仓库" @click="showComingSoon">
              <el-icon><Connection /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </aside>

      <section class="main-panel">
        <header class="page-header">
          <div class="page-header__left">
            <h1 class="title">小说原文</h1>
            <p class="desc">管理项目章节、卷次结构与事件清洗结果</p>
          </div>

          <div class="page-header__right">
            <el-button class="header-action" size="large" @click="openImportDialog">
              <el-icon><Upload /></el-icon>
              &nbsp;全文导入
            </el-button>

            <el-button class="header-action" size="large" @click="openCrawlDialog">
              <el-icon><Download /></el-icon>
              &nbsp;小说爬取
            </el-button>

            <el-button class="primary-button" type="primary" size="large" @click="openCreateDialog">
              <el-icon><Plus /></el-icon>
              &nbsp;新建章节
            </el-button>
          </div>
        </header>

        <section class="toolbar">
          <el-input
            v-model="searchKeyword"
            class="search-input"
            clearable
            placeholder="按章节标题搜索"
            @clear="searchKeyword = ''"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <div class="toolbar-spacer"></div>

          <el-button
            :disabled="selectedRows.length === 0 || cleaning"
            :loading="cleaning"
            @click="batchCleanSelected"
          >
            <el-icon><MagicStick /></el-icon>
            &nbsp;清洗事件 ({{ selectedRows.length }})
          </el-button>

          <el-button
            :disabled="selectedRows.length === 0"
            type="danger"
            @click="batchDeleteSelected"
          >
            <el-icon><Delete /></el-icon>
            &nbsp;批量删除
          </el-button>
        </section>

        <section class="table-wrap">
          <el-table
            ref="tableRef"
            v-loading="loading"
            :data="pagedNovels"
            class="novel-table"
            element-loading-background="rgba(13, 17, 23, 0.55)"
            row-key="id"
            stripe
            :tooltip-options="{ effect: 'dark', popperClass: 'novel-cell-tooltip' }"
            @selection-change="onSelectionChange"
          >
            <el-table-column type="selection" width="48" />

            <el-table-column prop="chapterIndex" label="序号" width="80">
              <template #default="{ row }">
                <span class="row-index">#{{ row.chapterIndex }}</span>
              </template>
            </el-table-column>

            <el-table-column prop="reel" label="卷次" width="140">
              <template #default="{ row }">
                <el-tag class="reel-tag" effect="plain" round>{{ row.reel || '未分卷' }}</el-tag>
              </template>
            </el-table-column>

            <el-table-column prop="chapter" label="章节标题" min-width="220" show-overflow-tooltip />

            <el-table-column label="字数" width="100">
              <template #default="{ row }">
                <span class="row-count">{{ (row.chapterData || '').length }}</span>
              </template>
            </el-table-column>

            <el-table-column label="事件状态" width="160">
              <template #default="{ row }">
                <span class="status-chip" :class="`status-chip--${statusKey(row.eventState)}`">
                  <span class="status-dot"></span>
                  {{ statusLabel(row.eventState) }}
                </span>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="220" align="right">
              <template #default="{ row }">
                <el-tooltip content="查看" placement="top">
                  <el-button text circle class="icon-action" @click="openViewDrawer(row)">
                    <el-icon><View /></el-icon>
                  </el-button>
                </el-tooltip>

                <el-tooltip content="清洗事件" placement="top">
                  <el-button
                    text
                    circle
                    class="icon-action"
                    :disabled="row.eventState === 0 && row.cleaningInline"
                    @click="cleanSingle(row)"
                  >
                    <el-icon><MagicStick /></el-icon>
                  </el-button>
                </el-tooltip>

                <el-tooltip content="编辑" placement="top">
                  <el-button text circle class="icon-action" @click="openEditDialog(row)">
                    <el-icon><EditPen /></el-icon>
                  </el-button>
                </el-tooltip>

                <el-tooltip content="删除" placement="top">
                  <el-button text circle class="icon-action delete" @click="handleDelete(row)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </el-tooltip>
              </template>
            </el-table-column>

            <template #empty>
              <el-empty description="该项目暂无章节，点击右上角新建" />
            </template>
          </el-table>
        </section>

        <div class="pagination-wrap">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="filteredNovels.length"
            layout="prev, pager, next, total"
            background
          />
        </div>
      </section>
    </div>

    <!-- 新增 / 编辑章节 -->
    <el-dialog
      v-model="formDialogVisible"
      :title="formDialogTitle"
      width="780px"
      destroy-on-close
      class="novel-dark-dialog"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        class="novel-form"
        label-position="top"
      >
        <div class="form-grid">
          <el-form-item label="章节序号" prop="chapterIndex">
            <el-input-number v-model="form.chapterIndex" :min="1" :max="9999" />
          </el-form-item>

          <el-form-item label="卷次" prop="reel">
            <el-input v-model="form.reel" placeholder="如：第一卷 · 风起" maxlength="60" />
          </el-form-item>
        </div>

        <el-form-item label="章节标题" prop="chapter">
          <el-input v-model="form.chapter" placeholder="如：第十二章 · 山雨欲来" maxlength="120" show-word-limit />
        </el-form-item>

        <el-form-item label="章节正文" prop="chapterData">
          <el-input
            v-model="form.chapterData"
            type="textarea"
            :rows="10"
            placeholder="粘贴章节正文（建议 500 字以上以便清洗事件）"
            maxlength="20000"
            show-word-limit
          />
        </el-form-item>

        <el-form-item v-if="formMode === 'edit'" label="清洗事件（可选编辑）" prop="event">
          <el-input
            v-model="form.event"
            type="textarea"
            :rows="6"
            placeholder="保存后系统会自动重新清洗，也可在此手动覆写"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="formDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 章节预览 / 事件清洗结果 -->
    <el-drawer
      v-model="viewDrawerVisible"
      :title="viewDrawerTitle"
      direction="rtl"
      size="62%"
      class="novel-dark-drawer"
    >
      <div v-if="viewingNovel" class="view-stack">
        <div class="view-field">
          <label class="view-field__label">章节名称</label>
          <div class="view-field__value view-field__value--single">
            {{ viewingNovel.chapter }}
          </div>
        </div>

        <div class="view-field">
          <div class="view-field__label-row">
            <label class="view-field__label">事件内容</label>
            <span class="status-chip" :class="`status-chip--${statusKey(viewingNovel.eventState)}`">
              <span class="status-dot"></span>
              {{ statusLabel(viewingNovel.eventState) }}
            </span>
          </div>

          <div v-if="viewingNovel.eventState === 1" class="view-field__value view-event">
            {{ viewingNovel.event }}
          </div>
          <div v-else-if="viewingNovel.eventState === -1" class="view-field__value view-error">
            <p>清洗失败：</p>
            <p>{{ viewingNovel.errorReason || '未知错误' }}</p>
          </div>
          <div v-else class="view-field__value view-empty">
            <el-empty description="尚未清洗，点击下方按钮生成事件" />
          </div>
        </div>

        <div class="view-field view-field--grow">
          <div class="view-field__label-row">
            <label class="view-field__label">章节内容</label>
            <span class="view-field__hint">{{ (viewingNovel.chapterData || '').length }} 字</span>
          </div>
          <div class="view-field__value view-text">
            <p
              v-for="(paragraph, idx) in splitParagraphs(viewingNovel.chapterData)"
              :key="idx"
            >
              {{ paragraph }}
            </p>
          </div>
        </div>

        <div class="view-actions">
          <el-button
            type="primary"
            :loading="viewingNovel.cleaningInline"
            @click="cleanSingle(viewingNovel)"
          >
            <el-icon><MagicStick /></el-icon>
            {{ viewingNovel.eventState === 1 ? '重新清洗' : '生成事件' }}
          </el-button>
        </div>
      </div>
    </el-drawer>

    <Settings v-model="settingsVisible" />
  </main>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Connection,
  Delete,
  Document,
  Download,
  EditPen,
  Folder,
  List,
  MagicStick,
  Plus,
  Reading,
  Search,
  Setting,
  Upload,
  View,
} from '@element-plus/icons-vue'
import Settings from '../components/Settings.vue'

type EventState = 0 | 1 | -1

interface NovelChapter {
  id: number
  projectId: number
  chapterIndex: number
  reel: string
  chapter: string
  chapterData: string
  event: string
  eventState: EventState
  errorReason: string | null
  cleaningInline?: boolean
  crawlSourceKey?: string  // 来源 key
  crawlNovelDirid?: string // 关联小说
  crawlChapterId?: number  // 章节 ID
  crawlTime?: string       // 章节时间
  crawlMd5?: string        // 正文内容哈希
}

const router = useRouter()
const tableRef = ref()
const formRef = ref<FormInstance>()

const CURRENT_PROJECT_ID = 1

const mockNovels: NovelChapter[] = [
  {
    id: 101,
    projectId: 1,
    chapterIndex: 1,
    reel: '第一卷 · 少年',
    chapter: '第一章 · 走出小镇',
    chapterData: '小镇坐落在群山之间，雨后泥土的气息混着青苔味弥漫开来。陈平安背着行囊，看着脚下一条蜿蜒山道，心中既忐忑又期待。山下的世界对他而言是陌生的，但少年没有回头，他知道，留在这里只会日复一日地重复着柴米油盐。出门前，宁姚的剑挂在他的腰间，她说过的那些话像风一样，吹散了他最后的犹豫。',
    event: '## 主要事件\n- 陈平安离开小镇，走上未知山道\n- 携带宁姚赠予的剑\n- 心理：忐忑与期待并存\n\n## 关键人物\n- 陈平安：少年主角，离乡远行\n- 宁姚：曾鼓励陈平安，赠剑相送\n\n## 场景\n- 雨后小镇山道',
    eventState: 1,
    errorReason: null,
  },
  {
    id: 102,
    projectId: 1,
    chapterIndex: 2,
    reel: '第一卷 · 少年',
    chapter: '第二章 · 山中逢老人',
    chapterData: '山道盘桓，少年走得腿酸脚软。一棵老槐树下，一名白须老者闭目静坐，听到脚步声后睁开眼，目光像剑一样落在陈平安身上。"小子，你这剑，配不上你。"老人开口便是一句没头没尾的话，陈平安一愣，却没有反驳。老人指着前方道路，淡淡道："往北三百里，有一座剑山，去那里。"',
    event: '## 主要事件\n- 陈平安在山中遇到神秘老者\n- 老者点评腰间之剑，并指引方向：往北三百里到剑山\n\n## 关键人物\n- 陈平安\n- 白须老者：身份不明，疑为高人\n\n## 场景\n- 山道上一棵老槐树下',
    eventState: 1,
    errorReason: null,
  },
  {
    id: 103,
    projectId: 1,
    chapterIndex: 3,
    reel: '第一卷 · 少年',
    chapter: '第三章 · 北望剑山',
    chapterData: '少年没有立刻动身。他在槐树下坐了一夜，反复思考老人那句话。天色微亮，他重新启程，每一步都带着某种新的笃定。山路渐陡，他偶尔回头，故乡的轮廓已经看不见了。他抚摸着腰间的剑，心想：宁姚，等我学到本事，再回去找你。',
    event: '',
    eventState: 0,
    errorReason: null,
  },
  {
    id: 104,
    projectId: 1,
    chapterIndex: 4,
    reel: '第一卷 · 少年',
    chapter: '第四章 · 山贼夜袭',
    chapterData: '夜色深沉，营地的篝火跳动着。少年裹着粗布毯子刚要入睡，远处传来异响。三个山贼从林中扑出，刀光在火光下显得格外刺眼。陈平安没有犹豫，握紧剑柄，他听到的不仅是风声，还有自己心跳的声音。',
    event: '',
    eventState: -1,
    errorReason: 'API 调用超时（30s），请稍后重试或检查网络',
  },
  {
    id: 105,
    projectId: 1,
    chapterIndex: 5,
    reel: '第二卷 · 远行',
    chapter: '第五章 · 渡河',
    chapterData: '一条黄褐色的河流横亘在前方，水势湍急。摆渡的老人嘴里叼着旱烟，懒洋洋地说道："五个铜板，过河。"陈平安摸了摸口袋，掏出最后几枚铜钱递了过去。船摇摇晃晃驶向对岸，他望着远处水雾中朦胧的山影，那里就是剑山。',
    event: '## 主要事件\n- 陈平安抵达大河，付费过渡\n- 远眺剑山方向\n\n## 关键人物\n- 陈平安\n- 摆渡老人：性格懒散\n\n## 场景\n- 黄褐色大河上的渡船',
    eventState: 1,
    errorReason: null,
  },
  {
    id: 106,
    projectId: 1,
    chapterIndex: 6,
    reel: '第二卷 · 远行',
    chapter: '第六章 · 剑山脚下',
    chapterData: '剑山脚下，石阶蜿蜒向上，一直消失在云雾里。山门前两位青衣弟子拦住了他："拜山者何人？"陈平安拱手："小镇陈平安，求一剑。"两人对视一眼，露出某种古怪的笑意，转身入山禀报。',
    event: '',
    eventState: 0,
    errorReason: null,
  },
]

const novels = ref<NovelChapter[]>(mockNovels.map((item) => ({ ...item })))
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(8)
const loading = ref(false)
const cleaning = ref(false)
const submitting = ref(false)

const selectedRows = ref<NovelChapter[]>([])

const formDialogVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingId = ref<number | null>(null)

const viewDrawerVisible = ref(false)
const viewingNovelId = ref<number | null>(null)

const settingsVisible = ref(false)

const importDialogVisible = ref(false)

const form = reactive({
  chapterIndex: 1,
  reel: '',
  chapter: '',
  chapterData: '',
  event: '',
})

const formRules: FormRules<typeof form> = {
  chapter: [{ required: true, message: '请输入章节标题', trigger: 'blur' }],
  chapterData: [{ required: true, message: '请输入章节正文', trigger: 'blur' }],
  chapterIndex: [{ required: true, message: '请填写章节序号', trigger: 'blur' }],
}

const filteredNovels = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return novels.value
    .filter((item) => (keyword ? item.chapter.toLowerCase().includes(keyword) : true))
    .sort((a, b) => a.chapterIndex - b.chapterIndex)
})

const pagedNovels = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredNovels.value.slice(start, start + pageSize.value)
})

const formDialogTitle = computed(() => (formMode.value === 'create' ? '新建章节' : '编辑章节'))

const viewingNovel = computed(() =>
  viewingNovelId.value ? novels.value.find((item) => item.id === viewingNovelId.value) ?? null : null,
)

const viewDrawerTitle = computed(() => (viewingNovel.value ? `章节预览：${viewingNovel.value.chapter}` : '章节预览'))

const statusKey = (state: EventState) => {
  if (state === 1) return 'success'
  if (state === -1) return 'error'
  return 'pending'
}

const statusLabel = (state: EventState) => {
  if (state === 1) return '已生成'
  if (state === -1) return '清洗失败'
  return '待清洗'
}

const splitParagraphs = (raw: string) => (raw || '').split(/\n+/).filter(Boolean)

const onSelectionChange = (rows: NovelChapter[]) => {
  selectedRows.value = rows
}

const nextChapterIndex = () => {
  if (novels.value.length === 0) return 1
  return Math.max(...novels.value.map((item) => item.chapterIndex)) + 1
}

const resetForm = () => {
  form.chapterIndex = nextChapterIndex()
  form.reel = ''
  form.chapter = ''
  form.chapterData = ''
  form.event = ''
}

const openCreateDialog = () => {
  formMode.value = 'create'
  editingId.value = null
  resetForm()
  formDialogVisible.value = true
}

const openEditDialog = (row: NovelChapter) => {
  formMode.value = 'edit'
  editingId.value = row.id
  form.chapterIndex = row.chapterIndex
  form.reel = row.reel
  form.chapter = row.chapter
  form.chapterData = row.chapterData
  form.event = row.event
  formDialogVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  await new Promise((resolve) => setTimeout(resolve, 200))

  if (formMode.value === 'create') {
    const newNovel: NovelChapter = {
      id: Date.now(),
      projectId: CURRENT_PROJECT_ID,
      chapterIndex: form.chapterIndex,
      reel: form.reel,
      chapter: form.chapter,
      chapterData: form.chapterData,
      event: '',
      eventState: 0,
      errorReason: null,
    }
    novels.value.push(newNovel)
    ElMessage.success('章节已新建，触发后台清洗')
    triggerMockClean(newNovel.id)
  } else if (editingId.value !== null) {
    const target = novels.value.find((item) => item.id === editingId.value)
    if (target) {
      target.chapterIndex = form.chapterIndex
      target.reel = form.reel
      target.chapter = form.chapter
      target.chapterData = form.chapterData
      if (form.event !== target.event) {
        target.event = form.event
        target.eventState = form.event ? 1 : 0
        target.errorReason = null
      }
      ElMessage.success('章节已更新')
    }
  }

  formDialogVisible.value = false
  submitting.value = false
}

const handleDelete = async (row: NovelChapter) => {
  try {
    await ElMessageBox.confirm(`确定删除「${row.chapter}」吗？删除后不可恢复。`, '删除章节', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'novel-dark-messagebox',
    })
    novels.value = novels.value.filter((item) => item.id !== row.id)
    ElMessage.success('章节已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error('删除失败')
  }
}

const batchDeleteSelected = async () => {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定批量删除 ${selectedRows.value.length} 个章节吗？`, '批量删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger',
      customClass: 'novel-dark-messagebox',
    })
    const ids = new Set(selectedRows.value.map((row) => row.id))
    novels.value = novels.value.filter((item) => !ids.has(item.id))
    selectedRows.value = []
    ElMessage.success('选中章节已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error('批量删除失败')
  }
}

const triggerMockClean = (id: number) => {
  const target = novels.value.find((item) => item.id === id)
  if (!target) return
  target.cleaningInline = true
  target.eventState = 0
  target.event = ''
  target.errorReason = null
  setTimeout(() => {
    if (target.chapterData.length < 80) {
      target.eventState = -1
      target.errorReason = '正文字数过少，无法提取有效事件'
    } else {
      target.eventState = 1
      target.event = `## 主要事件\n- 由「${target.chapter}」自动清洗生成（演示数据）\n- 共 ${target.chapterData.length} 字\n\n## 关键人物\n- 主角\n\n## 场景\n- 自动识别中...`
    }
    target.cleaningInline = false
  }, 1200)
}

const cleanSingle = (row: NovelChapter) => {
  if (row.cleaningInline) return
  triggerMockClean(row.id)
  ElMessage.info(`正在清洗「${row.chapter}」`)
}

const batchCleanSelected = async () => {
  if (selectedRows.value.length === 0) return
  cleaning.value = true
  const ids = selectedRows.value.map((row) => row.id)
  selectedRows.value = []
  for (const id of ids) {
    triggerMockClean(id)
    await new Promise((resolve) => setTimeout(resolve, 80))
  }
  ElMessage.success(`已提交 ${ids.length} 个章节进入清洗队列`)
  setTimeout(() => {
    cleaning.value = false
  }, 1500)
}

const openViewDrawer = (row: NovelChapter) => {
  viewingNovelId.value = row.id
  viewDrawerVisible.value = true
}

const goProject = () => {
  router.push('/project')
}

const showComingSoon = () => {
  ElMessage.info('功能开发中')
}

const openImportDialog = () => {
  ElMessage.info('功能开发中')
  importDialogVisible.value = true
}


const crawlDialogVisible = ref(false)

const openCrawlDialog = () => {
  ElMessage.info(`功能开发中`)
  crawlDialogVisible.value = true
}
</script>

<style scoped>
.novel-page {
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  padding: 16px;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  background:
    radial-gradient(circle at top, rgba(100, 116, 139, 0.18) 0%, rgba(11, 13, 16, 0) 32%),
    linear-gradient(180deg, #0d1117 0%, #0b0d10 100%);
}

.app-shell {
  height: calc(100vh - 32px);
  height: calc(100dvh - 32px);
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 16px;
}

.sidebar {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.side-top,
.side-bottom {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.brand {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: #0a0a0a;
  font-size: 20px;
  font-weight: 800;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, #f3d96b, #c4b5fd);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 6px 18px rgba(243, 217, 107, 0.18);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.brand:hover {
  transform: translateY(-1px);
}

.nav-btn {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 16px;
  color: #8b949e;
  background: transparent;
  cursor: pointer;
  font-size: 22px;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.nav-btn :deep(.el-icon) {
  font-size: 22px;
}

.nav-btn:hover {
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.05);
  transform: translateY(-1px);
}

.nav-btn.active {
  color: #dbeafe;
  border-color: rgba(37, 99, 235, 0.32);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.22), rgba(37, 99, 235, 0.12));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.main-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 24px 28px 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
  flex-shrink: 0;
}

.page-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  margin: 0;
  font-size: 32px;
  line-height: 1.1;
  font-weight: 800;
  background: linear-gradient(180deg, #ffffff 0%, #93a1b3 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.desc {
  margin: 6px 0 0;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.4;
}

.project-select {
  width: 220px;
}

.project-select :deep(.el-select__wrapper) {
  height: 38px;
  background-color: rgba(255, 255, 255, 0.04);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
  border-radius: 10px;
  color: #e6edf3;
}

.project-select :deep(.el-select__wrapper:hover) {
  background-color: rgba(255, 255, 255, 0.06);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset;
}

.project-select :deep(.el-select__wrapper.is-focused) {
  background-color: rgba(37, 99, 235, 0.08);
  box-shadow: 0 0 0 1px #2563eb inset;
}

.project-select :deep(.el-select__placeholder),
.project-select :deep(.el-select__selected-item) {
  color: #e6edf3;
}

.primary-button {
  height: 38px;
  padding: 0 16px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  background: #2563eb;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.18);
  transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.primary-button :deep(.el-icon) {
  margin-right: 0;
  font-size: 16px;
}

.primary-button:hover,
.primary-button:focus {
  background: #1d4ed8;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.28);
  transform: translateY(-1px);
}

.header-action {
  height: 38px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  color: #c5cdd6;
  background-color: rgba(255, 255, 255, 0.04);
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.header-action :deep(.el-icon) {
  margin-right: 0;
  font-size: 16px;
}

.header-action:hover,
.header-action:focus {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
  transform: translateY(-1px);
}

.header-action:active {
  transform: translateY(0);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.toolbar-spacer {
  flex: 1;
}

.search-input {
  max-width: 360px;
}

.toolbar :deep(.el-input__wrapper) {
  background-color: rgba(255, 255, 255, 0.04);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
  border-radius: 10px;
  transition: box-shadow 0.18s ease, background-color 0.18s ease;
}

.toolbar :deep(.el-input__wrapper:hover) {
  background-color: rgba(255, 255, 255, 0.06);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset;
}

.toolbar :deep(.el-input__wrapper.is-focus) {
  background-color: rgba(37, 99, 235, 0.08);
  box-shadow: 0 0 0 1px #2563eb inset;
}

.toolbar :deep(.el-input__inner) {
  color: #e6edf3;
}

.toolbar :deep(.el-input__inner::placeholder) {
  color: #6e7681;
}

.toolbar :deep(.el-input__prefix-inner .el-icon),
.toolbar :deep(.el-input__suffix-inner .el-icon) {
  color: #8b949e;
}

.toolbar :deep(.el-button) {
  height: 38px;
  padding: 0 16px;
  border-radius: 10px;
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.toolbar :deep(.el-button:hover:not(.is-disabled)) {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}

.toolbar :deep(.el-button.el-button--danger.is-plain) {
  background-color: rgba(248, 113, 113, 0.08);
  border-color: rgba(248, 113, 113, 0.32);
  color: #fca5a5;
}

.toolbar :deep(.el-button.el-button--danger.is-plain:hover:not(.is-disabled)) {
  background-color: rgba(248, 113, 113, 0.18);
  border-color: rgba(248, 113, 113, 0.45);
  color: #fecaca;
}

.toolbar :deep(.el-button.is-disabled) {
  opacity: 0.5;
  cursor: not-allowed;
}

.table-wrap {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.015);
}

.novel-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-border-color: rgba(255, 255, 255, 0.06);
  --el-table-border: 1px solid rgba(255, 255, 255, 0.06);
  --el-table-header-text-color: #c5cdd6;
  --el-table-text-color: #c5cdd6;
  --el-table-row-hover-bg-color: rgba(37, 99, 235, 0.08);
  background: transparent;
  height: 100%;
}

.novel-table :deep(thead th.el-table__cell) {
  background-color: rgba(255, 255, 255, 0.04);
  color: #c5cdd6;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-table :deep(td.el-table__cell),
.novel-table :deep(th.el-table__cell) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  background: transparent;
}

.novel-table :deep(tr.el-table__row--striped td.el-table__cell) {
  background: rgba(255, 255, 255, 0.012);
}

.novel-table :deep(tbody tr:hover > td.el-table__cell) {
  background-color: rgba(37, 99, 235, 0.08) !important;
}

.novel-table :deep(.el-checkbox__inner) {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.18);
}

.novel-table :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: #2563eb;
  border-color: #2563eb;
}

.novel-table :deep(.el-scrollbar__thumb) {
  background-color: rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.novel-table :deep(.el-scrollbar__thumb:hover) {
  background-color: rgba(255, 255, 255, 0.32);
}

.novel-table :deep(.el-scrollbar__bar.is-horizontal) {
  display: none;
}

.novel-table :deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-table :deep(.el-scrollbar__wrap::-webkit-scrollbar) {
  width: 6px;
  height: 0;
}

.novel-table :deep(.el-scrollbar__wrap::-webkit-scrollbar-track) {
  background: transparent;
}

.novel-table :deep(.el-scrollbar__wrap::-webkit-scrollbar-thumb) {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

.novel-table :deep(.el-scrollbar__wrap::-webkit-scrollbar-thumb:hover) {
  background-color: rgba(255, 255, 255, 0.24);
}

.row-index {
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  color: #93c5fd;
  font-size: 13px;
  font-weight: 600;
}

.row-count {
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  color: #8b949e;
  font-size: 12px;
}

.reel-tag {
  height: 24px;
  padding: 0 10px;
  font-size: 11px;
  font-weight: 500;
  color: #c4b5fd;
  border-color: rgba(167, 139, 250, 0.32);
  background: rgba(167, 139, 250, 0.12);
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  border: 1px solid transparent;
}

.status-chip .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  display: inline-block;
}

.status-chip--success {
  color: #86efac;
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.32);
}

.status-chip--success .status-dot {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.6);
}

.status-chip--pending {
  color: #fde68a;
  background: rgba(234, 179, 8, 0.1);
  border-color: rgba(234, 179, 8, 0.32);
}

.status-chip--pending .status-dot {
  background: #eab308;
  box-shadow: 0 0 6px rgba(234, 179, 8, 0.6);
}

.status-chip--error {
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.1);
  border-color: rgba(248, 113, 113, 0.32);
}

.status-chip--error .status-dot {
  background: #f87171;
  box-shadow: 0 0 6px rgba(248, 113, 113, 0.6);
}

.icon-action {
  width: 30px;
  height: 30px;
  font-size: 15px;
  color: #8b949e;
  border-radius: 8px;
  --el-fill-color-light: transparent;
  --el-fill-color: transparent;
  --el-color-info: #93c5fd;
  transition: color 0.2s ease, background-color 0.2s ease, transform 0.2s ease;
}

.icon-action :deep(.el-icon) {
  font-size: 15px;
}

.icon-action:hover,
.icon-action:focus {
  color: #93c5fd;
  background-color: rgba(59, 130, 246, 0.14);
  transform: translateY(-1px);
}

.icon-action.delete {
  --el-color-info: #fca5a5;
}

.icon-action.delete:hover,
.icon-action.delete:focus {
  color: #fca5a5;
  background-color: rgba(248, 113, 113, 0.16);
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 14px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.pagination-wrap :deep(.el-pagination.is-background .btn-prev),
.pagination-wrap :deep(.el-pagination.is-background .btn-next),
.pagination-wrap :deep(.el-pagination.is-background .el-pager li) {
  color: #8b949e;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 13px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.pagination-wrap :deep(.el-pagination.is-background .el-pager li.is-active) {
  color: #fff;
  border-color: #2563eb;
  background: #2563eb;
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.22);
}

.pagination-wrap :deep(.el-pagination__total) {
  color: #8b949e;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: 13px;
}

.novel-form {
  padding-right: 8px;
}

.form-grid {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 0 18px;
}

.view-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 4px;
  height: 100%;
  min-height: 0;
}

.view-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}

.view-field--grow {
  flex: 1;
  min-height: 220px;
}

.view-field__label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.view-field__label {
  font-size: 13px;
  font-weight: 600;
  color: #d5dce4;
  letter-spacing: 0.2px;
}

.view-field__hint {
  font-size: 12px;
  color: #6e7681;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
}

.view-field__value {
  padding: 12px 14px;
  border-radius: 10px;
  background-color: #0c1015;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #e6edf3;
  font-size: 14px;
  line-height: 1.7;
}

.view-field__value--single {
  padding: 10px 14px;
  min-height: 42px;
  display: flex;
  align-items: center;
}

.view-field__value.view-empty {
  padding: 8px 0;
  background: transparent;
  border: 1px dashed rgba(255, 255, 255, 0.08);
}

.view-empty :deep(.el-empty) {
  --el-empty-padding: 10px 0;
  --el-empty-description-margin-top: 8px;
}

.view-empty :deep(.el-empty__image) {
  width: 56px;
}

.view-empty :deep(.el-empty__description p) {
  color: #8b949e;
  font-size: 12px;
}

.view-text {
  flex: 1;
  overflow-y: auto;
  color: #c5cdd6;
  font-size: 14px;
  line-height: 1.8;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.view-text::-webkit-scrollbar,
.view-event::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.view-text::-webkit-scrollbar-track,
.view-event::-webkit-scrollbar-track {
  background: transparent;
}

.view-text::-webkit-scrollbar-thumb,
.view-event::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.view-text::-webkit-scrollbar-thumb:hover,
.view-event::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.view-text::-webkit-scrollbar-corner,
.view-event::-webkit-scrollbar-corner {
  background: transparent;
}

.view-text p {
  margin: 0 0 12px;
}

.view-text p:last-child {
  margin-bottom: 0;
}

.view-event {
  max-height: 200px;
  overflow-y: auto;
  color: #d5dce4;
  font-size: 13px;
  line-height: 1.7;
  background: rgba(34, 197, 94, 0.04);
  border-color: rgba(34, 197, 94, 0.22);
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  white-space: pre-wrap;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.view-error {
  background: rgba(248, 113, 113, 0.06);
  border-color: rgba(248, 113, 113, 0.22);
  color: #fca5a5;
  font-size: 13px;
  line-height: 1.7;
}

.view-error p {
  margin: 0 0 6px;
}

.view-error p:last-child {
  margin-bottom: 0;
}

.view-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 6px;
}

.view-actions :deep(.el-button) {
  border-radius: 10px;
}

@media (max-width: 1080px) {
  .view-field--grow {
    min-height: 180px;
  }
}

@media (max-width: 820px) {
  .app-shell {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .sidebar {
    flex-direction: row;
    padding: 12px 14px;
  }

  .side-top,
  .side-bottom {
    width: auto;
    flex-direction: row;
    gap: 10px;
  }

  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .page-header__right {
    flex-direction: column;
    align-items: stretch;
  }

  .project-select {
    width: 100%;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style>
/* novel 页专用暗色弹窗、下拉与抽屉（element-plus teleport 到 body，需置于非 scoped 块） */
.novel-dark-dialog {
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 24px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.novel-dark-dialog .el-dialog__header {
  margin: 0;
  padding: 22px 28px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-dark-dialog .el-dialog__title {
  color: #f2f4f8;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.4px;
}

.novel-dark-dialog .el-dialog__headerbtn {
  top: 16px;
  right: 20px;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
}

.novel-dark-dialog .el-dialog__headerbtn .el-dialog__close {
  color: #8b949e;
  font-size: 20px;
}

.novel-dark-dialog .el-dialog__headerbtn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.18);
}

.novel-dark-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: #ffffff;
}

.novel-dark-dialog .el-dialog__body {
  padding: 22px 28px 8px;
  color: #b8c2cc;
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-dark-dialog .el-dialog__body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.novel-dark-dialog .el-dialog__body::-webkit-scrollbar-track {
  background: transparent;
}

.novel-dark-dialog .el-dialog__body::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.novel-dark-dialog .el-dialog__body::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

.novel-dark-dialog .el-dialog__footer {
  padding: 16px 28px 22px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-dark-dialog .el-form-item__label {
  color: #d5dce4;
  font-size: 14px;
  font-weight: 600;
  padding: 0 0 8px;
}

.novel-dark-dialog .el-input__wrapper,
.novel-dark-dialog .el-select__wrapper,
.novel-dark-dialog .el-input-number .el-input__wrapper {
  min-height: 42px;
  padding: 0 14px;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border-radius: 10px;
  color: #e6edf3;
  font-size: 14px;
}

.novel-dark-dialog .el-textarea__inner {
  min-height: 120px;
  padding: 12px 14px;
  background-color: #0c1015;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
  border: none;
  border-radius: 10px;
  color: #e6edf3;
  font-size: 14px;
  line-height: 1.65;
  font-family: inherit;
  resize: vertical;
}

.novel-dark-dialog .el-input__wrapper:hover,
.novel-dark-dialog .el-textarea__inner:hover,
.novel-dark-dialog .el-select__wrapper:hover {
  background-color: #0e131a;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.22) inset;
}

.novel-dark-dialog .el-input__wrapper.is-focus,
.novel-dark-dialog .el-textarea__inner:focus,
.novel-dark-dialog .el-select__wrapper.is-focused {
  background-color: #0d1219;
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.55) inset,
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.novel-dark-dialog .el-input__inner,
.novel-dark-dialog .el-textarea__inner {
  color: #e6edf3;
}

.novel-dark-dialog .el-input__inner::placeholder,
.novel-dark-dialog .el-textarea__inner::placeholder {
  color: #7e8893;
}

.novel-dark-dialog .el-input__count,
.novel-dark-dialog .el-input__count-inner,
.novel-dark-dialog .el-input .el-input__count,
.novel-dark-dialog .el-textarea .el-input__count {
  color: #6e7681 !important;
  background: transparent !important;
  background-color: transparent !important;
  font-size: 12px;
}

.novel-dark-dialog .el-textarea .el-input__count {
  bottom: 8px;
  right: 12px;
}

.novel-dark-dialog .el-dialog__footer .el-button {
  height: 40px;
  min-width: 88px;
  padding: 0 20px;
  border-radius: 10px;
  font-weight: 700;
}

.novel-dark-dialog .el-dialog__footer .el-button:not(.el-button--primary) {
  background-color: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.12);
  color: #e6edf3;
}

.novel-dark-dialog .el-dialog__footer .el-button:not(.el-button--primary):hover {
  background-color: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.22);
  color: #ffffff;
}

.novel-dark-dialog .el-dialog__footer .el-button--primary {
  background-color: #2563eb;
  border-color: #2563eb;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
}

.novel-dark-dialog .el-dialog__footer .el-button--primary:hover {
  background-color: #1d4ed8;
  border-color: #1d4ed8;
}

/* select 浮层 */
.novel-dark-select.el-popper {
  background-color: #14181f;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
}

.novel-dark-select.el-popper .el-select-dropdown__list {
  padding: 6px 4px;
}

.novel-dark-select.el-popper .el-select-dropdown__item {
  color: #c5cdd6;
  border-radius: 8px;
  margin: 2px 4px;
  padding: 0 12px;
  height: 32px;
  line-height: 32px;
}

.novel-dark-select.el-popper .el-select-dropdown__item:hover,
.novel-dark-select.el-popper .el-select-dropdown__item.is-hovering {
  background-color: rgba(255, 255, 255, 0.06);
  color: #ffffff;
}

.novel-dark-select.el-popper .el-select-dropdown__item.is-selected {
  color: #93c5fd;
  background-color: rgba(37, 99, 235, 0.16);
  font-weight: 600;
}

.novel-dark-select.el-popper .el-popper__arrow::before {
  background-color: #14181f;
  border-color: rgba(255, 255, 255, 0.08);
}

/* multiple 模式下浮层选项的"已选" 状态（element-plus 多选下拉的勾选指示） */
.novel-dark-select.el-popper .el-select-dropdown__item.is-selected::after {
  color: #93c5fd;
}

/* multiple select 输入框内的已选 tag、折叠 tag 暗色风格 */
.novel-dark-dialog .el-select__wrapper .el-select__selected-item .el-tag,
.novel-dark-dialog .el-select .el-select__tags-text + .el-tag,
.novel-dark-dialog .el-select__wrapper .el-tag {
  background-color: rgba(37, 99, 235, 0.14);
  border-color: rgba(37, 99, 235, 0.4);
  color: #93c5fd;
  font-weight: 500;
}

.novel-dark-dialog .el-select__wrapper .el-tag .el-tag__close,
.novel-dark-dialog .el-select__wrapper .el-tag .el-icon {
  color: #93c5fd;
  background-color: transparent;
}

.novel-dark-dialog .el-select__wrapper .el-tag .el-tag__close:hover {
  background-color: rgba(37, 99, 235, 0.32);
  color: #ffffff;
}

/* collapse-tags-tooltip 浮层（鼠标 hover 已选 + N 标签时显示的全部已选项）暗色风格 */
.el-popper.is-dark.el-tooltip__popper.el-select__popper--multiple,
.el-popper.is-dark[role="tooltip"] {
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #e6edf3;
}

.el-popper.is-dark[role="tooltip"] .el-popper__arrow::before {
  background: #14181f;
  border-color: rgba(255, 255, 255, 0.12);
}

/* el-table show-overflow-tooltip 浮层（章节标题超长时） */
.novel-cell-tooltip.el-popper {
  max-width: 520px;
  padding: 10px 14px;
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  color: #e6edf3;
  font-size: 13px;
  line-height: 1.7;
}

.novel-cell-tooltip.el-popper .el-popper__arrow::before {
  background-color: #14181f;
  border-color: rgba(255, 255, 255, 0.12);
}

/* drawer 暗色 */
.novel-dark-drawer {
  background: linear-gradient(180deg, #12161b 0%, #0f141a 100%);
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.novel-dark-drawer .el-drawer__header {
  margin: 0;
  padding: 22px 24px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: #f2f4f8;
  font-size: 18px;
  font-weight: 700;
}

.novel-dark-drawer .el-drawer__close-btn {
  color: #8b949e;
}

.novel-dark-drawer .el-drawer__close-btn:hover {
  color: #ffffff;
}

.novel-dark-drawer .el-drawer__body {
  padding: 18px 24px 24px;
  background: transparent;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.14) transparent;
}

.novel-dark-drawer .el-drawer__body::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.novel-dark-drawer .el-drawer__body::-webkit-scrollbar-track {
  background: transparent;
}

.novel-dark-drawer .el-drawer__body::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  transition: background-color 0.18s ease;
}

.novel-dark-drawer .el-drawer__body::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.24);
}

/* messagebox 暗色 */
.novel-dark-messagebox {
  background: linear-gradient(180deg, #14181f 0%, #0d1117 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  color: #e6edf3;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.novel-dark-messagebox .el-message-box__header {
  padding: 18px 24px 8px;
}

.novel-dark-messagebox .el-message-box__title {
  color: #e6edf3;
  font-weight: 700;
}

.novel-dark-messagebox .el-message-box__content {
  padding: 8px 24px 18px;
  color: #b8c2cc;
}

.novel-dark-messagebox .el-message-box__btns {
  padding: 12px 24px 18px;
  background: rgba(255, 255, 255, 0.015);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.novel-dark-messagebox .el-message-box__btns .el-button {
  border-radius: 8px;
}

.novel-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger) {
  background-color: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #c5cdd6;
}

.novel-dark-messagebox .el-message-box__btns .el-button:not(.el-button--primary):not(.el-button--danger):hover {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}

</style>