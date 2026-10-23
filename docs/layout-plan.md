# 列表区布局改造（Phase 10）实施计划

> 状态：进行中。Step 1 已完成，Step 2/3 排队。每步一个提交，可单独 revert。

## 1. 背景与诉求

用户截图反馈（items 与 containers 两个 Tab 同样适用）：

| # | 现象 | 诉求 |
|---|---|---|
| 1 | 主区顶部「💼 My Warehouse」上方一大块空白 | 收紧 |
| 2 | 下滚到底，工具栏与列表之间出现空地 | 列表吃满剩余高度，页面本身不滚动 |
| 3 | 「View Mode」标签与「◉ List ○ Cards」分两行；页面右侧出现滚动条 | 标签+选项平铺一行；整页不需滚动 |
| 4 | 容器 Tab 顶部空地 +「Container Management」整行 | 该行可删；View Mode 同样平铺 |
| 5 | 不同显示器（1080p / 4K / 窗口缩放） | 列表高度自适应，列表自己内部滚 |
| 6 | Streamlit 自带的表格全屏按钮不合期望 | 「列表全屏」= **表格铺满主内容区**（用户红框区域），而非只在页面内放大网格 |
| 7 | 「+ Add Item」贴最右、「+ Add Container」在底部工具栏，两处位置不一致 | 两者都放到**浏览态控制行**，并在主内容区内**水平居中**（与吸底工具栏中心线一致） |

## 2. 已确认决策

1. **View Mode**：标签移除、只留选项（按反馈）；radio 自带 label 折叠（`label_visibility="collapsed"`）保留可访问性。
2. **表格下方提示**（💡 Click the checkboxes to select rows…）：保留原位。
3. **列表全屏范围**：表格铺满主内容区（红框区域）；侧边栏保留可见；标题/Tab 栏/View Mode 行/提示/工具栏隐藏；按钮 + ESC 退出。
4. items 与 containers 行为一致。
5. 分步实施，每步独立验证、可单独回滚。

## 3. 目标布局

```
┌ sidebar ┐┌───────── 主区（整页无滚动条）─────────┐
│ Language││ 💼 My Warehouse                      │
│         ││ Items Dashboard Timeline Tags Tree Containers
│ Global  ││ ◉ List ○ Cards   [ + Add Item ]  ← Step1：一行 + 居中（View Mode 标签已去）
│ Filter  ││┌──────────────────────────────────────┐│
│         │││ 列表：吃满剩余高度，自己滚             ││  ← Step2：高度视口自适应
│ Search  │││ （1080p / 4K / 缩放 自动适配）        ││
│ Tags    │││                                      ││
│         ││└──────────────────────────────────────┘│
│ SQL     ││ 💡 Click the checkboxes...            │  ← 保留原位
│         ││ [View][Edit][Delete][Export]  2882,0  │  ← fixed 底部工具栏
│ Last    │└───────────────────────────────────────┘
└─────────┘
容器 Tab 目标 = 同上，且无 "Container Management" 行
全屏态（Step 3）= 表格铺满整个主内容区，其余 chrome 全隐
```

## 4. 现状关键代码位置（改前索引）

- `app.py:33-76` 全局 `<style>`：工具栏 `position:fixed` + `section[data-testid="stMain"] { padding-bottom: 80px }`
- `app.py:81-112` JS 同步组件：写入 `--toolbar-left/width/bg`，监听 resize + MutationObserver
- `ui/items_tab.py` 浏览态 View Mode 行（`st.columns([2,1])` + radio + Add 按钮）
- `ui/items_tab.py` `render_list_view`：`st.dataframe(..., height=300)`
- `ui/containers_tab.py` `render()` 开头 `st.subheader(i18n.t("containers.title"))`
- `ui/containers_tab.py` 浏览态 View Mode 行
- `ui/containers_tab.py` `render_browse`：`st.dataframe(..., height=300)`

## 5. 分步计划

### Step 1 去废行 + 顶部留白（低风险）

