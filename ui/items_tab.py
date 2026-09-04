# -*- coding: utf-8 -*-
"""Tab1 物品浏览：列表/卡片双视图 + 详情页 + 编辑模式（含图片管理）。"""
import os
import base64
import mimetypes
from datetime import date
import streamlit as st
import db
import repo
import i18n

try:
    from streamlit.runtime import get_instance as _st_get_instance
except Exception:  # 版本变动时退回 st.image 满宽显示
    _st_get_instance = None


# ==================== 详情图片显示 ====================
# 显示尺寸用 CSS 约束（竖图高度上限 _DETAIL_IMG_MAX_H，等比缩放；横图高度
# 天然小于上限，宽度撑满列）。img 的 src 指向 media 存储里的原始文件：
# st.image(width=) 会经 image_to_url 在服务端重编码（正数宽度=缩放，负数
# 也会把超宽图压到容器上限），右键“在新标签页打开图像”拿到的是小图；
# media_file_mgr.add(路径) 按原字节入库（内容哈希去重），URL 即原图。
_DETAIL_IMG_MAX_H = 300


def _detail_image_url(abs_path, img_id):
    """返回 media 存储中的原图 URL：media_file_mgr.add(路径) 按文件原字节入库
    （内容哈希去重），服务端不做任何重编码，右键“新标签页打开图像”即原图。
    失败返回 None 由调用方兜底。img_id（数字）拼坐标键，不能带盘符/路径字符。"""
    if _st_get_instance is None:
        return None
    try:
        mgr = _st_get_instance().media_file_mgr
        mime, _ = mimetypes.guess_type(abs_path)
        return mgr.add(abs_path, mime or "image/jpeg", f"detail_img_{img_id}")
    except Exception as e:
        db.logger.warning("取详情图原图 URL 失败: %r", e, exc_info=True)
        return None


def _detail_img_style(single):
    """详情图 CSS：单张居中大图；多张缩略图左对齐、间距固定（不居中不铺满）。"""
    if single:
        return ("display:block;max-width:100%;max-height:600px;width:auto;"
                "height:auto;margin:0 auto;border-radius:8px")
    return ("max-height:%dpx;max-width:100%%;width:auto;height:auto;"
            "border-radius:8px" % _DETAIL_IMG_MAX_H)


# ==================== 删除对话框 ====================
# 注意：@st.dialog 的 title 参数在模块 import 时求值一次，不能直接用 i18n.t()
# （语言切换不重载模块）。因此标题用静态 emoji，语言化标题在 dialog 内部渲染。

@st.dialog("⚠️")
def confirm_delete(conn, item_id, item_name):
    st.subheader(i18n.t("items.confirm_delete_title"))
    st.write(i18n.t("items.confirm_delete_msg", name=item_name))
    col1, col2 = st.columns(2)
    with col1:
        if st.button(i18n.t("common.confirm_delete")):
            try:
                repo.delete_item(conn, item_id)
                st.toast(i18n.t("items.deleted", name=item_name), icon="🗑️")
                st.session_state.detail_item_id = None
                st.rerun()
            except Exception as e:
                db.logger.exception("删除物品失败")
                st.error(i18n.t("items.delete_fail", err=e))
                conn.rollback()
    with col2:
        if st.button(i18n.t("common.cancel")):
            st.rerun()


@st.dialog("⚠️")
def batch_delete_dialog(conn, item_ids):
    st.subheader(i18n.t("items.confirm_batch_title"))
    st.write(i18n.t("items.confirm_batch_msg", n=len(item_ids)))
    col1, col2 = st.columns(2)
    with col1:
        if st.button(i18n.t("items.confirm_batch_btn")):
            try:
                for item_id in item_ids:
                    repo.delete_item(conn, item_id)
                st.toast(i18n.t("items.batch_deleted", n=len(item_ids)), icon="🗑️")
                st.session_state.selected_indices = []
                st.rerun()
            except Exception as e:
                db.logger.exception("批量删除物品失败")
                st.error(i18n.t("items.batch_delete_fail", err=e))
                conn.rollback()
    with col2:
        if st.button(i18n.t("common.cancel")):
            st.rerun()


# ==================== 编辑模式 ====================

