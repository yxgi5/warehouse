# -*- coding: utf-8 -*-
"""Tab6 容器管理：树形容器的增删改 + 列表/卡片双视图 + 容器详情页（照片/物品清单）。

Phase 6 新增：
- 容器照片：container_images 独立表，编辑表单内上传/删除/排序（与物品编辑一致）；
- 浏览视图：列表（含批量操作）↔ 卡片（首图+信息，点击进详情）；
- 详情页：只读多图画廊 + 信息区 + 内部物品清单（点击跳转物品浏览标签的详情页）。

Phase 7 新增：
- 容器附注：containers.note 文本列，编辑表单「上级容器」下方整行附注框
  （与位置描述同级的基础信息），详情页信息区一并展示。

注意：容器列表不再在本 Tab 内重复重建——app.py 顶层每次 rerun 统一查询一次
（repo.get_container_options），本模块变更容器后仅 st.rerun() 即可刷新全局下拉框。
"""
import os
import mimetypes
import streamlit as st
import db
import repo
import i18n
from imgutil import safe_image

try:
    from streamlit.runtime import get_instance as _st_get_instance
except Exception:  # 版本变动时退回 st.image 满宽显示
    _st_get_instance = None

_CARD_IMG_MAX_H = 300   # 卡片首图高度上限，与物品详情页缩略图规格一致


