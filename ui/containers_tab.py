# -*- coding: utf-8 -*-
"""Tab7 容器管理：树形容器的增删改 + 表格/卡片双视图 + 容器详情页（照片/物品清单）。

Phase 6 新增：
- 容器照片：container_images 独立表，详情页内上传/删除/排序；
- 浏览视图：表格（含批量操作）↔ 卡片（首图+信息，点击进详情）；
- 详情页：多图画廊 + 信息区 + 内部物品清单（点击跳转物品浏览标签的详情页）。

注意：容器列表不再在本 Tab 内重复重建——app.py 顶层每次 rerun 统一查询一次
（repo.get_container_options），本模块变更容器后仅 st.rerun() 即可刷新全局下拉框。
"""
import os
import mimetypes
import streamlit as st
import db
import repo
import i18n

try:
    from streamlit.runtime import get_instance as _st_get_instance
except Exception:  # 版本变动时退回 st.image 满宽显示
    _st_get_instance = None

_CARD_IMG_MAX_H = 300   # 卡片首图高度上限，与物品详情页缩略图规格一致


@st.dialog("⚠️")
def confirm_container_delete(conn, ids, names_text):
    st.subheader(i18n.t("containers.confirm_title"))
    st.write(i18n.t("containers.confirm_msg", n=len(ids), names=names_text))
    col1, col2 = st.columns(2)
    with col1:
        if st.button(i18n.t("common.confirm_delete"), key="confirm_delete_container_yes"):
            try:
                repo.delete_containers(conn, ids)
                st.toast(i18n.t("containers.deleted", n=len(ids)), icon="🗑️")
                st.session_state.edit_container_id = None
                st.session_state.add_container_mode = False
                st.session_state.container_detail_id = None
                st.rerun()
            except Exception as e:
                db.logger.exception("删除容器失败")
                st.error(i18n.t("containers.delete_fail", err=e))
                conn.rollback()
    with col2:
        if st.button(i18n.t("common.cancel"), key="confirm_delete_container_no"):
            st.rerun()


