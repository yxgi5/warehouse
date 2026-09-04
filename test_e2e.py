# -*- coding: utf-8 -*-
"""Phase 3 端到端回归：AppTest 模拟真实用户操作 UI 全链路。

注意（AppTest 1.40 边界）：同一 widget 在多次 run 间重复 set_value 会被
上一轮回读值覆盖（get_widget_states 会把树上所有 widget 当前值重提交）。
因此本脚本保证【每个 widget 仅 set_value 一次】；"不误匹配"验证放在
repo 层（DB 逻辑已由 test_data_layer.py 覆盖）。
"""
import os
import base64
import sqlite3
import sys
import types

# 仓库根目录锚定：跟随脚本自身位置（目录可改名/搬移）
_BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_BASE)
sys.path.insert(0, _BASE)
from streamlit.testing.v1 import AppTest


def find_button(container, label_exact=None, label_contains=None):
    for b in container.button:
        lbl = str(getattr(b, "label", ""))
        if label_exact is not None and lbl.strip() == label_exact:
            return b
        if label_contains is not None and label_contains in lbl:
            return b
    return None


def main():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert len(at.exception) == 0, at.exception
    # 应用默认语言为英文；测试固定以中文界面执行（后续断言多依赖中文 label），
    # 第 6 步再单独验证「切英文生效」。
    at.session_state["lang"] = "zh"
    at.run()
    assert len(at.exception) == 0, at.exception
    print("✅ 初始渲染 0 异常（中文界面）")

    # ---- 1. 新增物品表单填表提交（每个控件仅 set 一次） ----
    at.text_input(key="draft_item_no").set_value("E2E_ITEM_001")
    at.text_input[1].set_value("E2E测试物品")       # name（tab6 表单第二个 text_input）
    at.text_input[4].set_value("端到端,回归")       # tags
    at.number_input[0].set_value(123.45)            # price
    btn = find_button(at, label_contains="保存物品")
    assert btn is not None, "找不到保存按钮"
    btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    # 回归保护：保存成功不得出现错误提示（历史 bug：widget 实例化后改写
    # draft_item_no 导致 Save failed，但物品已落库，误导用户）
    assert len(at.error) == 0, [str(getattr(e, "value", "")) for e in at.error]

    conn = sqlite3.connect("warehouse.db")
    conn.execute("PRAGMA foreign_keys=ON")
    row = conn.execute("SELECT id, name FROM items WHERE item_no='E2E_ITEM_001'").fetchone()
    assert row, "物品未落库"
    item_id = row[0]
    # 保存成功应打开新物品详情（detail_item_id 指向新物品；AppTest 不执行切 Tab 的 JS）
    assert at.session_state["detail_item_id"] == item_id, at.session_state["detail_item_id"]
    print("✅ 保存成功自动打开新物品详情")
    # 复位详情状态回到列表视图，供后续标签筛选/搜索的表格断言
    at.session_state["detail_item_id"] = None
    at.run()
    assert len(at.exception) == 0, at.exception
    tags = {r[0] for r in conn.execute(
        "SELECT t.name FROM item_tags it JOIN tags t ON it.tag_id=t.id WHERE it.item_id=?",
        (item_id,))}
    assert tags == {"端到端", "回归"}, tags
    print("✅ UI 新增物品 → 落库 → 标签关联", tags)

    # ---- 2. 全局标签筛选（精确匹配）命中路径（tag_filter 控件仅 set 一次） ----
    at.sidebar.text_input(key="global_tag_filter").set_value("端到端")
    at.run()
    dfv = at.dataframe[0].value
    assert "E2E_ITEM_001" in set(dfv["item_no"]), f"筛选'端到端'未命中: {dfv['item_no'].tolist()}"
    print("✅ 标签'端到端'精确命中（UI 链路）")

    # ---- 2b. 不误匹配验证（repo 层，DB 逻辑） ----
    import repo
    none_hit = repo.get_filtered_data(conn, "", "端到端回归")
    assert not any(r["item_no"] == "E2E_ITEM_001" for r in none_hit.to_dict("records")), "标签'端到端回归'误匹配!"
    print("✅ 标签'端到端回归'不误匹配（repo 层精确查询）")

    # ---- 2c. Phase 4: 全字段搜索命中（global_search 控件仅 set 一次） ----
    at.sidebar.text_input(key="global_search").set_value("E2E测试物品")
    at.run()
    dfv2 = at.dataframe[0].value
    assert "E2E_ITEM_001" in set(dfv2["item_no"]), f"搜索名称未命中: {dfv2['item_no'].tolist()}"
    print("✅ 全字段搜索命中名称（UI 链路）")

    # ---- 2d. 浏览态顶部有列表/卡片切换（子页面里不应再出现，见 3/4 步） ----
    assert len(at.tabs[0].radio) == 1, "浏览态缺少列表/卡片切换 radio"

    # ---- 3. 详情页渲染（注入 detail_item_id，等价于用户点开详情） ----
    at.session_state["detail_item_id"] = item_id
    at.run()
    assert len(at.exception) == 0, at.exception
    assert len(at.tabs[0].radio) == 0, "详情页不应出现列表/卡片切换 radio"
    # 详情是浏览态延伸：此时点其它 Tab 必须正常渲染（子页面不得 st.stop() 截断脚本）
    assert len(at.tabs[5].text_input) > 0, "详情页下 Add 页空白（st.stop 截断了脚本）"
    assert len(at.tabs[6].radio) >= 1, "详情页下 Containers 页空白（st.stop 截断了脚本）"
    print("✅ 详情页渲染 0 异常，其它 Tab 同轮正常渲染")

    # ---- 3b. 造两件共用同一张图（同字节内容）的物品：UI 无法上传文件，走 repo 层 ----
    cid2 = conn.execute("SELECT container_id FROM items WHERE id=?", (item_id,)).fetchone()[0]
    img_x = base64.b64decode(   # 合法 1x1 JPEG（魔数校验后 st.image 还能真正渲染）
        '/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U'
        'HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QA'
        'FAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//'
        '2Q==')
    peer_a = repo.add_item(conn, "E2E_IMG_A", "共图甲", cid2, "", "", "", 0, "", "", "",
                           [types.SimpleNamespace(name="x.jpg", getbuffer=lambda: img_x)])
    peer_b = repo.add_item(conn, "E2E_IMG_B", "共图乙", cid2, "", "", "", 0, "", "", "",
                           [types.SimpleNamespace(name="x.jpg", getbuffer=lambda: img_x)])
    assert repo.load_related_items(conn, peer_a) == [] and repo.load_related_items(conn, peer_b) == [], \
        "repo 直造物品不应有手动关联"
    assert len(repo.load_image_peers(conn, peer_a).get(
        repo.load_images_full(conn, peer_a)[0][0], [])) == 1, "共图关系未推导"
    print("✅ 共用图推导：两件物品同字节图互见（item_images 实时）")

    # ---- 4. 详情页点"✏️ 编辑" → 编辑页渲染 ----
    btn = find_button(at, label_exact="✏️ 编辑")
    assert btn is not None, "详情页无编辑按钮"
    btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    edit_texts = [str(getattr(t, "value", "")) for t in at.text_input]
    assert any("E2E_ITEM_001" in v for v in edit_texts), "编辑表单未带出编号"
    assert len(at.tabs[0].radio) == 0, "编辑页不应出现列表/卡片切换 radio"
    assert len(at.tabs[5].text_input) > 0, "编辑页下 Add 页空白（st.stop 截断了脚本）"
    assert len(at.tabs[6].radio) >= 1, "编辑页下 Containers 页空白（st.stop 截断了脚本）"
    print("✅ 编辑页渲染 0 异常，编号已带出，其它 Tab 同轮正常渲染")

    # ---- 4b. 编辑表单录入“关联物品编号”（整体校验通过）→ 提交落库 item_links ----
    at.text_input(key="edit_related_items").set_value("E2E_IMG_A, E2E_IMG_B")
    btn = find_button(at, label_contains="更新物品")
    assert btn is not None, "编辑表单无保存按钮"
    btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert len(at.error) == 0, [str(getattr(e, "value", "")) for e in at.error]
    # 只断言与本次物品相关的行（真实库可能有用户自己的关联数据）
    got_pairs = {tuple(r) for r in conn.execute(
        "SELECT a_id, b_id FROM item_links WHERE a_id=? OR b_id=?", (item_id, item_id))}
    want_pairs = {(min(item_id, peer_a), max(item_id, peer_a)),
                  (min(item_id, peer_b), max(item_id, peer_b))}
    assert got_pairs == want_pairs, got_pairs
    print("✅ 编辑保存关联编号 → item_links 落库（无向单行 a<b）")

    # ---- 4c. 详情页关联区与图下共用提示的跳转闭环 ----
    # E2E_ITEM_001（无图）详情：关联区列出两件，点按钮切到对方详情
    at.session_state["detail_item_id"] = item_id
    at.run()
    assert len(at.exception) == 0, at.exception
    btn_a = find_button(at, label_exact="E2E_IMG_A 共图甲")
    assert btn_a is not None, "详情关联区缺 E2E_IMG_A 按钮"
    btn_a.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert at.session_state["detail_item_id"] == peer_a, "关联按钮未跳转到 E2E_IMG_A"
    # E2E_IMG_A 详情（带图）：图下“也用于 E2E_IMG_B”，点按钮切过去
    btn_b = find_button(at, label_exact="E2E_IMG_B")
    assert btn_b is not None, "共用图下方缺 E2E_IMG_B 跳转按钮"
    btn_b.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert at.session_state["detail_item_id"] == peer_b, "共用图按钮未跳转到 E2E_IMG_B"
    # E2E_IMG_B 详情：图下提示 A、关联区提示 E2E_ITEM_001，均可跳
    btn_a2 = find_button(at, label_exact="E2E_IMG_A")
    assert btn_a2 is not None, "E2E_IMG_B 图下缺 E2E_IMG_A 按钮"
    back_link = find_button(at, label_exact="E2E_ITEM_001 E2E测试物品")
    assert back_link is not None, "E2E_IMG_B 关联区缺 E2E_ITEM_001 按钮"
    back_link.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert at.session_state["detail_item_id"] == item_id, "关联区按钮未跳回 E2E_ITEM_001"
    print("✅ 详情页关联区/共用图下按钮双向跳转闭环")

    # ---- 5. 清理测试数据（走唯一删除入口；只删 E2E 测试物品，不碰用户数据）----
    repo.delete_item(conn, peer_a)
    repo.delete_item(conn, peer_b)
    repo.delete_item(conn, item_id)
    assert conn.execute("SELECT COUNT(*) FROM item_links WHERE a_id=? OR b_id=?",
                        (item_id, item_id)).fetchone()[0] == 0, "删除物品后 item_links 残留"
    conn.close()
    print("✅ 测试数据已清理（含 item_links 级联清空）")

    # ---- 6. Phase 5: 语言切换（global_lang 仅 set 一次；切英文后 label 变化即生效） ----
    at.sidebar.selectbox(key="global_lang").set_value("English")
    at.run()
    assert len(at.exception) == 0, at.exception
    s1 = at.sidebar.text_input(key="global_search").label.strip()
    s2 = at.sidebar.text_input(key="global_tag_filter").label.strip()
    assert s1 == "Search", f"搜索框 label 未切换: {s1}"
    assert s2 == "Tags (comma-separated)", f"标签框 label 未切换: {s2}"
    lang_val = at.sidebar.selectbox(key="global_lang").value
    assert lang_val == "English", lang_val
    print("✅ 语言切换 → 英文界面生效（Search / Tags / English）")

    # ---- 6.5 列表视图工具栏：常驻表格下方，未选中时禁用 + 提示（与 UI 设计一致） ----
    # 回归保护：工具栏按钮在列表视图中直接可定位（不滚动、不等二次 rerun）。
    # 「View Details」需恰好选中 1 行才 enabled；AppTest 无法模拟表格行选中，
    # 因此这里验证 disabled 态按钮存在 + 未选中提示（info）已渲染；若历史状态
    # 恰好有选中（enabled），点击进入详情也不应崩溃。
    view_btn = find_button(at, label_contains="View Details")
    assert view_btn is not None, "列表工具栏「View Details」缺失"
    if view_btn.disabled:
        hints = [str(getattr(i, "value", "")) for i in at.info] + \
                [str(getattr(s, "value", "")) for s in at.success]
        assert any("select" in v.lower() for v in hints), f"未选中提示缺失: {hints}"
        print("✅ 列表工具栏常驻：未选中时按钮禁用且有提示")
    else:
        view_btn.click()
        at.run()
        assert len(at.exception) == 0, at.exception
        at.session_state["detail_item_id"] = None
        at.run()
        assert len(at.exception) == 0, at.exception
        print("✅ 列表工具栏常驻：选中状态下点击进入详情无异常")

    # ---- 7. Phase 6: 容器管理 → 卡片视图 + 容器详情页渲染 ----
    assert len(at.tabs) >= 7, f"tabs 数量: {len(at.tabs)}"
    cont_radio = at.tabs[6].radio(key="container_view_radio")
    assert cont_radio is not None, "容器视图切换 radio 不存在"
    cont_radio.set_value("Cards")   # 英文界面下容器卡片视图
    at.run()
    assert len(at.exception) == 0, at.exception
    card_btn = find_button(at.tabs[6], label_contains="Open Details")
    assert card_btn is not None, "卡片视图未渲染打开详情按钮"
    print("✅ 容器卡片视图渲染 0 异常")

    # 点开第一个容器详情页
    card_btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert at.session_state["container_detail_id"] is not None, "容器详情未打开"
    sub_headers = [str(getattr(h, "value", "")) for h in at.tabs[6].subheader]
    assert any("Container Details" in v for v in sub_headers), f"详情页标题缺失: {sub_headers}"
    print("✅ 容器详情页渲染 0 异常（含照片区/物品清单）")

    # 恢复浏览状态
    at.session_state["container_detail_id"] = None
    at.session_state["container_view_mode"] = "table"
    at.run()
    assert len(at.exception) == 0, at.exception

    # ---- 8. 容器树 Tab：纯层级树（顶层 isna 匹配 + 不平铺物品 + 详情跳转）----
    # 历史 bug：SQLite NULL 读入 pandas 为 NaN，`parent_id == None` 匹配 0 行
    # → 树完全空白。修复用 isna() 后断言顶层容器名出现在 Tab5。
    # Phase 6 调整：树只显示容器层级与物品数统计，不列具体物品行。
    # 顶层容器名从库中动态读取（demo 数据可能用不同命名，硬编码会过时）。
    conn2 = sqlite3.connect("warehouse.db")
    top_names = [r[0] for r in conn2.execute(
        "SELECT name FROM containers WHERE parent_id IS NULL ORDER BY id LIMIT 3")]
    conn2.close()
    assert top_names, "库中无顶层容器"
    tree_md = [str(getattr(m, "value", "")) for m in at.tabs[4].markdown]
    tree_text = "\n".join(tree_md)
    for top_name in top_names:
        assert top_name in tree_text, f"容器树未渲染顶层容器「{top_name}」: {tree_text[:200]}"
    assert "ITEM_" not in tree_text, "容器树不应平铺具体物品行"
    print(f"✅ 容器树渲染顶层容器（{', '.join(top_names)}）且不平铺物品（isna 修复防回归）")

    # 行尾「Detail」按钮 → 树 Tab 内就地打开容器详情页（1.40 无 tabs key，不做跨 Tab 跳转）
    tree_btn = find_button(at.tabs[4], label_contains="Detail")
    assert tree_btn is not None, "容器树行尾详情按钮缺失"
    tree_btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert "tree_detail_id" in at.session_state and at.session_state["tree_detail_id"] is not None, \
        "容器树详情按钮未设置 tree_detail_id"
    # 容器管理 Tab 状态不被污染（仍在浏览态）
    assert "container_detail_id" not in at.session_state or at.session_state["container_detail_id"] is None, \
        "容器管理 Tab 详情状态被误改"
    # 树 Tab 内渲染出详情页标题与返回按钮
    sub_headers = [str(getattr(h, "value", "")) for h in at.tabs[4].subheader]
    assert any("Container Details" in v for v in sub_headers), f"树内详情页标题缺失: {sub_headers}"
    back_btn = find_button(at.tabs[4], label_contains="Back")
    assert back_btn is not None, "树内详情页返回按钮缺失"
    print("✅ 容器树行尾详情按钮 → 树内就地打开容器详情页")

    # 返回按钮 → 回到树
    back_btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert "tree_detail_id" not in at.session_state or at.session_state["tree_detail_id"] is None, \
        "返回后 tree_detail_id 未清除"
    tree_md_after = [str(getattr(m, "value", "")) for m in at.tabs[4].markdown]
    assert any(top_names[0] in v for v in tree_md_after), "返回后容器树未重新渲染"
    print("✅ 容器树详情页返回按钮 → 回到树视图")

    # 恢复浏览状态
    at.session_state["container_detail_id"] = None
    at.session_state["container_view_mode"] = "table"
    at.run()
    assert len(at.exception) == 0, at.exception

    print("E2E RESULT: PASS")


if __name__ == "__main__":
    main()
