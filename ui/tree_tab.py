# -*- coding: utf-8 -*-
"""Tab5 容器树：纯容器层级树，体现容器间的父子相对关系。

设计要点：
- 每行 = 层级缩进 + 图标（🗂️ 有子容器 / 📦 叶子）+ 容器名 + 物品数徽标 + 位置；
  悬停高亮，层级用缩进与左侧竖线表达（不再用 ├─ └─ 字符画）。
  具体物品请看「容器管理」Tab 的容器详情页清单。
- 行尾「详情」按钮在树 Tab 内就地打开该容器的详情页
  （复用 containers_tab.render_detail_readonly，与容器管理 Tab 详情一致；
  返回按钮回到树）。注：Streamlit 1.40 的 st.tabs 不支持 key/on_change，
  无法程序化切换 Tab，故采用就地展开而非跨 Tab 跳转。
- 注意：SQLite parent_id NULL 读入 pandas 后是 NaN，顶层容器必须用
  isna() 匹配（`== None` 恒 False 会导致整树空白）。
"""
import html
import streamlit as st
import repo
import i18n
from ui.containers_tab import render_detail_readonly

# 树行样式：CSS 变量跟随 Streamlit 主题（浅/深色自适应），行 hover 高亮
_TREE_CSS = """
<style>
.tree-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 8px;
    border-radius: 6px;
    border-left: 2px solid rgba(128, 128, 128, 0.25);
    transition: background-color 0.15s;
}
.tree-row:hover { background: rgba(128, 128, 128, 0.08); }
.tree-icon { font-size: 1.05rem; line-height: 1; }
.tree-name { font-weight: 500; }
.tree-badge {
    background: color-mix(in srgb, var(--primary-color) 14%, transparent);
    color: var(--primary-color);
    border-radius: 10px;
    padding: 0 8px;
    font-size: 0.8rem;
    line-height: 1.4;
    font-weight: 500;
}
.tree-loc { color: var(--text-color); opacity: 0.55; font-size: 0.85rem; }
</style>
"""


def render(conn, search, tag_filter):
    containers_df = repo.list_containers(conn)
    if containers_df.empty:
        st.info(i18n.t("tree.empty"))
        return

    # ===== 详情模式：从树点击「详情」就地打开该容器的详情页 =====
    if st.session_state.get("tree_detail_id") is not None:
        cid = st.session_state.tree_detail_id
        col1, _ = st.columns([1, 6])
        with col1:
            if st.button(i18n.t("items.back"), key="tree_detail_back",
                         use_container_width=True):
                st.session_state.tree_detail_id = None
                st.rerun()
        render_detail_readonly(conn, containers_df, cid,
                               exit_key="tree_detail_id", key_prefix="tree_item")
        return

    st.subheader(i18n.t("app.tab.tree"))
    st.markdown(_TREE_CSS, unsafe_allow_html=True)

    # 直接物品数统计（配合侧边栏筛选；空 df 时 groupby 会崩，需兜底）
    df_all = repo.get_filtered_data(conn, search, tag_filter)
    if df_all.empty:
        item_counts = {}
    else:
        item_counts = df_all.groupby("container_id").size().to_dict()

    st.caption(i18n.t("tree.summary", containers=len(containers_df), items=len(df_all)))

    def render_tree(parent_id=None, depth=0):
        if parent_id is None:
            children = containers_df[containers_df["parent_id"].isna()]
        else:
            children = containers_df[containers_df["parent_id"] == parent_id]
        rows = children.sort_values("id")
        n = len(rows)
        for i, (_, row) in enumerate(rows.iterrows()):
            is_last = (i == n - 1)
            cid = int(row["id"])
            count = item_counts.get(cid, 0)
            name = html.escape(str(row["name"]))
            location = html.escape(str(row.get("location") or ""))
            has_children = bool((containers_df["parent_id"] == cid).any())
            icon = "🗂️" if has_children else "📦"
            loc_html = f'<span class="tree-loc">📍 {location}</span>' if location else ""
            # 行内装饰：margin-left 按深度缩进，徽标显示物品数，悬停高亮
            row_html = (
                f'<div class="tree-row" style="margin-left:{depth * 18}px;">'
                f'<span class="tree-icon">{icon}</span>'
                f'<span class="tree-name">{name}</span>'
                f'<span class="tree-badge">{count}</span>'
                f'{loc_html}'
                f'</div>'
            )
            col1, col2 = st.columns([6, 1])
            with col1:
                st.markdown(row_html, unsafe_allow_html=True)
            with col2:
                if st.button(i18n.t("tree.view_detail"), key=f"tree_btn_{cid}",
                             use_container_width=True):
                    st.session_state.tree_detail_id = cid   # 树 Tab 内就地打开详情页
                    st.toast(i18n.t("tree.goto_detail", name=row["name"]))
                    st.rerun()
            render_tree(cid, depth + 1)

    render_tree()