def render_edit_form(conn, containers_df, is_edit, cont_id=None):
    """编辑/新增容器的表单。is_edit=True 时 cont_id 必填。"""
    if is_edit:
        cont_data = repo.get_container(conn, cont_id)
        if not cont_data:
            st.warning(i18n.t("containers.not_found"))
            st.session_state.edit_container_id = None
            st.rerun()
            return
        _, current_name, current_parent_id, current_location = cont_data
        title = i18n.t("containers.edit_title", name=current_name)
    else:
        current_name = ""
        current_parent_id = None
        current_location = ""
        title = i18n.t("containers.add_title")

    st.subheader(title)
    with st.form("container_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input(i18n.t("containers.name"), value=current_name)
            # 上级容器（编辑时排除自身，新增时全部可选）
            if is_edit:
                parent_options = containers_df[containers_df['id'] != cont_id][['name', 'id']].copy()
            else:
                parent_options = containers_df[['name', 'id']].copy()
            parent_dict = dict(zip(parent_options['name'], parent_options['id']))
            none_label = i18n.t("containers.none_parent")
            parent_names = [none_label] + list(parent_dict.keys())
            # 当前上级名称（仅编辑时）
            if is_edit:
                current_parent_name = None
                if current_parent_id is not None:
                    current_parent_row = containers_df[containers_df['id'] == current_parent_id]
                    if not current_parent_row.empty:
                        current_parent_name = current_parent_row.iloc[0]['name']
                default_index = (0 if current_parent_name is None
                                 else parent_names.index(current_parent_name) if current_parent_name in parent_names else 0)
            else:
                default_index = 0
            selected_parent_name = st.selectbox(i18n.t("containers.parent"), parent_names,
                                                index=default_index)
            if selected_parent_name == none_label:
                new_parent_id = None
            else:
                new_parent_id = parent_dict[selected_parent_name]
        with col2:
            new_location = st.text_input(i18n.t("containers.location"), value=current_location)

        # 按钮布局：三列（更新/添加、取消、删除【仅编辑】）
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        with col_btn1:
            if is_edit:
                submitted = st.form_submit_button(i18n.t("containers.update"), use_container_width=True)
            else:
                submitted = st.form_submit_button(i18n.t("containers.add"), use_container_width=True)
        with col_btn2:
            cancel = st.form_submit_button(i18n.t("common.cancel"), use_container_width=True)
        with col_btn3:
            if is_edit:
                delete_btn = st.form_submit_button(i18n.t("containers.delete_btn"), use_container_width=True)
            else:
                delete_btn = False

        if submitted:
            if not new_name:
                st.error(i18n.t("containers.name_empty"))
            elif repo.container_name_exists(conn, new_name, exclude_id=cont_id if is_edit else None):
                st.error(i18n.t("containers.name_taken"))
            else:
                try:
                    if is_edit:
                        repo.update_container(conn, cont_id, new_name, new_parent_id, new_location)
                        saved_msg = i18n.t("containers.saved_updated", name=new_name)
                    else:
                        repo.add_container(conn, new_name, new_parent_id, new_location)
                        saved_msg = i18n.t("containers.saved_added", name=new_name)
                    st.toast(saved_msg, icon="✅")
                    st.session_state.edit_container_id = None
                    st.session_state.add_container_mode = False
                    st.rerun()   # 全局容器选项由 app.py 顶层重新查询
                except Exception as e:
                    db.logger.exception("保存容器失败")
                    st.error(i18n.t("containers.op_fail", err=e))
                    conn.rollback()
        if cancel:
            st.session_state.edit_container_id = None
            st.session_state.add_container_mode = False
            st.rerun()
        if delete_btn:
            # 检查容器是否可删除（无物品且无子容器）
            item_count, child_count = repo.container_usage(conn, cont_id)
            if item_count > 0 or child_count > 0:
                st.error(i18n.t("containers.not_empty", n=item_count, m=child_count))
            else:
                confirm_container_delete(conn, [cont_id], current_name)


# ==================== 容器详情页（Phase 6） ====================

def render_detail_readonly(conn, containers_df, cid, exit_key, key_prefix="cd"):
    """容器详情的只读部分：多图画廊 + 信息区 + 内部物品清单（可跳物品详情）。

    容器管理 Tab 与容器树 Tab 共用，保证两处详情一致。
    - exit_key：物品清单跳转时清除的 session_state key（退出当前详情）
    - key_prefix：物品跳转按钮 key 前缀，避免两处详情同时渲染时 widget ID 冲突
      （st.tabs 全量渲染，两个详情页同开时按钮 label 相同，key 必须唯一）
    """
    row = containers_df[containers_df['id'] == cid]
    if row.empty:
        st.warning(i18n.t("containers.not_found"))
        st.session_state[exit_key] = None
        st.rerun()
        return
    cont = row.iloc[0]
    name, parent_id, location = cont['name'], cont['parent_id'], cont['location'] or ''

    st.subheader(i18n.t("containers.detail_title", name=name))

    # 多图画廊（只读展示）
    img_paths = repo.load_container_images(conn, cid)
    if img_paths:
        st.write(i18n.t("containers.detail_images"))
        cols = st.columns(min(4, len(img_paths)))
        for idx, path in enumerate(img_paths):
            if os.path.exists(path):
                cols[idx % 4].image(path, use_container_width=True)
    else:
        st.caption(i18n.t("common.no_images"))

    # 信息区
    parent_name = i18n.t("containers.none_value")
    if parent_id is not None:
        prow = containers_df[containers_df['id'] == parent_id]
        if not prow.empty:
            parent_name = prow.iloc[0]['name']
    child_count = int((containers_df['parent_id'] == cid).sum())
    item_count, _ = repo.container_usage(conn, cid)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"{i18n.t('containers.detail_location')}: {location or i18n.t('containers.none_value')}")
        st.write(f"{i18n.t('containers.detail_parent')}: {parent_name}")
    with col2:
        st.write(f"{i18n.t('containers.detail_children')}: {child_count}")
        st.write(f"{i18n.t('containers.detail_items')}: {item_count}")

    # 内部物品清单（点击跳转物品浏览标签的详情页）
    items_in = repo.load_items_by_container(conn, cid)
    st.write(i18n.t("containers.detail_item_list"))
    if items_in:
        for item_id, item_no, item_name in items_in:
            c1, c2 = st.columns([1, 5])
            with c1:
                if st.button(i18n.t("items.open_detail"), key=f"{key_prefix}_item_{item_id}",
                             use_container_width=True):
                    st.session_state.detail_item_id = item_id
                    st.session_state[exit_key] = None   # 跳走即退出当前详情
                    st.toast(i18n.t("containers.jump_item_hint"), icon="📄")
                    st.rerun()
            with c2:
                st.write(f"{item_no} - {item_name}")
    else:
        st.caption(i18n.t("common.no_items"))