# ==================== 原图 URL（media 存储） ====================
# 设计意图：画廊/卡片“查看缩小、右键打开的是原图”。st.image 会把图片在服务端
# 重编码后再入库（图宽超 2×730 会压到 1460，格式不符会重压），右键拿到的是小图，
# 因此统一走 media_file_mgr.add(路径) 按原字节入库，URL 即原图（与物品详情一致）。
def _media_original_url(abs_path, tag):
    """返回 media 存储中的原图 URL；失败返回 None（调用方退回 st.image）。
    tag 为纯 ASCII 坐标键（media 缓存键，不能带盘符/路径字符）。"""
    if _st_get_instance is None:
        return None
    try:
        mgr = _st_get_instance().media_file_mgr
        ext = os.path.splitext(abs_path)[1].lower().lstrip('.')
        mime, _ = mimetypes.guess_type(abs_path)
        # avif/heic 在部分 Python/浏览器 mimetypes 缺失，显式兜底确保原图以正确 MIME 输出
        mime = mime or {'avif': 'image/avif', 'heic': 'image/heic'}.get(ext, 'image/jpeg')
        url = mgr.add(abs_path, mime, tag)
        return url or None
    except Exception as e:
        db.logger.warning("取原图 URL 失败: %r", e, exc_info=True)
        return None


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
                # 兼容从容器树入口打开的详情：清掉树的详情态，否则会重新渲染已删除容器
                st.session_state.tree_detail_id = None
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
        _, current_name, current_parent_id, current_location, current_note = cont_data
        title = i18n.t("containers.edit_title", name=current_name)
    else:
        current_name = ""
        current_parent_id = None
        current_location = ""
        current_note = ""
        title = i18n.t("containers.add_title")
        # 照片暂存区（表单外，与物品新增页同款交互）：先选文件 → 「添加照片」加入
        # 暂存并预览 → 可上移/下移/移除 → 点「添加」随表单一并落库（容器尚无 id，
        # 无法先附图后存）。存 session_state 的 UploadedFile 列表跨 rerun 保留；
        # 落库时 repo 层还会按内容去重。
        staged = st.session_state.setdefault('add_container_staged_photos', [])

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

        # 附注（Phase 7）：整行多行文本框，位于上级容器/位置之下、照片上传之上——
        # 与物品表单的特点/附加说明一致，长文本不撑破两列布局
        new_note = st.text_area(i18n.t("containers.note"), value=current_note, height=120)

        # 照片：编辑态在表单外图片管理区即时生效（与物品编辑一致，见下方）；
        # 新增态在表单外暂存区预览/调序、随「添加」一并落库（与物品新增一致，见下方）
        uploaded_files = None

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
                        repo.update_container(conn, cont_id, new_name, new_parent_id,
                                              new_location, new_note, uploaded_files)
                        saved_msg = i18n.t("containers.saved_updated", name=new_name)
                    else:
                        # 暂存照片随「添加」一并落库（add_container 内部按内容去重）
                        repo.add_container(conn, new_name, new_parent_id,
                                           new_location, new_note, list(staged))
                        st.session_state.add_container_staged_photos = []
                        saved_msg = i18n.t("containers.saved_added", name=new_name)
                    st.toast(saved_msg, icon="✅")
                    st.session_state.edit_container_id = None
                    st.session_state.add_container_mode = False
                    st.session_state.jump_to_tab = 5  # 返回容器 Tab
                    st.rerun()   # 全局容器选项由 app.py 顶层重新查询
                except Exception as e:
                    db.logger.exception("保存容器失败")
                    st.error(i18n.t("containers.op_fail", err=e))
                    conn.rollback()
        if cancel:
            # 取消：回到浏览态并清空照片暂存（避免下次进入残留上次的草稿）
            st.session_state.add_container_staged_photos = []
            st.session_state.edit_container_id = None
            st.session_state.add_container_mode = False
            st.session_state.jump_to_tab = 5  # 返回容器 Tab
            st.rerun()
        if delete_btn:
            # 检查容器是否可删除（无物品且无子容器）
            item_count, child_count = repo.container_usage(conn, cont_id)
            if item_count > 0 or child_count > 0:
                st.error(i18n.t("containers.not_empty", n=item_count, m=child_count))
            else:
                confirm_container_delete(conn, [cont_id], current_name)

    # 照片管理区（仅编辑；放表单外，避免按钮触发表单提交丢数据——与物品编辑一致。
    # 增/删/排序全部即时生效，不必点「更新」、更不必退出编辑态）
    if is_edit:
        col_up, col_btn = st.columns([3, 1])
        with col_up:
            new_files = st.file_uploader(i18n.t("containers.upload_images"),
                                         type=['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif', 'heic'],
                                         accept_multiple_files=True,
                                         key="cedit_upload_files")
            st.caption(i18n.t("containers.photo_hint"))
        with col_btn:
            # keyed 容器供 CSS 垂直居中（相对上传框），见 app.py .st-key-*_photo_add_btn
            with st.container(key="container_photo_add_btn"):
                add_clicked = st.button(i18n.t("containers.add_photos"),
                                        key="cedit_add_photos",
                                        use_container_width=True)
            if add_clicked:
                if not new_files:
                    st.warning(i18n.t("containers.no_photos_selected"))
                else:
                    try:
                        n = repo.save_container_images(conn, cont_id, new_files)
                        if n:
                            st.toast(i18n.t("containers.photos_added", n=n), icon="🖼️")
                        else:
                            st.warning(i18n.t("containers.no_photos_selected"))
                        st.rerun()
                    except Exception as e:
                        db.logger.exception("添加容器照片失败")
                        st.error(i18n.t("containers.photo_add_fail", err=e))
                        conn.rollback()

        img_rows = repo.load_container_images_full(conn, cont_id)
        if img_rows:
            st.write(i18n.t("items.existing_images"))
            for idx, (img_id, abs_path, _order) in enumerate(img_rows):
                col_img, col_up, col_down, col_del = st.columns([3, 1, 1, 1])
                with col_img:
                    if os.path.exists(abs_path):
                        safe_image(abs_path, width=120)
                    else:
                        st.caption(i18n.t("items.image_missing"))
                with col_up:
                    if idx > 0:
                        if st.button(i18n.t("items.img_up"), key=f"cedit_img_up_{img_id}",
                                     use_container_width=True):
                            repo.move_container_image(conn, img_id, "up")
                            st.rerun()
                    else:
                        st.button(i18n.t("items.img_up"), key=f"cedit_img_up_{img_id}_d",
                                  disabled=True, use_container_width=True)
                with col_down:
                    if idx < len(img_rows) - 1:
                        if st.button(i18n.t("items.img_down"), key=f"cedit_img_down_{img_id}",
                                     use_container_width=True):
                            repo.move_container_image(conn, img_id, "down")
                            st.rerun()
                    else:
                        st.button(i18n.t("items.img_down"), key=f"cedit_img_down_{img_id}_d",
                                  disabled=True, use_container_width=True)
                with col_del:
                    if st.button(i18n.t("items.img_del"), key=f"cedit_img_del_{img_id}",
                                 use_container_width=True):
                        repo.delete_container_image(conn, img_id)
                        st.rerun()

    # ==================== 照片暂存区（仅新增态；表单外，与物品新增页同款交互） ====================
    # 选图 → 「添加照片」加入暂存并预览 → 可上移/下移/移除 → 点「添加」随表单一并落库
    if not is_edit:
        col_up, col_btn = st.columns([3, 1])
        with col_up:
            new_files = st.file_uploader(i18n.t("containers.upload_images"),
                                         type=['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif', 'heic'],
                                         accept_multiple_files=True,
                                         key="cadd_upload_files")
            st.caption(i18n.t("containers.photo_hint_draft"))
        with col_btn:
            # keyed 容器供 CSS 垂直居中（相对上传框），见 app.py .st-key-*_photo_add_btn
            with st.container(key="container_add_photo_btn"):
                stage_clicked = st.button(i18n.t("containers.add_photos"),
                                          key="cadd_stage_photos",
                                          use_container_width=True)
            if stage_clicked:
                if not new_files:
                    st.warning(i18n.t("containers.no_photos_selected"))
                else:
                    # 按 (文件名, 大小) 防重复加入暂存（保存落库时另有内容级去重兜底）
                    seen = {(f.name, f.size) for f in staged}
                    add = [f for f in new_files if (f.name, f.size) not in seen]
                    if add:
                        staged.extend(add)
                        st.toast(i18n.t("containers.photos_added", n=len(add)), icon="🖼️")
                    else:
                        st.warning(i18n.t("containers.no_photos_selected"))
                    st.rerun()

        if staged:
            st.write(i18n.t("containers.staged_images"))
            for idx, f in enumerate(staged):
                col_img, col_up, col_down, col_del = st.columns([3, 1, 1, 1])
                with col_img:
                    safe_image(f, width=120)
                with col_up:
                    if idx > 0:
                        if st.button(i18n.t("items.img_up"), key=f"cstaged_up_{idx}",
                                     use_container_width=True):
                            staged[idx - 1], staged[idx] = staged[idx], staged[idx - 1]
                            st.rerun()
                    else:
                        st.button(i18n.t("items.img_up"), key=f"cstaged_up_{idx}_d",
                                  disabled=True, use_container_width=True)
                with col_down:
                    if idx < len(staged) - 1:
                        if st.button(i18n.t("items.img_down"), key=f"cstaged_down_{idx}",
                                     use_container_width=True):
                            staged[idx + 1], staged[idx] = staged[idx], staged[idx + 1]
                            st.rerun()
                    else:
                        st.button(i18n.t("items.img_down"), key=f"cstaged_down_{idx}_d",
                                  disabled=True, use_container_width=True)
                with col_del:
                    if st.button(i18n.t("items.img_del"), key=f"cstaged_del_{idx}",
                                 use_container_width=True):
                        staged.pop(idx)
                        st.rerun()


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
    # 附注：旧库迁移来的行 note 为 NULL（pandas 读作 NaN），统一归一为空串
    note = cont['note'] if isinstance(cont['note'], str) else ''

    st.subheader(i18n.t("containers.detail_title", name=name))

    # 多图画廊（只读展示）：与物品详情一致——查看缩小、右键打开的是原图。
    # HTML img + media 原图 URL + CSS 限高（st.image 服务端重编码、右键非原图）；
    # 取原图 URL 失败（异常/无运行时）时退回 st.image。tag 带容器 id，多详情同开不撞。
    img_paths = repo.load_container_images(conn, cid)
    if img_paths:
        st.write(i18n.t("containers.detail_images"))
        gallery, fallback = [], []
        for idx, path in enumerate(img_paths):
            if not os.path.exists(path):
                gallery.append('<span style="color:#888;font-size:0.85em;padding:6px 0">'
                               + i18n.t("items.image_missing") + '</span>')
                continue
            url = _media_original_url(path, f"cdetail_{cid}_{idx}")
            if url:
                gallery.append(f'<img src="{url}" alt="" style="max-height:{_CARD_IMG_MAX_H}px;'
                               f'max-width:100%;width:auto;height:auto;border-radius:8px">')
            else:
                fallback.append(path)
        if gallery:
            # flex 左对齐紧凑排布（不用 st.columns 等宽网格：列占满整行拉开图距），超宽自动折行
            st.markdown('<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start">'
                        + "".join(gallery) + "</div>", unsafe_allow_html=True)
        for path in fallback:
            safe_image(path, use_container_width=True)
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
    # 附注（可能为长文本）：单独整行展示，避免与统计信息挤在两列里被压窄
    st.write(f"{i18n.t('containers.detail_note')}: {note or i18n.t('containers.none_value')}")

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
                    # 记录来源：详情页 Back 时回到原页面（容器详情 / 树详情）而非物品列表顶层
                    if exit_key == "container_detail_id":
                        st.session_state.nav_origin = {"source": "container", "item_id": item_id,
                                                      "container_detail_id": cid}
                    elif exit_key == "tree_detail_id":
                        st.session_state.nav_origin = {"source": "tree", "item_id": item_id,
                                                      "tree_detail_id": cid}
                    # 物品详情渲染在「物品浏览」Tab：设置跳转标记，app.py 用 JS 切 Tab
                    st.session_state.jump_to_tab = 0
                    st.toast(i18n.t("containers.jump_item_hint"), icon="📄")
                    st.rerun()
            with c2:
                # 每物品行锚点：从详情点开 item 再返回时 scrollIntoView 精确滚回这行
                st.markdown(f'<a id="cont-item-{item_id}"></a>', unsafe_allow_html=True)
                st.write(f"{item_no} - {item_name}")
    else:
        st.caption(i18n.t("common.no_items"))

    # 精确回出发点：从容器/树详情点开 item 再返回时，滚动到原来那件物品的行
    # （详情页 item 列表是逐行普通 DOM，scrollIntoView 可靠；延迟较长为避开 app.py
    # 切 Tab 的 JS，确保先切到本 Tab 再滚动，否则在隐藏 Tab 上滚动无效）
    _ctarget = st.session_state.get("scroll_to_container_item")
    if _ctarget is not None:
        st.components.v1.html(
            f"<script>(function(){{var doc=window.parent.document,"
            f"el=doc.getElementById('cont-item-{int(_ctarget)}');"
            f"if(el){{[200,500,900,1500].forEach(function(t){{setTimeout(function(){{"
            f"el.scrollIntoView({{block:'center'}});}},t);}});}}}})();</script>",
            height=0)
        st.session_state.scroll_to_container_item = None


