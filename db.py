# -*- coding: utf-8 -*-
"""数据库层：连接、建表、迁移、备份、孤儿检测、路径解析。

设计约定（Phase 3 重构）：
- 本模块不依赖 streamlit，可被单元测试直接 import。
- 一切路径基于本文件所在目录（BASE_DIR），目录改名/搬移后依然可用。
- 连接缓存（st.cache_resource）放在 app.py 入口层做，这里只提供原始函数。
"""
import os
import re
import sqlite3
import uuid
import zipfile
import logging
import logging.handlers
from datetime import date, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "warehouse.db")
PHOTOS_DIR = os.path.join(BASE_DIR, "photos")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "warehouse.log")

logger = logging.getLogger("warehouse")


def setup_logging():
    """配置滚动日志文件（1MB × 3 份）。幂等：重复调用不会叠加 handler。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def get_conn():
    """建立新连接并开启外键约束。
    check_same_thread=False：连接可被 st.cache_resource 缓存复用，
    Streamlit 每次 rerun 可能在不同线程执行脚本（串行），SQLite 本身线程安全。
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# --- 初始化数据库 ---
def init_db(conn=None):
    """建表 + 迁移 + 默认容器种子。可传入已有连接（推荐），否则自建。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS containers (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, parent_id INTEGER
                REFERENCES containers(id) ON DELETE RESTRICT, location TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY, item_no TEXT UNIQUE, name TEXT, container_id INTEGER
                REFERENCES containers(id) ON DELETE RESTRICT,
            purchase_date TEXT, platform TEXT, order_no TEXT, price REAL,
            features TEXT, description TEXT, tags TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY, item_id INTEGER
                REFERENCES items(id) ON DELETE CASCADE,
            file_path TEXT, sort_order INTEGER)''')
        migrate_schema(conn)   # 旧版无外键的表结构升级（必须先于新表创建）
        c.execute('''CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS item_tags (
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (item_id, tag_id))''')
        # 容器图片表（Phase 6：与 items 的 images 表独立，互不干扰）
        c.execute('''CREATE TABLE IF NOT EXISTS container_images (
            id INTEGER PRIMARY KEY, container_id INTEGER
                REFERENCES containers(id) ON DELETE CASCADE,
            file_path TEXT, sort_order INTEGER)''')
        migrate_tags(conn)     # 旧版 items.tags 逗号字符串一次性拆入关联表
        c.execute("SELECT COUNT(*) FROM containers")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO containers (name, location) VALUES ('Box_A01', '书架顶层')")
            c.execute("INSERT INTO containers (name, location) VALUES ('Box_B02', '床底收纳箱')")
        conn.commit()
        return conn
    finally:
        if own:
            conn.close()


# 标签迁移：把 items.tags 里的逗号分隔字符串拆成 tags/item_tags 关联，然后清空旧列
# 幂等：只处理 item_tags 中尚无记录的物品；重复运行不会丢数据
def migrate_tags(conn):
    c = conn.cursor()
    c.execute('''SELECT id, tags FROM items
                 WHERE tags IS NOT NULL AND TRIM(tags) != ''
                 AND id NOT IN (SELECT item_id FROM item_tags)''')
    rows = c.fetchall()
    if not rows:
        return
    for item_id, tags_str in rows:
        for tag in (t.strip() for t in tags_str.split(',') if t.strip()):
            c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            c.execute("SELECT id FROM tags WHERE name=?", (tag,))
            tag_id = c.fetchone()[0]
            c.execute("INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)", (item_id, tag_id))
        c.execute("UPDATE items SET tags='' WHERE id=?", (item_id,))
    conn.commit()


# 旧版表结构（无外键约束）升级为带外键的新结构，保留全部数据
def migrate_schema(conn):
    fks = conn.execute("PRAGMA foreign_key_list(items)").fetchall()
    if fks:
        return   # 已是新结构
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("ALTER TABLE containers RENAME TO containers_old")
        conn.execute('''CREATE TABLE containers (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, parent_id INTEGER
                REFERENCES containers(id) ON DELETE RESTRICT, location TEXT)''')
        conn.execute("INSERT INTO containers (id, name, parent_id, location) SELECT id, name, parent_id, location FROM containers_old")
        conn.execute("DROP TABLE containers_old")

        conn.execute("ALTER TABLE items RENAME TO items_old")
        conn.execute('''CREATE TABLE items (
            id INTEGER PRIMARY KEY, item_no TEXT UNIQUE, name TEXT, container_id INTEGER
                REFERENCES containers(id) ON DELETE RESTRICT,
            purchase_date TEXT, platform TEXT, order_no TEXT, price REAL,
            features TEXT, description TEXT, tags TEXT)''')
        conn.execute('''INSERT INTO items (id, item_no, name, container_id, purchase_date,
                        platform, order_no, price, features, description, tags)
                        SELECT id, item_no, name, container_id, purchase_date,
                        platform, order_no, price, features, description, tags FROM items_old''')
        conn.execute("DROP TABLE items_old")

        conn.execute("ALTER TABLE images RENAME TO images_old")
        conn.execute('''CREATE TABLE images (
            id INTEGER PRIMARY KEY, item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
            file_path TEXT, sort_order INTEGER)''')
        conn.execute("INSERT INTO images (id, item_id, file_path, sort_order) SELECT id, item_id, file_path, sort_order FROM images_old")
        conn.execute("DROP TABLE images_old")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


# 生成当日递增编号 ITEM_YYYYMMDD_###，查库取当日最大序号+1，杜绝撞 UNIQUE
def next_item_no(conn):
    today = date.today().strftime('%Y%m%d')
    prefix = f"ITEM_{today}_"
    max_seq = 0
    c = conn.cursor()
    c.execute("SELECT item_no FROM items WHERE item_no LIKE ?", (prefix + "%",))
    for (no,) in c.fetchall():
        m = re.match(rf"^ITEM_{today}_(\d+)$", no)
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return f"{prefix}{max_seq + 1:03d}"


# 启动时自动备份：db + photos 打包 zip，只保留最近 keep 份
def backup_data(keep=10):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(BACKUP_DIR, f"backup_{ts}_{uuid.uuid4().hex[:4]}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(DB_PATH):
            zf.write(DB_PATH, "warehouse.db")
        if os.path.isdir(PHOTOS_DIR):
            for root, _, files in os.walk(PHOTOS_DIR):
                for f in files:
                    full = os.path.join(root, f)
                    try:
                        arc = os.path.relpath(full, BASE_DIR)
                    except ValueError:
                        arc = os.path.basename(full)   # photos 目录跨盘时退化为文件名
                    zf.write(full, arc)
    backups = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.startswith("backup_") and f.endswith(".zip")),
        key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)))
    for old in backups[:-keep]:
        # 单个旧备份删除失败（被占用/无权限）不应拖垮本次备份
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except OSError:
            logger.warning("删除旧备份失败(已跳过): %s", old)
    return zip_path


def last_backup_path():
    if not os.path.isdir(BACKUP_DIR):
        return None
    backups = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.startswith("backup_") and f.endswith(".zip")),
        key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)))
    return os.path.join(BACKUP_DIR, backups[-1]) if backups else None


# 把数据库里的图片路径解析为真实文件路径：
# 兼容三种存法——绝对路径 / "photos/xxx.jpg" 相对前缀 / 纯文件名
def img_abs_path(path):
    if not path:
        return path
    if os.path.isabs(path):
        return path
    p = path.replace("\\", "/")
    if p.startswith("photos/"):
        p = p[len("photos/"):]
    return os.path.join(PHOTOS_DIR, p)


# 扫描图片表（物品 + 容器），找出文件已不存在的孤儿记录。
# 返回 [(img_id, owner_label, path, table)]——owner_label 用于提示（物品 id / 容器 id），
# table 供清理时选择 'images' / 'container_images' 删除。
def find_orphan_images(conn):
    orphans = []
    for img_id, item_id, path in conn.execute("SELECT id, item_id, file_path FROM images"):
        if not os.path.exists(img_abs_path(path)):
            orphans.append((img_id, f"item:{item_id}", path, "images"))
    for img_id, cid, path in conn.execute(
            "SELECT id, container_id, file_path FROM container_images"):
        if not os.path.exists(img_abs_path(path)):
            orphans.append((img_id, f"container:{cid}", path, "container_images"))
    return orphans


# 上传图片扩展名白名单 + 各格式文件头魔数（落盘前校验真实类型，防伪装/损坏文件入库）
ALLOWED_IMAGE_EXTS = ('jpg', 'jpeg', 'png', 'gif', 'webp')


def _validate_image_bytes(data, ext):
    """按扩展名校验文件头魔数；不匹配抛 ValueError（由 UI 层捕获展示）。"""
    header = data[:12]
    if ext in ('jpg', 'jpeg'):
        ok = header.startswith(b'\xff\xd8\xff')
    elif ext == 'png':
        ok = header.startswith(b'\x89PNG\r\n\x1a\n')
    elif ext == 'gif':
        ok = header.startswith((b'GIF87a', b'GIF89a'))
    else:  # webp
        ok = header.startswith(b'RIFF') and header[8:12] == b'WEBP'
    if not ok:
        raise ValueError(f"文件内容与扩展名 .{ext} 不符，已拒绝保存（疑似伪装/损坏文件）")


def _save_image(uploaded_file, prefix):
    """通用落盘：扩展名白名单 + 文件头魔数校验，返回纯文件名。不合法抛 ValueError。"""
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    name = getattr(uploaded_file, 'name', '') or ''
    if '.' not in name:
        raise ValueError("文件名缺少扩展名，无法识别图片类型")
    ext = name.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError(f"不支持的图片类型 .{ext}（支持: {'/'.join(ALLOWED_IMAGE_EXTS)}）")
    data = bytes(uploaded_file.getbuffer()) if hasattr(uploaded_file, 'getbuffer') else bytes(uploaded_file.read())
    _validate_image_bytes(data, ext)
    filename = f"{prefix}_{uuid.uuid4().hex[:4]}.{ext}"
    with open(os.path.join(PHOTOS_DIR, filename), "wb") as f:
        f.write(data)
    return filename


def save_uploaded_file(uploaded_file, item_no):
    """把上传文件写入 photos/，返回纯文件名（物品图，前缀用 item_no）。"""
    return _save_image(uploaded_file, item_no)


def save_container_image(uploaded_file, container_id):
    """把容器照片写入 photos/，返回纯文件名（前缀用 CT_{id}）。"""
    return _save_image(uploaded_file, f"CT_{container_id}")