# 进入编辑模式：把物品当前值写入 session_state（控件带 key，rerun 后保留）
def start_edit(conn, item_id, container_options):
    item = repo.load_item_by_id(conn, item_id)
    if not item:
        return
    st.session_state.edit_item_no = item['item_no']
    st.session_state.edit_name = item['name']
    # 无容器的物品选中"未归档"占位（下拉首项，保存为 None），编辑不会悄悄挪进第一个容器
    cur_name = next((n for n, cid in container_options.items() if cid == item['container_id']),
                    i18n.t("items.unfiled"))
    st.session_state.edit_container_name = cur_name
    st.session_state.edit_no_date = not bool(item['purchase_date'])
    st.session_state.edit_purchase_date = (date.fromisoformat(item['purchase_date'])
                                           if item['purchase_date'] else date.today())
    st.session_state.edit_platform = item['platform']
    st.session_state.edit_order_no = item['order_no']
    st.session_state.edit_price = float(item['price'])
    st.session_state.edit_tags = item['tags']
    # 编辑框预填当前手动关联的编号（逗号分隔），保存时整体重建
    st.session_state.edit_related_items = ", ".join(
        r[1] for r in repo.load_related_items(conn, item_id))
    st.session_state.edit_features = item['features']
    st.session_state.edit_description = item['description']
    # 注意：edit_uploaded_files 是 file_uploader 的 key，禁止用 session_state 赋值（Streamlit 策略）
    st.session_state.edit_item_id = item_id
    st.session_state.detail_item_id = None


