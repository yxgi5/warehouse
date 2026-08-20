# -*- coding: utf-8 -*-
"""Tab5 容器树：纯容器层级树，体现容器间的父子相对关系。

设计要点：
- 每行 = 分支线 + 容器名 + 直接物品数统计；不列具体物品
  （具体物品请看「容器管理」Tab 的容器详情页清单）。
- 行尾「详情」按钮在树 Tab 内就地打开该容器的详情页
  （复用 containers_tab.render_detail_readonly，与容器管理 Tab 详情一致；
  返回按钮回到树）。注：Streamlit 1.40 的 st.tabs 不支持 key/on_change，
  无法程序化切换 Tab，故采用就地展开而非跨 Tab 跳转。
- 注意：SQLite parent_id NULL 读入 pandas 后是 NaN，顶层容器必须用
  isna() 匹配（`== None` 恒 False 会导致整树空白）。
"""
import streamlit as st
import repo
import i18n
from ui.containers_tab import render_detail_readonly


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

    # 直接物品数统计（配合侧边栏筛选；空 df 时 groupby 会崩，需兜底）
    df_all = repo.get_filtered_data(conn, search, tag_filter)
    if df_all.empty:
        item_counts = {}
    else:
        item_counts = df_all.groupby("container_id").size().to_dict()

    st.caption(i18n.t("tree.summary", containers=len(containers_df), items=len(df_all)))

    def render_tree(parent_id=None, prefix=""):
        if parent_id is None:
            children = containers_df[containers_df["parent_id"].isna()]
        else:
            children = containers_df[containers_df["parent_id"] == parent_id]
        rows = children.sort_values("id")
        n = len(rows)
        for i, (_, row) in enumerate(rows.iterrows()):
            is_last = (i == n - 1)
            branch = "└─ " if is_last else "├─ "
            cid = int(row["id"])
            count = item_counts.get(cid, 0)
            line = f"{prefix}{branch}{i18n.t('tree.container_line', name=row['name'], count=count)}"
            col1, col2 = st.columns([6, 1])
            with col1:
                st.markdown(line)
            with col2:
                if st.button(i18n.t("tree.view_detail"), key=f"tree_btn_{cid}",
                             use_container_width=True):
                    st.session_state.tree_detail_id = cid   # 树 Tab 内就地打开详情页
                    st.toast(i18n.t("tree.goto_detail", name=row["name"]))
                    st.rerun()
            child_prefix = prefix + ("   " if is_last else "│  ")
            render_tree(cid, child_prefix)

    render_tree()