- `app.py`：`<style>` 收紧主区顶部。根因：Streamlit 在 `.stMainBlockContainer` 上由 styled 生成的 class 施加顶部 padding（wide 默认 2.1rem；`addPaddingForHeader` 时 = `headerHeight+md` = 4.75rem），普通选择器覆盖会被压过 → 用 `!important`；外层 `stAppViewContainer` / `stMain` 也一并清零避免叠加。主区顶部收到恰好 = header 高度(3.75rem) + 4px 间隙（内容紧贴 header 下方）。
- **全宽 header 收进主内容区**：`section[data-testid="stHeader"]` 原为 `position:fixed;left:0;right:0` 独占整行窗体；改为 `left: var(--toolbar-left,21rem); width: var(--toolbar-width,...); right:auto`，即只覆盖主内容区（与吸底工具栏同宽），不再压住整行——侧边栏顶部释放，视觉上顶部更紧。
- `ui/items_tab.py` / `ui/containers_tab.py`：浏览态控制行包 `st.container(key=...)`，三列 `[5,2,5]`——左列放 radio（`label_visibility="collapsed"`，标签不显示但保留可访问性），中列放「新增」按钮（列中心在主内容区 50% 处，与吸底工具栏中心线一致）。**View Mode 标签按反馈移除，只留选项。**
- `ui/containers_tab.py`：删除 `st.subheader(i18n.t("containers.title"))`；「➕ 新增容器」从底部工具栏（原 col_tool4）移到控制行，工具栏改 4 列 `[3,3,3,5]`（详情/编辑/删除/计数）；`i18n.py` 移除中英 `containers.title` 死 key。
- **收益附带**：卡片视图下容器 Tab 原先没有新增入口（工具栏只在列表视图渲染），移到控制行后列表/卡片都有。
- **验收**：AppTest 断言浏览态 radio 仍为 1 个、两个新增按钮都在、0 异常；e2e 全绿（标签文本断言已改查按钮存在）；用户本地目视确认。
- **风险**：低。`label_visibility="collapsed"`、`st.container(key=)` 在 Streamlit 1.40 可用；`!important` 覆盖 Streamlit 内联/生成 class 为通用手法。

### Step 1.5 顶部空白实测收敛（selenium 无头实测，已完成）

用户截图反馈「顶部红框区域整条去掉」。此轮不再推断，直接用 selenium + 本机 Chrome 无头
打开应用量 DOM，拿到每层真实几何，找到三处空间来源并逐一消除：

| 来源 | 实测占位 | 处理 |
|---|---|---|
| block 容器 `padding-top` | Streamlit styled class 施加（wide 2.1rem / `addPaddingForHeader` 4.75rem / `showPadding` 6rem），普通选择器压不过 | `!important` 压到 `2.375rem`（= 最终 header 高 36px + 2px 间隙，按用户「能更紧就更紧」反馈二次收紧） |
| **CSS 注入 markdown 的元素容器** | 高 41.6px + flex gap 16px = **57.6px 纯浪费** | 包进 `st.container(key="css_inject")` 后整体 `display:none`——`<style>` 在隐藏容器内依然全局生效（已实测：块内 padding 修改仍生效） |
| **`components.html` 同步 iframe 的元素容器** | iframe 本身高 0，但元素容器占 25.6px + gap 16px = **41.6px** | 挪进同一 `css_inject` 隐藏容器；隐藏 iframe 的 JS 照常执行（实测变量仍被写入） |

**header 两个关键修正：**

1. **选择器错误**：header 实测是 `<header data-testid="stHeader">`（`z-index:999990`、
   `position:fixed`），此前写成 `section[...]` 导致上一轮的「收进主区」规则**从未生效**。
2. **高度压缩**：3.75rem(60px) → 2.5rem(40px) → **2.25rem(36px)（用户反馈二次收紧）**——
   Deploy 按钮实高 32px、原在 header 内 `top:20px`，把 `[data-testid="stToolbar"]` 上移到
   `top:2px` 后 36px 足够容纳（按钮 2..34，底边贴 header 底）。

**同步 JS 增强（隐藏容器内 iframe 执行更早，会量到侧边栏渲染前的全宽 left=0 且此后无属性
变化可再触发，导致 header/工具栏错位到全宽）**：`sync()` 触发点补齐 `load` 事件、
`[0,100,300,800,1500]ms` 延迟重试，并新增 `ResizeObserver` 观察主区——侧边栏折叠/展开
只改主区宽度、不伴随属性变化，属性观察抓不到，宽度观察可以（已实测：把侧边栏宽度压成 0，
header 与工具栏同步跟随到 `left=0/w=1904`）。

