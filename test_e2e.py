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
from datetime import date

# 仓库根目录锚定：跟随脚本自身位置（目录可改名/搬移）
_BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_BASE)
sys.path.insert(0, _BASE)
from streamlit.testing.v1 import AppTest
import repo


def find_button(container, label_exact=None, label_contains=None):
    for b in container.button:
        lbl = str(getattr(b, "label", ""))
        if label_exact is not None and lbl.strip() == label_exact:
            return b
        if label_contains is not None and label_contains in lbl:
            return b
    return None


def prune_dead_widgets(node):
    """摘除 AppTest 树中"已卸载但仍残留"的控件节点（测试辅助，不影响 app 行为）。

    AppTest 1.40 边界：app 在表单提交后主动 st.rerun() 切到别的子页面时，上一轮的
    表单控件已不在新页面渲染，Streamlit 会清掉它们的 widget state；但 AppTest 建树时
    Block 互相覆盖会让新 Block 继承旧 Block 的子节点，残留的输入类控件节点仍挂在树上
    ——下一轮 run() 收集 widget 状态时读 state 即 KeyError（按钮/上传框不读 state，
    不受影响；容器编辑→详情页因元素覆盖恰好干净，无需处理）。这里在继续跑之前把树上
    这些死节点摘掉。
    """
    children = getattr(node, "children", None)
    if not children:
        return
    for idx in list(children):
        child = children[idx]
        try:
            child._widget_state      # Widget 节点：探测服务端 state 是否已被清理
        except KeyError:
            del children[idx]        # 死节点：摘掉，避免下一轮 run() KeyError
            continue
        except AttributeError:
            pass                      # 非 Widget 节点：没有 _widget_state
        prune_dead_widgets(child)


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
    conn = sqlite3.connect("warehouse.db")
    conn.execute("PRAGMA foreign_keys=ON")
    # 预清理历史残留：上次异常中断退出会留下 E2E 物品/容器，否则重跑时编号冲突
    for rid in [r[0] for r in conn.execute("SELECT id FROM items WHERE item_no LIKE 'E2E_%'")]:
        repo.delete_item(conn, rid)
    for cid in [r[0] for r in conn.execute("SELECT id FROM containers WHERE name LIKE 'E2E_%'")]:
        repo.delete_containers(conn, [cid])
    # 空库保底（干净克隆无容器）：新增表单/3b/后续都要选容器 → 自建一个测试容器，
    # 结束统一清理；有演示数据则直接复用（评审 P1-⑤：不硬编码容器名也不要求种子）
    if conn.execute("SELECT COUNT(*) FROM containers").fetchone()[0] == 0:
        repo.add_container(conn, "E2E_CTR_BASE", None, "e2e 保底", "")
        # 容器写库后必须立即刷新元素树：AppTest 校验 selectbox 的 value 必须在其
        # options 内（旧渲染只有占位符），否则首次 at.run() 抛 ValueError:
        # 'E2E_CTR_BASE' is not in list（CI 实测；本地 1.40.1 不校验，新版才拦）
        at.run()
        assert len(at.exception) == 0, at.exception
    # Phase 7：新增入口收进「物品浏览」Tab——先点浏览态顶部「➕ 新增物品」
    # 进入新增子页面（不再有独立 Add Tab）
    add_entry = find_button(at, label_contains="新增物品")
    assert add_entry is not None, "物品 Tab 浏览态缺新增入口按钮"
    add_entry.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert "add_item_mode" in at.session_state and at.session_state["add_item_mode"] is True, \
        "点击新增入口未进入新增子页面"
    # 编号/容器/购买日期三个字段都在，但默认不给内容：编号空、容器=占位未选、
    # 日期靠默认勾选"无购买日期"留空（date_input 原生无空态）
    assert str(at.text_input(key="draft_item_no").value) == "", "编号不应预填"
    assert len(at.tabs[0].selectbox) == 1, "添加表单应有容器选择下拉"
    assert "(请选择容器)" in str(at.tabs[0].selectbox[0].value), "容器默认应为占位(未预选)"
    assert at.tabs[0].checkbox[0].value is True, "无购买日期应默认勾选(不预填日期)"
    assert at.tabs[0].date_input[0].disabled is False, "日期框应始终可填(不得 disabled 联动勾选框)"
    print("✅ 添加表单字段齐全且默认无内容（编号/容器/日期不预填）")

    at.text_input(key="draft_item_no").set_value("E2E_ITEM_001")
    at.text_input(key="add_name").set_value("E2E测试物品")       # name
    at.text_input(key="add_tags").set_value("端到端,回归")       # tags
    at.number_input(key="add_price").set_value(123.45)          # price
    # 容器/日期“可以填”：取消无日期勾选、各选一个真实值
    e2e_cont_name = conn.execute("SELECT name FROM containers ORDER BY id LIMIT 1").fetchone()[0]
    at.tabs[0].selectbox[0].set_value(e2e_cont_name)
    at.tabs[0].checkbox[0].set_value(False)
    at.tabs[0].date_input[0].set_value(date(2024, 1, 15))
    btn = find_button(at, label_contains="保存物品")
    assert btn is not None, "找不到保存按钮"
    btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    # 回归保护：保存成功不得出现错误提示（历史 bug：widget 实例化后改写
    # draft_item_no 导致 Save failed，但物品已落库，误导用户）
    assert len(at.error) == 0, [str(getattr(e, "value", "")) for e in at.error]

    row = conn.execute("SELECT id, name FROM items WHERE item_no='E2E_ITEM_001'").fetchone()
    assert row, "物品未落库"
    item_id = row[0]
    # 保存成功应退出新增态并打开新物品详情（新增子页面在物品 Tab 内，无需跨 Tab 跳转）
    assert at.session_state["detail_item_id"] == item_id, at.session_state["detail_item_id"]
    assert "add_item_mode" in at.session_state and at.session_state["add_item_mode"] is False, \
        "保存成功后应退出新增子页面"
    print("✅ 保存成功自动打开新物品详情")
    # 新增表单已随 rerun 卸载，但其输入控件节点会残留在 AppTest 树上（state 已清），
    # 摘掉后再跑，否则下一轮 run() 收集 widget 状态会 KeyError（见 prune_dead_widgets）
    prune_dead_widgets(at._tree)
    # 所填容器与日期按选择落库
    e2e_cont_id = conn.execute("SELECT id FROM containers WHERE name=?",
                               (e2e_cont_name,)).fetchone()[0]
    meta = conn.execute("SELECT container_id, purchase_date FROM items WHERE id=?",
                        (item_id,)).fetchone()
    assert meta == (e2e_cont_id, "2024-01-15"), f"所选容器/日期应落库: {meta}"
    print("✅ 新增落库：所填容器与日期生效")
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
    # Phase 10 Step1：控制行 = 视图 radio（标签已折叠，仅留选项）+ 水平居中的新增按钮
    assert find_button(at, label_contains="新增物品") is not None, \
        "物品浏览态缺「➕ 新增物品」按钮（应位于控制行）"

    # ---- 3. 详情页渲染（注入 detail_item_id，等价于用户点开详情） ----
    at.session_state["detail_item_id"] = item_id
    at.run()
    assert len(at.exception) == 0, at.exception
    assert len(at.tabs[0].radio) == 0, "详情页不应出现列表/卡片切换 radio"
    # 详情是浏览态延伸：此时其它 Tab 必须正常渲染（子页面不得 st.stop() 截断脚本）
    assert len(at.tabs[5].radio) >= 1, "详情页下 Containers 页空白（st.stop 截断了脚本）"
    assert any(e2e_cont_name in str(getattr(m, "value", "")) for m in at.tabs[0].markdown), \
        "详情页容器行应显示所选容器"
    print("✅ 详情页渲染 0 异常，其它 Tab 正常，容器行显示所选容器")

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

    # ---- 2e. 卡片视图：首图按详情页缩略图规格渲染（HTML img + media 原图 URL，
    # 非 st.image 满列宽——竖图会被撑得过高）。置于 3b 后：E2E_ITEM_001 由 UI 创建
    # 无照片（AppTest 无法上传文件），须用 3b repo 层造的带图物品 E2E_IMG_A 驱动；
    # 本段在步骤 6 切英文之前，界面为中文 ----
    at.session_state["detail_item_id"] = None   # 退出详情回浏览态（步骤 3 注入的）
    at.sidebar.text_input(key="global_search").set_value("")      # 清残留筛选
    at.sidebar.text_input(key="global_tag_filter").set_value("")
    at.run()
    assert len(at.exception) == 0, at.exception
    at.sidebar.text_input(key="global_search").set_value("E2E_IMG_A")
    at.run()
    assert len(at.exception) == 0, at.exception
    at.tabs[0].radio[0].set_value("卡片")   # 中文界面 items.view_card
    at.run()
    assert len(at.exception) == 0, at.exception
    # 卡片视图分页档位（Phase 9）：[48, 96, 192, 384]，默认 96（4 列网格整行梯）
    ps_sel = [s for s in at.selectbox if str(getattr(s, "label", "")) == "每页数量"]
    assert ps_sel and ps_sel[0].value == 96, \
        f"卡片视图每页数量默认应为 96: {[s.value for s in ps_sel]}"
    assert any("<img src=" in str(getattr(m, "value", "")) and "/media/" in str(getattr(m, "value", ""))
               for m in at.tabs[0].markdown), "卡片视图首图未走 HTML img 原图 URL 渲染"
    print("✅ 卡片视图每页数量默认 96；首图按详情页规格渲染（HTML img 限高原图）")
    at.tabs[0].radio[0].set_value("列表")   # 恢复列表视图与 2c 的筛选状态
    at.sidebar.text_input(key="global_search").set_value("E2E测试物品")
    at.sidebar.text_input(key="global_tag_filter").set_value("端到端")
    at.run()
    assert len(at.exception) == 0, at.exception
    at.session_state["detail_item_id"] = item_id   # 回到步骤 3 注入的详情页状态
    at.run()
    assert len(at.exception) == 0, at.exception

    # ---- 4-fs. 最大化列表 → 编辑页：应临时退出全屏且开关保留（返回自动恢复）----
    # 回归背景：全屏 CSS(body.wh-list-fullscreen) 会把 stMain overflow:hidden，
    # 子页面沿用全屏态会导致编辑/详情页无法下滚、右上角残留「退出最大化」按钮。
    def fs_var_text(at_):
        return "\n".join(str(getattr(m, "value", "")) for m in at_.markdown)

    at.session_state["list_fullscreen"] = True   # 模拟用户在最大化列表中操作
    at.run()
    assert len(at.exception) == 0, at.exception

    # ---- 4. 详情页点"✏️ 编辑" → 编辑页渲染 ----
    btn = find_button(at, label_exact="✏️ 编辑")
    assert btn is not None, "详情页无编辑按钮"
    btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    edit_texts = [str(getattr(t, "value", "")) for t in at.text_input]
    assert any("E2E_ITEM_001" in v for v in edit_texts), "编辑表单未带出编号"
    assert len(at.tabs[0].radio) == 0, "编辑页不应出现列表/卡片切换 radio"
    assert len(at.tabs[5].radio) >= 1, "编辑页下 Containers 页空白（st.stop 截断了脚本）"
    # 全屏临时退出：编辑子页面注入变量 0（可滚动、退出按钮随 body class 隐藏），开关保留
    assert "--list-fullscreen:0" in fs_var_text(at), "编辑页应临时退出全屏（--list-fullscreen:0）"
    assert at.session_state["list_fullscreen"] is True, "编辑页不得清除最大化开关（返回列表需恢复）"
    print("✅ 编辑页渲染 0 异常，编号已带出，其它 Tab 同轮正常渲染")

    # ---- 4a-2. 编辑态图片即时添加入口（Phase 8）：上传框+按钮在表单外，
    #      不必点「更新物品」、不必退出编辑态即可加图/调顺序 ----
    add_ph = find_button(at, label_contains="添加图片")
    assert add_ph is not None, "编辑态缺「添加图片」按钮（图片应可即时生效）"
    assert any("拖入或点选图片" in str(getattr(c, "value", "")) for c in at.caption), \
        "编辑态图片区缺操作提示文案"
    # 未选文件就点 → 警告提示，且仍停留在编辑态（不退出、不报错）
    add_ph.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert any("请先选择要添加的图片" in str(getattr(w, "value", "")) for w in at.warning), \
        "未选图片点添加应给出提示"
    assert at.session_state["edit_item_id"] == item_id, "提示后应仍停留在编辑态"
    print("✅ 编辑态「添加图片」入口在表单外，未选文件有点击提示且不退出编辑态")

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
    # 编辑保存不丢失已填容器/日期（也不得悄悄改掉）
    meta2 = conn.execute("SELECT container_id, purchase_date FROM items WHERE id=?",
                         (item_id,)).fetchone()
    assert meta2 == (e2e_cont_id, "2024-01-15"), f"编辑保存后容器/日期应保持: {meta2}"
    print("✅ 编辑保存保持容器与日期")
    # 保存退出编辑态 → 回到列表浏览态，全屏自动恢复；随后还原开关避免影响后续分节
    assert "--list-fullscreen:1" in fs_var_text(at), "返回列表应自动恢复最大化（--list-fullscreen:1）"
    at.session_state["list_fullscreen"] = False
    at.run()
    print("✅ 全屏仅在列表浏览态生效：编辑/详情临时退出，返回列表自动恢复")

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
    # 详情页图片必须走 HTML <img>（src 指向原图媒体 URL）——若退回 st.image
    # 满宽 fallback，markdown 里不会有 <img 标签。注意 AppTest 环境 URL 前缀是
    # /mock/media/，真实运行时是 /media/，故只断言 <img src 与 /media/ 片段
    assert any("<img src=" in str(getattr(m, "value", "")) and "/media/" in str(getattr(m, "value", ""))
               for m in at.tabs[0].markdown), "详情页图片未走原图 URL 渲染"
    print("✅ 详情页图片指向原图媒体 URL（右键新标签打开为原始尺寸）")
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
    # 2e 卡片段切过视图：无 key radio 跨语言切换按旧 index 恢复，可能停在卡片态；
    # 且列表需非空才有未选中提示 → 先显式回列表视图并清空筛选再验证工具栏。
    if len(at.tabs[0].radio) == 1 and str(getattr(at.tabs[0].radio[0], "value", "")) != "List":
        at.tabs[0].radio[0].set_value("List")
        at.run()
        assert len(at.exception) == 0, at.exception
    at.sidebar.text_input(key="global_search").set_value("")
    at.sidebar.text_input(key="global_tag_filter").set_value("")
    at.run()
    assert len(at.exception) == 0, at.exception
    assert len(at.tabs[0].radio) == 1, "列表视图缺失（radio 不在）"
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
    # Phase 7 起「新增物品」不再是独立 Tab（收进物品 Tab），容器管理为最后一个 Tab（index 5）
    assert len(at.tabs) >= 6, f"tabs 数量: {len(at.tabs)}"
    cont_radio = at.tabs[5].radio(key="container_view_radio")
    assert cont_radio is not None, "容器视图切换 radio 不存在"
    # Phase 10 Step1：「Add Container」从底部工具栏移到浏览态控制行（与 Add Item 同位、
    # 水平居中），列表/卡片视图下都有入口；视图标签已折叠，仅留选项
    assert find_button(at.tabs[5], label_contains="Add Container") is not None, \
        "容器浏览态缺「Add Container」按钮（应位于控制行，与 Add Item 一致）"
    cont_radio.set_value("Cards")   # 英文界面下容器卡片视图
    at.run()
    assert len(at.exception) == 0, at.exception
    card_btn = find_button(at.tabs[5], label_contains="Open Details")
    assert card_btn is not None, "卡片视图未渲染打开详情按钮"
    print("✅ 容器卡片视图渲染 0 异常")

    # 点开第一个容器详情页
    card_btn.click()
    at.run()
    assert len(at.exception) == 0, at.exception
    assert at.session_state["container_detail_id"] is not None, "容器详情未打开"
    sub_headers = [str(getattr(h, "value", "")) for h in at.tabs[5].subheader]
    assert any("Container Details" in v for v in sub_headers), f"详情页标题缺失: {sub_headers}"
    print("✅ 容器详情页渲染 0 异常（照片管理已移至编辑表单）")
    # st.write 的文本在 AppTest 树中落点为 markdown 元素；详情页只读展示，
    # 不再渲染照片管理区。详情页 Edit → 编辑表单，表单外的既有照片管理区
    # （上移/下移/删除）仅编辑模式渲染。AppTest 元素树不支持 file_uploader
    # （也无法模拟上传），改用文案/按钮断言。
    writes = [str(getattr(m, "value", "")) for m in at.tabs[5].markdown]
    assert not any("Upload container photos" in v for v in writes), \
        f"详情页不应再有照片管理区: {writes}"
    # 用 repo 层造带 2 张图的容器驱动「编辑表单含照片管理区」断言
    conn_c = sqlite3.connect("warehouse.db")
    conn_c.execute("PRAGMA foreign_keys=ON")
    try:
        pre = [r[0] for r in conn_c.execute(
            "SELECT id FROM containers WHERE name='E2E_CTR_IMG'")]
        if pre:
            repo.delete_containers(conn_c, pre)
        cid_c = repo.add_container(conn_c, "E2E_CTR_IMG", None, "e2e", "",
                                   [types.SimpleNamespace(name="a.jpg", getbuffer=lambda: img_x),
                                    types.SimpleNamespace(name="b.jpg", getbuffer=lambda: img_x)])
        at.session_state["container_detail_id"] = cid_c
        at.run()
        assert len(at.exception) == 0, at.exception
        writes = [str(getattr(m, "value", "")) for m in at.tabs[5].markdown]
        assert any("Container Photos" in v for v in writes), f"详情画廊标题缺失: {writes}"
        assert not any("Upload container photos" in v for v in writes), \
            f"详情页不应再有照片管理区: {writes}"
        edit_btn2 = find_button(at.tabs[5], label_contains="Edit")
        assert edit_btn2 is not None, "容器详情页缺编辑按钮"
        edit_btn2.click()
        at.run()
        assert len(at.exception) == 0, at.exception
        subs = [str(getattr(h, "value", "")) for h in at.tabs[5].subheader]
        assert any("Edit Container" in v for v in subs), f"编辑表单未打开: {subs}"
        writes = [str(getattr(m, "value", "")) for m in at.tabs[5].markdown]
        assert any("Existing images" in v for v in writes), f"编辑表单缺既有照片管理区: {writes}"
        assert find_button(at.tabs[5], label_exact="⬆️ Up") is not None, "缺照片上移按钮"
        assert find_button(at.tabs[5], label_exact="🗑️ Delete") is not None, "缺照片删除按钮"
        # Phase 8：照片即时添加入口与物品编辑一致（表单外上传框+按钮，不必点 Update）
        add_ph_c = find_button(at.tabs[5], label_contains="Add Photos")
        assert add_ph_c is not None, "容器编辑态缺「Add Photos」按钮（照片应可即时生效）"
        add_ph_c.click()
        at.run()
        assert len(at.exception) == 0, at.exception
        assert any("select photos" in str(getattr(w, "value", "")).lower() for w in at.warning), \
            "容器未选照片点添加应给出提示"
        assert at.session_state["edit_container_id"] == cid_c, "提示后应仍停留在容器编辑态"
        print("✅ 容器编辑态「Add Photos」入口在表单外，未选文件有点击提示且不退出编辑态")
        # Phase 7：附注框（编辑表单内唯一 text_area，位于上级容器/位置之下）→ 更新
        # → 落库 + 详情页整行展示；更新后回到详情页（edit_container_id 已清空）
        note_ta = at.tabs[5].text_area[0]
        assert note_ta is not None, "容器编辑表单缺附注文本框"
        note_ta.set_value("e2e 附注：靠窗第二层")
        update_btn = find_button(at.tabs[5], label_contains="Update")
        assert update_btn is not None, "容器编辑表单缺更新按钮"
        update_btn.click()
        at.run()
        assert len(at.exception) == 0, at.exception
        assert conn_c.execute("SELECT note FROM containers WHERE id=?",
                              (cid_c,)).fetchone()[0] == "e2e 附注：靠窗第二层", "附注未落库"
        writes = [str(getattr(m, "value", "")) for m in at.tabs[5].markdown]
        assert any("e2e 附注：靠窗第二层" in v for v in writes), f"详情页未展示附注: {writes}"
        assert at.session_state["container_detail_id"] == cid_c, "附注保存后应回容器详情"
        print("✅ 容器附注：编辑表单录入 → 落库 → 详情页展示")
        # 重新进入编辑表单，附注值应带回（验证取消仍回详情）
        edit_btn3 = find_button(at.tabs[5], label_contains="Edit")
        assert edit_btn3 is not None, "容器详情页缺编辑按钮"
        edit_btn3.click()
        at.run()
        assert len(at.exception) == 0, at.exception
        assert str(at.tabs[5].text_area[0].value) == "e2e 附注：靠窗第二层", \
            "重进编辑表单附注未带回"
        cancel_btn = find_button(at.tabs[5], label_contains="Cancel")
        assert cancel_btn is not None, "容器编辑表单缺取消按钮"
        cancel_btn.click()
        at.run()
        assert len(at.exception) == 0, at.exception
        assert at.session_state["container_detail_id"] == cid_c, "取消后应回容器详情"
        print("✅ 容器照片管理位于编辑表单：详情页无管理区，编辑表单含上传/排序/删除；附注可录入/落库/展示/带回")
    finally:
        left = [r[0] for r in conn_c.execute(
            "SELECT id FROM containers WHERE name='E2E_CTR_IMG'")]
        if left:
            repo.delete_containers(conn_c, left)   # 连带删除照片文件与记录
        conn_c.close()

    # 恢复浏览状态
    at.session_state["container_detail_id"] = None
    at.session_state["container_view_mode"] = "list"
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
    tree_labels = [str(getattr(b, "label", "")) for b in at.tabs[4].button]
    tree_text = "\n".join(tree_labels)
    for top_name in top_names:
        assert top_name in tree_text, f"容器树未渲染顶层容器「{top_name}」: {tree_text[:200]}"
    assert "ITEM_" not in tree_text, "容器树不应平铺具体物品行"
    print(f"✅ 容器树仅渲染顶层容器（{', '.join(top_names)}）且不平铺物品（isna 修复防回归）")

    # 默认折叠：有父级的二级容器默认不显示，需展开/搜索才可见
    conn2_sub = sqlite3.connect("warehouse.db")
    sub_name = conn2_sub.execute(
        "SELECT name FROM containers WHERE parent_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0]
    conn2_sub.close()
    assert sub_name not in tree_text, f"默认应折叠，二级容器「{sub_name}」不应出现: {tree_text[:200]}"
    # 搜索自动展开祖先链：输入二级容器名 → 命中行及其祖先可见
    at.text_input(key="tree_search").set_value(sub_name)
    at.run()
    tree_labels2 = [str(getattr(b, "label", "")) for b in at.tabs[4].button]
    assert sub_name in "\n".join(tree_labels2), f"搜索后二级容器「{sub_name}」应自动展开可见"
    print(f"✅ 搜索「{sub_name}」自动展开祖先链并高亮命中节点")
    # 清空搜索恢复折叠态
    at.text_input(key="tree_search").set_value("")
    at.run()

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
    tree_labels_after = [str(getattr(b, "label", "")) for b in at.tabs[4].button]
    assert any(top_names[0] in v for v in tree_labels_after), "返回后容器树未重新渲染"
    print("✅ 容器树详情页返回按钮 → 回到树视图")

    # 恢复浏览状态
    at.session_state["container_detail_id"] = None
    at.session_state["container_view_mode"] = "list"
    at.run()
    assert len(at.exception) == 0, at.exception

    # 清理 e2e 自建的保底/测试容器（7 段的 E2E_CTR_IMG 已在其 finally 中删除）；
    # 容器须为空才可删（物品 E2E_ 已在第 5 段清理），避免外键 RESTRICT 中断
    conn_f = sqlite3.connect("warehouse.db")
    conn_f.execute("PRAGMA foreign_keys=ON")
    for cid_f in [r[0] for r in conn_f.execute("SELECT id FROM containers WHERE name LIKE 'E2E_%'")]:
        if conn_f.execute("SELECT COUNT(*) FROM items WHERE container_id=?",
                          (cid_f,)).fetchone()[0] == 0:
            repo.delete_containers(conn_f, [cid_f])
    conn_f.close()

    print("E2E RESULT: PASS")


if __name__ == "__main__":
    main()
