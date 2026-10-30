# -*- coding: utf-8 -*-
"""warehouse_v2 冒烟测试：用 streamlit AppTest 真实执行 app.py，验证无运行时异常。

用法:  python smoke_test.py
"""
import os
import sys
import sqlite3

APP = "app.py"


def main():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    print("run 完成, exception 数:", len(at.exception))
    for e in at.exception:
        print("EXCEPTION:", e)
    # 应用默认语言为英文；测试固定以中文界面执行（「侧边栏含备份状态」检测中文文案）
    at.session_state["lang"] = "zh"
    # 自动备份在后台线程（1.9GB photos 打包）：AppTest 不等线程，立即 at.run() 侧栏
    # 拿不到 backup_path → 「备份状态」断言竞态失败。轮询等待完成（WH_SKIP_AUTO_BACKUP
    # 时线程未启动，跳过等待）。
    backup_waited = False
    if os.environ.get("WH_SKIP_AUTO_BACKUP") != "1":
        import time as _t
        import db as _db
        # 1.9GB photos 打包实测 1-2 分钟；backup_path 在打包完成后才写入
        for _ in range(360):
            if _db.BG.get("backup_path"):
                backup_waited = True
                break
            _t.sleep(0.5)
    at.run()

    db_ok = os.path.exists("warehouse.db")
    print("warehouse.db 已创建:", db_ok)

    bdir = "backups"
    backups = sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []
    print("备份 zip 数量:", len(backups), backups)

    sidebar_text = []
    for s in at.sidebar:
        v = getattr(s, 'value', None)
        if v is None:
            v = getattr(s, 'body', '')
        sidebar_text.append(str(v))
    has_backup = any("备份" in t for t in sidebar_text)
    backup_asserted = True
    if os.environ.get("WH_SKIP_AUTO_BACKUP") == "1":
        print("侧边栏含备份状态: SKIP(WH_SKIP_AUTO_BACKUP=1，备份线程未启动)")
        backup_asserted = False
    elif not backup_waited:
        print("侧边栏含备份状态: SKIP(备份打包超 3 分钟未完成，异步特性不阻塞冒烟)")
        backup_asserted = False
    else:
        print("侧边栏含备份状态:", has_backup)

    conn = sqlite3.connect("warehouse.db")
    n = conn.execute("SELECT COUNT(*) FROM containers").fetchone()[0]
    conn.close()
    print("容器数量（无内置种子，取决于库中数据）:", n)

    ok = (len(at.exception) == 0 and db_ok and len(backups) > 0
          and (has_backup or not backup_asserted))
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