def render_detail_page(conn, containers_df, cid, exit_key="container_detail_id",
                       return_tab=5, key_prefix="cd", post_back=None):
    """容器详情：工具栏（返回/编辑/删除）+ 只读详情 + 照片管理区。

    参数化以支持不同入口共用同一视图、保持按钮一致（用户反馈：从容器树打开的
    容器详情缺 编辑/删除 按钮，与容器管理 Tab 入口不一致）：
    - exit_key / return_tab：控制返回——清除哪个详情态、跳回哪个 Tab；
      容器树入口传 exit_key='tree_detail_id'、return_tab=4，使「从树打开的容器详情」
      也带完整工具栏且返回回到树。
    - key_prefix：避免不同入口同屏（理论上不会）键冲突。
    - post_back：返回时额外要设置的 session 键（如树的滚动还原标记 tree_scroll_restore）。
    """
    row = containers_df[containers_df['id'] == cid]
    if row.empty:
        st.warning(i18n.t("containers.not_found"))
        st.session_state[exit_key] = None
        st.rerun()
        return
    cont = row.iloc[0]
    name, parent_id, location = cont['name'], cont['parent_id'], cont['location'] or ''

    # 顶部工具栏：返回 / 编辑 / 删除
    col1, col2, col3, col4 = st.columns([1, 6, 1, 1])
    with col1:
        if st.button(i18n.t("items.back"), key=f"{key_prefix}_back", use_container_width=True):
            st.session_state[exit_key] = None
            st.session_state.jump_to_tab = return_tab  # 返回来源 Tab（详情在 tabs 之外渲染，否则会重置到首个 Tab）
            if post_back:
                st.session_state.update(post_back)
            st.rerun()
    with col3:
        # 编辑后保留 container_detail_id，保存/取消后回到详情页
        if st.button(i18n.t("items.edit"), key=f"{key_prefix}_edit", use_container_width=True):
            st.session_state.edit_container_id = cid
            st.rerun()
    with col4:
        if st.button(i18n.t("items.delete"), key=f"{key_prefix}_delete", use_container_width=True):
            item_count, child_count = repo.container_usage(conn, cid)
            if item_count > 0 or child_count > 0:
                st.error(i18n.t("containers.not_empty", n=item_count, m=child_count))
            else:
                confirm_container_delete(conn, [cid], name)

    render_detail_readonly(conn, containers_df, cid, exit_key=exit_key, key_prefix=key_prefix)


