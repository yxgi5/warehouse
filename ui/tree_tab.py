# -*- coding: utf-8 -*-
"""Tab5 容器树：纯容器层级树，体现容器间的父子相对关系。

设计要点（Phase 8 折叠化改造）：
- 默认只渲染第一级（顶层容器），点击节点才展开其直接子容器：长树不再一屏到底，
  没有 Home 键的键盘免去疯狂滚动。
- 图标：统一使用文件夹图标（合上 📁 / 展开 📂），按展开态切换，不再区分硬盘/文件夹。
- 行主体（图标+名称区域）点击 = 展开/收起；行尾「详情」按钮保留，就地打开详情页
  （复用 containers_tab.render_detail_readonly，与容器管理 Tab 一致；返回回到树）。
- 展开状态存 session_state（tree_expanded 集合）：切换 Tab / 做其他操作回来保持，
  刷新浏览器重置为全收起（无残留、无持久化副作用）。
- 搜索框：按容器名 / 位置匹配；命中节点的所有祖先自动展开、命中行以 🔍 前缀高亮，
  一眼看到全部匹配（浏览器 Ctrl+F 拦不到、且找不到未渲染节点，故用页面内搜索）。
- 顶部「全部展开 / 全部收起」快捷按钮，偶尔总览全库一键铺开。
- 注意：SQLite parent_id NULL 读入 pandas 后是 NaN，顶层容器必须用 isna() 匹配。
"""
import streamlit as st
import pandas as pd
import repo
import i18n
from ui.containers_tab import render_detail_readonly

# 展开状态集合（session 内记忆）：存已展开容器的 id
_EXPAND_KEY = "tree_expanded"


def _toggle(cid):
    s = st.session_state.setdefault(_EXPAND_KEY, set())
    if cid in s:
        s.discard(cid)
    else:
        s.add(cid)


def _expand_all(cids):
    st.session_state[_EXPAND_KEY] = set(cids)


def _collapse_all():
    st.session_state[_EXPAND_KEY] = set()


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
    item_counts = (df_all.groupby("container_id").size().to_dict()
                   if not df_all.empty else {})

    # ===== 构建层级索引 =====
    rows = containers_df.sort_values("id")
    parent_of = {int(r["id"]): (int(r["parent_id"]) if pd.notna(r["parent_id"]) else None)
                 for _, r in rows.iterrows()}
    children_map = {}
    name_of, loc_of = {}, {}
    for _, r in rows.iterrows():
        cid = int(r["id"])
        pid = int(r["parent_id"]) if pd.notna(r["parent_id"]) else None
        children_map.setdefault(pid, []).append(cid)
        name_of[cid] = str(r["name"])
        loc_of[cid] = str(r.get("location") or "")

    st.caption(i18n.t("tree.summary", containers=len(containers_df), items=len(df_all)))

    # ===== 搜索 + 全部展开/收起 =====
    q = (st.text_input(i18n.t("tree.search"), key="tree_search") or "").strip().lower()
    ctl1, ctl2, ctl3 = st.columns([4, 1, 1])
    with ctl2:
        st.button(i18n.t("tree.expand_all"), on_click=_expand_all,
                  args=(list(name_of.keys()),), use_container_width=True)
    with ctl3:
        st.button(i18n.t("tree.collapse_all"), on_click=_collapse_all,
                  use_container_width=True)

    expanded = set(st.session_state.get(_EXPAND_KEY, set()))
    matched = set()
    if q:
        for cid, nm in name_of.items():
            if q in nm.lower() or q in loc_of.get(cid, "").lower():
                matched.add(cid)
        # 命中节点的所有祖先自动展开，确保命中行可见
        for cid in matched:
            p = parent_of.get(cid)
            while p is not None:
                expanded.add(p)
                p = parent_of.get(p)
        if matched:
            st.caption(i18n.t("tree.hit_count", n=len(matched)))
        else:
            st.caption(i18n.t("tree.no_match"))

    # ===== 递归渲染（仅在 expanded 内向下展开）=====
    def render_node(cid, depth):
        kids = children_map.get(cid, [])
        has_children = bool(kids)
        is_open = cid in expanded
        # 图标统一为文件夹：合上 📁 / 展开 📂（不区分硬盘，按展开态切换）
        icon = "📂" if is_open else "📁"
        arrow = "▾ " if is_open else ("▸ " if has_children else "· ")
        indent = " " * depth  # 全角空格，等比缩进
        nm = name_of[cid]
        cnt = item_counts.get(cid, 0)
        loc = loc_of.get(cid, "")
        hit = "🔍 " if cid in matched else ""
        label = (f"{hit}{indent}{arrow}{icon} {nm}  ({cnt})"
                 + (f"  📍 {loc}" if loc else ""))
        c1, c2 = st.columns([6, 1])
        with c1:
            # 行主体点击 = 展开/收起
            st.button(label, key=f"tree_toggle_{cid}", on_click=_toggle,
                      args=(cid,), use_container_width=True)
        with c2:
            if st.button(i18n.t("tree.view_detail"), key=f"tree_btn_{cid}",
                         use_container_width=True):
                st.session_state.tree_detail_id = cid   # 树 Tab 内就地打开详情页
                st.toast(i18n.t("tree.goto_detail", name=nm))
                st.rerun()
        if is_open:
            for ch in kids:
                render_node(ch, depth + 1)

    for top in children_map.get(None, []):
        render_node(top, 0)
