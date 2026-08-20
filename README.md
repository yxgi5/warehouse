# 个人物品仓库 (warehouse)

## 安装与运行

```bash
pip install -r requirements.txt

streamlit run app.py
# or
python -m streamlit run app.py
```

依赖已装到系统 Python38（streamlit 1.40.1 / pandas 2.0.3 / pillow 10.4.0）。
注意：本机 pip 请用默认官方源（清华镜像对该环境不可用）。

## 数据安全特性（Phase 1）

- **自动编号**：新增物品默认生成 `ITEM_YYYYMMDD_###`（当日递增），不再撞唯一约束；编辑时也可修改编号，重复会被拦截。
- **外键约束**：`items.container_id` / `images.item_id` 已建外键；删除非空容器被数据库拒绝，删除物品自动级联清理图片记录。
- **自动备份**：每次启动会话自动打包 `warehouse.db` + `photos/` 到 `backups/backup_时间戳.zip`，自动保留最近 10 份。
- **孤儿清理**：启动时检测"图片记录存在但文件缺失"的记录，侧边栏显示提示，可一键清理。

## 数据模型升级（Phase 2）

- **标签独立表**：`tags` + `item_tags` 关联表，旧库逗号字符串自动一次性迁移（迁移后旧 `items.tags` 列清空，读取走聚合查询）。
  - 标签筛选改为精确匹配：点"苹果"不再误匹配"苹果手机"；多标签为 AND 关系。
  - 无物品使用的孤儿标签自动清理。
- **图片管理**：编辑页可删除单张图片、⬆️⬇️ 调整顺序（删除后自动重排）。
- **路径锚定**：所有路径基于 `app.py` 所在目录（`BASE_DIR`），数据库只存文件名，目录改名/搬移后图片不失效；兼容旧库三种路径存法（绝对路径 / `photos/` 前缀 / 纯文件名）。

## 代码分层重构（Phase 3）

- **分层**：`db.py`（数据层，零 streamlit 依赖）→ `repo.py`（访问层，零 streamlit 依赖）→ `ui/*.py`（渲染层，每 Tab 一个模块）→ `app.py`（纯入口 + Tab 调度）。
- **删除逻辑收敛**：`repo.delete_item()` 为唯一删除入口（列表单删/批量删除/详情页删除统一调用，连带图片文件清理）。
- **N+1 消除**：卡片视图用 `load_first_image_map()` 一条 SQL 批量取首图，不再逐卡查询。
- **统一日志**：`db.setup_logging()` 滚动日志（1MB × 3 份）到 `logs/warehouse.log`。
- **连接复用**：`st.cache_resource` 缓存连接（`check_same_thread=False`，Streamlit 串行执行安全）。
- **备份容错**：删除旧备份失败只记 warning，不再拖垮整个备份流程。
- **全局筛选**：sidebar 控件带显式 key（`global_search`/`global_tag_filter`），与 session_state 双向绑定。

## 体验补全（Phase 4）

- **全字段搜索**：侧边栏关键词一次命中 名称/编号/特点/说明/平台/订单号/标签/容器名 任一字段（部分匹配）。
- **CSV 批量导入**：「➕ 新增物品」页底部展开器——下载模板 → 上传 CSV（UTF-8/GBK 均可，Excel 导出可直接用）→ 预览有效行与错误行 → 确认写入。
  - 表头固定：`item_no,name,container,purchase_date,platform,order_no,price,features,description,tags`
  - `item_no` 留空自动生成；`container` 必须是已有容器名；`tags` 用 逗号/分号 分隔；编号重复/解析失败的行记错误不中断，其余照常导入。
- **分页越界修复**：卡片视图在筛选/删除后页码越界时自动回退到合法范围（不再抛 ValueError）。
- **图片 MIME 校验**：上传落盘前校验扩展名白名单 + 文件头魔数，伪装/损坏/无扩展名文件被拒绝（不写库）。

## 多语言（Phase 5）

- **中英双语**：侧边栏顶部「语言 / Language」下拉一键切换（默认英文，刷新后保持），全界面（标题/Tab/表单/按钮/提示/CSV 错误消息）即时生效。
- **实现**：`i18n.py` 轻量翻译层（零第三方依赖、零 streamlit 依赖）——`i18n.t("key", ...)` 按当前语言取文案，支持 `.format` 参数；key 缺失回退默认语言、再缺失回显 key（便于排查漏译）。
- **注意**：`@st.dialog` 的标题参数在模块 import 时求值一次、不会随语言切换，故对话框标题用静态 emoji + 内部 `st.subheader(i18n.t(...))` 渲染语言化标题。

## 容器照片与浏览视图（Phase 6）