def render_detail_full(conn, cid):
    """全屏渲染容器详情（app.py 在 st.tabs 之外调用，规避 st.tabs 1.40 无 key 的 Tab 重置问题）。"""
    render_detail_page(conn, repo.list_containers(conn), cid)


def render_edit_full(conn, cid):
    render_edit_form(conn, repo.list_containers(conn), is_edit=True, cont_id=cid)


def render_add_full(conn):
    render_edit_form(conn, repo.list_containers(conn), is_edit=False)


# ==================== 列表视图 ====================

def render_browse(conn, containers_df):
    """列表视图：表格 + 工具栏（详情/编辑/删除/新增）。命名与物品一致（list 视图）。"""
    df_display = containers_df.copy()
    df_display['parent_name'] = df_display['parent_id'].map(
        containers_df.set_index('id')['name'].to_dict()
    ).fillna(i18n.t("containers.none_parent"))

    # 显示表格（带选择）；Step 2 包一层带 key 容器，高度自适应视口（height=300 兜底）
    with st.container(key="container_list_wrap"):
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
            key="container_list"
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
    # Step 2.5：包 key 容器供 CSS 紧凑化（与物品 Tab list_hint 同款处理）
    with st.container(key="container_hint"):
        if len(containers_df) > 0 and selected_count == 0:
            st.info(i18n.t("containers.hint_no_selection"))
        elif selected_count == 1:
            st.success(i18n.t("containers.hint_one"))
        elif selected_count > 1:
            st.success(i18n.t("containers.hint_many", n=selected_count))

    # --- 工具栏（sticky 吸底：页面滚动时固定在视口底部，见 app.py 全局样式）---
    # Phase 10 Step1：「➕ 新增容器」已移到浏览态控制行（与物品一致，且卡片视图
    # 下也有入口），工具栏只剩选中项操作：详情 / 编辑 / 删除 + 计数。
    with st.container(key="container_toolbar"):
        col_tool1, col_tool2, col_tool3, col_tool4 = st.columns([3, 3, 3, 5])
        with col_tool1:
            if selected_count == 1:
                if st.button(i18n.t("containers.open_detail"), key="container_detail_active",
                             use_container_width=True):
                    # 互斥：打开容器详情前清掉其它 Tab 的详情/子页态，避免残留的
                    # detail_item_id 让「物品浏览」Tab 在后台仍渲染旧物品详情、进而劫持活动 Tab
                    st.session_state.detail_item_id = None
                    st.session_state.edit_item_id = None
                    st.session_state.add_item_mode = False
                    st.session_state.tree_detail_id = None
                    st.session_state.container_detail_id = selected_container_ids[0]
                    # 本次来源是列表（非卡片）：清掉可能残留的卡片锚点标记，
                    # 避免之后切到卡片视图时被旧标记拽到旧位置
                    st.session_state.container_card_return = None
                    st.rerun()
            else:
                st.button(i18n.t("containers.open_detail"), key="container_detail_disabled",
                          disabled=True, use_container_width=True)
        with col_tool2:
            if selected_count == 1:
                if st.button(i18n.t("items.edit"), key="container_edit_active", use_container_width=True):
                    st.session_state.edit_container_id = selected_container_ids[0]
                    st.session_state.container_card_return = None   # 同上：来源是列表
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
            st.caption(i18n.t("containers.list_count", total=len(containers_df), n=selected_count))

    # 容器管理列表滚动位置还原（点 5）：与物品列表同机制（.dvn-scroller + localStorage），
    # 打开容器详情再返回（cd_back）时停在原位置。v3 短窗强制 + 用户滚动即释放
    # （同 items v3）：消除"返回时顶/底交替闪、最后停在顶"——长窗反复设 scrollTop
    # 与 glide 初始化(0)互相抢位；现仅压过初始抖动后交还用户。
    # 监听仅当滚动元素正是已还原元素时才写回，避免重挂载瞬间把 0 写进存储。
    # 切 Tab 由 app.py 统一清 localStorage（点 6）。
    _cjs = (
        "<script>(function(){"
        "var doc=window.parent.document,KEY='wh_containers_list_scroll',last=null;"
        "function scroller(){var df=doc.querySelector('.st-key-container_list_wrap [data-testid=\"stDataFrame\"]');"
        "return df?df.querySelector('.dvn-scroller'):null;}"
        "function save(){if(this===last){try{localStorage.setItem(KEY,this.scrollTop);}catch(e){}}}"
        "function enforce(g,val,ms){var t0=Date.now(),stopped=false,el=g,win=window.parent;"
        "function set(){el.scrollTop=val;}"
        "function release(){stopped=true;}"
        "if(!window.__whRelSet){window.__whRelSet=new Set();"
        "function fire(e){var t=e.target;if(e.type==='keydown'&&t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.isContentEditable))return;window.__whRelSet.forEach(function(fn){fn();});}"
        "win.addEventListener('wheel',fire,{passive:true,capture:true});"
        "win.addEventListener('touchmove',fire,{passive:true,capture:true});"
        "win.addEventListener('keydown',fire,{capture:true});}"
        "window.__whRelSet.add(release);"
        "function onScroll(){if(Math.abs(el.scrollTop-val)>2)stopped=true;}"
        "el.addEventListener('scroll',onScroll,{passive:true});"
        "function loop(){if(stopped){window.__whRelSet.delete(release);return;}set();if(Date.now()-t0<ms)requestAnimationFrame(loop);else window.__whRelSet.delete(release);}loop();}"
        "function tick(){var g=scroller();if(!g)return;"
        "if(!g.__whBound){g.__whBound=1;g.addEventListener('scroll',save,{passive:true});}"
        "if(g!==last){last=g;var y=parseInt(localStorage.getItem(KEY)||'0',10);enforce(g,y,700);}}"
        "[0,120,300,600,1000,1600,2400,4000].forEach(function(t){setTimeout(tick,t);});"
        "})();</script>"
    )
    st.components.v1.html(_cjs, height=0)


