# -*- coding: utf-8 -*-
"""侧边栏：语言切换、全局筛选、SQL 控制台、备份状态、孤儿图片清理。"""
import os
import sqlite3
import pandas as pd
import streamlit as st
import db
import i18n


def render(conn):
    """渲染侧边栏，返回 (search, tag_filter) 供各 Tab 使用。"""
    with st.sidebar:
        # ---- 语言切换（写入 session_state.lang，rerun 后 app.py 顶部 set_lang 生效） ----
        # 选项值用语言码（跨语言稳定），显示文本走 i18n（lang.zh/lang.en）：
        # 中文界面下选项显示「中文/英语」而非硬编码的 "English"（用户反馈：界面中文、
        # 选项却是英文）。不能拿本地化文本当 option 值——切语言后旧会话残留的旧标签
        # 会在新选项列表里失配，选择器会跳回首项。
        lang_codes = ["zh", "en"]
        current_lang = st.session_state.get('lang', 'en')
        if current_lang not in lang_codes:
            current_lang = 'en'
        lang_code = st.selectbox(
            i18n.t("lang.label"), lang_codes,
            index=lang_codes.index(current_lang), key="global_lang_code",
            format_func=lambda c: i18n.t(f"lang.{c}"))
        st.session_state.lang = lang_code
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
                    # 只读连接执行（mode=ro 由 SQLite 强制）：误输 DROP/DELETE/UPDATE
                    # 直接报错，无法破坏数据；主连接供全应用读写，不给控制台碰
                    ro = sqlite3.connect(f"file:{db.DB_PATH}?mode=ro", uri=True)
                    try:
                        df = pd.read_sql_query(sql_query, ro)
                    finally:
                        ro.close()
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
                    # 同步重置进程级缓存（app.py 的 10 分钟复用），避免下次会话仍提示已清理的孤儿
                    db.BG["orphans"] = []
                    import time as _time
                    db.BG["orphans_ts"] = _time.time()
                    st.toast(i18n.t("sidebar.orphan_cleaned", n=n), icon="🧹")
                    st.rerun()
                except Exception as e:
                    db.logger.exception("清理孤儿记录失败")
                    st.error(i18n.t("sidebar.orphan_fail", err=e))
                    conn.rollback()
        return search, tag_filter
