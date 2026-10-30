# 仓库数据库专业点评与改进建议（WMS 视角）

> 第三方（AI 协助）以仓库管理专业性视角，对个人物品库存系统 `warehouse.git` 的数据模型与
> 应用现状做的点评，以及针对「挖使用价值 / 定位查找」诉求的改进建议。
> 本文**只读分析，未改动任何数据与代码**；文档由用户自行加入 git 仓库。
> 关联：`README.md`（Phase 1–9 完工编年史）、`docs/layout-plan.md`（Phase 10 UI 布局改造计划）。

## 0. 背景与现状

- 系统形态：Flask/Streamlit + SQLite 个人物品库存应用（`db.py` 数据层 → `repo.py` 访问层 →
  `ui/*.py` 渲染层 → `app.py` 入口）。
- 数据规模（分析当日）：`items` 共 **3067 件**，已录参考价值合计 **¥102,206**；
  其中 **约 2500 件无价格**（用户所述「还有几万元没统计」的主体）。
- 物品构成远超「板卡」：含旧平板、发电机、镜头、电感、夹线、面包板等广义电子杂物；
  MCU/SoC/开发板子集约 106 件（已录价 61 件，¥30,667），其中 ARM9/ARM11 古董、8 位 MCU、
  弱 x64 老主机等明确过时类约 34 件 / 录价 ¥6,275。
- 定位覆盖：仅 3 件 `container_id` 为空，其余均已上架到容器层级树中。

## 1. 总体评价：**B+**（个人项目里属尖子）

数据建模与工程健壮性已超过 90% 的个人库存工具。当前主要矛盾不在「结构对错」，
而在**分析型需求缺三个一等公民字段**（成色 / 处置 / 维护日期），以及
**App 层缺「处置维度」的分流看板**——价值维度看板已存在（见第 5 节修正说明）。

## 2. 做得好的（专业级，有据可查）

| # | 专业点 | 代码证据（db.py / 结构） | 为什么专业 |
|---|---|---|---|
| 1 | **定位是层级树，非单层** | `containers.parent_id` 自引用 + `location` 文本字段 | 真 WMS「库→架→盒→袋」思路：`item → container → 祖先链` 能拼出完整「在哪」 |
| 2 | **定位覆盖率极高** | 仅 3/3067 件 `container_id` 为空 | 几乎全库已上架，物理可找 |
| 3 | **引用完整性** | `PRAGMA foreign_keys=ON`；`container` 用 `ON DELETE RESTRICT`，子表 `ON DELETE CASCADE` | 删容器不会 orphan 物品；子表自动级联。多数个人库根本没有 |
| 4 | **标签归一化** | `tags` + `item_tags` 多对多；旧逗号串一次性迁走并清空 | 无持久双来源；精确匹配、AND 关系、孤儿标签自清 |
| 5 | **图片内容寻址去重** | `images` 池 + `sha256` + `item_images` 多对多；魔数校验 | 同图多物共用不重复落盘；上传前校验防坏文件 |
| 6 | **备份一致性** | `VACUUM INTO` 快照 + 滚动保留 10 份（含 photos） | 个人项目有这意识的极少 |
| 7 | **迁移框架可重入自愈** | `_migrate_group` 状态机，中断续迁不丢数据 | 企业级严谨度 |
| 8 | **采购可追溯** | `platform` / `order_no` / `purchase_date` / `price` | 等于收货记录，资产估值有源 |
| 9 | **开发流程纪律** | `layout-plan.md` 每步可单独 revert；selenium 无头实测 + AppTest + e2e 全绿 | 这是库底子扎实的根本原因 |

## 3. 专业视角下的真缺口（按对「挖价值 + 定位」的优先级排）

1. **❌ 没有「成色 / 处置」一等字段（最该补）**
   现有「有残值 / 损坏 / 永久损坏」与「保留 / 可出 / 电子垃圾」都只是**自由标签**。
   WMS 的核心是 *disposition*（留 / 修 / 卖 / 捐 / 弃）。标签无法可靠报表——
   「标记待售的有几件、总值多少」得靠解析标签。建议加 `condition`（enum）+ `disposition`（enum）
   两列，或至少把价值状态做成**受控标签词表**。

2. **❌ 维护靠标签而非日期（电池类会翻车）**
   `定期充电 / 定时充电` 是标签，表达不了「下次该充的日期」。约 25 件带电池设备需要
   `last_maintained` / `next_maintenance` DATE，才能查「本周该充什么」。标签答不了这个问题。

3. **⚠️ 没有移动 / 流水账（transaction ledger）**
   WMS 每次 入 / 出 / 移 都记时间戳 + 原因。这里物品改了容器无从追溯——
   「我上月把 X 挪到哪了」答不出。个人库优先级低，但想要「找物」可靠性，加个 `movements`
   表（`item_id, from_container, to_container, ts, note`）很值。

4. **⚠️ 物品命名无管控 → 可发现性差、难聚合**
   `wifi天线` 出现 15+、各类 `wifi模块` 一堆，纯自由文本。没有「产品主数据 / 类目」把
   「所有 wifi 天线」归并、也算不清跨容器总量。WMS 区分 *Item Master*（是什么，归一）与
   *Stock*（实物 + 位置）。建议加 `category` 字段 + 规范名，搜索 / 汇总才灵。

5. **⚠️ 估值完整性与流程缺口（2500/3067 未计价）**
   不是 schema 问题，是**录入摩擦**导致。专业做法：按容器批量补价 + 订单 CSV 导入；
   并区分 `purchase_price` 与 `resale_value`（卖价 ≠ 买价，FS2410 录 ¥2500 卖不掉即例证）。