# ==================== 卡片视图（Phase 6） ====================


def _card_img_markdown(img_path, tag):
    """容器卡片首图 HTML：media 原图 URL + CSS 限高（_CARD_IMG_MAX_H），与物品
    详情页缩略图同规格；查看缩小、右键即原图。失败返回 None，由调用方退回 st.image。"""
    url = _media_original_url(img_path, tag)
    if not url:
        return None
    return (f'<img src="{url}" alt="" style="display:block;max-width:100%;'
            f'max-height:{_CARD_IMG_MAX_H}px;width:auto;height:auto;'
            f'margin:0 auto;border-radius:8px">')


def _no_image_markdown(label):
    """无图卡片本地占位块（替代外链 placeholder——离线/墙内会显示破图）：
    灰底圆角 + 图标 + 文案，与物品卡片占位一致。"""
    return (f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'justify-content:center;height:140px;border-radius:8px;gap:4px;'
            f'background:rgba(128,128,128,0.10);color:rgba(128,128,128,0.75);'
            f'font-size:0.85em">'
            f'<span style="font-size:32px;line-height:1">📦</span>'
            f'<span>{label}</span></div>')


def render_card_view(conn, containers_df):
    """卡片视图：4 列网格（首图 + 名称 + 位置 + 物品数），点击进详情。"""
    total = len(containers_df)
    # 每页数量：与物品卡片视图同梯（4 列网格，档位取 4 的倍数翻倍，每页整行）；
    # 默认 96，容器数量级小，基本一页看全。
    page_size = st.selectbox(i18n.t("items.page_size"), [48, 96, 192, 384], index=1)
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
                # 每卡锚点：从卡片进详情再 Back 时 scrollIntoView 精确回到原卡（点 5，
                # 与物品卡片视图 card-item-{id} 同机制）
                st.markdown(f'<a id="card-container-{int(row["id"])}"></a>', unsafe_allow_html=True)
                img = first_imgs.get(row['id'])
                if img and os.path.exists(img):
                    html = _card_img_markdown(img, f"ccard_img_{int(row['id'])}")
                    if html:
                        st.markdown(html, unsafe_allow_html=True)
                    else:
                        safe_image(img, use_container_width=True)
                else:
                    # 无图卡片渲染本地占位块，不请求外链 placeholder（离线/墙内破图）
                    st.markdown(_no_image_markdown(i18n.t("common.no_images")),
                                unsafe_allow_html=True)

                st.subheader(row['name'])
                if row['location']:
                    st.caption(f"📍 {row['location']}")
                st.caption(i18n.t("containers.card_items", n=item_counts.get(row['id'], 0)))

                if st.button(i18n.t("containers.open_detail"), key=f"ccard_{row['id']}",
                             use_container_width=True):
                    # 互斥：清掉其它 Tab 的详情/子页态（同列表 Open Details）
                    st.session_state.detail_item_id = None
                    st.session_state.edit_item_id = None
                    st.session_state.add_item_mode = False
                    st.session_state.tree_detail_id = None
                    st.session_state.container_detail_id = row['id']
                    # 记录来源卡：cd_back 回卡片视图时 scrollIntoView 到该卡（点 5）
                    st.session_state.container_card_return = int(row['id'])
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

    # 卡片视图位置还原（点 5）：若标记了 container_card_return（从卡片进详情时记录），
    # 滚动到对应卡锚点后清除。容器卡片用页面(stMain)滚动，无 localStorage 记忆，
    # 锚点是唯一可靠的还原手段（stMain scrollTop 数值跨内容切换无意义）。
    # 短窗(700ms)内多次 scrollIntoView 压过初始抖动 + 用户滚动即释放（避免返回时
    # 反复 scrollIntoView 引起顶/底交替闪）。
    _target = st.session_state.get("container_card_return")
    if _target is not None:
        st.components.v1.html(
            f"<script>(function(){{var doc=window.parent.document,"
            f"el=doc.getElementById('card-container-{int(_target)}');"
            f"if(el){{var t0=Date.now(),stopped=false,lastOur=-1;"
            f"function set(){{lastOur=Date.now();el.scrollIntoView({{block:'center'}});}}"
            f"function onScroll(){{if(Date.now()-lastOur<50)return;stopped=true;}}"
            f"doc.querySelector('section[data-testid=\"stMain\"]').addEventListener('scroll',onScroll,{{passive:true}});"
            f"function loop(){{if(stopped)return;set();if(Date.now()-t0<700)requestAnimationFrame(loop);}}loop();"
            f"[0,150,400].forEach(function(t){{setTimeout(set,t);}});}}}})();</script>",
            height=0)
        st.session_state.container_card_return = None