**实测结果（selenium，1920×900 视口）**：

- 主区标题 top：**121.6px → 38px**（首轮收敛 44px，用户反馈「能更紧就更紧」后二次收紧至 38；
  用户截图环境实测约 156px，因其 block padding 走了 Streamlit 默认 6rem 路径）；
  stTabs top 210.4 → 126.8，一屏多显示约两行表格数据。
- header：`left=336, w=1568, h=36`——与吸底工具栏（`left=336, w=1568`）完全对齐，
  不再独占整行窗体，侧边栏顶部随之释放。用户确认 Deploy/⋮ 正常可点。
- 隐藏容器（`css_inject`，`display:none, h=0`）内 `<style>` 与 iframe JS 均正常生效。
- 回归：i18n 17、data-layer 139、smoke 224 项、e2e 全部 PASS（AppTest 在隔离副本实测）。

**遗留（不影响诉求）**：顶部约 5px 的主题装饰线 `stDecoration` 仍为全窗宽（用户截图红框
顶边即它），属主题点缀非空白；`stSidebarCollapseButton` 实测 0×0 不可交互，为 Streamlit
1.40 自身行为、与本次改动无关（改动前后截图均无折叠箭头）。

**TODO（微调项，待用户确认）**：Deploy 按钮「贴边」——header 已压到 36px、按钮 2..34，底边
已贴 header 底；若要更紧只能让按钮与 header 上下边距对称（如 top:2 不变，header 不变；
或进一步把按钮上移、header 降到 32px 让按钮正好填满）。属纯视觉微调、风险极低，未做以
免误伤点击热区；用户明确要再紧时一行改动即可。

### Step 2 表格高度视口自适应（核心，中风险）—— 已完成

思路：JS 实测「表格可用高度」→ 写 CSS 变量 → CSS `!important` 覆盖 `stDataFrameResizable` 的内联高度（`height:300px`）。

- `ui/items_tab.py` / `ui/containers_tab.py`：用 `st.container(key="item_list_wrap")` / `st.container(key="container_list_wrap")` 包住 `st.dataframe`（获得稳定类名供 CSS/JS 定位）；`height` 参数保留 300 作兜底（无 JS 时）。
- `app.py` `<style>`：
  ```css
  .st-key-item_list_wrap [data-testid="stDataFrameResizable"],
  .st-key-container_list_wrap [data-testid="stDataFrameResizable"] {
      height: var(--list-avail-h, 300px) !important;
  }
  ```
- `app.py` JS（扩展现有 sync）新增 `calcListHeight()`（**v2.1 自校正公式**）：
  `avail = 当前表高 + (stMain盒高 − stMain.padding-bottom(80) − 20缓冲 − 流内末元素底边)`
  流内末元素底边 = 表格/提示 alert 中更靠下者（自动涵盖表与 alert 间 margin 及模型外占位）。
  触发：初次 / 延迟重试 / `ResizeObserver`(main) / `MutationObserver`(main, childList+subtree) /
  **父窗口 resize 监听**（隐藏 iframe 收不到自身 resize，窗口缩放后必须靠它重算）。
- **五个实测踩坑（均有 selenium 数据）**：
  1. 同步脚本在 `css_inject` 隐藏 iframe 内执行，iframe 自身 viewport 高 0 → 视口相关量必须取父窗口。
  2. **`stMain` 才是真正滚动容器**（`overflow:auto`），根元素 scrollHeight 恒等于视口高——
     v2 曾据 `scrollingElement.scrollHeight` 自校正，slack 恒 0 导致表格一路缩到下限，方向全错。
  3. **滚动污染**：v1 用「视口高 − 表顶(视口坐标)」，stMain 滚动过再重算会把滚动量当内容高、
     表格越算越大（用户环境滚动条/大空区/提示行被顶走的根源）。v2.1 全部改用相对 main
     盒模型的差值，滚动量在差值中抵消；表顶瞬态守卫同样用差值（top 差 < 50 跳过）。
  4. **block 容器默认 11rem(176px) 底部内边距**——「滚到底出现大空区」的直接来源，
     已归零（吸底工具栏避让由 stMain 的 80px 承担）。
  5. Streamlit 非激活 Tab 面板仍留在 DOM（隐藏），querySelector 按文档序会命中隐藏的物品
     wrap（高 0）→ 必须遍历挑可见的那个；吸底工具栏贴底(bottom:0)还会给 main 贡献 ~3px
     溢出 → `bottom:4px` 抬离底边消掉。