- **容器照片**：新增独立表 `container_images`（容器可传多张照片），在容器详情页内上传/删除/⬆️⬇️ 排序（MIME 校验与物品图片同一套规则，文件名前缀 `CT_{id}`）。
- **浏览视图**：「📦 容器管理」Tab 支持 **表格 / 卡片** 切换：
  - 表格视图：原有批量选择 + 详情/编辑/删除/新增工具栏；
  - 卡片视图：4 列网格显示容器首图 + 名称 + 位置 + 物品数，点击卡片进入详情页。
- **容器详情页**：多图画廊 + 位置/上级/子容器/物品数信息区 + 内部物品清单（点击跳转「物品浏览」Tab 的物品详情）+ 照片管理区。
- **容器树 Tab 详情跳转**：树行尾「详情」按钮在树 Tab 内就地打开该容器的详情页（复用与容器管理 Tab 相同的只读详情渲染，两处一致；返回按钮回到树）。注：Streamlit 1.40 的 `st.tabs` 不支持 `key`/`on_change`（1.55 才引入），无法程序化切换 Tab，故采用就地展开而非跨 Tab 跳转；两处详情同开时物品跳转按钮用不同 key 前缀（`cd_`/`tree_item_`）避免 widget ID 冲突。
- **数据安全衔接**：删除容器先删照片文件再删记录（`container_images` 记录外键级联清理）；孤儿图片扫描扩展到容器照片；备份自动包含 `photos/` 全部容器图。
- **N+1 消除**：卡片视图用 `load_container_first_image_map()` / `item_count_map()` 批量取首图与物品数。

## 列表视图操作优化（Phase 6.1）

- **工具栏在表格下方**：「物品浏览」列表视图的 查看详情/编辑/删除/导出 工具栏与容器列表布局一致，放在表格下方，常驻可见，选中行后**无需滚动即可操作**。
- **固定高度**：表格高度固定 300px（与容器列表一致），不再提供高度滑块。
- **交互时序**：工具栏按钮与选中状态联动——未选中时置灰 disabled（详情/编辑需恰好选中 1 行，删除/导出需 ≥1 行），选中后 `on_select="rerun"` 立即刷新按钮可用状态。工具栏在表格之后渲染，直接读取本轮选中结果，无滞后。

## 列表工具栏吸底与容器树美化（Phase 6.2）

- **工具栏吸底**：物品/容器列表的 详情/编辑/删除/导出 工具栏用 `st.container(key="list_toolbar"/"container_toolbar")` 包裹，注入 CSS `position: fixed; bottom: 0`——工具栏**钉死在视口底部，不依赖页面滚动**，页面再短也常驻可见。
  - **实现要点**：早期尝试 `position: sticky` 失败——Streamlit 1.40 的多层 `stVerticalBlockBorderWrapper` 使 `.st-key-*` 的包含块仅有自身高度（~53px），sticky 无处可粘；fixed 方案直接对工具栏容器定位，绕开包含块问题。left/width 由内嵌 JS 组件（不可见 iframe）实时同步主内容区 `stMain` 的位置到 CSS 变量 `--toolbar-left/--toolbar-width`，侧边栏折叠/窗口缩放自动对齐，异常时回退 `21rem`（展开侧边栏默认宽度）。已用 Chrome headless 实测：滚动后工具栏 bottom 恒定贴视口底（left=336、width=1064），表格底部留 80px 防遮挡。
  - **按钮组居中**：工具栏内部按钮 + 计数提示作为一个整体在主内容区横向居中。实现上让内部 `stVerticalBlock` 占满 fixed 容器，`stHorizontalBlock` 限制最大宽度 960px 并 `margin: 0 auto`；按钮设 `white-space: nowrap` 避免被压成竖排。侧边栏折叠后主区变宽，按钮组仍保持在主区中心，不会左移。
  - **提示位置与文案**：选中提示移到表格与工具栏之间，避免吸底后提示被顶出视线；物品/容器两处提示统一为 "...then use the toolbar below"，并移除 "Ctrl for multi-select"——`st.dataframe` 的 `selection_mode="multi-row"` 下直接点击复选框即可多选，无需 Ctrl。
- **容器树行内装饰**：树行改用 HTML 渲染——等宽字体字符画连接线（`├─ └─ │`）+ 🗂️/📦 图标（有子容器/叶子）+ 数量徽标（`color-mix` 取主题色）+ 📍位置 + hover 高亮；缩进用 `margin-left` 按深度递增，保留详情按钮原生交互。
- **列表高度**：表格固定 300px（列表内部滚动）；fixed 工具栏不依赖滚动，任何页面长度下都常驻视口底部。

## 提交规范（Git Convention）

- **前缀**：统一 Conventional Commits——`feat / fix / refactor / chore / docs / style / test`，带 scope 更佳，如 `feat(i18n)`。
- **中英双语、英文为主**：`<type>(<scope>): <English subject> · <中文描述>`，英文在前为主、中文在后补充。

