# -*- coding: utf-8 -*-
"""Tab6 新增物品：录入表单（自动编号 + 标签 + 多图）+ CSV 批量导入。"""
from datetime import date
import pandas as pd
import streamlit as st
import db
import repo
import i18n


def render(conn, container_options):
    with st.form("add_item", clear_on_submit=True):
        st.subheader(i18n.t("add.title"))
        col1, col2 = st.columns(2)
        with col1:
            if 'draft_item_no' not in st.session_state:
                st.session_state.draft_item_no = db.next_item_no(conn)
            item_no = st.text_input(i18n.t("add.item_no"), key="draft_item_no")
            name = st.text_input(i18n.t("form.name"))
            container_name = st.selectbox(i18n.t("form.container"), list(container_options.keys()))
            purchase_date = st.date_input(i18n.t("form.purchase_date"), value=date.today())
        with col2:
            platform = st.text_input(i18n.t("form.platform"))
            order_no = st.text_input(i18n.t("form.order_no"))
            price = st.number_input(i18n.t("form.price"), min_value=0.0, format="%.2f", step=0.1)
            tags = st.text_input(i18n.t("form.tags"))
        features = st.text_area(i18n.t("form.features"))
        description = st.text_area(i18n.t("form.description"))
        uploaded_files = st.file_uploader(i18n.t("add.upload_images"), type=['jpg', 'png', 'jpeg', 'gif'],
                                          accept_multiple_files=True)

        if st.form_submit_button(i18n.t("add.save")):
            if not item_no or not name:
                st.error(i18n.t("form.required_msg"))
            elif repo.item_no_exists(conn, item_no):
                st.error(i18n.t("add.item_no_exists", item_no=item_no))
            else:
                try:
                    repo.add_item(conn, item_no, name, container_options[container_name],
                                  purchase_date.strftime('%Y-%m-%d'), platform, order_no,
                                  price, features, description, tags, uploaded_files)
                    st.session_state.draft_item_no = db.next_item_no(conn)   # 预生成下一个编号
                    st.toast(i18n.t("add.saved", item_no=item_no), icon="🎉")
                    st.rerun()
                except Exception as e:
                    db.logger.exception("保存物品失败")
                    st.error(i18n.t("add.save_fail", err=e))
                    conn.rollback()

    # ==================== CSV 批量导入区（表单外） ====================
    st.divider()
    with st.expander(i18n.t("import.title")):
        col_t, col_h = st.columns([1, 3])
        with col_t:
            st.download_button(i18n.t("import.download_template"),
                               data=repo.import_template_csv(),
                               file_name="import_template.csv", mime="text/csv",
                               use_container_width=True)
        with col_h:
            st.caption(i18n.t("import.header_hint", cols=", ".join(repo.IMPORT_COLUMNS)))

        upload = st.file_uploader(i18n.t("import.upload_label"), type=["csv"], key="import_csv")
        if upload is not None:
            # 文件变化时重置导入状态（防止重复导入同一批数据）
            if st.session_state.get('import_uploaded_name') != upload.name:
                st.session_state.import_uploaded_name = upload.name
                st.session_state.import_last_done = False

            if st.session_state.get('import_last_done'):
                st.info(i18n.t("import.done"))
            else:
                try:
                    rows, errors = repo.parse_import_csv(upload, container_options)
                except Exception as e:
                    db.logger.exception("解析 CSV 失败")
                    st.error(i18n.t("import.parse_fail", err=e))
                    rows, errors = [], []

                st.write(i18n.t("import.parse_done", ok=len(rows), err=len(errors)))
                if rows:
                    preview_cols = [c for c in repo.IMPORT_COLUMNS if c != 'item_no']
                    preview_df = pd.DataFrame(
                        [{c: r.get(c, '') for c in preview_cols} for r in rows])
                    st.dataframe(preview_df, use_container_width=True, height=220)
                if errors:
                    st.error(i18n.t("import.errors_title"))
                    st.dataframe(pd.DataFrame(errors, columns=[i18n.t("import.row_no"),
                                                               i18n.t("import.error")]),
                                 use_container_width=True, height=160)
                if rows and st.button(i18n.t("import.confirm", n=len(rows)), use_container_width=True):
                    try:
                        ok, imp_errors = repo.import_items(conn, rows)
                        st.session_state.import_last_done = True
                        msg = i18n.t("import.done_ok", ok=ok)
                        if imp_errors:
                            msg += i18n.t("import.done_fail_sep", n=len(imp_errors))
                        st.success(msg)
                        if imp_errors:
                            st.dataframe(pd.DataFrame(imp_errors, columns=[i18n.t("import.row_no"),
                                                                            i18n.t("import.error")]),
                                         use_container_width=True, height=160)
                        st.rerun()
                    except Exception as e:
                        db.logger.exception("批量导入失败")
                        st.error(i18n.t("import.fail", err=e))
                        conn.rollback()