6. **⚠️ 应用层缺「处置维度」分流看板**
   Dashboard 已有**价值维度**图（各容器价值 / 各采购年份价值，见第 5 节），但缺
   **处置维度**看板（按 condition / disposition 分布、待维护日历）。这是 UI 缺口，非库缺口。

7. **○ 物理查找缺条码 / 二维码**
   3067 件规模，「打印每张物品 / 容器二维码、扫一下显位置」是专业收尾动作。
   SQLite + 一个小标签视图即可做。

8. **○ `items.tags` 列已成尸体字段**
   迁移后清成 `''` 但列仍在，可择机 `DROP` 保持整洁（无害）。

## 4. 落地建议（不动大结构，优先三处补强）

### 4.1 数据层：加三列（幂等迁移，沿用现有风格）

```sql
-- db.py migrate_item_triage() 幂等：旧库 ALTER 补齐，历史物品给默认
ALTER TABLE items ADD COLUMN condition     TEXT;   -- 成色：全新/良好/一般/损坏/永久损坏
ALTER TABLE items ADD COLUMN disposition   TEXT;   -- 处置：保留/待用/可出售/可捐赠/电子垃圾/待决定
ALTER TABLE items ADD COLUMN next_maintenance TEXT; -- 下次维护日 ISO 'YYYY-MM-DD'，电池设备用
-- 可选：last_maintained TEXT 记录上次维护日，用于推算周期
```

- `condition` / `disposition` 作为**受控词表**（在 `i18n.py` 或常量里枚举），UI 用下拉而非自由输入，
  保证可聚合。迁移函数命名与 `migrate_item_qty` / `migrate_container_note` 一致，纳入 `init_db`。
- 旧库历史行 `condition/disposition` 默认 `NULL`（= 待决定），`next_maintenance` 默认 `NULL`；
  可写一次性脚本把现有 `有残值/损坏/永久损坏` 标签回填进 `condition`，把 `定期充电/定时充电`
  标签持有者批量填 `next_maintenance = 今日 + 90 天`。

### 4.2 repo 层

- `add_item` / `update_item` 透传三新字段；`get_filtered_data` SELECT 补列；
  CSV 导入 `IMPORT_COLUMNS` 增加 `condition, disposition, next_maintenance` 与模板示例。

### 4.3 UI 层（新增页 + 编辑页两处都改，沿用 quantity/unit 改造的既有模式）

- 表单增加「成色」下拉、「处置」下拉、「下次维护日」date_input（可空）。
- 详情页展示三字段；列表视图加「成色」「处置」列（维护日可进筛选）。

### 4.4 分流看板（处置维度，补 Dashboard 价值图之不足）

在 `ui/dashboard_tab.py` 价值图之后，加处置维度聚合（沿用 `get_filtered_data` 返回的 DataFrame 内联
`groupby`，不新增 repo 函数，与既有价值图风格一致）：

```python
# 处置分布
df.groupby('disposition').agg(件数=('id','size'), 总值=('subtotal','sum'))
# 成色分布
df.groupby('condition').agg(件数=('id','size'), 总值=('subtotal','sum'))
# 本周待维护（next_maintenance 非空且 <= 今+7天）
due = df[(df.next_maintenance.notna()) & (df.next_maintenance <= today+7)]
```

- 空数据与第一类图一致显示「无数据」占位。
- `i18n.py` 增 `dash.disposition` / `dash.condition` / `dash.due_maintenance` 等键。

### 4.5 验证方式（沿用 layout-plan.md 纪律）

- `test_data_layer.py` 增三列落库 / 读取 / CSV 导入用例（目标 139 → 14x 项）。
- `test_e2e.py` 覆盖新增表单含三字段、提交 0 异常；AppTest 针对性验证编辑页改值落库。
- 视觉：selenium 切到 Dashboard 确认新看板文案 + 图表存在、无异常。
- 每步一个提交，可单独 revert。

## 5. 修正说明（避免与现有文档矛盾）

- 早期口头点评曾言「App 缺分流看板」——**此说半句有误**。`docs/layout-plan.md` 的
  「Dashboard 价值看板」已落地「各容器价值 / 各采购年份价值」两张图，**价值维度可视化已存在**。
- 真正缺口是**处置维度**看板（依赖第 4 节的 `disposition/condition/next_maintenance` 三字段），
  属数据模型层升级；Phase 10 及之前所有规划只动 UI chrome 与字段 UI，从未触及 schema 语义。
- 因此本文建议的「三字段 + 处置看板」是一个**规划空白点**，而非对既有工作的否定。

## 6. 可选后续：Phase 11 方向（轻量，待用户决定是否展开为正式计划）

若采纳第 4 节，可正式立项 **Phase 11: 使用价值分流（数据模型 + 看板）**，沿用 `layout-plan.md`
的「分步 + selenium 实测 + 可单独 revert」风格，拆为：

- Step 1：三列幂等迁移 + 旧标签回填脚本（低风险）。
- Step 2：repo / CSV 导入透传（中低）。
- Step 3：新增页 + 编辑页表单与详情 / 列表列（中，沿用 quantity/unit 改造模式）。
- Step 4：Dashboard 处置维度看板 + 本周待维护（中低）。
- Step 5（加分）：二维码标签打印视图（低）。

> 注：本文件为分析建议稿，不含实现代码（第 4 节 DDL / 查询为示意）。是否立项、如何拆步，
> 由用户决定；正式计划可续写于 `docs/layout-plan.md` 或新建 `docs/triage-plan.md`。
