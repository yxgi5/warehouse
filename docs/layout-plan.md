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

1. **View Mode**：保留「标签 + 选项一行」（标签不删，与 radio 并排）。
2. **表格下方提示**（💡 Click the checkboxes to select rows…）：保留原位。
3. **列表全屏范围**：表格铺满主内容区（红框区域）；侧边栏保留可见；标题/Tab 栏/View Mode 行/提示/工具栏隐藏；按钮 + ESC 退出。
4. items 与 containers 行为一致。
5. 分步实施，每步独立验证、可单独回滚。

## 3. 目标布局

```
┌ sidebar ┐┌───────── 主区（整页无滚动条）─────────┐
│ Language││ 💼 My Warehouse                      │
│         ││ Items Dashboard Timeline Tags Tree Containers
│ Global  ││ View Mode  ◉ List ○ Cards   [ + Add Item ]  ← Step1：一行 + 居中
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

### Step 1 去废行（低风险）

- `app.py`：`<style>` 增加主区 `padding-top` 收紧（两层都显式定值：`stMain`=1rem、内层 `.stMainBlockContainer`=0，避免默认值所在层不确定导致叠加）；与既有 `padding-bottom` 合并同一条规则。
- `ui/items_tab.py` / `ui/containers_tab.py`：浏览态控制行包 `st.container(key=...)`，改三列 `[5,2,5]`——左列内再分「标签文本 | radio（标签折叠，`label_visibility="collapsed"`）」，中列放「新增」按钮（列中心正好在主内容区 50% 处，与吸底工具栏中心线一致）。
- `ui/containers_tab.py`：删除 `st.subheader(i18n.t("containers.title"))`；「➕ 新增容器」从底部工具栏（原 col_tool4）移到控制行，工具栏改 4 列 `[3,3,3,5]`（详情/编辑/删除/计数）；`i18n.py` 移除中英 `containers.title` 死 key。
- **收益附带**：卡片视图下容器 Tab 原先没有新增入口（工具栏只在列表视图渲染），移到控制行后列表/卡片都有。
- **验收**：AppTest 断言浏览态 radio 仍为 1 个、两个新增按钮都在、0 异常；e2e 全绿；用户本地目视确认。
- **风险**：低。`label_visibility="collapsed"`、`st.container(key=)` 在 Streamlit 1.40 可用。

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
