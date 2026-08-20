# -*- coding: utf-8 -*-
"""侧边栏：语言切换、全局筛选、SQL 控制台、备份状态、孤儿图片清理。"""
import os
import pandas as pd
import streamlit as st
import db
import i18n


def render(conn):
    """渲染侧边栏，返回 (search, tag_filter) 供各 Tab 使用。"""
    with st.sidebar:
        # ---- 语言切换（写入 session_state.lang，rerun 后 app.py 顶部 set_lang 生效） ----
        lang_opts = {"中文": "zh", "English": "en"}
        current_lang = st.session_state.get('lang', 'en')
        cur_label = next((lb for lb, code in lang_opts.items() if code == current_lang), "English")
        lang_label = st.selectbox(i18n.t("lang.label"), list(lang_opts.keys()),
                                  index=list(lang_opts.keys()).index(cur_label), key="global_lang")
        st.session_state.lang = lang_opts[lang_label]
        i18n.set_lang(st.session_state.lang)   # 立即生效（sidebar 之后渲染的内容用新语言）

        st.divider()
        st.header(i18n.t("sidebar.filter_title"))
        # 控件带显式 key：widget 值与 session_state[key] 双向绑定，跨 rerun/测试可靠
        search = st.text_input(i18n.t("sidebar.search_label"), key="global_search",
                               placeholder=i18n.t("sidebar.search_placeholder"))
        tag_filter = st.text_input(i18n.t("sidebar.tag_label"), key="global_tag_filter",
                                   value=st.session_state.tag_filter)
        # 同步到旧访问器，保持 items_tab 等模块兼容
        st.session_state.tag_filter = tag_filter
        st.divider()
        with st.expander(i18n.t("sidebar.sql_title")):
            sql_query = st.text_area(i18n.t("sidebar.sql_input"), "SELECT * FROM items LIMIT 10")
            if st.button(i18n.t("sidebar.sql_run")):
                try:
                    df = pd.read_sql_query(sql_query, conn)
                    st.dataframe(df)
                except Exception as e:
                    db.logger.exception("SQL 查询失败")
                    st.error(i18n.t("sidebar.sql_error", err=e))

        st.divider()
        if st.session_state.last_backup:
            st.caption(i18n.t("sidebar.last_backup", name=os.path.basename(st.session_state.last_backup)))
        if st.session_state.orphans:
            st.warning(i18n.t("sidebar.orphans_warn", n=len(st.session_state.orphans)))
            if st.button(i18n.t("sidebar.orphan_clean"), use_container_width=True):
                try:
                    n = len(st.session_state.orphans)
                    for (img_id, _, _, table) in st.session_state.orphans:
                        # table 仅来自 find_orphan_images 的白名单（images / container_images）
                        conn.execute(f"DELETE FROM {table} WHERE id=?", (img_id,))
                    conn.commit()
                    st.session_state.orphans = []
                    st.toast(i18n.t("sidebar.orphan_cleaned", n=n), icon="🧹")
                    st.rerun()
                except Exception as e:
                    db.logger.exception("清理孤儿记录失败")
                    st.error(i18n.t("sidebar.orphan_fail", err=e))
                    conn.rollback()
        return search, tag_filter
