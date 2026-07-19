# Korean Cinematic Art and Rule Survival Styles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-ready Korean semi-realistic cinematic illustration style and a reusable rule-survival challenge director manual, including original preview images and repository integration checks.

**Architecture:** Keep visual rendering rules under `data/skills/art_list` and narrative direction rules under `data/skills/director_manual`. Reuse the existing filesystem discovery mechanism and established Markdown/image package layouts; do not modify backend or frontend code.

**Tech Stack:** Markdown skill manuals, PNG preview assets, existing Python/FastAPI filesystem readers, shell validation commands, image generation tooling.

---

## File map

### Create

- `data/skills/art_list/korean_semi_realistic_cinematic/README.md`: complete visual style manual.
- `data/skills/art_list/korean_semi_realistic_cinematic/images/character_turnaround_sheet.png`: character continuity sample.
- `data/skills/art_list/korean_semi_realistic_cinematic/images/landscape_four_states_sheet.png`: environment continuity sample.
- `data/skills/art_list/korean_semi_realistic_cinematic/images/scene_character_in_landscape.png`: client cover and representative cinematic sample.
- `data/skills/director_manual/Rule_survival_challenge/README.md`: director package overview.
- `data/skills/director_manual/Rule_survival_challenge/director_manual/director_planning_narrative.md`: macro narrative planning manual.
- `data/skills/director_manual/Rule_survival_challenge/director_manual/director_storyboard_table_narrative.md`: shot-table execution manual.
- `data/skills/director_manual/Rule_survival_challenge/images/concept_image_prompt.md`: director concept image prompt.
- `data/skills/director_manual/Rule_survival_challenge/images/director_concept.png`: original director concept image.

### Modify

- `data/skills/art_list/README.md`: add the new visual style to the animation/comics index.
- `data/skills/art_list/STYLE_TAXONOMY.md`: add selection and key-control guidance.
- `data/skills/director_manual/README.md`: add the new director package to the root index.

### Preserve

- `data/skills/art_list/2D_korean_webtoon/**`
- `backend/**`
- `frontend/**`
- all existing user changes shown by `git status`

The repository ignores `data/skills`, so commits for these files must use `git add -f` with explicit paths.

---

### Task 1: Add the visual style manual and indexes

**Files:**
- Create: `data/skills/art_list/korean_semi_realistic_cinematic/README.md`
- Modify: `data/skills/art_list/README.md`
- Modify: `data/skills/art_list/STYLE_TAXONOMY.md`

- [ ] **Step 1: Verify the visual style does not already exist**

Run:

```bash
test ! -e data/skills/art_list/korean_semi_realistic_cinematic
```

Expected: exit code `0`.

- [ ] **Step 2: Create the visual style manual**

Use this exact front matter:

```yaml
---
name: korean_semi_realistic_cinematic
description: 艺术风格手册 · 韩系电影级半写实插画风 — 定义该动画/漫画风格在商用定位、视觉DNA、角色/场景/道具资产规范、分镜与视频提示词、质量验收和风险规避上的生成方法。适用于都市情感、悬疑、规则闯关、轻幻想和现代剧情，突出近写实骨相、精修数字绘画、弱线稿、电影光影与浅景深。
metaData: art_style
---
```

Follow the existing ten-section art manual structure:

Use this exact document title:

```markdown
# 韩系电影级半写实插画风（Korean semi-realistic cinematic illustration）艺术风格手册
```

1. `商用定位`
2. `风格视觉 DNA`
3. `全局提示词结构`
4. `角色资产规范`
5. `场景资产规范`
6. `道具资产规范`
7. `分镜与视频规范`
8. `商用质量验收`
9. `风险词改写规则`
10. `使用边界`

Use this exact global style anchor in the positive templates:

```text
Korean semi-realistic cinematic illustration, polished digital painting,
near-realistic anatomy and facial structure, subtly idealized refined features,
soft matte skin rendered through light and shadow, clean focus-dependent edges,
detailed grouped hair strands, cinematic motivated lighting,
shallow depth of field, atmospheric perspective, restrained color grading
```

Use this exact base negative block:

```text
no flat webtoon coloring, no thick comic outlines, no cel shading,
no photorealistic camera look, no waxy skin, no plastic doll face,
no 3D render appearance, no exaggerated anime proportions,
no identical generic faces, no excessive beauty filter,
no text, no subtitles, no logo, no watermark
```

Add asset-specific continuity rules:

- Character: fix face shape, eye spacing, nose/lip structure, hairstyle silhouette, body proportions, costume tailoring, main colors, and one original identifier.
- Scene: fix architecture, entrances, action area, key prop positions, camera axis, and motivated light direction.
- Prop: fix scale, construction, surface, wear, state changes, and interaction points.
- Shot/video: specify shot size, camera height, movement start/end, duration, action, emotion, 35mm/50mm/85mm equivalent focal length, and continuity.

Keep the primary medium as digital illustration. Explicitly reject `RAW photo`, `DSLR photo`, `documentary photography`, `CGI`, and generic `3D render` as primary style descriptors.

- [ ] **Step 3: Add the visual style to both root indexes**

In `data/skills/art_list/README.md`, add this row under `动画/漫画`, immediately after `2D_korean_webtoon`:

```markdown
| `korean_semi_realistic_cinematic` | 韩系电影级半写实插画风 | Korean semi-realistic cinematic illustration | 都市情感、悬疑、规则闯关、轻幻想、现代剧情 |
```

In `data/skills/art_list/STYLE_TAXONOMY.md`, add this row under `动画/漫画`, immediately after `2D_korean_webtoon`:

```markdown
| `korean_semi_realistic_cinematic` | 韩系电影级半写实插画风 | 都市情感、悬疑、规则闯关、轻幻想、现代剧情 | 精修数字绘画；近写实骨相、弱线稿、有来源电影光、浅景深与克制调色 |
```

- [ ] **Step 4: Validate the visual manual**

Run:

```bash
rg -n "^name: korean_semi_realistic_cinematic$|^metaData: art_style$|Korean semi-realistic cinematic illustration|no flat webtoon coloring|35mm|50mm|85mm" data/skills/art_list/korean_semi_realistic_cinematic/README.md
rg -n "korean_semi_realistic_cinematic" data/skills/art_list/README.md data/skills/art_list/STYLE_TAXONOMY.md
rg -n "全球高考|游惑|秦究|TBD|TODO" data/skills/art_list/korean_semi_realistic_cinematic data/skills/art_list/README.md data/skills/art_list/STYLE_TAXONOMY.md
```

Expected:

- The first two commands find every required marker.
- The final command returns no matches and exits with code `1`.

- [ ] **Step 5: Commit the visual manual and indexes**

```bash
git add -f data/skills/art_list/korean_semi_realistic_cinematic/README.md data/skills/art_list/README.md data/skills/art_list/STYLE_TAXONOMY.md
git diff --cached --check
git commit -m "feat: add Korean cinematic illustration style"
```

Expected: one commit containing only the visual manual and its two index changes.

---

### Task 2: Generate and validate the visual style samples

**Files:**
- Create: `data/skills/art_list/korean_semi_realistic_cinematic/images/character_turnaround_sheet.png`
- Create: `data/skills/art_list/korean_semi_realistic_cinematic/images/landscape_four_states_sheet.png`
- Create: `data/skills/art_list/korean_semi_realistic_cinematic/images/scene_character_in_landscape.png`

- [ ] **Step 1: Generate the character turnaround sheet**

Generate one original 1920×1080 image with this prompt:

```text
Create a professional 16:9 character design sheet for one entirely original adult East Asian male character, age about 27, calm analytical presence, lean realistic build, distinct long oval face with a firm jaw, slightly hooded amber-brown eyes, straight nose, restrained expression, ash-black layered hair swept back with two loose front strands. Wardrobe: tailored deep navy high-collar overcoat, pale gray shirt, muted teal tie, dark trousers, matte leather shoes, one small original geometric silver cuff detail with no letters or emblem. Show full-body front, full-body side, full-body back, three-quarter portrait, six compact expression studies, fabric and hair detail callouts. Keep identity, face, body, hair, and clothing exactly consistent across every view. Korean semi-realistic cinematic illustration, polished digital painting, near-realistic anatomy and facial structure, subtly idealized refined features, soft matte skin rendered through light and shadow, clean focus-dependent edges, detailed grouped hair strands, restrained cool-gray and navy palette, soft motivated studio lighting. Clean warm-gray design-board background, balanced grid, no readable annotations. No flat webtoon coloring, no thick comic outlines, no cel shading, no photorealistic camera look, no waxy skin, no plastic doll face, no 3D render appearance, no exaggerated anime proportions, no identical duplicate faces, no text, no logo, no watermark, no copyrighted character.
```

