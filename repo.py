# -*- coding: utf-8 -*-
"""数据访问层：items / containers / images / tags 的 CRUD 与查询。

设计约定（Phase 3 重构）：
- 本模块不依赖 streamlit，可被单元测试直接 import。
- 所有函数显式接收 conn，内部自行创建 cursor；异常向上抛出，由 UI 层统一处理。
- 物品删除只有一个入口 delete_item()——单个删除 / 批量删除都走它。
"""
import os
import re
import pandas as pd
import db
import i18n


# ==================== 物品 ====================

def load_item_by_id(conn, item_id):
    c = conn.cursor()
    c.execute('''SELECT i.id, i.item_no, i.name, i.container_id, i.purchase_date, i.platform,
                      i.order_no, i.price, i.features, i.description,
                      (SELECT GROUP_CONCAT(t.name, ',') FROM item_tags it JOIN tags t
                       ON it.tag_id = t.id WHERE it.item_id = i.id) AS tags
               FROM items i WHERE i.id=?''', (item_id,))
    row = c.fetchone()
    if not row:
        return None
    return {
        'id': row[0], 'item_no': row[1], 'name': row[2], 'container_id': row[3],
        'purchase_date': row[4], 'platform': row[5] or '', 'order_no': row[6] or '',
        'price': row[7] or 0.0, 'features': row[8] or '', 'description': row[9] or '',
        'tags': row[10] or ''
    }


def item_no_exists(conn, item_no, exclude_id=None):
    c = conn.cursor()
    if exclude_id is None:
        c.execute("SELECT COUNT(*) FROM items WHERE item_no=?", (item_no,))
    else:
        c.execute("SELECT COUNT(*) FROM items WHERE item_no=? AND id<>?", (item_no, exclude_id))
    return c.fetchone()[0] > 0


