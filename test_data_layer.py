# -*- coding: utf-8 -*-
"""Phase 3 数据层回归测试：直接 import db/repo（零 streamlit 依赖），验证与旧版等价。

用法:  python test_data_layer.py
临时数据写在系统临时目录，不污染项目 warehouse.db / photos / backups。
"""
import io
import os
import sqlite3
import sys
import tempfile
import types

# 确保能 import 到项目模块（脚本可能从任意目录运行）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import repo
import i18n

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  OK  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  -> {detail}")


def fake_upload(name="test.jpg", data=None):
    """构造一个模仿 streamlit UploadedFile 的对象（getbuffer 返回 bytes）。
    Phase 4 起 save_uploaded_file 校验文件头魔数，默认给合法 JPEG 头字节。"""
    data = data if data is not None else b"\xff\xd8\xff\xe0" + b"\x00" * 16
    return types.SimpleNamespace(name=name, getbuffer=lambda: data)


# 四张内容不同的合法 JPEG：图片池按内容 sha256 去重，相同字节的图只落一份
# IMG_A/B 供 i1 常规用例；IMG_C/D 供共享用例（内容必须与库中已有图互不相同，
# 否则去重复用会让“新增份数 / 引用计数”断言失真）
IMG_A = b"\xff\xd8\xff\xe0" + b"A" * 16
IMG_B = b"\xff\xd8\xff\xe0" + b"B" * 16
IMG_C = b"\xff\xd8\xff\xe0" + b"C" * 16
IMG_D = b"\xff\xd8\xff\xe0" + b"D" * 16


