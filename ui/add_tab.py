# -*- coding: utf-8 -*-
"""物品新增子页面：录入表单（编号/容器/日期均无预填 + 标签 + 照片暂存）+ CSV 批量导入。

原为独立 Tab（「➕ 新增物品」），Phase 7 起收进「物品浏览」Tab 作为子页面
（与详情/编辑子页面同级的 add_item_mode 态）：入口按钮放在物品 Tab 浏览态
顶部，从其他 Tab 不应直接进入新增页，否则会覆盖当前浏览状态、造成逻辑混乱。
保存成功后在本 Tab 内直接打开新物品详情，不再需要跨 Tab 跳转机制。

照片交互与编辑页同款（Step 4 对齐）：上传器与「添加图片」按钮在表单外独立成区，
选中的照片先进暂存区预览、可上移/下移/移除，点「保存物品」时随 add_item
一并落库（repo 层按内容 sha256 去重）；暂存列表存 session_state（UploadedFile
跨 rerun 保留），保存/取消即清空，避免残留到下一次新增。
"""
import pandas as pd
import streamlit as st
import db
import repo
import i18n


def render(conn, container_options):
    # 照片暂存区（表单外）：先选文件 → 「添加图片」加入暂存并预览 → 保存时一并生效
    staged = st.session_state.setdefault('add_staged_photos', [])

    with st.form("add_item", clear_on_submit=True):
        st.subheader(i18n.t("add.title"))
        col1, col2 = st.columns(2)
        with col1:
            # 编号由用户自行输入，不预填自动编号（真实使用中多为自有编号如 A0330）；
            # 自动编号 next_item_no 保留给 CSV 导入等场景。容器与购买日期可填但默认
            # 不给内容：容器下拉首项占位=不选（保存为未归档），日期默认无（不默认今天）。
            item_no = st.text_input(i18n.t("add.item_no"), key="draft_item_no")
            name = st.text_input(i18n.t("form.name"), key="add_name")
            cont_opts = [i18n.t("add.select_container")] + list(container_options.keys())
            container_name = st.selectbox(i18n.t("form.container"), cont_opts)
            # date_input 无法原生留空（不给 value 也默认今天）。勾选框是保存语义：
            # 默认勾选=无购买日期（存空）；取消勾选即可填日期。注意不能把 date_input
            # disabled 绑定到勾选框——form 内控件变化不触发 rerun，禁用状态不会刷新，
            # 会出现“勾了没反应/取消了仍不可填”。日期框始终保持可用。
            no_date = st.checkbox(i18n.t("common.no_date"), value=True,
                                  help=i18n.t("common.no_date_help"))
            purchase_date = st.date_input(i18n.t("form.purchase_date"))
            related_items = st.text_input(i18n.t("form.related_items"),
                                          help=i18n.t("form.related_help"))
        with col2:
            platform = st.text_input(i18n.t("form.platform"))
            order_no = st.text_input(i18n.t("form.order_no"))
            price = st.number_input(i18n.t("form.price"), min_value=0.0, format="%.2f", step=0.1, key="add_price")
            quantity = st.number_input(i18n.t("form.quantity"), min_value=1, step=1, value=1, key="add_quantity")
            unit = st.text_input(i18n.t("form.unit"), placeholder=i18n.t("form.unit_ph"), key="add_unit")
            tags = st.text_input(i18n.t("form.tags"), key="add_tags")
        features = st.text_area(i18n.t("form.features"))
        description = st.text_area(i18n.t("form.description"))

        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            submitted = st.form_submit_button(i18n.t("add.save"))
        with col_btn2:
            cancel = st.form_submit_button(i18n.t("common.cancel"))

        if cancel:
            # 取消新增：清空照片暂存（避免下次进入残留上次的草稿）并回到物品浏览态
            st.session_state.add_staged_photos = []
            st.session_state.add_item_mode = False
            st.rerun()

        if submitted:
            if not item_no or not name:
                st.error(i18n.t("form.required_msg"))
            elif repo.item_no_exists(conn, item_no):
                st.error(i18n.t("add.item_no_exists", item_no=item_no))
            else:
                try:
                    # 暂存照片随保存一并落库（repo.add_item → attach_item_images 内容去重）
                    item_id = repo.add_item(conn, item_no, name,
                                            container_options.get(container_name),  # 占位未选 → 未归档
                                            purchase_date.strftime('%Y-%m-%d') if (purchase_date and not no_date) else '',
                                            platform, order_no, price, features, description,
                                            tags, list(staged), repo.parse_related_text(related_items),
                                            quantity=quantity, unit=unit)
                    # 保存成功：清暂存、退出新增态并直接打开新物品详情
                    st.session_state.add_staged_photos = []
                    st.session_state.detail_item_id = item_id
                    st.session_state.add_item_mode = False
                    st.toast(i18n.t("add.saved", item_no=item_no), icon="🎉")
                    st.rerun()
                except Exception as e:
                    db.logger.exception("保存物品失败")
                    st.error(i18n.t("add.save_fail", err=e))
                    conn.rollback()

    # ==================== 照片暂存区（表单外，与编辑页同款布局） ====================
    # 表单字段在点暂存区按钮的 rerun 中保留（Streamlit form 未提交时控件状态持久）
    col_up, col_btn = st.columns([3, 1])
    with col_up:
        new_files = st.file_uploader(i18n.t("add.upload_images"),
                                     type=['jpg', 'jpeg', 'png', 'gif', 'webp'],
                                     accept_multiple_files=True, key="add_uploaded_files")
        st.caption(i18n.t("items.photo_hint_draft"))
    with col_btn:
        # keyed 容器供 CSS 垂直居中（相对上传框），见 app.py .st-key-*_photo_add_btn
        with st.container(key="add_photo_btn"):
            add_clicked = st.button(i18n.t("items.add_photos"), key="add_stage_photos",
                                    use_container_width=True)
        if add_clicked:
            if not new_files:
                st.warning(i18n.t("items.no_photos_selected"))
            else:
                # 按 (文件名, 大小) 防重复加入暂存（保存落库时另有内容级去重兜底）
                seen = {(f.name, f.size) for f in staged}
                add = [f for f in new_files if (f.name, f.size) not in seen]
                if add:
                    staged.extend(add)
                    st.toast(i18n.t("items.photos_added", n=len(add)), icon="🖼️")
                else:
                    st.warning(i18n.t("items.photos_none_new"))
                st.rerun()

    if staged:
        st.write(i18n.t("items.staged_images"))
        for idx, f in enumerate(staged):
            col_img, col_mv_up, col_mv_down, col_del = st.columns([3, 1, 1, 1])
            with col_img:
                st.image(f, width=120)
            with col_mv_up:
                if idx > 0:
                    if st.button(i18n.t("items.img_up"), key=f"staged_up_{idx}",
                                 use_container_width=True):
                        staged[idx - 1], staged[idx] = staged[idx], staged[idx - 1]
                        st.rerun()
                else:
                    st.button(i18n.t("items.img_up"), key=f"staged_up_{idx}_disabled",
                              disabled=True, use_container_width=True)
            with col_mv_down:
                if idx < len(staged) - 1:
                    if st.button(i18n.t("items.img_down"), key=f"staged_down_{idx}",
                                 use_container_width=True):
                        staged[idx + 1], staged[idx] = staged[idx], staged[idx + 1]
                        st.rerun()
                else:
                    st.button(i18n.t("items.img_down"), key=f"staged_down_{idx}_disabled",
                              disabled=True, use_container_width=True)
            with col_del:
                if st.button(i18n.t("items.img_del"), key=f"staged_del_{idx}",
                             use_container_width=True):
                    staged.pop(idx)
                    st.rerun()
    else:
        st.caption(i18n.t("common.no_images"))

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
