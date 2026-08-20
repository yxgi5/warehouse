# -*- coding: utf-8 -*-
"""Tab3 时间线：按购买年份分组浏览物品。"""
import pandas as pd
import streamlit as st
import repo
import i18n


def render(conn, search, tag_filter):
    st.subheader(i18n.t("app.tab.timeline"))
    df_all = repo.get_filtered_data(conn, search, tag_filter)
    if df_all.empty:
        st.info(i18n.t("common.no_items"))
    else:
        df_all['year'] = pd.to_datetime(df_all['purchase_date'], errors='coerce').dt.year
        years = sorted(df_all['year'].dropna().unique(), reverse=True)
        for yr in years:
            with st.expander(i18n.t("timeline.expander", year=int(yr),
                                    count=len(df_all[df_all['year'] == yr]))):
                yr_df = df_all[df_all['year'] == yr][['item_no', 'name', 'container_name', 'purchase_date']]
                st.dataframe(yr_df, use_container_width=True, hide_index=True)