def render_edit_mode(conn, item_data, container_options):
    st.subheader(i18n.t("items.edit_title", item_no=item_data['item_no'], name=item_data['name']))
    with st.form("edit_item_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            item_no = st.text_input(i18n.t("form.item_no"), key="edit_item_no")
            name = st.text_input(i18n.t("form.name"), key="edit_name")
            # "未归档"占位在首项：无容器物品可继续留空，也可随时改挂容器
            cont_opts = [i18n.t("items.unfiled")] + list(container_options.keys())
            container_name = st.selectbox(i18n.t("form.container"), cont_opts,
                                          key="edit_container_name")
            # 无日期勾选框是保存语义；date_input 不能 disabled 联动（form 内控件
            # 变化不 rerun，禁用态不刷新，会出现“取消勾选仍不可填”）
            no_date = st.checkbox(i18n.t("common.no_date"), key="edit_no_date",
                                  help=i18n.t("common.no_date_help"))
            purchase_date = st.date_input(i18n.t("form.purchase_date"), key="edit_purchase_date")
        with col2:
            platform = st.text_input(i18n.t("form.platform"), key="edit_platform")
            order_no = st.text_input(i18n.t("form.order_no"), key="edit_order_no")
            price = st.number_input(i18n.t("form.price"), min_value=0.0, format="%.2f", step=0.1,
                                    key="edit_price")
            tags = st.text_input(i18n.t("form.tags"), key="edit_tags")
            related_items = st.text_input(i18n.t("form.related_items"), key="edit_related_items",
                                          help=i18n.t("form.related_help"))
        features = st.text_area(i18n.t("form.features"), key="edit_features")
        description = st.text_area(i18n.t("form.description"), key="edit_description")

        uploaded_files = st.file_uploader(i18n.t("add.upload_images"), type=['jpg', 'png', 'jpeg', 'gif'],
                                          accept_multiple_files=True, key="edit_uploaded_files")

        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            submitted = st.form_submit_button(i18n.t("items.save_update"))
        with col_btn2:
            cancel = st.form_submit_button(i18n.t("items.cancel_edit"))

        if submitted:
            if not item_no or not name:
                st.error(i18n.t("form.required_msg"))
            elif repo.item_no_exists(conn, item_no, exclude_id=item_data['id']):
                st.error(i18n.t("items.item_no_taken", item_no=item_no))
            else:
                try:
                    repo.update_item(conn, item_data['id'], item_no, name,
                                     container_options.get(container_name),   # 未归档占位 → None
                                     '' if no_date else purchase_date.strftime('%Y-%m-%d'),
                                     platform, order_no, price, features, description, tags,
                                     uploaded_files, repo.parse_related_text(related_items))
                    st.session_state.edit_item_id = None
                    st.toast(i18n.t("items.updated"), icon="🎉")
                    st.rerun()
                except Exception as e:
                    db.logger.exception("更新物品失败")
                    st.error(i18n.t("items.update_fail", err=e))
                    conn.rollback()
        if cancel:
            st.session_state.edit_item_id = None
            st.rerun()

    # 图片管理区（放表单外，避免按钮触发表单提交丢数据）
    img_rows = repo.load_images_full(conn, item_data['id'])
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
                    if st.button(i18n.t("items.img_up"), key=f"img_up_{img_id}", use_container_width=True):
                        repo.move_image(conn, item_data['id'], img_id, "up")
                        st.rerun()
                else:
                    st.button(i18n.t("items.img_up"), key=f"img_up_{img_id}_disabled", disabled=True,
                              use_container_width=True)
            with col_down:
                if idx < len(img_rows) - 1:
                    if st.button(i18n.t("items.img_down"), key=f"img_down_{img_id}", use_container_width=True):
                        repo.move_image(conn, item_data['id'], img_id, "down")
                        st.rerun()
                else:
                    st.button(i18n.t("items.img_down"), key=f"img_down_{img_id}_disabled", disabled=True,
                              use_container_width=True)
            with col_del:
                if st.button(i18n.t("items.img_del"), key=f"img_del_{img_id}", use_container_width=True):
                    repo.delete_image(conn, item_data['id'], img_id)
                    st.rerun()
    else:
        st.caption(i18n.t("common.no_images"))


# ==================== 详情页 ====================

def render_detail_page(conn, item, container_options):
    container_name = next((n for n, cid in container_options.items() if cid == item['container_id']),
                          i18n.t("items.unfiled"))

    col1, col2, col3, col4 = st.columns([1, 6, 1, 1])
    with col1:
        if st.button(i18n.t("items.back"), use_container_width=True):
            st.session_state.detail_item_id = None
            st.rerun()
    with col3:
        if st.button(i18n.t("items.edit"), use_container_width=True):
            start_edit(conn, item['id'], container_options)
            st.rerun()
    with col4:
        if st.button(i18n.t("items.delete"), use_container_width=True):
            confirm_delete(conn, item['id'], item['name'])

    st.subheader(i18n.t("items.detail_title", item_no=item['item_no'], name=item['name']))

    img_rows = repo.load_images_full(conn, item['id'])
    if img_rows:
        st.write(i18n.t("items.detail_images"))
        # 共用关系由 item_images 实时推导：某张图同时被别的物品引用时，在图区下方
        # 标注共用的物品（点按钮直接在详情间跳转）。共用提示不混入 HTML 画廊。
        peers = repo.load_image_peers(conn, item['id'])
        single = len(img_rows) == 1
        # 画廊：单张居中大图；多张用 flex 左对齐紧凑排布（不用 st.columns 等宽
        # 网格——列会占满整行把图距拉开、图又在列内居中），超宽自动折行
        gallery, fallback = [], []
        for img_id, path, _order in img_rows:
            if not os.path.exists(path):
                gallery.append('<span style="color:#888;font-size:0.85em;padding:6px 0">'
                               + i18n.t("items.image_missing") + '</span>')
                continue
            url = _detail_image_url(path, img_id)
            if url:
                gallery.append(f'<img src="{url}" alt="" style="{_detail_img_style(single)}">')
            else:
                fallback.append(path)  # 取原图 URL 失败（异常/无运行时）→ st.image 兜底
        if gallery:
            if single:
                st.markdown("<div style='text-align:center'>" + "".join(gallery) + "</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start">'
                    + "".join(gallery) + "</div>",
                    unsafe_allow_html=True)
        for path in fallback:
            st.image(path, use_container_width=True)
        # 共用物品提示（集中列于图区下方，按图顺序编号保持归属）
        for idx, (img_id, _path, _order) in enumerate(img_rows):
            shared = peers.get(img_id)
            if shared:
                st.caption(i18n.t("items.img_shared_at", n=idx + 1))
                bcols = st.columns(len(shared))
                for j, (pid, pno, pname) in enumerate(shared):
                    with bcols[j]:
                        if st.button(pno, key=f"imgpeer_{pid}_{img_id}",
                                     help=pname, use_container_width=True):
                            st.session_state.detail_item_id = pid
                            st.rerun()
    else:
        st.caption(i18n.t("common.no_images"))

    st.divider()

    # --- 关联物品（手动录入的关系，点击按钮直接跳到对方详情）---
    related = repo.load_related_items(conn, item['id'])
    st.write(i18n.t("items.related_title"))
    if related:
        for k in range(0, len(related), 3):
            row_cols = st.columns(min(3, len(related) - k))
            for j, (rid, rno, rname) in enumerate(related[k:k + 3]):
                with row_cols[j]:
                    if st.button(f"{rno} {rname}", key=f"related_{rid}",
                                 use_container_width=True):
                        st.session_state.detail_item_id = rid
                        st.rerun()
    else:
        st.caption(i18n.t("items.related_empty"))

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"{i18n.t('items.f_item_no')}: {item['item_no']}")
        st.write(f"{i18n.t('items.f_name')}: {item['name']}")
        st.write(f"{i18n.t('items.f_container')}: {container_name}")
        st.write(f"{i18n.t('items.f_purchase_date')}: {item['purchase_date'] or i18n.t('items.not_set')}")
    with col2:
        st.write(f"{i18n.t('items.f_platform')}: {item['platform']}")
        st.write(f"{i18n.t('items.f_order_no')}: {item['order_no']}")
        price_text = f"¥{item['price']:.2f}" if item['price'] else i18n.t("items.not_set")
        st.write(f"{i18n.t('items.f_price')}: {price_text}")
        st.write(f"{i18n.t('items.f_tags')}: {item['tags']}")
    if item['features']:
        st.write(f"{i18n.t('items.f_features')}: {item['features']}")
    if item['description']:
        st.write(f"{i18n.t('items.f_description')}: {item['description']}")


