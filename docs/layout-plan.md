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

### Step 2 表格高度视口自适应（核心，中风险）

思路：JS 实测「表格可用高度」→ 写 CSS 变量 → CSS `!important` 覆盖 `stDataFrameResizable` 的内联高度。

- `ui/items_tab.py` / `ui/containers_tab.py`：用 `st.container(key="item_list_wrap")` / `st.container(key="container_list_wrap")` 包住 `st.dataframe`（获得稳定类名供 CSS/JS 定位）；`height` 参数保留 300 作兜底。
- `app.py` `<style>`：
  ```css
  .st-key-item_list_wrap [data-testid="stDataFrameResizable"],
  .st-key-container_list_wrap [data-testid="stDataFrameResizable"] {
      height: var(--list-avail-h, 300px) !important;
  }
  ```
- `app.py` JS（扩展现有 sync）新增 `calcListHeight()`：
  `avail = 主区高度 − (表格容器 top − 主区 top) − 底部预留`
  底部预留 = 工具栏高度（`.st-key-list_toolbar` / `.st-key-container_toolbar` 的 `offsetHeight`，隐藏为 0）
  \+ 提示行高度（表格之后的 `stAlert` `offsetHeight`，无为 0）+ 8px 余量；写入 `--list-avail-h`。
  触发：初次 / resize / MutationObserver（扩展到 childList+subtree，捕获提示行三态切换引起的高度变化）。
  表格容器不存在时（卡片视图/详情页）不计算。
- **验收**：e2e 全绿且卡片视图不受影响；用户本地确认 1080p 全屏无页面滚动条、4K 表格更高、缩放连续自适应。
- **风险与降级**：`!important` 覆盖 Streamlit 内联高度，升级版本可能失效 → 选择器与理由写注释；失效时退回 `height=300`（页面可滚，不破功能）。

### Step 3 列表全屏（中风险）

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
