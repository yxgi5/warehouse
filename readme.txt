# 个人物品仓库 (warehouse_v2)

## 安装与运行

    pip install -r requirements.txt
    streamlit run app.py

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
- **交互时序**：工具栏按钮始终可点，未选中时点击给 toast 提示（不做 disabled——`st.dataframe` 的选中结果渲染后才能拿到，disabled 会导致按钮状态滞后一次交互）。工具栏在表格之后渲染，直接读取本轮选中结果，无滞后。

## 提交规范（Git Convention）

- **前缀**：统一 Conventional Commits——`feat / fix / refactor / chore / docs / style / test`，带 scope 更佳，如 `feat(i18n)`。
- **中英双语、英文为主**：`<type>(<scope>): <English subject> · <中文描述>`，英文在前为主、中文在后补充。

## Git 历史

- **2026-08-20 13:45 重建**：仓库 `.git` 在 rebase 操作后意外丢失（本仓库无 remote，历史无法找回），已 `git init` 重建，HEAD=`eb640ac`（`chore(repo): rebuild git repository after .git loss`）。**全部代码文件完好无损**（与丢失前最新版一致），下述丢失前的提交 message 与 Phase 章节一一对应，可追溯。
- **丢失前提交记录**（自新到旧）：
  - `716b49b` 默认语言改为英文；测试脚本固定中文界面执行并同步断言
  - `9c06dad` 列表视图布局对齐容器：表格在上(固定300px)、工具栏在下，去掉高度滑块
  - `a93671f` ui: keep list view toolbar visible without scrolling
  - `c21cb7f` chore: add reusable demo data seeding script
  - `851e060` fix: container tree detail button now opens detail page in-tree
  - `be778d4` refactor: container tree shows hierarchy only, not item rows
  - `8ff22cb` 容器树空白修复（message 原文未留存，见 Phase 6 容器树）
  - `1653197` 容器照片与浏览视图（message 原文未留存，见 Phase 6）
  - `7b27c8b` 中英双语（message 原文未留存，见 Phase 5）
- **备份**：重建后立即导出 `D:\repos\warehouse_v2_backup\warehouse_v2-<时间戳>.bundle`。每次重要提交后建议刷新该 bundle（`git bundle create ... --all`），并强烈建议关联远程仓库（git remote add origin <url>）防止单点丢失。

## 自测

    python smoke_test.py      # AppTest 真实执行 app.py，验证无异常
    python test_data_layer.py # 数据层单测 76 项（建表/迁移/标签/图片/删除/备份/搜索/CSV导入/MIME/容器图片）
    python test_i18n.py       # i18n 单测 17 项（双语言 key 集一致/无空值/format/语言联动）
    python test_e2e.py        # 端到端回归（新增→筛选→搜索→详情→编辑→清理→语言切换→容器卡片/详情，全 UI 链路）

注：`test_e2e.py` 受 AppTest 1.40 边界限制——同一 widget 多次 `set_value` 会被上一轮回读值覆盖，脚本保证每个控件仅交互一次；"不误匹配"验证走 repo 层。

## 数据文件

- `warehouse.db`：SQLite 数据库（运行时生成）
- `photos/`：上传的图片（运行时生成）
- `backups/`：自动备份 zip（运行时生成）

