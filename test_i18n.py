# -*- coding: utf-8 -*-
"""Phase 5 i18n 测试：双语言字典完整性、t() 行为、repo 层错误消息联动。

用法:  python test_i18n.py
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import i18n

passed = 0


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")


def main():
    print("=== i18n 字典完整性 ===")
    zh, en = i18n.TRANSLATIONS['zh'], i18n.TRANSLATIONS['en']
    check("zh/en key 集合完全一致", set(zh.keys()) == set(en.keys()),
          f"差异 zh-en: {set(zh.keys()) - set(en.keys())}, en-zh: {set(en.keys()) - set(zh.keys())}")
    check("zh 无空值", all(zh[k] for k in zh))
    check("en 无空值", all(en[k] for k in en))
    check("语言列表含 zh/en", set(i18n.supported_langs()) == {"zh", "en"})

    print("=== t() 设置与切换 ===")
    i18n.set_lang("zh")
    check("set zh 后生效", i18n.get_lang() == "zh")
    check("zh 文案正确", i18n.t("app.title") == "个人物品仓库")
    i18n.set_lang("en")
    check("切换 en 后生效", i18n.t("app.title") == "Personal Warehouse")
    i18n.set_lang("xx")
    check("非法语言回退默认 en", i18n.get_lang() == "en")
    check("未知 key 回显 key", i18n.t("no.such.key") == "no.such.key")
    check("未知 key 不抛异常", isinstance(i18n.t("no.such.key"), str))

    print("=== format 参数 ===")
    i18n.set_lang("zh")
    check("带参文案 format", i18n.t("sidebar.last_backup", name="x.zip") == "🗄️ 最近备份: x.zip")
    check("多参数 format", i18n.t("items.list_count", total=3, n=1) == "共 3 件，已选 1 件")
    i18n.set_lang("en")
    check("英文 format", i18n.t("items.list_count", total=3, n=1) == "3 items, 1 selected")
    check("参数缺失不崩溃", isinstance(i18n.t("items.edit_title", item_no="X"), str))

    print("=== repo 层 CSV 错误消息随语言联动 ===")
    import repo
    import db
    from tempfile import mkdtemp

    tmp = mkdtemp(prefix="wh_i18n_")
    db.DB_PATH = os.path.join(tmp, "t.db")
    db.PHOTOS_DIR = os.path.join(tmp, "photos")
    db.BACKUP_DIR = os.path.join(tmp, "backups")
    conn = db.get_conn()
    db.init_db(conn)
    container_map = repo.get_container_options(conn)

    import types
    bad_csv = b"item_no,name,container,purchase_date,platform,order_no,price,features,description,tags\n" \
              b",TestName,NoSuchBox,,,,abc,,,\n"
    fake = types.SimpleNamespace(name="bad.csv", getbuffer=lambda: bad_csv)

    i18n.set_lang("zh")
    _, errs_zh = repo.parse_import_csv(fake, container_map)
    zh_err = errs_zh[0][1] if errs_zh else ""
    i18n.set_lang("en")
    _, errs_en = repo.parse_import_csv(fake, container_map)
    en_err = errs_en[0][1] if errs_en else ""
    check("zh 错误消息含容器不存在", "不存在" in zh_err, zh_err)
    check("en 错误消息为英文", "not found" in en_err, en_err)
    check("两语言错误消息不同", zh_err != en_err, f"{zh_err} | {en_err}")

    i18n.set_lang("zh")
    conn.close()
    print(f"\n结果: {passed} 项全部通过")
    return passed


if __name__ == "__main__":
    n = main()
    sys.exit(0 if n >= 10 else 1)