def render_detail_page(conn, containers_df, cid):
    """容器详情：工具栏（返回/编辑/删除）+ 只读详情 + 照片管理区。"""
    row = containers_df[containers_df['id'] == cid]
    if row.empty:
        st.warning(i18n.t("containers.not_found"))
        st.session_state.container_detail_id = None
        st.rerun()
        return
    cont = row.iloc[0]
    name, parent_id, location = cont['name'], cont['parent_id'], cont['location'] or ''

    # 顶部工具栏：返回 / 编辑 / 删除
    col1, col2, col3, col4 = st.columns([1, 6, 1, 1])
    with col1:
        if st.button(i18n.t("items.back"), key="cd_back", use_container_width=True):
            st.session_state.container_detail_id = None
            st.rerun()
    with col3:
        # 编辑后保留 container_detail_id，保存/取消后回到详情页
        if st.button(i18n.t("items.edit"), key="cd_edit", use_container_width=True):
            st.session_state.edit_container_id = cid
            st.rerun()
    with col4:
        if st.button(i18n.t("items.delete"), key="cd_delete", use_container_width=True):
            item_count, child_count = repo.container_usage(conn, cid)
            if item_count > 0 or child_count > 0:
                st.error(i18n.t("containers.not_empty", n=item_count, m=child_count))
            else:
                confirm_container_delete(conn, [cid], name)

    render_detail_readonly(conn, containers_df, cid, exit_key="container_detail_id", key_prefix="cd")

    # 照片管理区（上传 + 已有图删除/排序）
    st.divider()
    st.write(i18n.t("containers.upload_images"))
    uploaded = st.file_uploader(i18n.t("containers.upload_images"),
                                type=['jpg', 'png', 'jpeg', 'gif'],
                                accept_multiple_files=True, key="container_img_upload")
    if uploaded:
        try:
            repo.save_container_images(conn, cid, uploaded)
            st.rerun()
        except Exception as e:
            db.logger.exception("保存容器照片失败")
            st.error(i18n.t("containers.op_fail", err=e))
            conn.rollback()

    img_rows = repo.load_container_images_full(conn, cid)
    if img_rows:
        st.write(i18n.t("items.existing_images"))
        for idx, (img_id, abs_path, _order) in enumerate(img_rows):
            col_img, col_up, col_down, col_del = st.columns([3, 1, 1, 1])
            with col_img:
                if os.path.exists(abs_path):
                    st.image(abs_path, width=120)
                else:
                    st.caption(i18n.t("items.image_missing"))
            with col_up:
                if idx > 0:
                    if st.button(i18n.t("items.img_up"), key=f"cimg_up_{img_id}", use_container_width=True):
                        repo.move_container_image(conn, img_id, "up")
                        st.rerun()
                else:
                    st.button(i18n.t("items.img_up"), key=f"cimg_up_{img_id}_d", disabled=True,
                              use_container_width=True)
            with col_down:
                if idx < len(img_rows) - 1:
                    if st.button(i18n.t("items.img_down"), key=f"cimg_down_{img_id}", use_container_width=True):
                        repo.move_container_image(conn, img_id, "down")
                        st.rerun()
                else:
                    st.button(i18n.t("items.img_down"), key=f"cimg_down_{img_id}_d", disabled=True,
                              use_container_width=True)
            with col_del:
                if st.button(i18n.t("items.img_del"), key=f"cimg_del_{img_id}", use_container_width=True):
                    repo.delete_container_image(conn, img_id)
                    st.rerun()
    else:
        st.caption(i18n.t("common.no_images"))


# ==================== 表格视图 ====================