def add_item(conn, item_no, name, container_id, purchase_date, platform, order_no,
             price, features, description, tags, uploaded_files, related_nos=None):
    """新增物品（含标签关联、图片落盘与手动关联）。返回新物品 id。
    related_nos 为关联的已有物品编号列表：等于本物品编号的静默忽略（自关联无意义），
    任一编号不存在则抛 ValueError——先整体校验再动库，绝不写一半。"""
    c = conn.cursor()
    if related_nos:
        link_ids, missing = _resolve_linked_ids(
            conn, [no for no in related_nos if no != item_no])
        if missing:
            raise ValueError(i18n.t("items.err_related_missing", nos=", ".join(missing)))
    else:
        link_ids = []
    c.execute('''INSERT INTO items (item_no, name, container_id, purchase_date, platform,
                                    order_no, price, features, description)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (item_no, name, container_id, purchase_date, platform, order_no,
               price, features, description))
    item_id = c.lastrowid
    set_item_tags(conn, item_id, tags)
    if uploaded_files:
        # 去重是双层的：save_shared_image 按内容只落一份文件；同一物品内同内容
        # 也只关联一次（item_images 主键 (item_id, image_id)，重复关联会冲突）
        seen = set()
        for f in uploaded_files:
            image_id = db.save_shared_image(conn, f, item_no)
            if image_id in seen:
                continue   # 本次上传中的重复内容 → 跳过，避免主键冲突
            seen.add(image_id)
            c.execute("INSERT INTO item_images (item_id, image_id, sort_order) VALUES (?, ?, ?)",
                      (item_id, image_id, len(seen) - 1))
    if link_ids:
        _replace_item_links(c, item_id, link_ids)
    conn.commit()
    return item_id


def update_item(conn, item_id, item_no, name, container_id, purchase_date, platform,
                order_no, price, features, description, tags, uploaded_files,
                related_nos=None):
    """更新物品（含标签重建与新图片追加）。related_nos=None 不改动关联；
    传入列表则整体重建手动关联（编辑框内容即最终状态），自身编号静默忽略，
    不存在的编号先整体报错——校验通过前不写库。"""
    c = conn.cursor()
    if related_nos is not None:
        link_ids, missing = _resolve_linked_ids(conn, related_nos, exclude_id=item_id)
        if missing:
            raise ValueError(i18n.t("items.err_related_missing", nos=", ".join(missing)))
    else:
        link_ids = None
    c.execute('''UPDATE items SET item_no=?, name=?, container_id=?, purchase_date=?,
                                 platform=?, order_no=?, price=?, features=?, description=?
                 WHERE id=?''',
              (item_no, name, container_id, purchase_date, platform, order_no,
               price, features, description, item_id))
    set_item_tags(conn, item_id, tags)
    if uploaded_files:
        # 追加去重：物品已有的与本轮重复的内容一律跳过（同内容在物品内只关联一次）
        seen = {r[0] for r in c.execute("SELECT image_id FROM item_images WHERE item_id=?",
                                        (item_id,))}
        order = c.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM item_images WHERE item_id=?",
                          (item_id,)).fetchone()[0]
        for f in uploaded_files:
            image_id = db.save_shared_image(conn, f, item_no)   # 内容去重：同图被多物品共用只落一份
            if image_id in seen:
                continue
            seen.add(image_id)
            c.execute("INSERT INTO item_images (item_id, image_id, sort_order) VALUES (?, ?, ?)",
                      (item_id, image_id, order))
            order += 1
    if link_ids is not None:
        _replace_item_links(c, item_id, link_ids)
    conn.commit()


# ==================== 物品关联（item_links：手动录入，无向一行 a<b） ====================

def parse_related_text(text):
    """解析“关联物品编号”输入 → 去空去重后的编号列表。兼容 中文逗号/英文逗号/分号
    分隔，编号两侧空白一律无视（与标签归一先例一致）。"""
    if not text or not text.strip():
        return []
    seen, out = set(), []
    for no in (p.strip() for p in re.split(r"[,，;；]", text) if p.strip()):
        if no not in seen:
            seen.add(no)
            out.append(no)
    return out


def _resolve_linked_ids(conn, item_nos, exclude_id=None):
    """关联编号 → (目标 id 列表, 缺失编号列表)：自身（exclude_id）静默忽略。"""
    c = conn.cursor()
    ids, missing = [], []
    for no in item_nos:
        row = c.execute("SELECT id FROM items WHERE item_no=?", (no,)).fetchone()
        if row is None:
            missing.append(no)
        elif row[0] != exclude_id:
            ids.append(row[0])
    return ids, missing


def _replace_item_links(c, item_id, link_ids):
    """重建某物品的手动关联：删除其参与的全部行，再按 a<b 规范化插入
    （配合 item_links 的 CHECK (a_id < b_id) 与复合主键天然去重）。"""
    c.execute("DELETE FROM item_links WHERE a_id=? OR b_id=?", (item_id, item_id))
    for oid in set(link_ids):
        if oid == item_id:
            continue   # 防御：正常已由 _resolve_linked_ids 的 exclude_id 剔除
        a, b = (item_id, oid) if item_id < oid else (oid, item_id)
        c.execute("INSERT INTO item_links (a_id, b_id) VALUES (?, ?)", (a, b))


def load_related_items(conn, item_id):
    """物品手动关联的其他物品 [(id, item_no, name)]（按 id 升序；
    单行无向，从任一端查询结果一致）。"""
    c = conn.cursor()
    c.execute('''SELECT i.id, i.item_no, i.name FROM item_links l
                 JOIN items i ON i.id = CASE WHEN l.a_id=? THEN l.b_id ELSE l.a_id END
                 WHERE l.a_id=? OR l.b_id=? ORDER BY i.id''',
              (item_id, item_id, item_id))
    return c.fetchall()


def delete_item(conn, item_id):
    """删除物品：先解关联其全部图片（图片可多物品共用，引用归零才删文件与池记录），
    最后删物品记录。这是唯一的物品删除入口。"""
    c = conn.cursor()
    rows = c.execute('''SELECT ii.image_id, im.file_path FROM item_images ii
                        JOIN images im ON im.id = ii.image_id
                        WHERE ii.item_id=?''', (item_id,)).fetchall()
    c.execute("DELETE FROM item_images WHERE item_id=?", (item_id,))
    for image_id, path in rows:
        refs = c.execute("SELECT COUNT(*) FROM item_images WHERE image_id=?",
                         (image_id,)).fetchone()[0]
        if refs == 0:
            _remove_photo_file(path)
            c.execute("DELETE FROM images WHERE id=?", (image_id,))
    c.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()


def get_filtered_data(conn, search, tag_filter):
    """物品列表查询（含容器名与聚合标签）。
    筛选：关键词模糊（Phase 4 起覆盖 名称/编号/特点/说明/平台/订单号/标签/容器名）
          + 标签精确匹配（多标签 AND）。"""
    query = '''SELECT items.id, items.item_no, items.name, items.container_id, items.purchase_date,
                      items.platform, items.order_no, items.price, items.features, items.description,
                      containers.name as container_name,
                      (SELECT GROUP_CONCAT(t.name, ',') FROM item_tags it JOIN tags t
                       ON it.tag_id = t.id WHERE it.item_id = items.id) AS tags
               FROM items LEFT JOIN containers ON items.container_id = containers.id WHERE 1=1'''
    params = []
    if search:
        query += ''' AND (items.name LIKE ? OR items.item_no LIKE ? OR items.features LIKE ?
                     OR items.description LIKE ? OR items.platform LIKE ? OR items.order_no LIKE ?
                     OR EXISTS (SELECT 1 FROM item_tags it JOIN tags t
                                ON it.tag_id = t.id WHERE it.item_id = items.id AND t.name LIKE ?)
                     OR containers.name LIKE ?)'''
        p = f"%{search}%"
        params.extend([p] * 8)
    if tag_filter:
        tags = [t.strip() for t in tag_filter.split(',') if t.strip()]
        for tag in tags:
            # 精确匹配：t.name = ? 而非 LIKE，避免"苹果"误匹配"苹果手机"
            query += ''' AND EXISTS (SELECT 1 FROM item_tags it JOIN tags t
                         ON it.tag_id = t.id WHERE it.item_id = items.id AND t.name = ?)'''
            params.append(tag)
    query += " ORDER BY items.id DESC"
    return pd.read_sql_query(query, conn, params=params)


# ==================== 图片（图片池 + item_images 关联） ====================
# 图片存于 images 池，物品↔图片多对多（item_images）：同一内容（sha256）只落一份
# 文件、可被多个物品共用；物理文件仅在无任何物品引用时删除（见 _remove_photo_file）。
# 图片在某物品内的顺序记录在关联行 sort_order，各物品互不影响。

def load_images_by_item(conn, item_id):
    """返回物品图片绝对路径列表（按顺序），用于展示。"""
    c = conn.cursor()
    c.execute('''SELECT im.file_path FROM item_images ii
                 JOIN images im ON im.id = ii.image_id
                 WHERE ii.item_id=? ORDER BY ii.sort_order''', (item_id,))
    return [db.img_abs_path(r[0]) for r in c.fetchall()]


def load_images_full(conn, item_id):
    """返回 [(image_id, 绝对路径, sort_order)]，用于编辑页图片管理。"""
    c = conn.cursor()
    c.execute('''SELECT im.id, im.file_path, ii.sort_order FROM item_images ii
                 JOIN images im ON im.id = ii.image_id
                 WHERE ii.item_id=? ORDER BY ii.sort_order''', (item_id,))
    return [(r[0], db.img_abs_path(r[1]), r[2]) for r in c.fetchall()]


def load_first_image_map(conn, item_ids):
    """批量取每个物品的第一张图：{item_id: 绝对路径}。消除卡片视图的 N+1 查询。"""
    if not item_ids:
        return {}
    marks = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f'''SELECT ii.item_id, im.file_path FROM item_images ii
            JOIN images im ON im.id = ii.image_id
            JOIN (SELECT item_id, MIN(sort_order) AS so FROM item_images GROUP BY item_id) m
              ON ii.item_id = m.item_id AND ii.sort_order = m.so
            WHERE ii.item_id IN ({marks})''', list(item_ids)).fetchall()
    return {iid: db.img_abs_path(p) for iid, p in rows}


def load_image_peers(conn, item_id):
    """该物品每张图片的共用者（排除自身）：{image_id: [(id, item_no, name)]}。
    共用关系不入库，由 item_images 实时推导，供详情页在图片下标注并跳转。"""
    c = conn.cursor()
    c.execute('''SELECT ii.image_id, i.id, i.item_no, i.name
                 FROM item_images ii
                 JOIN item_images mine ON mine.item_id=? AND mine.image_id=ii.image_id
                 JOIN items i ON i.id = ii.item_id
                 WHERE ii.item_id != ? ORDER BY i.id''', (item_id, item_id))
    peers = {}
    for image_id, pid, pno, pname in c.fetchall():
        peers.setdefault(image_id, []).append((pid, pno, pname))
    return peers


def set_item_tags(conn, item_id, tags_str):
    """写物品标签：重建关联（先删后插），并清理无任何物品使用的孤儿标签。"""
    c = conn.cursor()
    c.execute("DELETE FROM item_tags WHERE item_id=?", (item_id,))
    for tag in (t.strip() for t in tags_str.split(',') if t.strip()):
        c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        c.execute("SELECT id FROM tags WHERE name=?", (tag,))
        tag_id = c.fetchone()[0]
        c.execute("INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)", (item_id, tag_id))
    c.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM item_tags)")


def move_image(conn, item_id, img_id, direction):
    """上移/下移某物品的一张图片：与该物品相邻顺序的图片交换 sort_order。
    图片可被多物品共用，这里只动本物品的关联顺序。"""
    c = conn.cursor()
    row = c.execute("SELECT sort_order FROM item_images WHERE item_id=? AND image_id=?",
                    (item_id, img_id)).fetchone()
    if not row:
        return False
    order = row[0]
    peer_order = order - 1 if direction == "up" else order + 1
    peer = c.execute("SELECT image_id FROM item_images WHERE item_id=? AND sort_order=?",
                     (item_id, peer_order)).fetchone()
    if not peer:
        return False
    c.execute("UPDATE item_images SET sort_order=? WHERE item_id=? AND image_id=?",
              (peer_order, item_id, img_id))
    c.execute("UPDATE item_images SET sort_order=? WHERE item_id=? AND image_id=?",
              (order, item_id, peer[0]))
    conn.commit()
    return True


def delete_image(conn, item_id, img_id):
    """把一张图从该物品移除（仅解关联，不影响其他物品对它的引用）；
    若图片已无任何物品引用，删除物理文件与池记录。随后重排该物品剩余图片顺序。"""
    c = conn.cursor()
    row = c.execute('''SELECT im.file_path FROM item_images ii
                       JOIN images im ON im.id = ii.image_id
                       WHERE ii.item_id=? AND ii.image_id=?''',
                    (item_id, img_id)).fetchone()
    if not row:
        return False
    c.execute("DELETE FROM item_images WHERE item_id=? AND image_id=?", (item_id, img_id))
    refs = c.execute("SELECT COUNT(*) FROM item_images WHERE image_id=?",
                     (img_id,)).fetchone()[0]
    if refs == 0:
        _remove_photo_file(row[0])
        c.execute("DELETE FROM images WHERE id=?", (img_id,))
    for new_order, (iid,) in enumerate(c.execute(
            "SELECT image_id FROM item_images WHERE item_id=? ORDER BY sort_order",
            (item_id,)).fetchall()):
        c.execute("UPDATE item_images SET sort_order=? WHERE item_id=? AND image_id=?",
                  (new_order, item_id, iid))
    conn.commit()
    return True


def _remove_photo_file(path):
    """尽力删除图片物理文件（兼容三种路径存法），失败不阻塞记录删除。"""
    ap = db.img_abs_path(path)
    if ap and os.path.exists(ap):
        try:
            os.remove(ap)
        except OSError:
            pass   # 文件删不掉不阻塞记录删除


def _move_owner_image(conn, table, owner_col, img_id, direction):
    """通用图片排序（容器照片专用）：table 仅取 'container_images'，owner_col 仅取
    'container_id'（内部白名单调用，无 SQL 注入风险）。"""
    c = conn.cursor()
    c.execute(f"SELECT {owner_col}, sort_order FROM {table} WHERE id=?", (img_id,))
    row = c.fetchone()
    if not row:
        return False
    owner_id, order = row
    peer_order = order - 1 if direction == "up" else order + 1
    c.execute(f"SELECT id FROM {table} WHERE {owner_col}=? AND sort_order=?",
              (owner_id, peer_order))
    peer = c.fetchone()
    if not peer:
        return False
    c.execute(f"UPDATE {table} SET sort_order=? WHERE id=?", (peer_order, img_id))
    c.execute(f"UPDATE {table} SET sort_order=? WHERE id=?", (order, peer[0]))
    conn.commit()
    return True


def _delete_owner_image(conn, table, owner_col, img_id):
    """通用图片删除（容器照片专用，白名单同上）：先删文件，再删记录，重排连续化。"""
    c = conn.cursor()
    c.execute(f"SELECT {owner_col}, file_path FROM {table} WHERE id=?", (img_id,))
    row = c.fetchone()
    if not row:
        return False
    owner_id, path = row
    abs_path = db.img_abs_path(path)
    if os.path.exists(abs_path):
        try:
            os.remove(abs_path)
        except OSError:
            pass   # 文件删不掉不阻塞记录删除
    c.execute(f"DELETE FROM {table} WHERE id=?", (img_id,))
    c.execute(f"SELECT id FROM {table} WHERE {owner_col}=? ORDER BY sort_order", (owner_id,))
    for new_order, (img_id2,) in enumerate(c.fetchall()):
        c.execute(f"UPDATE {table} SET sort_order=? WHERE id=?", (new_order, img_id2))
    conn.commit()
    return True


# ==================== 容器图片 ====================

def save_container_images(conn, cid, uploaded_files):
    """容器照片追加保存（可多张）。返回新增张数。"""
    if not uploaded_files:
        return 0
    c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(sort_order), -1) FROM container_images WHERE container_id=?",
              (cid,))
    max_order = c.fetchone()[0]
    for i, f in enumerate(uploaded_files):
        path = db.save_container_image(f, cid)
        c.execute("INSERT INTO container_images (container_id, file_path, sort_order) VALUES (?, ?, ?)",
                  (cid, path, max_order + 1 + i))
    conn.commit()
    return len(uploaded_files)


def load_container_images(conn, cid):
    """容器照片绝对路径列表（按 sort_order），用于展示。"""
    c = conn.cursor()
    c.execute("SELECT file_path FROM container_images WHERE container_id=? ORDER BY sort_order", (cid,))
    return [db.img_abs_path(r[0]) for r in c.fetchall()]


def load_container_images_full(conn, cid):
    """返回 [(img_id, 绝对路径, sort_order)]，用于详情页图片管理。"""
    c = conn.cursor()
    c.execute("SELECT id, file_path, sort_order FROM container_images WHERE container_id=? ORDER BY sort_order",
              (cid,))
    return [(r[0], db.img_abs_path(r[1]), r[2]) for r in c.fetchall()]


def load_container_first_image_map(conn, cids):
    """批量取每个容器的第一张照片：{cid: 绝对路径}。消除卡片视图的 N+1 查询。"""
    if not cids:
        return {}
    marks = ",".join("?" * len(cids))
    rows = conn.execute(
        f'''SELECT ci.container_id, ci.file_path FROM container_images ci
            JOIN (SELECT container_id, MIN(sort_order) AS so FROM container_images GROUP BY container_id) m
              ON ci.container_id = m.container_id AND ci.sort_order = m.so
            WHERE ci.container_id IN ({marks})''', list(cids)).fetchall()
    return {cid: db.img_abs_path(p) for cid, p in rows}


def move_container_image(conn, img_id, direction):
    """上移/下移容器照片。"""
    return _move_owner_image(conn, "container_images", "container_id", img_id, direction)


def delete_container_image(conn, img_id):
    """删除单张容器照片：先删文件，再删记录，重排 sort_order。"""
    return _delete_owner_image(conn, "container_images", "container_id", img_id)


# ==================== 容器 ====================

def list_containers(conn):
    """全部容器 DataFrame（含 parent_id），供容器管理/容器树使用。"""
    return pd.read_sql_query("SELECT * FROM containers", conn)


def get_container_options(conn):
    """{容器名: id} 映射，供下拉框使用。"""
    return {name: cid for name, cid in conn.execute("SELECT name, id FROM containers")}


def get_container(conn, cid):
    return conn.execute("SELECT id, name, parent_id, location FROM containers WHERE id=?",
                        (cid,)).fetchone()


def container_name_exists(conn, name, exclude_id=None):
    c = conn.cursor()
    if exclude_id is None:
        c.execute("SELECT COUNT(*) FROM containers WHERE name=?", (name,))
    else:
        c.execute("SELECT COUNT(*) FROM containers WHERE name=? AND id<>?", (name, exclude_id))
    return c.fetchone()[0] > 0


def add_container(conn, name, parent_id, location):
    conn.execute("INSERT INTO containers (name, parent_id, location) VALUES (?, ?, ?)",
                 (name, parent_id, location))
    conn.commit()


def update_container(conn, cid, name, parent_id, location):
    conn.execute("UPDATE containers SET name=?, parent_id=?, location=? WHERE id=?",
                 (name, parent_id, location, cid))
    conn.commit()


def container_usage(conn, cid):
    """返回 (物品数, 子容器数)——非空容器不允许删除。"""
    items = conn.execute("SELECT COUNT(*) FROM items WHERE container_id=?", (cid,)).fetchone()[0]
    children = conn.execute("SELECT COUNT(*) FROM containers WHERE parent_id=?",
                            (cid,)).fetchone()[0]
    return items, children


def item_count_map(conn, cids):
    """批量取每个容器的物品数：{cid: 数量}。消除容器卡片视图的 N+1 查询。"""
    if not cids:
        return {}
    marks = ",".join("?" * len(cids))
    rows = conn.execute(
        f"SELECT container_id, COUNT(*) FROM items WHERE container_id IN ({marks}) GROUP BY container_id",
        list(cids)).fetchall()
    return dict(rows)


def delete_containers(conn, ids):
    """批量删除容器（调用方需先确认全部为空）。先删容器照片文件，再删记录
    （container_images 记录由外键级联清理）。"""
    marks = ",".join("?" * len(ids))
    c = conn.cursor()
    c.execute(f"SELECT file_path FROM container_images WHERE container_id IN ({marks})", ids)
    for (path,) in c.fetchall():
        ap = db.img_abs_path(path)
        if ap and os.path.exists(ap):
            try:
                os.remove(ap)
            except OSError:
                pass   # 文件删不掉不阻塞记录删除
    c.execute(f"DELETE FROM containers WHERE id IN ({marks})", ids)
    conn.commit()


def load_items_by_container(conn, cid):
    """容器内物品简要列表 [(id, item_no, name)]，供容器详情页展示/跳转。"""
    return conn.execute(
        "SELECT id, item_no, name FROM items WHERE container_id=? ORDER BY id", (cid,)).fetchall()


# ==================== CSV 批量导入 ====================

# CSV 表头（与 items 字段对齐；item_no 留空则导入时自动生成）
IMPORT_COLUMNS = ['item_no', 'name', 'container', 'purchase_date', 'platform', 'order_no',
                  'price', 'features', 'description', 'tags']


def import_template_csv():
    """生成带示例行的模板 CSV 文本（UTF-8 带 BOM，Excel 可直接打开）。
    示例行不指定容器——填自己已建的容器名即可，不存在的容器名会被逐行报错。"""
    rows = [",".join(IMPORT_COLUMNS),
            ",示例物品,,2026-08-20,京东,JD123456,99.9,全新,备注,数码;充电器"]
    return "\n".join(rows) + "\n"


def _norm_tags(tags):
    """标签列兼容 中文逗号/分号/英文逗号 分隔，统一为英文逗号。"""
    if not tags:
        return ''
    return tags.replace('；', ',').replace(';', ',').replace('，', ',').strip(',')


def parse_import_csv(uploaded_file, container_options):
    """解析上传 CSV → (rows, errors)。

    rows: 规范行 dict 列表，key 为 items 字段名（container 已解析为 container_id；
          item_no 为空串则留待导入时自动生成）。
    errors: [(行号, 错误信息)]，行号从 2 起（第 1 行为表头）。
    """
    import io
    import pandas as pd

    raw = uploaded_file.getbuffer() if hasattr(uploaded_file, 'getbuffer') else uploaded_file.read()
    data = bytes(raw)
    df = None
    for enc in ('utf-8-sig', 'gbk'):
        try:
            # index_col=False: 首列全空时 pandas 会误把空串当 index，导致 iterrows 索引变 str
            df = pd.read_csv(io.BytesIO(data), encoding=enc, dtype=str,
                             keep_default_na=False, index_col=False)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    if df is None:
        return [], [(1, i18n.t("import.err_encoding"))]

    # 列名校验
    cols = [str(c).strip() for c in df.columns]
    if cols != IMPORT_COLUMNS:
        return [], [(1, i18n.t("import.err_header", cols=",".join(IMPORT_COLUMNS),
                               got=",".join(cols)))]

    name_to_id = container_options
    rows, errors = [], []
    for i, rec in df.iterrows():
        line_no = i + 2   # 第 1 行是表头
        d = {c: str(rec[c]).strip() if rec[c] is not None else '' for c in IMPORT_COLUMNS}

        if not d['name']:
            errors.append((line_no, i18n.t("import.err_name")))
            continue
        if d['container']:
            if d['container'] not in name_to_id:
                errors.append((line_no, i18n.t("import.err_container", name=d['container'])))
                continue
            d['container_id'] = name_to_id[d['container']]
        else:
            d['container_id'] = None
        try:
            d['price'] = float(d['price']) if d['price'] else 0.0
        except ValueError:
            errors.append((line_no, i18n.t("import.err_price", val=d['price'])))
            continue
        d['tags'] = _norm_tags(d['tags'])
        rows.append(d)
    return rows, errors


def import_items(conn, rows):
    """批量写入物品，逐行独立成败：编号重复/写入异常的行记 error，其余正常写入。
    返回 (成功数, [(行号, 错误信息)])。item_no 为空的自动生成当日递增编号。"""
    ok, errors = 0, []
    for i, d in enumerate(rows):
        line_no = i + 2
        item_no = d['item_no'] or db.next_item_no(conn)
        try:
            add_item(conn, item_no, d['name'], d['container_id'], d['purchase_date'],
                     d['platform'], d['order_no'], d['price'], d['features'],
                     d['description'], d['tags'], [])
            ok += 1
        except Exception as e:
            db.logger.warning("CSV 导入第 %d 行失败(%s): %s", line_no, item_no, e)
            errors.append((line_no, f"{item_no}: {e}"))
    return ok, errors