## Git 历史

- **2026-08-20 重建**：仓库 `.git` 在 rebase 操作后意外丢失（无 remote 无法找回对象库），已按对话上下文**重建提交脉络**：根提交 `69dd304` 承载全量代码快照，其后 9 个提交按丢失前的提交 message 顺序重建（均为占位提交，tree 与最终版一致——**checkout 任意提交都有完整代码，不会出现空目录**；中间阶段的代码快照无法复原，请以 readme 各 Phase 章节了解演进过程）。
- **考古恢复的原始哈希链**（2026-08-20 追加）：重建后从 D 盘回收站发现丢失 `.git` 的部分残留（`$RECYCLE.BIN\...\$RUC0BLS.git`，13:42 删除时刻），其中的 `gitk.cache` 记录了 **gitk 展示过的全部原始提交的真实哈希**，据此恢复 48 个哈希与主链：
  - **Phase 5+（message 已知，与各 Phase 章节对应）**：`716b49ba`(默认英文) ← `9c06dadf`(布局对齐) ← `a93671fc`(工具栏) ← `c21cb7fc`(seed) ← `851e0604`(树内详情) ← `be778d4f`(树层级) ← `8ff22cb0`(树空白) ← `16531972`(容器照片) ← `7b27c8b3`(i18n)
  - **Phase 1-4 主链（哈希真实、message 未留存）**：`20891923` → `ac028e75` → `4787f147` → `adbf1b8d` → `cf9395ca` → `44e9fde8` → `2e18986e`（其后接 `7b27c8b3`）；另检出约 30 个分支/中间提交哈希。
  - **内容级验证**：残留的 `index`（13:36 暂存快照）解析出 21 个文件 blob 哈希，与重建根提交 `69dd304` 逐文件对比 **20/21 一致**（仅 readme.txt 因丢失后补写历史而更新）——证明重建内容 = 丢失前 HEAD 内容。
  - 原始 commit/tree/blob 对象数据仍无法恢复，真实哈希仅作追溯锚点；重建链使用新哈希。完整 48 哈希列表与 index 清单见备份目录 `recycle-evidence/`。
- **重建后的提交链**（自新到旧，HEAD=`4fa76e5`）：
  - `4fa76e5` docs: record archaeologically recovered original commit hashes · 记录考古恢复的原始提交哈希链
  - `c6ece3f` docs: describe rebuilt git history chain · 更新 Git 历史章节为重建后的提交链
  - `b4ece10` refactor(i18n): set English as default UI language · 默认语言改为英文
  - `d88b0fe` refactor(items): align items list layout with containers · 物品列表布局对齐容器
  - `c9bee23` refactor(items): keep list view toolbar visible without scrolling · 列表工具栏常驻可见
  - `9fe73f6` chore(seed): add reusable demo data seeding script · 演示数据灌入脚本
  - `2b23cbd` fix(tree): detail button opens container detail in-tree · 容器树详情就地打开
  - `6c337ad` refactor(tree): container tree shows hierarchy only, not item rows · 容器树仅显示层级关系
  - `98af35f` fix(tree): container tree tab shows nothing · 容器树空白修复
  - `ed69e3e` feat(containers): container photos and browse views · 容器照片与浏览视图
  - `3f2bce8` feat(i18n): add bilingual zh/en support · 中英双语
  - `69dd304` chore(repo): full code snapshot as rebuild root · 重建根提交（全量代码快照）
- **备份**：2026-08-20 13:55 起执行多重备份到 `D:\repos\warehouse_v2_backup\<时间戳>\`（`full.bundle` + `mirror.git` 镜像 + `gitdir-copy` 完整 .git 复制 + `recycle-evidence/` 考古证据）。重要操作后建议刷新 bundle（`git bundle create ... --all`），并强烈建议关联远程仓库（`git remote add origin <url>`）防止单点丢失。

## 自测

```bash
python smoke_test.py      # AppTest 真实执行 app.py，验证无异常
python test_data_layer.py # 数据层单测 76 项（建表/迁移/标签/图片/删除/备份/搜索/CSV导入/MIME/容器图片）
python test_i18n.py       # i18n 单测 17 项（双语言 key 集一致/无空值/format/语言联动）
python test_e2e.py        # 端到端回归（新增→筛选→搜索→详情→编辑→清理→语言切换→容器卡片/详情，全 UI 链路）
```

注：`test_e2e.py` 受 AppTest 1.40 边界限制——同一 widget 多次 `set_value` 会被上一轮回读值覆盖，脚本保证每个控件仅交互一次；"不误匹配"验证走 repo 层。

## 数据文件

- `warehouse.db`：SQLite 数据库（运行时生成）
- `photos/`：上传的图片（运行时生成）
- `backups/`：自动备份 zip（运行时生成）