- **实测结果（selenium，1920 宽）**：物品/容器两 Tab 在视口高 631/749/1149/549 下表高
  211/329/729/129px，`stMain.scrollHeight − clientHeight = 0`（零溢出、无滚动条、无空区），
  且「滚到底 + 触发重算」后表高增长 0（滚动污染根除）。`avail≥100` 才写变量；无 JS 回退 300px。
  i18n 17 / data-layer 139 / smoke / e2e 全绿。
- **Step 2.5 提示行紧凑化（用户反馈：上下等距、贴紧吸底按钮）**：
  两个 Tab 的选中提示包 `st.container(key="list_hint" / "container_hint")`；CSS 紧凑化——
  实高盒是 `[data-testid="stAlertContainer"]`（默认 padding 16/16 + 内容行 24 = 56px，
  外壳 `.stAlert` 不带实高，pad 打错层会白加 6px），压到 4/4 + 字号 0.82rem + 图标 15px
  ≈ 32px；容器对称负外边距（上 −15/下 −12，配平实测基础间隙 24/9→9/9）；
  主区 padding-bottom 80→46（配平式：提示行定点 = main高−46−JS缓冲20，距工具栏顶恰 9px，
  高度公式动态读 computed padding-bottom 故无需动 JS）。
  实测：提示行 56→32px、上下间隙 9/9、mainOver=0，表格反而多得 ~33px。
  表格容器不存在时（卡片视图/详情页）不计算。
- **验收**：e2e 全绿且卡片视图不受影响；用户本地确认 1080p 全屏无页面滚动条、4K 表格更高、缩放连续自适应。
- **风险与降级**：`!important` 覆盖 Streamlit 内联高度，升级版本可能失效 → 选择器与理由写注释；失效时退回 `height=300`（页面可滚，不破功能）。

### Step 3 列表全屏（中风险）—— 已完成

思路：View Mode 行加「⛶ 全屏」按钮 → 切 `st.session_state.list_fullscreen` + rerun；session_state 经隐藏容器注入 `:root { --list-fullscreen: 1|0 }`；同步 JS 读该变量给 `body` toggle class `wh-list-fullscreen` 驱动全屏 CSS。

- `ui/items_tab.py` / `ui/containers_tab.py`：浏览态控制行列改为 `[5,2,3,2]`，第 4 列放「⛶ 全屏」按钮——**仅列表视图渲染**（卡片视图无表格，误入全屏会一片空白）。
- `app.py`：
  - `fs_state` 隐藏容器：`st.markdown("<style>:root{--list-fullscreen:0|1}</style>")` 把 session_state 透传给前端（同 css_inject 模式隐藏，避免占顶部间隙）。
  - `fs_exit` 浮动退出按钮：常驻 DOM（默认 display:none，全屏态 fixed 右上角显示），点击清 `list_fullscreen`；容器 `width:max-content`（fixed 容器 + use_container_width 子按钮会互相撑成整行宽）。
  - 全屏 CSS：隐藏页面标题(`stHeadingWithActionElements`)、**仅 Tab 栏**(`stTabs [role=tablist]`)、header、两个控制行、提示行；**吸底工具栏保留**（用户反馈：全屏选中行后仍需 查看详情/编辑/删除/导出）并 z-index 1002 压在表格 1001 之上；表格 wrap `fixed + top:0 + height:calc(100vh - 57px) + left/width 复用 --toolbar-*`（57 = 工具栏 53 + bottom 4，预留避免末行被工具栏遮住下半）。
  - JS：`applyFullscreen()` 读变量切 body class；主区 MutationObserver 加 `characterData`（变量由 `<style>` 文本注入、非 :root inline style，`:root` style 观察者收不到）；ESC 监听 → 找 `.st-key-fs_exit button` click()。