- [ ] **Step 2: Generate the four-state environment sheet**

Generate one original 1920×1080 image with this prompt:

```text
Create a professional 16:9 environment design sheet showing the exact same original grand transit-hall interior in four equally sized cinematic states: clear late afternoon, rainy night with warm practical lamps, controlled anomalous activation with subtle geometric light patterns and stopped clocks, and quiet post-crisis dawn with minor recoverable damage. The architecture must remain identical across all four panels: central stair, two side corridors, tall arched windows, circular information platform with blank surfaces, brass-and-stone material language, fixed entrances and action zones. Korean semi-realistic cinematic illustration, polished digital painting, realistic perspective, painterly stone, glass, metal and wet-floor reflections, cinematic motivated lighting, atmospheric perspective, restrained color grading, clear foreground/midground/background, usable character staging space. No people, no readable signage, no letters, no numbers, no logo, no watermark. No flat webtoon coloring, no thick comic outlines, no cel shading, no photorealistic camera look, no plastic 3D render appearance, no architecture drift between panels, no inconsistent camera axis.
```

- [ ] **Step 3: Generate the representative cover image**

Generate one original 1920×1080 image with this prompt:

```text
Create an original 16:9 cinematic medium close-up in an elegant contemporary hotel conservatory at night. An entirely original adult East Asian man, about 27, with a distinct long oval face, firm jaw, slightly hooded amber-brown eyes, straight nose, ash-black layered hair swept back with two loose strands, sits in a dark leather lounge chair and calmly studies a small blank brass token held near his lap. He wears a tailored deep navy high-collar overcoat, pale gray shirt and muted teal tie with a small geometric silver cuff detail. Frame from mid-torso upward at a natural three-quarter angle, 85mm-equivalent portrait perspective, eyes in sharp focus, hands anatomically correct. Background: glass conservatory, warm chandelier bokeh, softly blurred guests as indistinct silhouettes, cool night beyond the windows. Korean semi-realistic cinematic illustration, polished digital painting, near-realistic anatomy and facial structure, subtly idealized refined features, soft matte skin rendered through light and shadow, clean focus-dependent edges, detailed grouped hair strands, cinematic motivated key light from camera-left, soft fill, restrained rim light, shallow depth of field, atmospheric perspective, restrained cool-gray and warm-gold color grading. No flat webtoon coloring, no thick comic outlines, no cel shading, no photorealistic camera look, no waxy skin, no plastic doll face, no 3D render appearance, no exaggerated anime proportions, no text, no subtitles, no logo, no watermark, no copyrighted character, no copied composition.
```

- [ ] **Step 4: Inspect and correct all visual samples**

Inspect each image visually. Reject and regenerate any image that has:

- visible text, numbers, subtitles, logo, watermark, or signature;
- flat webtoon/cel shading, thick outlines, photorealistic photography, or plastic 3D appearance;
- identity drift, broken anatomy, duplicate expression faces, or inconsistent clothing;
- environment architecture drift across the four states;
- cover composition that does not clearly show the B-direction balance of illustration and cinematic realism.

Run:

```bash
file data/skills/art_list/korean_semi_realistic_cinematic/images/*.png
sips -g pixelWidth -g pixelHeight data/skills/art_list/korean_semi_realistic_cinematic/images/*.png
```

Expected: three PNG files; every file reports `pixelWidth: 1920` and `pixelHeight: 1080`.

- [ ] **Step 5: Commit the visual samples**

```bash
git add -f data/skills/art_list/korean_semi_realistic_cinematic/images/character_turnaround_sheet.png data/skills/art_list/korean_semi_realistic_cinematic/images/landscape_four_states_sheet.png data/skills/art_list/korean_semi_realistic_cinematic/images/scene_character_in_landscape.png
git commit -m "feat: add Korean cinematic style samples"
```

