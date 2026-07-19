# 韩系电影级半写实视觉风格与规则生存闯关导演手册设计

## 1. 目标

新增两个可独立选择、可组合使用的通用技能包：

- 视觉风格：`korean_semi_realistic_cinematic`
- 导演风格：`Rule_survival_challenge`

视觉风格用于生成接近参考图质感的韩系电影级半写实数字插画。导演风格用于规则驱动、封闭空间、生存闯关、群像协作和长线系统谜团类故事。

保留现有 `2D_korean_webtoon`，不改变已绑定该风格的项目。新技能包不得包含具体作品名、角色名、考场设定、品牌、平台或可识别 IP 元素。

## 2. 设计依据

### 2.1 参考图视觉拆解

参考图的目标特征为：

- 弱线稿或无线稿，以明暗和边缘控制塑造形体。
- 接近真实的人体比例、骨相和透视，五官适度理想化。
- 柔和哑光皮肤、成组发束、克制高光和精修服装材质。
- 有明确来源的电影布光、浅景深、空气透视和背景散景。
- 画面保留数字绘画质感，不生成真人摄影或塑料 3D 效果。

该目标与现有 `2D_korean_webtoon` 的细线稿、网络漫画媒介和平滑平涂存在明确差异，应作为独立视觉风格管理。

### 2.2 规则生存闯关类型依据

《全球高考》的公开作品简介将故事概括为高危险性考试、失控系统、团队闯关、真实与虚幻交错、过去与现在并行，以及逐步发现系统真相。整部长线同时包含规则验证、单元破局、身份记忆、群像协作和双主角关系推进。

现有导演手册只能覆盖部分能力：

- `Mystery_thriller` 可覆盖线索公平、信息差和真相重排，但不包含规则试错、副本循环和系统惩罚。
- `Horror_supernatural` 可覆盖异常规则和空间压迫，但整体偏向等待恐惧，不适合主动拆解规则和强者博弈。
- `Psychological_drama` 可辅助失忆与认知错位，但不能承担主要闯关结构。
- `Sweet_romance_novel` 的关系节奏偏日常甜宠，不适合双强对峙、行动默契与共同反叛。

项目当前只绑定一个 `director_manual`，无法组合多个导演手册。因此，为整部长线适配新增通用 `Rule_survival_challenge`；只制作单个悬疑关卡时仍可使用 `Mystery_thriller`。

参考来源：

- 晋江文学城作品页：<https://www.jjwxc.net/onebook.php?novelid=3419133>
- 北京服装学院图书馆馆藏简介：<https://libopac.bift.edu.cn/bookInfo_01h0473832.html>

## 3. 文件结构

```text
data/skills/art_list/korean_semi_realistic_cinematic/
├── README.md
└── images/
    ├── character_turnaround_sheet.png
    ├── landscape_four_states_sheet.png
    └── scene_character_in_landscape.png

data/skills/director_manual/Rule_survival_challenge/
├── README.md
├── images/
│   ├── concept_image_prompt.md
│   └── director_concept.png
└── director_manual/
    ├── director_planning_narrative.md
    └── director_storyboard_table_narrative.md
```

更新以下索引：

- `data/skills/art_list/README.md`
- `data/skills/art_list/STYLE_TAXONOMY.md`
- `data/skills/director_manual/README.md`

不修改后端和前端发现机制。现有服务按配置根目录枚举子目录，新目录创建后即可被读取。

## 4. 职责边界

### 4.1 视觉风格负责

- 人物比例、骨相、五官理想化程度和身份连续性。
- 弱线稿或无线稿、数字绘画材质和焦点边缘控制。
- 皮肤、发丝、布料、玻璃、金属和环境材质。
- 色彩、光源方向、景深、散景、空气透视和电影调色。
- 角色、场景、道具、分镜和视频提示词模板。

### 4.2 导演风格负责

- 规则公布、验证、违规代价、漏洞发现和反向破局。
- 观众信息、角色信息和规则状态的分层管理。
- 单元关卡与系统级长线谜团的同步推进。
- 群像分工、双主角关系阶段、节奏释放和声音策略。
- 导演规划和分镜表执行规范。