- **四个实测踩坑（均有 selenium 数据）**：
  1. **面板在 stTabs 容器内**：整块 `stTabs{display:none}` 会把当前表格面板一起灭掉（计算高度正常但 offsetHeight=0，前四轮"fixed 塌缩"全是它的假象）→ 只隐藏 `[role=tablist]`。
  2. **flex-basis:0 压过 height**：Streamlit 给 wrap/resizable 设 `flex:1 1 0`，flex 主轴尺寸优先于 `height`，`height:100vh` 不生效（表格 26px）→ `flex:none !important` 解除。
  3. **嵌套 flex 下百分比高度不解析**：resizable `height:100%` 塌成内容高 12px → 改 `100vh` 基准。
  4. **普通流有 82px 杂项占位**（fs_state 容器 + 2px 分隔线 + tabpanel padding 16 + flex gap 16），把流内表格顶下去、底部裁掉 82px → 表格 fixed 出流（top:0/height:100vh 基准），无视全部流内杂项。
- **实测（selenium，1920×900）**：进入全屏表格 fixed top=0、高 689 = 746−57（底部精确预留工具栏），工具栏可见 `z-index 1002`、顶边 689 = 表格底边 689 零重叠、4 个操作按钮常驻（未选中禁用同正常态）；标题/Tab 栏/控制行/提示隐藏、侧边栏保留、退出按钮可见；ESC 与浮动按钮两条退出路径都精确恢复（表高 367）；容器 Tab 同样验证通过。smoke / e2e / i18n 17 / data-layer 139 全绿。
  注：全屏态 calcListHeight 被「表顶−主区顶 < 50」守卫自动跳过（表格 fixed 后表顶=主区顶），不会污染正常态表高。
- **Step 3.1 微调（用户反馈）**：
  1. 退出按钮盖住 ITEM No. 列头——`fs_exit` 容器虽 fixed `right:18`，但 Streamlit 块级包装链
     撑成 fill-available（实测 1402px），按钮落在容器左缘 → 视觉在表格左上。修法：容器及内层
     `[data-testid]`/`>div` 全部 `width:max-content`，容器收缩为按钮宽（152px）贴右缘
     （实测 left 1729 / right 1880）。
  2. 按钮文案「⛶ 全屏/Fullscreen」改「⛶ 最大化/Maximize」，退出键同步「退出最大化 (Esc)」
     （用户认为最大化更符合"表格铺满主内容区"的意图）。

- `ui/items_tab.py` / `ui/containers_tab.py`：View Mode 行加「⛶ 全屏 / 退出全屏」按钮 → 切 `st.session_state.list_fullscreen` + rerun。
- `app.py`：按 session_state 注入 `:root { --list-fullscreen: 1|0 }`；JS 读该变量给 `body` toggle class `wh-list-fullscreen`。
- `app.py` `<style>`：
  - 表格容器：`position: fixed; top:0; bottom:0; left/width` 复用现有 `--toolbar-left/width`（即主区矩形），`height:auto !important`，z-index 高于工具栏。
  - 隐藏 chrome：`stTitle`、`stTabs`、View Mode 行（需包 `st.container(key=...)` 才能精确隐藏）、提示行、两个工具栏。
- ESC 退出（加分项）：JS 监听 `Escape` → 在 parent 文档找到「退出全屏」按钮并 `click()`（沿用 `goto_tab` 模拟点击先例）。
- **验收**：AppTest 断言按钮存在、session_state 切换、rerun 后表格正常、退出后 chrome 恢复；用户本地目视。
- **风险**：全屏态隐藏工具栏 → 批量操作不可用（预期行为，纯查看）；ESC 纯前端退出会与 session_state 不同步 → 用模拟点击解决。

## 6. 验证方式与已知限制

- 自动化：每步在隔离副本跑 `test_i18n.py` / `test_data_layer.py` / `smoke_test.py` / `test_e2e.py`（本地库大、启动备份会使 AppTest 超时，故用副本）。
- 视觉：**AI 侧无法可靠截图**（无头浏览器建不了 Streamlit WebSocket 会话），需开发者本地确认：1080p 全屏 / 4K / 窗口缩放 / 侧边栏折叠 / 中英文 五种状态。
- 回滚：每步一个提交，可单独 `revert`。