def render_browse(conn, containers_df):
    """表格视图：表格 + 工具栏（详情/编辑/删除/新增）。"""
    df_display = containers_df.copy()
    df_display['parent_name'] = df_display['parent_id'].map(
        containers_df.set_index('id')['name'].to_dict()
    ).fillna(i18n.t("containers.none_parent"))

    # 显示表格（带选择）
    event = st.dataframe(
        df_display[['id', 'name', 'parent_name', 'location']],
        selection_mode="multi-row",
        on_select="rerun",
        use_container_width=True,
        height=300,
        hide_index=True,
        column_config={
            "id": None,
            "name": i18n.t("containers.col_name"),
            "parent_name": i18n.t("containers.col_parent"),
            "location": i18n.t("containers.col_location")
        },
        key="container_table"
    )

    selected_indices = event.selection.rows
    # 安全过滤：只保留有效索引，防止删除后遗留旧索引
    max_index = len(df_display) - 1
    selected_indices = [i for i in selected_indices if i <= max_index]

    selected_count = len(selected_indices)
    selected_container_ids = []
    if selected_count > 0:
        selected_container_ids = df_display.iloc[selected_indices]['id'].tolist()

    # --- 选中提示（放表格与吸底工具栏之间，避免被固定栏顶出视线）---
    if len(containers_df) > 0 and selected_count == 0:
        st.info(i18n.t("containers.hint_no_selection"))
    elif selected_count == 1:
        st.success(i18n.t("containers.hint_one"))
    elif selected_count > 1:
        st.success(i18n.t("containers.hint_many", n=selected_count))

    # --- 工具栏（sticky 吸底：页面滚动时固定在视口底部，见 app.py 全局样式）---
    with st.container(key="container_toolbar"):
        col_tool1, col_tool2, col_tool3, col_tool4, col_tool5 = st.columns([3, 3, 3, 3, 5])
        with col_tool1:
            if selected_count == 1:
                if st.button(i18n.t("containers.open_detail"), key="container_detail_active",
                             use_container_width=True):
                    st.session_state.container_detail_id = selected_container_ids[0]
                    st.rerun()
            else:
                st.button(i18n.t("containers.open_detail"), key="container_detail_disabled",
                          disabled=True, use_container_width=True)
        with col_tool2:
            if selected_count == 1:
                if st.button(i18n.t("items.edit"), key="container_edit_active", use_container_width=True):
                    st.session_state.edit_container_id = selected_container_ids[0]
                    st.rerun()
            else:
                st.button(i18n.t("items.edit"), key="container_edit_disabled", disabled=True, use_container_width=True)
        with col_tool3:
            if selected_count > 0:
                if st.button(i18n.t("items.delete"), key="container_delete_active", use_container_width=True):
                    # 检查选中的容器是否可删除（无物品且无子容器）
                    non_deletable = []
                    for cid in selected_container_ids:
                        item_cnt, child_cnt = repo.container_usage(conn, cid)
                        if item_cnt > 0 or child_cnt > 0:
                            non_deletable.append((cid, item_cnt, child_cnt))
                    if non_deletable:
                        st.error(i18n.t("containers.not_empty_list", list=non_deletable))
                    else:
                        names = [df_display[df_display['id'] == cid].iloc[0]['name'] for cid in selected_container_ids]
                        confirm_container_delete(conn, selected_container_ids, "、".join(names))
            else:
                st.button(i18n.t("items.delete"), key="container_delete_disabled", disabled=True, use_container_width=True)
        with col_tool4:
            if st.button(i18n.t("containers.add_btn"), key="container_add_btn", use_container_width=True):
                st.session_state.add_container_mode = True
                st.rerun()
        with col_tool5:
            st.caption(i18n.t("containers.list_count", total=len(containers_df), n=selected_count))


# ==================== 卡片视图（Phase 6） ====================


def _card_img_markdown(img_path, tag):
    """容器卡片首图 HTML：media 原图 URL + CSS 限高（_CARD_IMG_MAX_H），与物品
    详情页缩略图同规格；st.image 满列宽会把竖图撑得过高且服务端重编码。
    失败返回 None，由调用方退回 st.image。tag 为纯 ASCII 坐标键。"""
    if _st_get_instance is None:
        return None
    try:
        mgr = _st_get_instance().media_file_mgr
        mime, _ = mimetypes.guess_type(img_path)
        url = mgr.add(img_path, mime or "image/jpeg", tag)
    except Exception as e:
        db.logger.warning("取容器卡片原图 URL 失败: %r", e, exc_info=True)
        return None
    if not url:
        return None
    return (f'<img src="{url}" alt="" style="display:block;max-width:100%;'
            f'max-height:{_CARD_IMG_MAX_H}px;width:auto;height:auto;'
            f'margin:0 auto;border-radius:8px">')