视觉手册不得规定故事结构。导演手册不得规定线条、材质、固定配色或具体画风。

## 5. 视觉风格设计

### 5.1 商用定位

| 维度 | 设计 |
|---|---|
| 中文名称 | 韩系电影级半写实插画风 |
| 英文通用词 | Korean semi-realistic cinematic illustration |
| 风格分类 | 动画/漫画 |
| 适用内容 | 都市情感、悬疑、规则闯关、轻幻想、现代剧情 |
| 情绪基调 | 克制、精致、冷静、电影化 |
| 媒介基础 | 精修数字绘画与电影构图 |
| 轮廓系统 | 弱线稿或无线稿，使用焦点相关的软硬边缘 |
| 材质系统 | 柔和哑光皮肤、成组发束、细腻布料、克制反射 |
| 光影系统 | 有来源的主光、柔和补光、克制轮廓光、浅景深 |
| 色彩系统 | 中性肤色、冷灰暗部、暖色实景灯、低至中饱和 |

### 5.2 核心风格锚点

```text
Korean semi-realistic cinematic illustration, polished digital painting,
near-realistic anatomy and facial structure, subtly idealized refined features,
soft matte skin rendered through light and shadow, clean focus-dependent edges,
detailed grouped hair strands, cinematic motivated lighting,
shallow depth of field, atmospheric perspective, restrained color grading
```

不得使用会将结果推向真人摄影的 `RAW photo`、`DSLR photo`、`documentary photography` 等主媒介词。可使用焦段和景深描述镜头，但最终媒介必须保持为数字插画。

### 5.3 提示词顺序

```text
主体与叙事动作
→ 风格锚点
→ 固定人物身份与骨相
→ 服装和材质
→ 场景空间
→ 有来源的电影布光
→ 镜头焦段、景别和景深
→ 连续性约束
→ 安全与质量负向约束
```

推荐镜头控制：

- 35mm 等效焦段：空间建立、群像走位和环境关系。
- 50mm 等效焦段：双人互动和中景叙事。
- 85mm 等效焦段：人物近景、微表情和参考图式肖像。

### 5.4 负向约束

```text
no flat webtoon coloring, no thick comic outlines, no cel shading,
no photorealistic camera look, no waxy skin, no plastic doll face,
no 3D render appearance, no exaggerated anime proportions,
no identical generic faces, no excessive beauty filter,
no text, no subtitles, no logo, no watermark
```

各资产模板继续包含身份漂移、解剖错误、手部错误、透视错误、光源矛盾和场景结构漂移等针对性约束。

## 6. 规则生存闯关导演设计

### 6.1 类型定位

角色被置于封闭或受控环境，在有限时间内识别规则、验证代价、发现漏洞，并通过协作与选择突破规则。多个单元关卡持续回收为一条系统级长线谜团。

### 6.2 单元关卡结构

1. 异常进入：建立封闭空间、任务目标和退出条件。
2. 规则公布：区分明确规则、隐含规则和疑似误导。
3. 首次验证：通过可见行动测试规则，不用旁白代替过程。
4. 代价显现：违规结果改变团队策略，避免猎奇伤害展示。
5. 信息分工：角色分别承担观察、推理、执行、保护和质疑。
6. 漏洞发现：解法来自此前可见线索与规则冲突。
7. 反向破局：角色主动利用规则，不等待外部救援。
8. 余波回收：本关结束，同时留下关系变化或系统主线证据。

### 6.3 长线控制

- 每个关卡解决一个局部目标，并推进一条系统真相。
- 身份和记忆谜团通过物件、动作、声源与空间记忆逐层回收。
- 双主角关系按“能力对峙 → 被迫合作 → 行动默契 → 记忆回响 → 共同选择”推进。
- 感情通过站位、视线、交接道具和替对方承担风险等动作表达，不套用甜宠桥段。
- 高压段落之间保留冷幽默、群像善意和现实感，避免全程阴暗恐怖。

