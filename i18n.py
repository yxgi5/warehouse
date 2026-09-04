# -*- coding: utf-8 -*-
"""轻量 i18n：中英双语，零第三方依赖（不依赖 streamlit，可被测试直接 import）。

用法：
    import i18n
    i18n.set_lang('en')          # app.py 每次 rerun 开始时调用（读 session_state.lang）
    text = i18n.t('items.edit')  # 取当前语言文案
    text = i18n.t('sidebar.last_backup', name='xxx.zip')   # .format 参数

规则：
- 默认语言 zh；key 在目标语言缺失时回退 zh，zh 也缺失时回显 key（便于排查漏译）。
- 模块级 _CURRENT 由 set_lang() 设置——Streamlit rerun 是单线程整脚本重跑，
  每次 rerun 都会重新 set_lang，故模块级全局安全。
- 注意：@st.dialog 装饰器的 title 参数在模块 import 时求值一次，不能直接放 t()，
  应改为静态标题 + dialog 内部 st.subheader(t(...))。
"""

_CURRENT = 'en'
_DEFAULT = 'en'

TRANSLATIONS = {
    "zh": {
        # ==================== 应用框架 ====================
        "app.title": "个人物品仓库",
        "app.main_title": "🧰 我的物品仓库",
        "app.backup_fail": "自动备份失败: {err}",
        "app.tab.items": "📦 物品浏览",
        "app.tab.dashboard": "📊 数据看板",
        "app.tab.timeline": "⏳ 时间线",
        "app.tab.tags": "🏷 标签墙",
        "app.tab.tree": "🌳 容器树",
        "app.tab.add": "➕ 新增物品",
        "app.tab.containers": "📦 容器管理",

        # ==================== 通用 ====================
        "common.cancel": "❌ 取消",
        "common.confirm_delete": "✅ 确认删除",
        "common.no_data": "暂无数据",
        "common.no_images": "暂无图片",
        "common.no_items": "没有物品",

        # ==================== 语言切换 ====================
        "lang.label": "语言",
        "lang.zh": "中文",
        "lang.en": "English",

        # ==================== 侧边栏 ====================
        "sidebar.filter_title": "🔍 全局筛选",
        "sidebar.search_label": "搜索关键词",
        "sidebar.search_placeholder": "名称/编号/特点/说明/平台/订单号/标签/容器",
        "sidebar.tag_label": "标签（逗号分隔）",
        "sidebar.sql_title": "🐍 SQL 控制台（高级用户）",
        "sidebar.sql_input": "输入 SQL 语句",
        "sidebar.sql_run": "执行查询",
        "sidebar.sql_error": "SQL错误: {err}",
        "sidebar.last_backup": "🗄️ 最近备份: {name}",
        "sidebar.orphans_warn": "发现 {n} 条图片记录的文件已缺失",
        "sidebar.orphan_clean": "🧹 清理孤儿记录",
        "sidebar.orphan_cleaned": "已清理 {n} 条孤儿记录",
        "sidebar.orphan_fail": "清理失败: {err}",

        # ==================== 表单共用字段 ====================
        "form.item_no": "ITEM 编号 *",
        "form.name": "名称 *",
        "form.container": "所属容器",
        "form.purchase_date": "购买日期",
        "form.platform": "平台",
        "form.order_no": "订单号",
        "form.price": "价格 (元)",
        "form.tags": "标签 (逗号分隔)",
        "form.related_items": "关联物品编号 (逗号分隔)",
        "form.related_help": "输入已有物品的编号，多个用英文/中文逗号或分号分隔（编号两侧空格自动忽略）；编号不存在会阻止保存",
        "form.features": "特点",
        "form.description": "附加说明",
        "form.required_msg": "编号和名称不能为空",

        # ==================== 物品浏览 ====================
        "items.switch_view": "切换视图",
        "items.view_list": "列表",
        "items.view_card": "卡片",
        "items.confirm_delete_title": "⚠️ 确认删除",
        "items.confirm_delete_msg": "你确定要永久删除 **{name}** 吗？此操作不可撤销，关联的图片文件也会被删除。",
        "items.deleted": "已删除 {name}",
        "items.delete_fail": "删除失败: {err}",
        "items.confirm_batch_title": "⚠️ 批量删除确认",
        "items.confirm_batch_msg": "你确定要永久删除选中的 **{n}** 件物品吗？",
        "items.confirm_batch_btn": "✅ 确认全部删除",
        "items.batch_deleted": "已删除 {n} 件物品",
        "items.batch_delete_fail": "批量删除失败: {err}",
        "items.edit_title": "✏️ 编辑物品: {item_no} - {name}",
        "items.save_update": "💾 更新物品",
        "items.cancel_edit": "❌ 取消编辑",
        "items.item_no_taken": "编号 {item_no} 已被其他物品使用",
        "items.updated": "✅ 物品更新成功！",
        "items.update_fail": "更新失败: {err}",
        "items.existing_images": "📷 已有图片（可删除、调整顺序）：",
        "items.image_missing": "(图片文件缺失)",
        "items.img_up": "⬆️ 上移",
        "items.img_down": "⬇️ 下移",
        "items.img_del": "🗑️ 删除",
        "items.back": "🔙 返回",
        "items.edit": "✏️ 编辑",
        "items.delete": "🗑️ 删除",
        "items.detail_title": "📦 {item_no} - {name}",
        "items.detail_images": "**📷 图片**",
        "items.img_shared_with": "此图也用于",
        "items.f_item_no": "**编号**",
        "items.f_name": "**名称**",
        "items.f_container": "**容器**",
        "items.f_purchase_date": "**购买日期**",
        "items.f_platform": "**平台**",
        "items.f_order_no": "**订单号**",
        "items.f_price": "**价格**",
        "items.not_set": "未设置",
        "items.unfiled": "(未归档)",
        "common.no_date": "无购买日期",
        "items.f_tags": "**标签**",
        "items.f_features": "**特点**",
        "items.f_description": "**附加说明**",
        "items.view_detail": "📄 查看详情",
        "items.export_selected": "📥 导出选中",
        "items.click_download": "点击下载",
        "items.export_ok": "导出成功！点击上方链接下载。",
        "items.list_count": "共 {total} 件，已选 {n} 件",
        "items.hint_no_selection": "💡 点击行首的复选框可选中整行，选中后下方工具栏可用",
        "items.hint_one": "✅ 已选中 1 件，可查看详情、编辑或删除",
        "items.hint_many": "✅ 已选中 {n} 件，可批量删除或导出",
        "items.page_size": "每页数量",
        "items.card_count": "共 {total} 件",
        "items.page_no": "页码",
        "items.prev_page": "⬅️ 上一页",
        "items.next_page": "下一页 ➡️",
        "items.open_detail": "📄 打开详情",
        "items.not_found": "物品不存在",
        "items.edit_not_found": "要编辑的物品不存在",
        "items.err_related_missing": "关联物品编号不存在: {nos}",
        "items.related_title": "**🔗 关联物品**",
        "items.related_empty": "暂无关联物品（添加/编辑时输入编号即可关联）",

        # ==================== 新增物品 ====================
        "add.title": "📝 录入新物品",
        "add.item_no": "ITEM 编号 *",
        "add.select_container": "(请选择容器)",
        "add.upload_images": "上传图片 (支持多张)",
        "add.save": "💾 保存物品",
        "add.item_no_exists": "编号 {item_no} 已存在，请修改编号",
        "add.saved": "✅ 物品 {item_no} 录入成功！",
        "add.save_fail": "保存失败: {err}",

        # ==================== CSV 批量导入 ====================
        "import.title": "📥 CSV 批量导入（一次录入多件）",
        "import.download_template": "⬇️ 下载模板",
        "import.header_hint": "表头: {cols}　·　item_no 留空自动生成　·　tags 用 逗号/分号 分隔",
        "import.upload_label": "选择 CSV 文件（UTF-8 或 GBK 编码）",
        "import.done": "✅ 这批数据已导入完成。如需再次导入，请重新选择文件。",
        "import.parse_fail": "解析失败: {err}",
        "import.parse_done": "解析完成：有效 **{ok}** 行，错误 **{err}** 行",
        "import.errors_title": "以下行存在错误，不会导入：",
        "import.row_no": "行号",
        "import.error": "错误",
        "import.confirm": "✅ 确认导入 {n} 条",
        "import.done_ok": "🎉 导入完成：成功 {ok} 条",
        "import.done_fail_sep": "，失败 {n} 条",
        "import.fail": "批量导入失败: {err}",
        "import.err_encoding": "无法解析 CSV（编码需为 UTF-8 或 GBK）",
        "import.err_header": "表头必须是: {cols}（当前: {got}）",
        "import.err_name": "名称(name)不能为空",
        "import.err_container": "容器 '{name}' 不存在",
        "import.err_price": "价格 '{val}' 不是数字",

        # ==================== 容器管理 ====================
        "containers.title": "📦 容器管理",
        "containers.confirm_title": "⚠️ 确认删除",
        "containers.confirm_msg": "你确定要永久删除选中的 **{n}** 个容器吗？({names})",
        "containers.deleted": "已删除 {n} 个容器",
        "containers.delete_fail": "删除失败: {err}",
        "containers.not_found": "要编辑的容器不存在",
        "containers.edit_title": "✏️ 编辑容器: {name}",
        "containers.add_title": "➕ 新增容器",
        "containers.name": "容器名称 *",
        "containers.none_parent": "（无）",
        "containers.parent": "上级容器",
        "containers.location": "位置描述",
        "containers.update": "💾 更新",
        "containers.add": "➕ 添加",
        "containers.delete_btn": "🗑️ 删除此容器",
        "containers.name_empty": "容器名称不能为空",
        "containers.name_taken": "容器名称已存在",
        "containers.saved_updated": "容器 {name} 已更新",
        "containers.saved_added": "容器 {name} 已添加",
        "containers.op_fail": "操作失败: {err}",
        "containers.not_empty": "容器非空，不能删除（物品 {n} 个，子容器 {m} 个）",
        "containers.col_name": "容器名称",
        "containers.col_parent": "上级容器",
        "containers.col_location": "位置",
        "containers.add_btn": "➕ 新增容器",
        "containers.list_count": "共 {total} 个容器，已选 {n}",
        "containers.hint_no_selection": "💡 点击行首的复选框可选中容器，选中后下方工具栏可用",
        "containers.hint_one": "✅ 已选中 1 个容器，可编辑或删除",
        "containers.hint_many": "✅ 已选中 {n} 个容器，可批量删除",
        "containers.not_empty_list": "以下容器非空，不能删除：{list}",
        # ---- 容器图片/卡片视图/详情页（Phase 6） ----
        "containers.switch_view": "切换视图",
        "containers.view_table": "表格",
        "containers.view_card": "卡片",
        "containers.card_count": "共 {total} 个容器",
        "containers.card_items": "{n} 件物品",
        "containers.card_children": "{n} 个子容器",
        "containers.open_detail": "打开详情",
        "containers.detail_title": "📦 容器详情: {name}",
        "containers.detail_location": "**位置**",
        "containers.detail_parent": "**上级容器**",
        "containers.detail_children": "**子容器**",
        "containers.detail_items": "**物品数**",
        "containers.detail_images": "**📷 容器照片**",
        "containers.detail_item_list": "**📦 容器内物品**",
        "containers.upload_images": "上传容器照片 (支持多张)",
        "containers.jump_item_hint": "已在「物品浏览」标签打开物品详情",
        "containers.none_value": "无",

        # ==================== 数据看板 ====================
        "dash.total_items": "总物品数",
        "dash.total_value": "总价值",
        "dash.none": "无",
        "dash.container_count": "容器数",
        "dash.container_dist": "📦 各容器物品数量",
        "dash.col_container": "容器",
        "dash.col_count": "数量",
        "dash.year_dist": "📅 购买年份分布",
        "dash.col_year": "年份",
        "dash.hot_tags": "🏷️ 热门标签",
        "dash.col_tag": "标签",
        "dash.col_times": "出现次数",

        # ==================== 时间线 / 标签墙 / 容器树 ====================
        "timeline.expander": "📆 {year}年 ({count}件)",
        "tags.none": "暂无标签",
        "tree.container_line": "📁 **{name}** ({count}件)",
        "tree.summary": "共 {containers} 个容器 · {items} 件物品",
        "tree.view_detail": "详情",
        "tree.goto_detail": "已打开「{name}」详情页",
        "tree.empty": "暂无容器，去「容器管理」创建一个吧",
    },

    "en": {
        # ==================== App frame ====================
        "app.title": "Personal Warehouse",
        "app.main_title": "🧰 My Warehouse",
        "app.backup_fail": "Auto backup failed: {err}",
        "app.tab.items": "📦 Items",
        "app.tab.dashboard": "📊 Dashboard",
        "app.tab.timeline": "⏳ Timeline",
        "app.tab.tags": "🏷 Tags",
        "app.tab.tree": "🌳 Container Tree",
        "app.tab.add": "➕ Add Item",
        "app.tab.containers": "📦 Containers",

        # ==================== Common ====================
        "common.cancel": "❌ Cancel",
        "common.confirm_delete": "✅ Confirm Delete",
        "common.no_data": "No data",
        "common.no_images": "No images",
        "common.no_items": "No items",

        # ==================== Language ====================
        "lang.label": "Language",
        "lang.zh": "中文",
        "lang.en": "English",

        # ==================== Sidebar ====================
        "sidebar.filter_title": "🔍 Global Filter",
        "sidebar.search_label": "Search",
        "sidebar.search_placeholder": "name/no/features/desc/platform/order/tags/container",
        "sidebar.tag_label": "Tags (comma-separated)",
        "sidebar.sql_title": "🐍 SQL Console (advanced)",
        "sidebar.sql_input": "Enter SQL",
        "sidebar.sql_run": "Run Query",
        "sidebar.sql_error": "SQL error: {err}",
        "sidebar.last_backup": "🗄️ Last backup: {name}",
        "sidebar.orphans_warn": "{n} image records are missing files",
        "sidebar.orphan_clean": "🧹 Clean Up Orphans",
        "sidebar.orphan_cleaned": "Cleaned {n} orphan records",
        "sidebar.orphan_fail": "Cleanup failed: {err}",

        # ==================== Shared form fields ====================
        "form.item_no": "ITEM No. *",
        "form.name": "Name *",
        "form.container": "Container",
        "form.purchase_date": "Purchase Date",
        "form.platform": "Platform",
        "form.order_no": "Order No.",
        "form.price": "Price (CNY)",
        "form.tags": "Tags (comma-separated)",
        "form.related_items": "Related Item No. (comma-separated)",
        "form.related_help": "Existing item numbers separated by English/Chinese comma or semicolon (spaces around numbers are ignored); an unknown number blocks saving",
        "form.features": "Features",
        "form.description": "Description",
        "form.required_msg": "Item No. and name are required",

        # ==================== Items ====================
        "items.switch_view": "View Mode",
        "items.view_list": "List",
        "items.view_card": "Cards",
        "items.confirm_delete_title": "⚠️ Confirm Delete",
        "items.confirm_delete_msg": "Delete **{name}** permanently? This cannot be undone and the associated image files will also be removed.",
        "items.deleted": "Deleted {name}",
        "items.delete_fail": "Delete failed: {err}",
        "items.confirm_batch_title": "⚠️ Confirm Batch Delete",
        "items.confirm_batch_msg": "Delete the selected **{n}** items permanently?",
        "items.confirm_batch_btn": "✅ Confirm Delete All",
        "items.batch_deleted": "Deleted {n} items",
        "items.batch_delete_fail": "Batch delete failed: {err}",
        "items.edit_title": "✏️ Edit Item: {item_no} - {name}",
        "items.save_update": "💾 Update Item",
        "items.cancel_edit": "❌ Cancel Edit",
        "items.item_no_taken": "Item No. {item_no} is already used by another item",
        "items.updated": "✅ Item updated!",
        "items.update_fail": "Update failed: {err}",
        "items.existing_images": "📷 Existing images (delete / reorder):",
        "items.image_missing": "(image file missing)",
        "items.img_up": "⬆️ Up",
        "items.img_down": "⬇️ Down",
        "items.img_del": "🗑️ Delete",
        "items.back": "🔙 Back",
        "items.edit": "✏️ Edit",
        "items.delete": "🗑️ Delete",
        "items.detail_title": "📦 {item_no} - {name}",
        "items.detail_images": "**📷 Images**",
        "items.img_shared_with": "Also used by",
        "items.f_item_no": "**Item No.**",
        "items.f_name": "**Name**",
        "items.f_container": "**Container**",
        "items.f_purchase_date": "**Purchase Date**",
        "items.f_platform": "**Platform**",
        "items.f_order_no": "**Order No.**",
        "items.f_price": "**Price**",
        "items.not_set": "Not set",
        "items.unfiled": "(Unfiled)",
        "common.no_date": "No purchase date",
        "items.f_tags": "**Tags**",
        "items.f_features": "**Features**",
        "items.f_description": "**Description**",
        "items.view_detail": "📄 View Details",
        "items.export_selected": "📥 Export Selected",
        "items.click_download": "Click to download",
        "items.export_ok": "Export OK! Click the link above to download.",
        "items.list_count": "{total} items, {n} selected",
        "items.hint_no_selection": "💡 Click the checkboxes to select rows, then use the toolbar below",
        "items.hint_one": "✅ 1 item selected — view, edit or delete",
        "items.hint_many": "✅ {n} items selected — batch delete or export",
        "items.page_size": "Page Size",
        "items.card_count": "{total} items",
        "items.page_no": "Page",
        "items.prev_page": "⬅️ Prev",
        "items.next_page": "Next ➡️",
        "items.open_detail": "📄 Open Details",
        "items.not_found": "Item not found",
        "items.edit_not_found": "The item to edit was not found",
        "items.err_related_missing": "Related item numbers not found: {nos}",
        "items.related_title": "**🔗 Related Items**",
        "items.related_empty": "No related items (type item numbers in Add/Edit to link)",

        # ==================== Add item ====================
        "add.title": "📝 Add New Item",
        "add.item_no": "ITEM No. *",
        "add.select_container": "(Select container)",
        "add.upload_images": "Upload images (multiple)",
        "add.save": "💾 Save Item",
        "add.item_no_exists": "Item No. {item_no} already exists, please change it",
        "add.saved": "✅ Item {item_no} added!",
        "add.save_fail": "Save failed: {err}",

        # ==================== CSV import ====================
        "import.title": "📥 CSV Bulk Import",
        "import.download_template": "⬇️ Download Template",
        "import.header_hint": "Header: {cols} · blank item_no auto-generates · tags split by , or ;",
        "import.upload_label": "Choose CSV file (UTF-8 or GBK)",
        "import.done": "✅ This batch has been imported. Re-choose the file to import again.",
        "import.parse_fail": "Parse failed: {err}",
        "import.parse_done": "Parsed: **{ok}** valid rows, **{err}** errors",
        "import.errors_title": "Rows below have errors and will NOT be imported:",
        "import.row_no": "Row",
        "import.error": "Error",
        "import.confirm": "✅ Import {n} rows",
        "import.done_ok": "🎉 Import done: {ok} succeeded",
        "import.done_fail_sep": ", {n} failed",
        "import.fail": "Import failed: {err}",
        "import.err_encoding": "Cannot parse CSV (encoding must be UTF-8 or GBK)",
        "import.err_header": "Header must be: {cols} (current: {got})",
        "import.err_name": "Name is required",
        "import.err_container": "Container '{name}' not found",
        "import.err_price": "Price '{val}' is not a number",

        # ==================== Containers ====================
        "containers.title": "📦 Container Management",
        "containers.confirm_title": "⚠️ Confirm Delete",
        "containers.confirm_msg": "Delete the selected **{n}** containers permanently? ({names})",
        "containers.deleted": "Deleted {n} containers",
        "containers.delete_fail": "Delete failed: {err}",
        "containers.not_found": "The container to edit was not found",
        "containers.edit_title": "✏️ Edit Container: {name}",
        "containers.add_title": "➕ Add Container",
        "containers.name": "Container Name *",
        "containers.none_parent": "(None)",
        "containers.parent": "Parent Container",
        "containers.location": "Location",
        "containers.update": "💾 Update",
        "containers.add": "➕ Add",
        "containers.delete_btn": "🗑️ Delete Container",
        "containers.name_empty": "Container name is required",
        "containers.name_taken": "Container name already exists",
        "containers.saved_updated": "Container {name} updated",
        "containers.saved_added": "Container {name} added",
        "containers.op_fail": "Operation failed: {err}",
        "containers.not_empty": "Container not empty (items: {n}, children: {m}) — cannot delete",
        "containers.col_name": "Container Name",
        "containers.col_parent": "Parent",
        "containers.col_location": "Location",
        "containers.add_btn": "➕ Add Container",
        "containers.list_count": "{total} containers, {n} selected",
        "containers.hint_no_selection": "💡 Click the checkboxes to select containers, then use the toolbar below",
        "containers.hint_one": "✅ 1 container selected — edit or delete",
        "containers.hint_many": "✅ {n} containers selected — batch delete",
        "containers.not_empty_list": "Containers below are not empty: {list}",
        # ---- Container photos / card view / detail page (Phase 6) ----
        "containers.switch_view": "View Mode",
        "containers.view_table": "Table",
        "containers.view_card": "Cards",
        "containers.card_count": "{total} containers",
        "containers.card_items": "{n} items",
        "containers.card_children": "{n} children",
        "containers.open_detail": "Open Details",
        "containers.detail_title": "📦 Container Details: {name}",
        "containers.detail_location": "**Location**",
        "containers.detail_parent": "**Parent**",
        "containers.detail_children": "**Children**",
        "containers.detail_items": "**Items**",
        "containers.detail_images": "**📷 Container Photos**",
        "containers.detail_item_list": "**📦 Items in Container**",
        "containers.upload_images": "Upload container photos (multiple)",
        "containers.jump_item_hint": "Item details opened in the Items tab",
        "containers.none_value": "None",

        # ==================== Dashboard / Timeline / Tags / Tree ====================
        "dash.total_items": "Total Items",
        "dash.total_value": "Total Value",
        "dash.none": "N/A",
        "dash.container_count": "Containers",
        "dash.container_dist": "📦 Items by Container",
        "dash.col_container": "Container",
        "dash.col_count": "Count",
        "dash.year_dist": "📅 By Purchase Year",
        "dash.col_year": "Year",
        "dash.hot_tags": "🏷️ Hot Tags",
        "dash.col_tag": "Tag",
        "dash.col_times": "Occurrences",

        # ==================== Timeline / Tags / Tree ====================
        "timeline.expander": "📆 {year} ({count} items)",
        "tags.none": "No tags",
        "tree.container_line": "📁 **{name}** ({count} items)",
        "tree.summary": "Total {containers} containers · {items} items",
        "tree.view_detail": "Detail",
        "tree.goto_detail": "Opened \"{name}\" details",
        "tree.empty": "No containers yet, create one in the Containers tab",
    },
}


def set_lang(lang):
    """设置当前语言（zh / en）。非法值回退默认。"""
    global _CURRENT
    if lang in TRANSLATIONS:
        _CURRENT = lang
    else:
        _CURRENT = _DEFAULT


def get_lang():
    return _CURRENT


def supported_langs():
    return list(TRANSLATIONS.keys())


def t(key, **kwargs):
    """取当前语言文案；key 缺失回退默认语言，再缺失回显 key。支持 .format 参数。"""
    table = TRANSLATIONS.get(_CURRENT, TRANSLATIONS[_DEFAULT])
    text = table.get(key)
    if text is None:
        text = TRANSLATIONS[_DEFAULT].get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass   # 参数不匹配时返回原文，避免崩溃
    return text