def render_card_view(conn, containers_df):
    """卡片视图：4 列网格（首图 + 名称 + 位置 + 物品数），点击进详情。"""
    total = len(containers_df)
    page_size = st.selectbox(i18n.t("items.page_size"), [12, 24, 48, 96], index=1)
    total_pages = max(1, (total + page_size - 1) // page_size)
    if 'container_card_page' not in st.session_state:
        st.session_state.container_card_page = 1
    # 容器增删后旧页码可能越界 → clamp（否则 number_input 抛 ValueError）
    st.session_state.container_card_page = min(max(1, st.session_state.container_card_page), total_pages)

    col1, col2, col3 = st.columns([2, 2, 4])
    with col1:
        st.write(i18n.t("containers.card_count", total=total))
    with col2:
        if total_pages > 1:
            st.session_state.container_card_page = st.number_input(i18n.t("items.page_no"),
                                                                   min_value=1, max_value=total_pages,
                                                                   value=st.session_state.container_card_page,
                                                                   step=1)

    start = (st.session_state.container_card_page - 1) * page_size
    df_page = containers_df.iloc[start:start + page_size]

    if df_page.empty:
        st.info(i18n.t("common.no_data"))
    else:
        cids = df_page['id'].tolist()
        # 批量取首图与物品数，消除 N+1 查询
        first_imgs = repo.load_container_first_image_map(conn, cids)
        item_counts = repo.item_count_map(conn, cids)
        cols = st.columns(4)
        for idx, row in df_page.iterrows():
            with cols[idx % 4]:
                img = first_imgs.get(row['id'])
                if img and os.path.exists(img):
                    html = _card_img_markdown(img, f"ccard_img_{int(row['id'])}")
                    if html:
                        st.markdown(html, unsafe_allow_html=True)
                    else:
                        st.image(img, use_container_width=True)
                else:
                    st.image("https://via.placeholder.com/150?text=No+Image", use_container_width=True)

                st.subheader(row['name'])
                if row['location']:
                    st.caption(f"📍 {row['location']}")
                st.caption(i18n.t("containers.card_items", n=item_counts.get(row['id'], 0)))

                if st.button(i18n.t("containers.open_detail"), key=f"ccard_{row['id']}",
                             use_container_width=True):
                    st.session_state.container_detail_id = row['id']
                    st.rerun()

        if total_pages > 1:
            col1, col2 = st.columns([1, 5])
            with col1:
                if st.button(i18n.t("items.prev_page"), key="ccard_prev"):
                    if st.session_state.container_card_page > 1:
                        st.session_state.container_card_page -= 1
                        st.rerun()
            with col2:
                if st.button(i18n.t("items.next_page"), key="ccard_next"):
                    if st.session_state.container_card_page < total_pages:
                        st.session_state.container_card_page += 1
                        st.rerun()


def render(conn):
    st.subheader(i18n.t("containers.title"))

    # 会话状态：编辑/新增/详情/视图模式
    if 'edit_container_id' not in st.session_state:
        st.session_state.edit_container_id = None
    if 'add_container_mode' not in st.session_state:
        st.session_state.add_container_mode = False
    if 'container_detail_id' not in st.session_state:
        st.session_state.container_detail_id = None
    if 'container_view_mode' not in st.session_state:
        st.session_state.container_view_mode = 'table'   # 'table' 或 'card'（内部值稳定，显示文本由 i18n 决定）

    # 获取容器数据（实时，单次查询供本 Tab 使用）
    containers_df = repo.list_containers(conn)

    # ========== 编辑或新增模式（优先） ==========
    # 子页面用 return 退出本函数即可，不能用 st.stop()——st.tabs 全量渲染，
    # stop 会中断整个脚本，使本 Tab 之后的其它 Tab 内容变空。
    if st.session_state.edit_container_id is not None or st.session_state.add_container_mode:
        if st.session_state.edit_container_id is not None:
            render_edit_form(conn, containers_df, is_edit=True,
                             cont_id=st.session_state.edit_container_id)
        else:
            render_edit_form(conn, containers_df, is_edit=False)
        return  # 编辑/新增模式下不显示浏览视图

    # ========== 详情模式 ==========
    if st.session_state.container_detail_id is not None:
        render_detail_page(conn, containers_df, st.session_state.container_detail_id)
        return

    # ========== 浏览模式：表格/卡片切换 ==========
    mode_labels = [i18n.t("containers.view_table"), i18n.t("containers.view_card")]
    current_mode = st.session_state.container_view_mode if st.session_state.container_view_mode in ("table", "card") else "table"
    mode_choice = st.radio(i18n.t("containers.switch_view"), mode_labels, horizontal=True,
                           index=0 if current_mode == "table" else 1, key="container_view_radio")
    st.session_state.container_view_mode = "table" if mode_choice == mode_labels[0] else "card"

    if st.session_state.container_view_mode == "table":
        render_browse(conn, containers_df)
    else:
        render_card_view(conn, containers_df)
