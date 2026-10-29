# -*- coding: utf-8 -*-
"""Global Filter 搜索：大小写不敏感 + 支持 * ? 通配符。

运行：python tests/test_filter.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"D:\repos\warehouse.git")
sys.path.insert(0, str(ROOT))

import db
import repo


def build():
    conn = sqlite3.connect(":memory:")
    db.init_db(conn)
    conn.execute("INSERT INTO containers (id,name,parent_id,location) "
                 "VALUES (1,'BoxA',NULL,'loc')")
    conn.execute(
        "INSERT INTO items (id,item_no,name,container_id,features,description,"
        "platform,order_no) VALUES (1,'P001','TestPhone XyZ',1,'featABC',"
        "'descXYZ','PlatForm','ORD123')")
    conn.execute("INSERT INTO tags (id,name) VALUES (1,'MyTag')")
    conn.execute("INSERT INTO item_tags (item_id,tag_id) VALUES (1,1)")
    conn.commit()
    return conn


def cnt(conn, q):
    return len(repo.get_filtered_data(conn, q, ""))


def main():
    conn = build()
    checks = [
        ("小写命中(大小写不敏感)", cnt(conn, "testphone") == 1),
        ("大写命中(大小写不敏感)", cnt(conn, "TESTPHONE") == 1),
        ("混合大小写", cnt(conn, "TestPhone") == 1),
        ("通配符前缀 Test*", cnt(conn, "Test*") == 1),
        ("通配符后缀 *XyZ", cnt(conn, "*XyZ") == 1),
        ("通配符 ? 单字 PlatFor?=PlatForm", cnt(conn, "PlatFor?") == 1),
        ("默认子串 phone", cnt(conn, "phone") == 1),
        ("订单号子串 ord123(小写)", cnt(conn, "ord123") == 1),
        ("标签名子串 mytag(小写)", cnt(conn, "mytag") == 1),
        ("容器名 boxa(小写)", cnt(conn, "boxa") == 1),
        ("不匹配", cnt(conn, "zzznomatch") == 0),
        ("全通配 * 至少命中自身", cnt(conn, "*") >= 1),
    ]
    passed = 0
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        passed += 1 if ok else 0
    print(f"\nSUMMARY: {passed}/{len(checks)} passed")
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