Expected: one commit containing exactly three PNG files.

---

### Task 3: Add the rule-survival director package

**Files:**
- Create: `data/skills/director_manual/Rule_survival_challenge/README.md`
- Create: `data/skills/director_manual/Rule_survival_challenge/director_manual/director_planning_narrative.md`
- Create: `data/skills/director_manual/Rule_survival_challenge/director_manual/director_storyboard_table_narrative.md`
- Create: `data/skills/director_manual/Rule_survival_challenge/images/concept_image_prompt.md`
- Modify: `data/skills/director_manual/README.md`

- [ ] **Step 1: Verify the director package does not already exist**

Run:

```bash
test ! -e data/skills/director_manual/Rule_survival_challenge
```

Expected: exit code `0`.

- [ ] **Step 2: Create the package README**

Use the title:

```markdown
# 规则生存闯关 · 导演叙事手法技能包
```

Use this core table:

```markdown
| 维度 | 要求 |
|---|---|
| 类型核心 | 规则识别、试错验证、漏洞破局、群像协作、系统谜团 |
| 离场感受 | 高压释放后能够复盘规则与线索，并相信角色靠观察、勇气和协作赢得出口 |
| 规划重点 | 关卡目标、规则层级、违规代价、信息分工、长线回收、关系阶段和节奏释放 |
| 分镜重点 | 观众信息、角色信息、规则状态、空间证据、动作因果、时长、声音和连续性 |
```

Document the exact package tree, usage order, combination with `art_list`, and commercial boundary.

- [ ] **Step 3: Create the planning manual**

Use this exact front matter:

```yaml
---
name: director_planning_narrative
description: 叙事手法技法 · 规则生存闯关 — 定义规则生存闯关在封闭环境、规则层级、试错代价、漏洞破局、群像分工、系统长线、关系回收和压力节奏上的导演规划方法。适用于任何视觉风格。
metaData: director_manual
---
```

Create these sections:

1. `商业定位`
2. `主题立意与人物内核`
3. `单元关卡八段结构`
4. `长线系统谜团与单元回收`
5. `典型场景设计矩阵`
6. `群像分工与双主角关系`
7. `声音与音乐方向`
8. `构图与景别叙事`
9. `镜头运动与段落节奏`
10. `常见失败模式与修正`
11. `商用验收清单`
12. `与视觉风格的组合规则`

The eight stages must be:

```text
异常进入 → 规则公布 → 首次验证 → 代价显现
→ 信息分工 → 漏洞发现 → 反向破局 → 余波回收
```

Require every solution to come from previously visible rules, prop state, spatial evidence, sound evidence, or character action. Prohibit last-minute rules, unexplained rescue, random sacrifice, and exposition-only solutions.

Use this relationship progression:

```text
能力对峙 → 被迫合作 → 行动默契 → 记忆回响 → 共同选择
```

Use dry humor and group kindness as pressure-release tools; do not turn the genre into continuous horror or everyday sweet romance.

- [ ] **Step 4: Create the storyboard execution manual**

Use this exact front matter:

```yaml
---
name: director_storyboard_table_narrative
description: 分镜表叙事手法 · 规则生存闯关 — 定义规则生存闯关在规则展示、试错因果、空间证据、倒计时压力、群像分工、漏洞回收和破局动作上的分镜执行方法。适用于任何视觉风格。
metaData: director_manual
---
```

Require the standard fields plus these four rule-state fields in the narrative guidance:

```text
观众已知规则
角色已知规则
当前验证状态
违规代价或漏洞证据
```

Do not change the backend JSON schema. These concepts must be expressed inside existing `description`, `action`, `lighting`, `sound`, and continuity guidance rather than adding output keys.

Define:

- shot selection for rule boards, timers, props, entrances, paths, reactions, and spatial changes;
- complete test-action chain: setup → action → trigger → consequence → reaction;
- 180-degree axis and direction continuity for group movement;
- readable duration for rules and evidence;
- stable shots for decisive choices;
- faster cutting only after spatial orientation is established;
- visual or sound callbacks for loophole revelation.

- [ ] **Step 5: Create the concept image prompt**

Write this prompt in `images/concept_image_prompt.md`:

```text
# 规则生存闯关 概念图提示词

1920:1080 横向电影画幅，原创规则生存闯关场景；一座封闭的旧式公共交通大厅在深夜进入异常状态，所有出口同时关闭，中央无字信息台发出克制的几何冷光，墙上多个无数字圆盘停在不同角度。前景两名原创成年主角并肩检查一枚空白黄铜通行牌和地面光线边界，一人观察结构，一人保护行动路线；中景四名不同年龄的原创队员分别记录变化、看守入口、照顾受惊成员和验证安全距离；背景拱窗外没有可辨城市，侧廊深处保留一个可能的出口。导演重点：规则证据必须可见，空间关系可复盘，团队分工清楚，倒计时压力通过灯光与动作表现，双主角关系通过站位和默契体现；画面高压但不猎奇，不展示露骨伤害。可叠加任意视觉风格；无可读文字、无数字、无标志、无品牌、无知名 IP、无真实人物。
```

- [ ] **Step 6: Add the director package to the root index**

In `data/skills/director_manual/README.md`, add this row after `Mystery_thriller`:

```markdown
| `Rule_survival_challenge` | 规则生存闯关 | 适用于任何视觉风格，通过规则识别、试错验证、漏洞破局、群像协作与系统长线谜团，讲述人物如何在受控环境中主动争取出口。 |
```

- [ ] **Step 7: Validate the director package**

Run:

```bash
rg -n "^metaData: director_manual$|异常进入|规则公布|首次验证|代价显现|信息分工|漏洞发现|反向破局|余波回收|能力对峙|共同选择" data/skills/director_manual/Rule_survival_challenge
rg -n "Rule_survival_challenge" data/skills/director_manual/README.md
rg -n "全球高考|游惑|秦究|TBD|TODO" data/skills/director_manual/Rule_survival_challenge data/skills/director_manual/README.md
```

Expected:

- The first two commands find all required markers.
- The final command returns no matches and exits with code `1`.

- [ ] **Step 8: Commit the director documents**

```bash
git add -f data/skills/director_manual/Rule_survival_challenge/README.md data/skills/director_manual/Rule_survival_challenge/director_manual/director_planning_narrative.md data/skills/director_manual/Rule_survival_challenge/director_manual/director_storyboard_table_narrative.md data/skills/director_manual/Rule_survival_challenge/images/concept_image_prompt.md data/skills/director_manual/README.md
git diff --cached --check
git commit -m "feat: add rule survival director manual"
```

Expected: one commit containing five Markdown files.

---

### Task 4: Generate and validate the director concept image

**Files:**
- Create: `data/skills/director_manual/Rule_survival_challenge/images/director_concept.png`

- [ ] **Step 1: Generate the director concept image**

Generate one original 1920×1080 image with this prompt:

```text
Create an original 16:9 cinematic rule-survival challenge concept scene in a sealed old public transit hall at night. Every exit is visibly closed. A circular blank information platform in the center emits restrained cool geometric light; several wall-mounted blank circular dials are stopped at different angles with no letters or numbers. In the foreground, two entirely original adult East Asian protagonists stand side by side: one studies a blank brass transit token and the floor-light boundary while the other watches the corridor and protects the route. In the midground, four original teammates of varied adult ages perform clearly different functions: recording spatial changes on blank cards, guarding an entrance, calming a frightened teammate, and testing a safe distance with a plain rope. In the background, tall arched windows reveal featureless darkness and one side corridor remains a possible exit. Make rule evidence visible, spatial relationships easy to reconstruct, team roles readable, and countdown pressure implied through lighting changes and body action. Korean semi-realistic cinematic illustration, polished digital painting, near-realistic anatomy, subtly idealized features, motivated cold-and-warm cinematic lighting, atmospheric perspective, controlled depth of field, restrained color grading. High pressure without gore, no exposed injury, no horror jump scare. No readable text, no letters, no numbers, no logo, no brand, no watermark, no copyrighted character, no recognizable existing scene, no photorealistic camera look, no flat webtoon coloring, no plastic 3D render.
```

- [ ] **Step 2: Inspect and correct the director concept**

Reject and regenerate if:

- rules and spatial relationships cannot be understood from the image;
- the two leads or four team functions are visually merged;
- the image contains text, letters, numbers, logo, watermark, recognizable IP, gore, or a copied composition;
- the result becomes generic horror instead of active observation and cooperation.