def render(conn):
    # Phase 10 Step1：删掉「Container Management」整行——Tab 名已说明用途，
    # 且该行与上方标题之间还有一大块空白，纯浪费纵向空间（物品 Tab 本就没有这行）。

    # 会话状态：编辑/新增/详情/视图模式
    if 'edit_container_id' not in st.session_state:
        st.session_state.edit_container_id = None
    if 'add_container_mode' not in st.session_state:
        st.session_state.add_container_mode = False
    if 'container_detail_id' not in st.session_state:
        st.session_state.container_detail_id = None
    if 'container_view_mode' not in st.session_state:
        st.session_state.container_view_mode = 'list'   # 'list' 或 'card'（内部值稳定，显示文本由 i18n 决定）

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

    # ========== 浏览模式：列表/卡片切换（命名与物品一致：list 视图） ==========
    # 控制行（Phase 10 Step1，与物品 Tab 同布局）：[ 视图 radio | ➕ 新增容器（水平居中）
    # | 留白]；View Mode 标签已按反馈移除（只留选项），radio 标签折叠保留可访问性。
    # 新增按钮从底部工具栏移到这里——与物品的「➕ 新增物品」位置一致，且卡片视图下
    # 也有入口（原先只有列表视图有）。
    with st.container(key="containers_viewrow"):
        col_left, col_add, col_pad, col_fs = st.columns([5, 2, 3, 2])
        with col_left:
            mode_labels = [i18n.t("containers.view_list"), i18n.t("containers.view_card")]
            current_mode = st.session_state.container_view_mode if st.session_state.container_view_mode in ("list", "card") else "list"
            mode_choice = st.radio(i18n.t("containers.switch_view"), mode_labels, horizontal=True,
                                   label_visibility="collapsed",
                                   index=0 if current_mode == "list" else 1,
                                   key="container_view_radio")
            st.session_state.container_view_mode = "list" if mode_choice == mode_labels[0] else "card"
        with col_add:
            if st.button(i18n.t("containers.add_btn"), key="container_add_btn", use_container_width=True):
                st.session_state.add_container_mode = True
                st.session_state.add_container_staged_photos = []   # 进入新增前清空照片暂存草稿
                st.rerun()
        # Step 3 列表全屏：仅列表视图显示（卡片视图无表格，进入全屏会空白）
        with col_fs:
            if st.session_state.container_view_mode == 'list':
                if st.button(i18n.t("app.fullscreen"), key="container_fullscreen_btn",
                             use_container_width=True):
                    st.session_state.list_fullscreen = True
                    st.rerun()

    # 页面滚动锁定（需求：页面不能滚，只有 list 内部滚）：list 视图注入 :root 变量，
    # app.py 同步 JS 按活动 Tab + 变量给 body 加 wh-lock-scroll（stMain overflow:hidden）。
    # 卡片视图页面本身要滚动，不锁；变量写在 Tab 面板内，子页面 rerun 时自动解除。
    st.markdown(
        f"<style>:root{{--wh-containers-lock:{'1' if st.session_state.container_view_mode == 'list' else '0'}}}</style>",
        unsafe_allow_html=True)

    if st.session_state.container_view_mode == "list":
        render_browse(conn, containers_df)
    else:
        render_card_view(conn, containers_df)