### 6.4 分镜执行

- 用全景保存可复盘的空间、人物位置和规则关系。
- 规则、计时、关键道具和违规结果必须给足可读镜头。
- 试错镜头完整呈现动作起点、规则触发、结果和人物反应。
- 漏洞揭示回用前文构图或声源，但改变其意义。
- 破局高潮可提高剪辑密度，关键选择落点使用稳定镜头。
- 每条分镜明确观众信息、角色信息、当前规则状态和连续性。

## 7. 原创样张

所有样张使用原创人物、原创场景和原创道具，不复制参考图构图，不包含字幕、界面头像、平台标识或水印。

### 7.1 视觉风格样张

- `character_turnaround_sheet.png`：原创东亚成年角色的正面、侧面、背面、三分之二视角、六种表情和服装材质细节。
- `landscape_four_states_sheet.png`：同一原创场景的日间、雨夜、异常启动和破局后四种状态。
- `scene_character_in_landscape.png`：原创角色置于精致室内环境的电影近景，使用 85mm 人像透视、暖色散景和浅景深，作为项目页面封面。

### 7.2 导演概念图

`director_concept.png` 展示原创封闭公共空间中的规则异常、倒计时压力、团队分工和双主角协作。画面必须让规则证据、人物站位和行动目标可分镜，不使用任何具体作品场景。

## 8. 生成偏差与修正

| 偏差 | 修正 |
|---|---|
| 偏平涂韩漫 | 降低线稿权重，强化明暗塑形、软硬边缘和数字绘画材质 |
| 偏真人摄影 | 移除摄影媒介词，强化 cinematic illustration 和 polished digital painting |
| 偏塑料 3D | 移除 render、CGI 等词，强化哑光皮肤、绘画边缘和克制反射 |
| 人物同脸 | 增加脸型、眉眼距离、鼻唇结构和原创识别点 |
| 背景抢主体 | 降低背景对比和细节锐度，强化焦点层级与空气透视 |
| 规则场景不可读 | 增加空间建立镜头、规则证据位置和角色行动区 |
| 破局依赖新设定 | 把解法改为前文已经可见的规则冲突、道具状态或空间变化 |

不稳定样张必须调整提示词并重新生成，不作为最终交付。

## 9. 验收与验证

### 9.1 文档检查

- Front matter 的 `name`、`description` 和 `metaData` 与现有文件格式一致。
- 视觉手册保持现有十节主结构，导演技能包保持 README、规划手册、分镜手册和概念图提示词结构。
- 根目录索引包含新目录、中文名称、英文通用词、适用方向和关键控制。
- 扫描具体作品名、角色名、品牌名、平台名、残留占位符和风险词。

### 9.2 视觉检查

- 四张 PNG 均为 1920×1080。
- 视觉风格三张图可识别为同一媒介和同一质量等级。
- 封面图符合 B 方向：近写实骨相、数字绘画、弱线稿、柔化皮肤、电影光影和浅景深。
- 不出现字幕、标志、水印、真实人物或可识别 IP。

### 9.3 集成检查

- 后端视觉风格枚举能够读取 `korean_semi_realistic_cinematic`。
- 后端导演手册枚举能够读取 `Rule_survival_challenge`。
- 客户端可通过固定文件名读取 `scene_character_in_landscape.png` 作为视觉风格封面。
- 运行相关测试、格式检查、差异检查和最小加载验证。

### 9.4 三轮验证

1. 检查文件结构、Front matter、索引和安全命名。
2. 检查全部样张尺寸、画面内容和风格一致性；不合格则重新生成。
3. 运行服务层枚举测试和最小加载验证，确认两个技能包可被项目选择。

## 10. 非目标

- 不修改现有 `2D_korean_webtoon` 或任何已绑定项目。
- 不新增第三方依赖。
- 不改变视觉风格或导演手册的后端 API、数据库字段和前端交互。
- 不把具体小说改写为通用手册内容。
- 不复制参考截图、现有商业角色、知名场景或作品构图。