Run:

```bash
file data/skills/director_manual/Rule_survival_challenge/images/director_concept.png
sips -g pixelWidth -g pixelHeight data/skills/director_manual/Rule_survival_challenge/images/director_concept.png
```

Expected: PNG, `pixelWidth: 1920`, `pixelHeight: 1080`.

- [ ] **Step 3: Commit the director concept**

```bash
git add -f data/skills/director_manual/Rule_survival_challenge/images/director_concept.png
git commit -m "feat: add rule survival director concept"
```

Expected: one commit containing exactly one PNG file.

---

### Task 5: Run three-round final verification

**Files:**
- Verify: all files created or modified in Tasks 1–4

- [ ] **Step 1: Round 1 — structure and text contract**

Run:

```bash
test -f data/skills/art_list/korean_semi_realistic_cinematic/README.md
test -f data/skills/art_list/korean_semi_realistic_cinematic/images/character_turnaround_sheet.png
test -f data/skills/art_list/korean_semi_realistic_cinematic/images/landscape_four_states_sheet.png
test -f data/skills/art_list/korean_semi_realistic_cinematic/images/scene_character_in_landscape.png
test -f data/skills/director_manual/Rule_survival_challenge/README.md
test -f data/skills/director_manual/Rule_survival_challenge/director_manual/director_planning_narrative.md
test -f data/skills/director_manual/Rule_survival_challenge/director_manual/director_storyboard_table_narrative.md
test -f data/skills/director_manual/Rule_survival_challenge/images/concept_image_prompt.md
test -f data/skills/director_manual/Rule_survival_challenge/images/director_concept.png
rg -n "^metaData: art_style$" data/skills/art_list/korean_semi_realistic_cinematic/README.md
rg -n "^metaData: director_manual$" data/skills/director_manual/Rule_survival_challenge/director_manual/*.md
```

Expected: all commands exit `0`.

- [ ] **Step 2: Round 2 — image dimensions and visual QA**

Run:

```bash
sips -g pixelWidth -g pixelHeight data/skills/art_list/korean_semi_realistic_cinematic/images/*.png data/skills/director_manual/Rule_survival_challenge/images/director_concept.png
```

Expected: four images; every image reports `1920×1080`.

Visually inspect all four files again and confirm:

- consistent Korean semi-realistic cinematic illustration medium;
- no text, subtitle, logo, watermark, real person, or recognizable IP;
- no flat webtoon, camera-photo, wax figure, or plastic 3D drift;
- usable character continuity, environment continuity, and rule-scene readability.

- [ ] **Step 3: Round 3 — service discovery**

Run from the repository root:

```bash
PYTHONPATH=backend backend/.venv/bin/python -c "from app.services.project import _read_visual_style, _read_director_manual; visual = _read_visual_style('korean_semi_realistic_cinematic'); director = _read_director_manual('Rule_survival_challenge'); assert visual.style_path == 'korean_semi_realistic_cinematic'; assert any(file.path == 'README.md' and '# 韩系电影级半写实插画风' in file.content for file in visual.files); assert {image.filename for image in visual.images} == {'character_turnaround_sheet.png', 'landscape_four_states_sheet.png', 'scene_character_in_landscape.png'}; assert director.manual_path == 'Rule_survival_challenge'; assert director.name.startswith('规则生存闯关'); assert {image.filename for image in director.images} == {'director_concept.png'}; print('visual and director packages load successfully')"
```

Expected:

```text
visual and director packages load successfully
```

- [ ] **Step 4: Run related backend regression tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/app/tests/test_project_service.py backend/app/tests/test_project_router.py -q
```

Expected: all selected tests pass. If an existing unrelated failure occurs, record the failing test and confirm it does not touch the new data directories before deciding whether any in-scope correction is needed.

- [ ] **Step 5: Check the final diff boundary**

Run:

```bash
git status --short
git log --oneline -5
git diff --check 5df1d00..HEAD
```

Expected:

- new commits contain only the two approved skill packages, indexes, samples, and plan;
- pre-existing backend, frontend, and database worktree changes remain uncommitted and untouched;
- no whitespace errors.