def main():
    global passed, failed
    tmp = tempfile.mkdtemp(prefix="wh3_")
    db.PHOTOS_DIR = os.path.join(tmp, "photos")
    db.BACKUP_DIR = os.path.join(tmp, "backups")
    db.DB_PATH = os.path.join(tmp, "warehouse.db")
    os.makedirs(db.PHOTOS_DIR, exist_ok=True)
    print(f"临时数据目录: {tmp}")

    conn = db.get_conn()
    db.init_db(conn)

    # ---------- 建表与初始化 ----------
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    check("建表齐全", {"tags", "item_tags", "containers", "items", "images", "container_images",
                     "item_links"} <= tables, str(tables))
    check("外键已开启", conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1)
    check("初始化后无内置容器（种子已移除）", conn.execute("SELECT COUNT(*) FROM containers").fetchone()[0] == 0)

    # ---------- 物品 CRUD ----------
    # 种子容器已移除：自建容器供后续用例使用（容器名同时用于「全字段搜索命中容器名」用例）
    repo.add_container(conn, "测试容器甲", None, "测试位")
    TEST_CNAME = "测试容器甲"
    cid = conn.execute("SELECT id FROM containers WHERE name=?", (TEST_CNAME,)).fetchone()[0]
    i1 = repo.add_item(conn, "ITEM_20260820_001", "苹果手机", cid, "2026-01-01",
                       "淘宝", "ORD1", 4999.0, "红色", "", "苹果,数码,手机",
                       [fake_upload("a.jpg", IMG_A), fake_upload("b.jpg", IMG_B)])
    i2 = repo.add_item(conn, "ITEM_20260820_002", "红苹果", cid, "2026-02-02",
                       "拼多多", "ORD2", 8.0, "", "", "苹果,水果", [])
    i3 = repo.add_item(conn, "ITEM_20260820_003", "无标签物", cid, "2026-03-03",
                       "", "", 0.0, "", "", "", [])
    check("add_item 返回自增 id", i3 == i1 + 2, f"{i1},{i3}")

    check("编号唯一校验", repo.item_no_exists(conn, "ITEM_20260820_001") is True)
    check("编号唯一校验 exclude_id 排除自身",
          repo.item_no_exists(conn, "ITEM_20260820_001", exclude_id=i1) is False)

    it = repo.load_item_by_id(conn, i1)
    check("load_item_by_id 聚合标签", it['tags'] == "苹果,数码,手机", it['tags'])
    check("load_item_by_id 编号", it['item_no'] == "ITEM_20260820_001")

    # ---------- 标签精确筛选 ----------
    df = repo.get_filtered_data(conn, "", "苹果")
    hit = set(df['item_no'])
    check("标签'苹果'精确命中 2 件", hit == {"ITEM_20260820_001", "ITEM_20260820_002"}, str(hit))
    df2 = repo.get_filtered_data(conn, "", "苹果手机")
    check("标签'苹果手机'不误匹配", set(df2['item_no']) == set(), str(set(df2['item_no'])))
    df3 = repo.get_filtered_data(conn, "", "苹果,手机")
    check("多标签 AND 关系", set(df3['item_no']) == {"ITEM_20260820_001"}, str(set(df3['item_no'])))
    df4 = repo.get_filtered_data(conn, "苹果", "")
    check("关键词搜索命中名称", {"苹果手机", "红苹果"} <= set(df4['name']), str(set(df4['name'])))

    # ---------- Phase 4: 全字段搜索 ----------
    df5 = repo.get_filtered_data(conn, "红色", "")    # features
    check("全字段搜索命中特点(features)", set(df5['item_no']) == {"ITEM_20260820_001"}, str(set(df5['item_no'])))
    df6 = repo.get_filtered_data(conn, "ORD1", "")    # order_no
    check("全字段搜索命中订单号", set(df6['item_no']) == {"ITEM_20260820_001"}, str(set(df6['item_no'])))
    df7 = repo.get_filtered_data(conn, "淘宝", "")    # platform
    check("全字段搜索命中平台", set(df7['item_no']) == {"ITEM_20260820_001"}, str(set(df7['item_no'])))
    df8 = repo.get_filtered_data(conn, "数码", "")    # 标签名（子查询）
    check("全字段搜索命中标签", set(df8['item_no']) == {"ITEM_20260820_001"}, str(set(df8['item_no'])))
    df9 = repo.get_filtered_data(conn, TEST_CNAME, "")    # 容器名（左连接列）
    check("全字段搜索命中容器名", set(df9['item_no']) == {"ITEM_20260820_001", "ITEM_20260820_002", "ITEM_20260820_003"},
          str(set(df9['item_no'])))
    df10 = repo.get_filtered_data(conn, "不存在的词", "")
    check("全字段搜索无命中返回空", df10.empty)

    # ---------- 标签重建与孤儿标签清理 ----------
    repo.update_item(conn, i2, "ITEM_20260820_002", "红苹果", cid, "2026-02-02",
                     "拼多多", "ORD2", 8.0, "", "", "梨子", [])
    check("update_item 标签重建", repo.load_item_by_id(conn, i2)['tags'] == "梨子")
    tag_names = {r[0] for r in conn.execute("SELECT name FROM tags")}
    check("孤儿标签'水果'已被清理", "水果" not in tag_names, str(tag_names))

    # ---------- 中文分隔符：表单标签录入兼容 中文逗号/分号（与 CSV 导入一致） ----------
    i4 = repo.add_item(conn, "ITEM_20260820_090", "分隔符物", cid, "2026-04-04",
                       "", "", 0.0, "", "", "电子，配件;游戏；怀旧", [])
    check("add 中文逗号/分号标签拆分",
          repo.load_item_by_id(conn, i4)['tags'] == "电子,配件,游戏,怀旧",
          repo.load_item_by_id(conn, i4)['tags'])
    repo.update_item(conn, i4, "ITEM_20260820_090", "分隔符物", cid, "2026-04-04",
                     "", "", 0.0, "", "", "数码，充电器", [])
    check("update 中文逗号标签拆分",
          repo.load_item_by_id(conn, i4)['tags'] == "数码,充电器",
          repo.load_item_by_id(conn, i4)['tags'])

    # ---------- 图片管理 ----------
    imgs = repo.load_images_by_item(conn, i1)
    check("load_images_by_item 返回绝对路径", len(imgs) == 2 and all(os.path.isabs(p) for p in imgs))
    first_map = repo.load_first_image_map(conn, [i1, i2, i3])
    check("load_first_image_map 批量首图", len(first_map) == 1 and i1 in first_map, str(first_map))

    img_full = repo.load_images_full(conn, i1)
    first_id, first_path, first_order = img_full[0]
    check("首图不能上移", repo.move_image(conn, i1, first_id, "up") is False)
    check("尾图不能下移", repo.move_image(conn, i1, img_full[-1][0], "down") is False)
    ok_move = repo.move_image(conn, i1, img_full[1][0], "up")   # 第二张上移
    new_ids = [r[0] for r in repo.load_images_full(conn, i1)]
    check("第二张上移成功且顺序交换", ok_move and new_ids == [img_full[1][0], img_full[0][0]], str(new_ids))
    # 删一张（仅被本物品引用 → 引用归零，文件一并删除），检查 sort_order 连续化
    target = repo.load_images_full(conn, i1)[0]
    old_file_exists = os.path.exists(target[1])
    ok_del = repo.delete_image(conn, i1, target[0])
    orders = [r[2] for r in repo.load_images_full(conn, i1)]
    check("delete_image 删记录+重排连续", ok_del and orders == [0], str(orders))
    check("delete_image 删除物理文件", old_file_exists and not os.path.exists(target[1]))

    # ---------- 图片池 M:N：同内容去重、多物品共享、引用归零才删文件（Phase 7） ----------
    n_pool_before = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    files_before = {f for f in os.listdir(db.PHOTOS_DIR)}
    s1 = repo.add_item(conn, "ITEM_20260820_900", "共享源", cid, "", "", "", 0, "", "", "",
                       [fake_upload("c.jpg", IMG_C), fake_upload("d.jpg", IMG_D)])
    s2 = repo.add_item(conn, "ITEM_20260820_901", "共享客", cid, "", "", "", 0, "", "", "",
                       [fake_upload("c.jpg", IMG_C), fake_upload("c.jpg", IMG_C)])
    # 与 s1 的 c.jpg 同字节 → 应复用；同物品内重复上传同样内容 → 只关联一次不报 PK 冲突
    check("同内容上传只新增一份池记录",
          conn.execute("SELECT COUNT(*) FROM images").fetchone()[0] == n_pool_before + 2)
    new_files = {f for f in os.listdir(db.PHOTOS_DIR)} - files_before
    check("同内容上传不重复落盘", len(new_files) == 2, str(new_files))
    s1_rows = repo.load_images_full(conn, s1)   # [c, d]
    s2_rows = repo.load_images_full(conn, s2)   # [c]，与 s1 的 c 同一池记录
    check("两物品关联同一池图片", len(s1_rows) == 2 and len(s2_rows) == 1
          and s2_rows[0][0] == s1_rows[0][0], f"{s1_rows} | {s2_rows}")
    # 共用图在详情页的“也用于”提示数据源：实时推导共用者，独有图不出现
    peers_s1 = repo.load_image_peers(conn, s1)
    check("load_image_peers 独有图无共用者", s1_rows[1][0] not in peers_s1, str(peers_s1))
    check("load_image_peers 共用图列出对方",
          peers_s1.get(s1_rows[0][0]) == [(s2, "ITEM_20260820_901", "共享客")], str(peers_s1))
    # 物品内重复上传被跳过（s2 只关联 1 行）；共享图在 s1 内上移（d 与 c 交换），
    # s2 中顺序不受影响
    ok_smove = repo.move_image(conn, s1, s1_rows[1][0], "up")
    check("共享图排序按物品独立",
          ok_smove and [r[0] for r in repo.load_images_full(conn, s1)] == [s1_rows[1][0], s1_rows[0][0]]
          and [r[0] for r in repo.load_images_full(conn, s2)] == [s1_rows[0][0]])
    # 从 s1 移除共享图 c：s2 仍引用 → 只解关联，不删文件不删池记录
    shared_c = repo.load_images_full(conn, s1)[1]   # 交换后 c 在位置 1
    ok_unlink = repo.delete_image(conn, s1, shared_c[0])
    check("从 s1 移除共享图仅解关联", ok_unlink
          and [r[0] for r in repo.load_images_full(conn, s1)] == [s1_rows[1][0]])
    check("解关联后另一物品不再提示共用者", repo.load_image_peers(conn, s2) == {})
    check("共享图文件保留（仍被 s2 引用）", os.path.exists(shared_c[1]))
    check("共享图池记录保留", conn.execute("SELECT COUNT(*) FROM images WHERE id=?",
                                           (shared_c[0],)).fetchone()[0] == 1)
    # s1 删除：其独有图 d 引用归零 → 清文件；共享图 c 不受影响
    d_path = repo.load_images_full(conn, s1)[0][1]
    repo.delete_item(conn, s1)
    check("删除物品后其独有图文件清除", not os.path.exists(d_path))
    check("删除物品不影响他人共享图", os.path.exists(shared_c[1]))
    # s2 删除（c 的最后引用）→ 文件清除 + 池记录删除
    repo.delete_item(conn, s2)
    check("最后引用删除后共享图文件清除", not os.path.exists(shared_c[1]))
    check("引用归零后池记录清除",
          conn.execute("SELECT COUNT(*) FROM images WHERE id=?", (shared_c[0],)).fetchone()[0] == 0)
    # save_shared_image 与旧函数同样校验文件头魔数
    try:
        db.save_shared_image(conn, fake_upload("evil.jpg", b"MZ\x90\x00" + b"\x00" * 16), "EVIL")
        check("save_shared_image 拒绝伪装文件", False, "未抛异常")
    except ValueError as e:
        check("save_shared_image 拒绝伪装文件", "不符" in str(e), str(e))

    # ---------- Phase 4: 图片 MIME 校验（save_uploaded_file） ----------
    png_ok = db.save_uploaded_file(fake_upload("ok.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16), "MIME_PNG")
    check("合法 PNG 头通过校验并落盘", png_ok.endswith(".png") and os.path.exists(db.img_abs_path(png_ok)), png_ok)
    fake_jpg = fake_upload("evil.jpg", b"MZ\x90\x00" + b"\x00" * 16)   # 伪装成 jpg 的 exe 头
    try:
        db.save_uploaded_file(fake_jpg, "MIME_EVIL")
        check("伪装 .jpg 被拒绝", False, "未抛异常")
    except ValueError as e:
        check("伪装 .jpg 被拒绝", "不符" in str(e), str(e))
    try:
        db.save_uploaded_file(fake_upload("noext", b"\xff\xd8\xff\xe0"), "MIME_NOEXT")
        check("无扩展名被拒绝", False, "未抛异常")
    except ValueError as e:
        check("无扩展名被拒绝", "缺少扩展名" in str(e), str(e))
    try:
        db.save_uploaded_file(fake_upload("doc.txt", b"plain text"), "MIME_TXT")
        check("非法扩展名被拒绝", False, "未抛异常")
    except ValueError as e:
        check("非法扩展名被拒绝", "不支持的图片类型" in str(e), str(e))

    # ---------- delete_item 唯一入口：单个删除 ----------
    d = repo.add_item(conn, "ITEM_20260820_004", "待删", cid, "2026-04-04", "", "", 0, "", "", "",
                      [fake_upload("d1.jpg")])
    d_img = repo.load_images_full(conn, d)
    d_file = d_img[0][1]
    file_existed = os.path.exists(d_file)
    repo.delete_item(conn, d)
    check("delete_item 删除物品记录", repo.load_item_by_id(conn, d) is None)
    check("delete_item 级联清图片记录", repo.load_images_by_item(conn, d) == [])
    check("delete_item 删除图片文件", file_existed and not os.path.exists(d_file))

    # ---------- 批量删除走同一 delete_item ----------
    b1 = repo.add_item(conn, "ITEM_20260820_005", "批量1", cid, "", "", "", 0, "", "", "", [])
    b2 = repo.add_item(conn, "ITEM_20260820_006", "批量2", cid, "", "", "", 0, "", "", "", [])
    for bid in (b1, b2):
        repo.delete_item(conn, bid)
    check("批量删除=多次 delete_item", repo.load_item_by_id(conn, b1) is None
          and repo.load_item_by_id(conn, b2) is None)

    # ---------- Phase 8: 物品手动关联（item_links：编号录入，整体校验） ----------
    check("parse_related_text 空输入为 []", repo.parse_related_text("") == []
          and repo.parse_related_text(" ， ； ") == [])
    parsed = repo.parse_related_text(" ITEM_20260820_001 , ITEM_20260820_002；ITEM_20260820_001， ITEM_20260820_003 ")
    check("parse_related_text 混合分隔/去空格/去重",
          parsed == ["ITEM_20260820_001", "ITEM_20260820_002", "ITEM_20260820_003"], str(parsed))

    r1 = repo.add_item(conn, "ITEM_20260820_800", "关联新人", cid, "", "", "", 0, "", "", "", [],
                       repo.parse_related_text("ITEM_20260820_001, ITEM_20260820_002"))
    rl1 = repo.load_related_items(conn, r1)
    check("add_item 关联落库（按 id 升序）",
          [(x[1], x[2]) for x in rl1] == [("ITEM_20260820_001", "苹果手机"),
                                          ("ITEM_20260820_002", "红苹果")], str(rl1))
    check("关联双向对称（对方视角含新物品）",
          [x[1] for x in repo.load_related_items(conn, i1)] == ["ITEM_20260820_800"])
    rows = conn.execute("SELECT a_id, b_id FROM item_links").fetchall()
    check("item_links 无向单行且 a<b 规范化",
          len(rows) == 2 and all(a < b for a, b in rows) and (min(i1, r1), max(i1, r1)) in rows,
          str(rows))

    # 整体校验：任一编号不存在 → 整单报错，物品与关联都不写入
    n_before = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    try:
        repo.add_item(conn, "ITEM_20260820_801", "坏关联", cid, "", "", "", 0, "", "", "", [],
                      repo.parse_related_text("ITEM_20260820_001, 不存在_XYZ, ITEM_20260820_802"))
        check("add 缺失编号整单报错", False, "未抛异常")
    except ValueError as e:
        check("add 缺失编号整单报错并列出全部",
              "不存在_XYZ" in str(e) and "ITEM_20260820_802" in str(e), str(e))
    check("add 报错时物品未插入",
          conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == n_before)

    # 更新 = 整体重建：旧关系被替换；输入自身编号静默忽略；空列表清空
    repo.update_item(conn, r1, "ITEM_20260820_800", "关联新人", cid, "", "", "", 0, "", "", "", [],
                     related_nos=repo.parse_related_text("ITEM_20260820_003, ITEM_20260820_800"))
    check("update_item 覆盖重建关联且自身忽略",
          [x[1] for x in repo.load_related_items(conn, r1)] == ["ITEM_20260820_003"], str(rl1))
    check("被移除端的关联同步消失", repo.load_related_items(conn, i1) == [])
    repo.update_item(conn, r1, "ITEM_20260820_800", "关联新人", cid, "", "", "", 0, "", "", "", [],
                     related_nos=[])
    check("空关联列表清空关联", repo.load_related_items(conn, r1) == []
          and repo.load_related_items(conn, i3) == [])

    # 更新带缺失编号：整体报错，名称与既有关联都不变
    try:
        repo.update_item(conn, r1, "ITEM_20260820_800", "改名", cid, "", "", "", 0, "", "", "", [],
                         related_nos=repo.parse_related_text("ITEM_20260820_003, 不存在_XYZ"))
        check("update 缺失编号整单报错", False, "未抛异常")
    except ValueError:
        check("update 缺失编号时名称与关联都不变",
              repo.load_item_by_id(conn, r1)['name'] == "关联新人"
              and repo.load_related_items(conn, r1) == [])

    # 删除物品：外键级联清掉它参与的全部关联行
    r2 = repo.add_item(conn, "ITEM_20260820_803", "关联临时", cid, "", "", "", 0, "", "", "", [],
                       repo.parse_related_text("ITEM_20260820_800"))
    repo.delete_item(conn, r2)
    check("删除物品级联清关联",
          repo.load_related_items(conn, r1) == []
          and conn.execute("SELECT COUNT(*) FROM item_links").fetchone()[0] == 0)

    # ---------- Phase 4: CSV 批量导入 ----------
    i18n.set_lang("zh")   # 错误消息断言依赖中文（应用默认语言为英文）
    container_map = repo.get_container_options(conn)
    cname = list(container_map.keys())[0]
    csv_ok = (f"item_no,name,container,purchase_date,platform,order_no,price,features,description,tags\n"
              f",导入物1,{cname},2026-08-20,京东,JD1,99.9,全新,备注一,数码;充电器\n"
              f",导入物2,{cname},2026-08-21,,,10,,,数码，保护壳\n").encode("utf-8-sig")
    rows, errs = repo.parse_import_csv(fake_upload("imp.csv", csv_ok), container_map)
    check("parse_import_csv 有效 2 行", len(rows) == 2 and not errs, f"rows={len(rows)} errs={errs}")
    check("parse_import_csv 容器解析为 id", rows[0]['container_id'] == container_map[cname])
    check("parse_import_csv item_no 留空", rows[0]['item_no'] == "" and rows[1]['item_no'] == "")
    check("parse_import_csv 标签归一化(分号/中文逗号)",
          rows[0]['tags'] == "数码,充电器" and rows[1]['tags'] == "数码,保护壳",
          f"{rows[0]['tags']} | {rows[1]['tags']}")
    check("parse_import_csv 价格转 float", rows[0]['price'] == 99.9)

    csv_err = (f"item_no,name,container,purchase_date,platform,order_no,price,features,description,tags\n"
               f",,{cname},,,,0,,,,\n"                  # 缺名称
               f",坏容器,不存在的容器,,,,0,,,,\n"         # 容器不存在
               f",坏价格,{cname},,,,abc,,,,\n").encode("utf-8")
    rows2, errs2 = repo.parse_import_csv(fake_upload("err.csv", csv_err), container_map)
    check("parse_import_csv 错误行全部识别", len(rows2) == 0 and len(errs2) == 3, str(errs2))
    check("parse_import_csv 错误信息含行号", all(isinstance(n, int) and n >= 2 for n, _ in errs2))

    csv_bad_header = b"a,b,c\n1,2,3\n"
    _, errs3 = repo.parse_import_csv(fake_upload("bad.csv", csv_bad_header), container_map)
    check("parse_import_csv 表头错误被拒", len(errs3) == 1 and "表头" in errs3[0][1], str(errs3))

    gbk_csv = (f"item_no,name,container,purchase_date,platform,order_no,price,features,description,tags\n"
               f",GBK物品,{cname},,,,0,,,,\n").encode("gbk")
    rows_g, errs_g = repo.parse_import_csv(fake_upload("gbk.csv", gbk_csv), container_map)
    check("parse_import_csv 支持 GBK 编码", len(rows_g) == 1 and rows_g[0]['name'] == "GBK物品", str(errs_g))

    rows, _ = repo.parse_import_csv(fake_upload("imp.csv", csv_ok), container_map)
    ok_n, imp_errs = repo.import_items(conn, rows)
    check("import_items 成功 2 条", ok_n == 2 and not imp_errs, f"ok={ok_n} errs={imp_errs}")
    new_items = repo.get_filtered_data(conn, "导入物", "")
    check("导入物品已落库且自动编号", len(new_items) == 2
          and all(str(no).startswith("ITEM_") for no in new_items['item_no']), str(new_items['item_no'].tolist()))
    # 编号冲突行：手动占用编号后导入应记 error 不中断
    dup_csv = (f"item_no,name,container,purchase_date,platform,order_no,price,features,description,tags\n"
               f"{new_items.iloc[0]['item_no']},重复编号,{cname},,,,0,,,,\n"
               f",第三件,{cname},,,,0,,,,\n").encode("utf-8")
    dup_rows, _ = repo.parse_import_csv(fake_upload("dup.csv", dup_csv), container_map)
    ok_n2, imp_errs2 = repo.import_items(conn, dup_rows)
    check("import_items 重复编号记 error 不中断", ok_n2 == 1 and len(imp_errs2) == 1, f"ok={ok_n2} errs={imp_errs2}")

    # ---------- 容器 CRUD ----------
    repo.add_container(conn, "Box_C03", None, "衣柜上层")
    cid3 = conn.execute("SELECT id FROM containers WHERE name='Box_C03'").fetchone()[0]
    check("容器名称唯一校验", repo.container_name_exists(conn, "Box_C03") is True)
    repo.update_container(conn, cid3, "Box_C03_改", cid, "衣柜顶层")
    check("update_container", repo.get_container(conn, cid3)[1] == "Box_C03_改")
    item_cnt, child_cnt = repo.container_usage(conn, cid3)
    check("container_usage 空容器", item_cnt == 0 and child_cnt == 0)
    # 造子容器再验证 usage
    repo.add_container(conn, "Box_C03_子", cid3, "")
    _, child_cnt2 = repo.container_usage(conn, cid3)
    check("container_usage 统计子容器", child_cnt2 == 1)
    repo.delete_containers(conn, [conn.execute("SELECT id FROM containers WHERE name='Box_C03_子'").fetchone()[0]])
    repo.delete_containers(conn, [cid3])
    check("delete_containers 已删除", repo.get_container(conn, cid3) is None)
    check("get_container_options 与库一致",
          repo.get_container_options(conn) == {n: i for i, n in conn.execute("SELECT id, name FROM containers")})

    # ---------- Phase 6: 容器图片 ----------
    repo.add_container(conn, "Box_D04", None, "抽屉下层")
    cd = conn.execute("SELECT id FROM containers WHERE name='Box_D04'").fetchone()[0]
    n1 = repo.save_container_images(conn, cd, [fake_upload("c1.jpg"), fake_upload("c2.jpg")])
    n2 = repo.save_container_images(conn, cd, [fake_upload("c3.jpg")])
    check("save_container_images 追加张数", n1 == 2 and n2 == 1, f"{n1},{n2}")
    cpaths = repo.load_container_images(conn, cd)
    check("load_container_images 3 张绝对路径", len(cpaths) == 3 and all(os.path.isabs(p) for p in cpaths))
    cfull = repo.load_container_images_full(conn, cd)
    check("load_container_images_full 顺序 0,1,2", [r[2] for r in cfull] == [0, 1, 2], str([r[2] for r in cfull]))
    cmap = repo.load_container_first_image_map(conn, [cd, cid])
    check("load_container_first_image_map 批量首图", cmap.get(cd) == cpaths[0], str(cmap))

    # 排序：第二张上移
    ok_cmove = repo.move_container_image(conn, cfull[1][0], "up")
    cids_after = [r[0] for r in repo.load_container_images_full(conn, cd)]
    check("move_container_image 上移交换",
          ok_cmove and cids_after == [cfull[1][0], cfull[0][0], cfull[2][0]], str(cids_after))
    check("move_container_image 首图不能上移", repo.move_container_image(conn, cids_after[0], "up") is False)

    # 删除中间一张 → 重排连续 + 物理文件删除
    target = repo.load_container_images_full(conn, cd)[1]
    old_existed = os.path.exists(target[1])
    ok_cdel = repo.delete_container_image(conn, target[0])
    orders_after = [r[2] for r in repo.load_container_images_full(conn, cd)]
    check("delete_container_image 删记录+重排", ok_cdel and orders_after == [0, 1], str(orders_after))
    check("delete_container_image 删物理文件", old_existed and not os.path.exists(target[1]))

    # 容器内物品清单 + 批量物品数（卡片视图数据）
    repo.add_item(conn, "ITEM_20260820_010", "容器内物1", cd, "", "", "", 0, "", "", "", [])
    repo.add_item(conn, "ITEM_20260820_011", "容器内物2", cd, "", "", "", 0, "", "", "", [])
    icm = repo.item_count_map(conn, [cd, cid])
    check("item_count_map 批量物品数", icm.get(cd) == 2, str(icm))
    items_in = repo.load_items_by_container(conn, cd)
    check("load_items_by_container 列表",
          len(items_in) == 2 and items_in[0][1].startswith("ITEM_"), str(items_in))

    # 删除容器：先删内部物品（外键 RESTRICT 保护非空容器），再删容器
    # → container_images 记录级联清 + 物理文件删
    for iid, _, _ in repo.load_items_by_container(conn, cd):
        repo.delete_item(conn, iid)
    cd_files = [r[1] for r in repo.load_container_images_full(conn, cd) if os.path.exists(r[1])]
    repo.delete_containers(conn, [cd])
    check("delete_containers 级联清容器图片记录",
          conn.execute("SELECT COUNT(*) FROM container_images WHERE container_id=?",
                       (cd,)).fetchone()[0] == 0)
    check("delete_containers 删除容器照片文件",
          bool(cd_files) and all(not os.path.exists(p) for p in cd_files))
    check("delete_containers 已删容器",
          repo.get_container(conn, cd) is None)

    # ---------- Phase 6: 孤儿扫描扩展到容器图片 ----------
    repo.add_container(conn, "Box_E05", None, "测试孤儿")
    ce = conn.execute("SELECT id FROM containers WHERE name='Box_E05'").fetchone()[0]
    conn.execute("INSERT INTO container_images (container_id, file_path, sort_order) VALUES (?, 'ghost_photo.jpg', 0)",
                 (ce,))
    conn.commit()
    orphans = db.find_orphan_images(conn)
    c_orphans = [o for o in orphans if o[3] == "container_images"]
    check("find_orphan_images 识别容器孤儿",
          len(c_orphans) == 1 and c_orphans[0][1] == f"container:{ce}", str(c_orphans))

    # ---------- 自动编号递增 ----------
    n1 = db.next_item_no(conn)
    conn.execute("INSERT INTO items (item_no, name) VALUES (?, 'x')", (n1,))
    conn.commit()
    n2 = db.next_item_no(conn)
    check("next_item_no 递增", n2 > n1, f"{n1} -> {n2}")

    # ---------- 自动备份轮转 ----------
    p1 = db.backup_data(keep=2)
    p2 = db.backup_data(keep=2)
    p3 = db.backup_data(keep=2)
    files = sorted(os.listdir(db.BACKUP_DIR))
    check("backup_data 轮转只留 2 份", len(files) == 2, str(files))
    check("backup_data 返回最新 zip 路径", p3.endswith(".zip") and p3 in [os.path.join(db.BACKUP_DIR, f) for f in files])

    # ---------- 旧库迁移 ----------
    conn.close()
    old_db = os.path.join(tmp, "old.db")
    oc = sqlite3.connect(old_db)
    oc.execute("CREATE TABLE containers (id INTEGER PRIMARY KEY, name TEXT UNIQUE, parent_id INTEGER, location TEXT)")
    oc.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, item_no TEXT UNIQUE, name TEXT, container_id INTEGER, "
               "purchase_date TEXT, platform TEXT, order_no TEXT, price REAL, features TEXT, description TEXT, tags TEXT)")
    oc.execute("CREATE TABLE images (id INTEGER PRIMARY KEY, item_id INTEGER, file_path TEXT, sort_order INTEGER)")
    oc.execute("INSERT INTO containers VALUES (1, 'Old_Box', NULL, '角落')")
    oc.execute("INSERT INTO items VALUES (1, 'OLD001', '旧物品', 1, '2025-01-01', 'x', '', 9.9, '', '', '旧标签A,旧标签B')")
    oc.execute("INSERT INTO images VALUES (1, 1, 'old_pic.jpg', 0)")
    oc.commit()

    db.DB_PATH = old_db
    oc.execute("PRAGMA foreign_keys=ON")
    db.init_db(oc)
    check("migrate_schema 保留旧数据", oc.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1)
    check("migrate_schema 重建外键",
          len(oc.execute("PRAGMA foreign_key_list(items)").fetchall()) >= 1)
    tags_rows = oc.execute("SELECT t.name FROM item_tags it JOIN tags t ON it.tag_id=t.id WHERE it.item_id=1").fetchall()
    check("migrate_tags 拆分旧逗号标签", {r[0] for r in tags_rows} == {"旧标签A", "旧标签B"}, str(tags_rows))
    check("migrate_tags 清空旧列", oc.execute("SELECT tags FROM items WHERE id=1").fetchone()[0] == "")
    # 旧版 images(item_id 归属，一图一物品) 原地迁移为图片池 + item_images（无需重新录入）
    img_cols = {r[1] for r in oc.execute("PRAGMA table_info(images)")}
    check("旧库 images 迁移为池结构（去 item_id 加 sha256）",
          {"id", "file_path", "sha256"} <= img_cols and "item_id" not in img_cols, str(img_cols))
    check("旧库图片入池且 id 保留",
          oc.execute("SELECT file_path FROM images WHERE id=1").fetchone()[0] == "old_pic.jpg")
    link = oc.execute("SELECT item_id, image_id, sort_order FROM item_images WHERE image_id=1").fetchone()
    check("旧库原归属 1:1 搬入关联表", link == (1, 1, 0), str(link))
    check("历史行 sha256 留空（不参与去重）",
          oc.execute("SELECT sha256 IS NULL FROM images WHERE id=1").fetchone()[0] == 1)
    db.init_db(oc)   # 幂等
    check("迁移幂等（不重复拆）", oc.execute("SELECT COUNT(*) FROM item_tags").fetchone()[0] == 2)
    check("图片池迁移幂等", oc.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 1
          and oc.execute("SELECT COUNT(*) FROM item_images").fetchone()[0] == 1)
    # item_links 是全新表：迁移只补建表，无需搬任何数据
    check("迁移建出 item_links 空表",
          oc.execute("SELECT COUNT(*) FROM item_links").fetchone()[0] == 0
          and {r[1] for r in oc.execute("PRAGMA table_info(item_links)")} == {"a_id", "b_id"})
    # 旧库 items 表无外键：验证迁移后删除容器被 RESTRICT 拒绝
    oc.execute("PRAGMA foreign_keys=ON")
    try:
        oc.execute("DELETE FROM containers WHERE id=1")
        rejected = False
    except sqlite3.IntegrityError:
        rejected = True
    check("迁移后外键 RESTRICT 生效", rejected)
    oc.close()

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
