# -*- coding: utf-8 -*-
"""个人物品仓库 —— 应用入口（Phase 3 重构后）

分层：
- db.py    数据层：连接/建表/迁移/备份/孤儿检测/路径解析（不依赖 streamlit）
- repo.py  访问层：items/containers/images/tags 的 CRUD 与查询（不依赖 streamlit）
- ui/      渲染层：各 Tab 的 Streamlit 渲染（sidebar/items/dashboard/timeline/tags/tree/add/containers）
- app.py   入口：页面配置、会话状态、Tab 调度、全局数据加载

运行:  streamlit run app.py
"""
import streamlit as st
import db
import repo
import i18n
from ui import sidebar, items_tab, dashboard_tab, timeline_tab, tags_tab, tree_tab, add_tab, containers_tab

# --- 语言设置（set_page_config 之前；set_lang 不是 st 调用，不违反"第一个 st 调用"约束） ---
i18n.set_lang(st.session_state.get('lang', 'en'))

# --- 页面配置（必须是第一个 st 调用） ---
st.set_page_config(page_title=i18n.t("app.title"), layout="wide")

# --- 全局样式：列表工具栏吸底（sticky 不脱离文档流、不遮挡内容） ---
# 工具类 .st-key-<key> 由 st.container(key=...) 生成（Streamlit 1.39+），
# 配合 position: sticky + bottom:0 使工具栏在页面滚动时始终固定在视口底部。
st.markdown("""
<style>
.st-key-list_toolbar, .st-key-container_toolbar {
    position: sticky;
    bottom: 0;
    background: var(--background-color);
    padding: 8px 0 4px;
    z-index: 1000;
    border-top: 1px solid rgba(128, 128, 128, 0.15);
}
</style>
""", unsafe_allow_html=True)

# --- 日志与连接（连接复用：Streamlit 每次 rerun 不重复建连） ---
db.setup_logging()
get_conn = st.cache_resource(db.get_conn)

# --- 会话状态初始化 ---
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'list'   # 'list' 或 'card'（多语言后内部值稳定，显示文本由 i18n 决定）
if 'detail_item_id' not in st.session_state:
    st.session_state.detail_item_id = None
if 'edit_item_id' not in st.session_state:
    st.session_state.edit_item_id = None
if 'selected_indices' not in st.session_state:
    st.session_state.selected_indices = []
if 'tag_filter' not in st.session_state:
    st.session_state.tag_filter = ''
if 'backup_done' not in st.session_state:
    st.session_state.backup_done = False
if 'last_backup' not in st.session_state:
    st.session_state.last_backup = None
if 'orphans' not in st.session_state:
    st.session_state.orphans = None

# --- 数据库连接 + 建表/迁移 ---
conn = get_conn()
db.init_db(conn)

# 每个会话只做一次自动备份（Streamlit 每次交互都会 rerun，不能放在顶层裸执行）
if not st.session_state.backup_done:
    try:
        st.session_state.last_backup = db.backup_data()
    except Exception as e:
        db.logger.exception("自动备份失败")
        st.warning(i18n.t("app.backup_fail", err=e))
    st.session_state.backup_done = True

# 孤儿图片记录扫描（会话内只查一次）
if st.session_state.orphans is None:
    st.session_state.orphans = db.find_orphan_images(conn)

# 全局容器选项（统一在此查询一次，各 Tab 通过参数共享，不再各自重建）
container_options = repo.get_container_options(conn)

# --- 侧边栏（返回全局筛选条件） ---
search, tag_filter = sidebar.render(conn)

# --- 主界面 ---
st.title(i18n.t("app.main_title"))

# --- 定义Tabs ---
# 注：Streamlit 1.40 的 st.tabs 不支持 key/on_change（1.55 才引入），
# 跨 Tab 跳转通过"树 Tab 内就地渲染详情页"实现（见 tree_tab.py）。
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [i18n.t("app.tab.items"), i18n.t("app.tab.dashboard"), i18n.t("app.tab.timeline"),
     i18n.t("app.tab.tags"), i18n.t("app.tab.tree"), i18n.t("app.tab.add"),
     i18n.t("app.tab.containers")]
)

with tab1:
    items_tab.render(conn, search, tag_filter, container_options)

with tab2:
    dashboard_tab.render(conn, search, tag_filter)

with tab3:
    timeline_tab.render(conn, search, tag_filter)

with tab4:
    tags_tab.render(conn, search, tag_filter)

with tab5:
    tree_tab.render(conn, search, tag_filter)

with tab6:
    add_tab.render(conn, container_options)

with tab7:
    containers_tab.render(conn)
