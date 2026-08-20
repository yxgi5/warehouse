# -*- coding: utf-8 -*-
"""Tab2 数据看板：总览指标、容器分布、年份分布、热门标签。"""
import pandas as pd
import streamlit as st
import repo
import i18n


def render(conn, search, tag_filter):
    st.subheader(i18n.t("app.tab.dashboard"))
    df_all = repo.get_filtered_data(conn, search, tag_filter)
    total_items = len(df_all)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(i18n.t("dash.total_items"), total_items)
    with col2:
        total_value = df_all['price'].sum()
        st.metric(i18n.t("dash.total_value"), f"¥{total_value:.2f}" if total_value else i18n.t("dash.none"))
    with col3:
        container_count = df_all['container_name'].nunique()
        st.metric(i18n.t("dash.container_count"), container_count)

    # 容器分布
    st.subheader(i18n.t("dash.container_dist"))
    if not df_all.empty:
        container_stats = df_all['container_name'].value_counts().reset_index()
        container_stats.columns = [i18n.t("dash.col_container"), i18n.t("dash.col_count")]
        st.bar_chart(container_stats.set_index(i18n.t("dash.col_container")))
    else:
        st.info(i18n.t("common.no_data"))

    # 购买年份分布
    st.subheader(i18n.t("dash.year_dist"))
    if not df_all.empty:
        df_all['year'] = pd.to_datetime(df_all['purchase_date'], errors='coerce').dt.year
        year_stats = df_all['year'].value_counts().sort_index().reset_index()
        year_stats.columns = [i18n.t("dash.col_year"), i18n.t("dash.col_count")]
        st.bar_chart(year_stats.set_index(i18n.t("dash.col_year")))
    else:
        st.info(i18n.t("common.no_data"))

    # 热门标签
    st.subheader(i18n.t("dash.hot_tags"))
    if not df_all.empty:
        all_tags = df_all['tags'].dropna().str.split(',').explode().str.strip()
        tag_counts = all_tags.value_counts().head(10).reset_index()
        tag_counts.columns = [i18n.t("dash.col_tag"), i18n.t("dash.col_times")]
        st.dataframe(tag_counts, use_container_width=True)
    else:
        st.info(i18n.t("common.no_data"))