## 7. 不在本次范围

- 卡片视图布局调整（本次只改列表视图）。
- 侧边栏自身收紧。
- Streamlit 版本升级。

## 8. 追加反馈（规划外，按用户反馈逐项实施）

### Step 4 表单照片交互对齐（已完成）

用户反馈：编辑页有独立的「添加图片」区（选图 → 预览 → 调序），新增页却是表单内嵌上传器、
保存时才生效，两者应一致。

- `ui/add_tab.py` 重构：表单内上传器移除；表单外新增**照片暂存区**（与编辑页同款
  `[3,1]` 列布局：上传器+提示 | 添加图片按钮）。选中的照片存
  `session_state.add_staged_photos`（UploadedFile 跨 rerun 保留），暂存区预览
  （120px 缩略图 + 上移/下移/移除，与编辑页图片管理区同款）；按 (文件名, 大小)
  防重复，落库时 `repo.add_item → attach_item_images` 另有内容 sha256 去重兜底。
  「保存物品」把暂存列表一并传入 add_item；保存成功/取消/重新进入新增页都清空暂存。
- `i18n.py` 新增 `items.photo_hint_draft`（暂存提示，区别于编辑页"立即生效"）、
  `items.staged_images`（暂存区标题）。
- **实测（selenium 全流程）**：选 2 图 → 暂存预览 2 张 → 上移交换 → 保存 → 自动打开
  详情页、详情 2 张图、`item_images` 落库 2 条。smoke / e2e / i18n 17 / data-layer 139 全绿。

### Dashboard 价值看板（用户追加需求，已完成）

用户要求：看板增加「Items by Container 的价值看板」与「按采购年份价值分布」两张价值图
（与原有数量图成对）。

- `ui/dashboard_tab.py`：在「各容器物品数量」「购买年份分布」两张数量图后，各加一张价值图——
  直接对 `get_filtered_data` 返回的 DataFrame 做 `groupby(...)[‘price’].sum()`（沿用既有
  pandas 内联聚合风格，无需新增 repo 函数）；容器价值按价值降序、年份价值按年份升序，
  均经全局 search / tag_filter 过滤。空数据时与既有图一致显示「无数据」占位。
- `i18n.py` 新增 `dash.container_value`（📦 各容器价值 / Value by Container）、
  `dash.year_value`（📅 按采购年份价值 / Value by Purchase Year）、`dash.col_value`（价值 / Value）。
- **实测（selenium）**：切到 Dashboard 标签，两张新看板文案存在、vega 图表共 4 张、无异常；
  i18n 键中英配对、smoke、data-layer 139 全绿。

### 照片区「添加图片」按钮垂直居中（用户微调，已完成）

用户反馈：上传框右侧的「➕ Add Photos」按钮偏上，要求下移至与上传框竖向居中。

- `ui/items_tab.py`（编辑页）/ `ui/add_tab.py`（新增页）/ `ui/containers_tab.py`（容器编辑）：
  三处同款布局，去掉 `st.write("")` 空行占位，按钮包进 keyed 容器
  （`edit_photo_add_btn` / `add_photo_btn` / `container_photo_add_btn`），点击 handler 移出
  with 块（缩进不变）。
- `app.py`：`.st-key-*_photo_add_btn { margin-top: 47.5px }`。**踩坑**：原打算用
  `margin:auto` 在按钮列内自动居中，实测按钮列高=内容高、不随 flex 行拉伸，auto 解析为 0；
  改固定下移 47.5px（= 上传框中心 − 按钮中心，按钮高 40 + Dropzone 高 79.1，偏移由上传框
  上方 label 高度决定；Streamlit 升级致尺寸变化时需重测）。
- **实测（selenium）**：新增页/编辑页按钮中心与 Dropzone 中心偏差 0px（改前 -47.5）；
  空选点击仍弹「请先选择」警告（handler 迁移无副作用）；smoke / e2e / i18n 17 / data 139 全绿。