# ==================== 列表视图 ====================

def render_list_view(conn, df_all, total_items, container_options):
    df_display = df_all[['id', 'item_no', 'name', 'container_name', 'purchase_date', 'platform', 'price', 'tags']].copy()
    df_display['price'] = df_display['price'].apply(lambda x: f"¥{x:.2f}" if x else "")

    # --- 表格（高度与容器列表一致：固定 300，不提供滑块）---
    # 表格先渲染，下方工具栏直接读 event.selection.rows 即本轮最新选中，
    # 不存在"选中结果滞后一帧"的问题；同时写回 session_state 供批量删除后清空。
    event = st.dataframe(
        df_display,
        key="item_table",
        selection_mode="multi-row",
        on_select="rerun",
        use_container_width=True,
        height=300,
        hide_index=True,
        column_config={
            "id": None,
            "item_no": i18n.t("form.item_no"),
            "name": i18n.t("form.name"),
            "container_name": i18n.t("form.container"),
            "purchase_date": i18n.t("form.purchase_date"),
            "platform": i18n.t("form.platform"),
            "price": i18n.t("form.price"),
            "tags": i18n.t("form.tags")
        }
    )
    # 当前轮选中：过滤越界旧索引（删除/筛选后行号可能失效）
    selected_indices = [i for i in event.selection.rows if 0 <= i < len(df_all)]
    selected_item_ids = df_all.iloc[selected_indices]['id'].tolist()
    selected_count = len(selected_item_ids)
    st.session_state.selected_indices = list(event.selection.rows)

    # --- 选中提示（放表格与吸底工具栏之间，避免被固定栏顶出视线）---
    if total_items > 0 and selected_count == 0:
        st.info(i18n.t("items.hint_no_selection"))
    elif selected_count == 1:
        st.success(i18n.t("items.hint_one"))
    elif selected_count > 1:
        st.success(i18n.t("items.hint_many", n=selected_count))

    # --- 工具栏（fixed 钉死视口底部：不依赖页面滚动，见 app.py 全局样式）---
    # 未选中时按钮 disabled（与容器列表一致）：详情/编辑需恰好选中 1 行，
    # 删除/导出需至少 1 行。选中后 on_select="rerun" 会立即刷新按钮状态。
    with st.container(key="list_toolbar"):
        col_tool1, col_tool2, col_tool3, col_tool4, col_tool5 = st.columns([3, 3, 3, 3, 5])
        with col_tool1:
            if selected_count == 1:
                if st.button(i18n.t("items.view_detail"), key="item_detail_active",
                             use_container_width=True):
                    st.session_state.detail_item_id = selected_item_ids[0]
                    st.rerun()
            else:
                st.button(i18n.t("items.view_detail"), key="item_detail_disabled",
                          disabled=True, use_container_width=True)
        with col_tool2:
            if selected_count == 1:
                if st.button(i18n.t("items.edit"), key="item_edit_active",
                             use_container_width=True):
                    start_edit(conn, selected_item_ids[0], container_options)
                    st.rerun()
            else:
                st.button(i18n.t("items.edit"), key="item_edit_disabled",
                          disabled=True, use_container_width=True)
        with col_tool3:
            if selected_count > 0:
                if st.button(i18n.t("items.delete"), key="item_delete_active",
                             use_container_width=True):
                    batch_delete_dialog(conn, selected_item_ids)
            else:
                st.button(i18n.t("items.delete"), key="item_delete_disabled",
                          disabled=True, use_container_width=True)
        with col_tool4:
            if selected_count > 0:
                if st.button(i18n.t("items.export_selected"), key="item_export_active",
                             use_container_width=True):
                    export_df = df_all[df_all['id'].isin(selected_item_ids)]
                    csv = export_df.to_csv(index=False).encode('utf-8-sig')
                    b64 = base64.b64encode(csv).decode()
                    href = f'<a href="data:file/csv;base64,{b64}" download="export_selected.csv">{i18n.t("items.click_download")}</a>'
                    st.markdown(href, unsafe_allow_html=True)
                    st.success(i18n.t("items.export_ok"))
            else:
                st.button(i18n.t("items.export_selected"), key="item_export_disabled",
                          disabled=True, use_container_width=True)
        with col_tool5:
            st.caption(i18n.t("items.list_count", total=total_items, n=selected_count))


