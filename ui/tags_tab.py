# -*- coding: utf-8 -*-
"""Tab4 标签墙：点击标签精确筛选。"""
import streamlit as st
import repo
import i18n


def render(conn, search, tag_filter):
    st.subheader(i18n.t("app.tab.tags"))
    df_all = repo.get_filtered_data(conn, search, tag_filter)
    if df_all.empty:
        st.info(i18n.t("tags.none"))
    else:
        all_tags = df_all['tags'].dropna().str.split(',').explode().str.strip()
        unique_tags = sorted(all_tags.unique())
        if not unique_tags:
            st.info(i18n.t("tags.none"))
        else:
            cols = st.columns(4)
            for i, tag in enumerate(unique_tags):
                with cols[i % 4]:
                    count = all_tags[all_tags == tag].count()
                    if st.button(f"#{tag} ({count})", use_container_width=True):
                        st.session_state.tag_filter = tag
                        st.rerun()