# ==================== 卡片视图 ====================

def render_card_view(conn, df_all, total_items):
    page_size = st.selectbox(i18n.t("items.page_size"), [12, 24, 48, 96], index=1)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    if 'card_page' not in st.session_state:
        st.session_state.card_page = 1
    # 筛选/删除后数据量变化，旧页码可能越界 → clamp 到合法范围（否则 number_input 抛 ValueError）
    st.session_state.card_page = min(max(1, st.session_state.card_page), total_pages)

    col1, col2, col3 = st.columns([2, 2, 4])
    with col1:
        st.write(i18n.t("items.card_count", total=total_items))
    with col2:
        if total_pages > 1:
            st.session_state.card_page = st.number_input(i18n.t("items.page_no"), min_value=1,
                                                         max_value=total_pages,
                                                         value=st.session_state.card_page, step=1)

    start = (st.session_state.card_page - 1) * page_size
    end = start + page_size
    df_page = df_all.iloc[start:end]

    if df_page.empty:
        st.info(i18n.t("common.no_items"))
    else:
        # 批量取首图，消除逐卡 N+1 查询
        first_imgs = repo.load_first_image_map(conn, df_page['id'].tolist())
        cols = st.columns(4)
        for idx, row in df_page.iterrows():
            with cols[idx % 4]:
                img = first_imgs.get(row['id'])
                if img and os.path.exists(img):
                    st.image(img, use_container_width=True)
                else:
                    st.image("https://via.placeholder.com/150?text=No+Image", use_container_width=True)

                st.subheader(row['name'])
                st.caption(f"📌 {row['item_no']}")
                st.caption(f"📦 {row['container_name'] or i18n.t('items.unfiled')}")
                if row['tags']:
                    st.caption(f"🏷️ {row['tags']}")

                if st.button(i18n.t("items.open_detail"), key=f"card_{row['id']}", use_container_width=True):
                    st.session_state.detail_item_id = row['id']
                    st.rerun()

        if total_pages > 1:
            col1, col2 = st.columns([1, 5])
            with col1:
                if st.button(i18n.t("items.prev_page")):
                    if st.session_state.card_page > 1:
                        st.session_state.card_page -= 1
                        st.rerun()
            with col2:
                if st.button(i18n.t("items.next_page")):
                    if st.session_state.card_page < total_pages:
                        st.session_state.card_page += 1
                        st.rerun()


# ==================== Tab 入口 ====================

def render(conn, search, tag_filter, container_options):
    # 详情/编辑是子页面：优先渲染并 return，避免浏览态控件（视图切换 radio、
    # 列表/卡片）出现在详情/编辑页顶部。注意不能 st.stop()——那会中断整个
    # 脚本，st.tabs 全量渲染，其后所有 tab 内容都会变空。
    if st.session_state.detail_item_id is not None:
        item = repo.load_item_by_id(conn, st.session_state.detail_item_id)
        if item is None:
            st.error(i18n.t("items.not_found"))
            st.session_state.detail_item_id = None
            st.rerun()
            return
        render_detail_page(conn, item, container_options)
        return

    if st.session_state.edit_item_id is not None:
        item_data = repo.load_item_by_id(conn, st.session_state.edit_item_id)
        if not item_data:
            st.warning(i18n.t("items.edit_not_found"))
            st.session_state.edit_item_id = None
            st.rerun()
            return
        render_edit_mode(conn, item_data, container_options)
        return

    # --- 浏览态：子视图切换（内部值用稳定 list/card，显示文本按语言翻译）---
    mode_labels = [i18n.t("items.view_list"), i18n.t("items.view_card")]
    current_mode = st.session_state.view_mode if st.session_state.view_mode in ("list", "card") else "list"
    mode_choice = st.radio(i18n.t("items.switch_view"), mode_labels, horizontal=True,
                           index=0 if current_mode == "list" else 1)
    st.session_state.view_mode = "list" if mode_choice == mode_labels[0] else "card"

    # 获取数据（用传入的 tag_filter，与 sidebar 同步后的 session_state 保持一致）
    df_all = repo.get_filtered_data(conn, search, tag_filter)
    total_items = len(df_all)

    # --- 列表视图 ---
    if st.session_state.view_mode == "list":
        render_list_view(conn, df_all, total_items, container_options)
    # --- 卡片视图 ---
    else:
        render_card_view(conn, df_all, total_items)
