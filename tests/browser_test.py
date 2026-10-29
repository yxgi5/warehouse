"""浏览器实测（Edge）：位置记忆六大场景真机验证。

用法:  python tests/browser_test.py
依赖:  playwright（pip install playwright），用系统 Edge（channel=msedge），不下载浏览器。
跳过自动备份：WH_SKIP_AUTO_BACKUP=1（否则 1.9GB photos 打包卡死首屏）。

场景 A  物品列表滚动还原：滚到 2500 → 详情 → Back → 回 2500
场景 A2 列表选中刷新保位：滚到 1500 → 选中某行（触发 on_select rerun）→ 仍 1500
场景 A3 切 Tab 丢弃记忆：列表滚到 1500 → 切到别的 Tab 再切回 → 回顶部（点 6）
场景 E  详情页置顶：容器详情滚到底 → 点开 item → 详情页 window.scrollY≈0（点 3）
场景 B  容器/树详情锚点：树详情点 item → Back → 锚点行在视口（既有）
场景 C  容器管理列表还原：容器列表滚到 2000 → 开详情 → Back → 回 2000（点 5）
场景 D  卡片视图还原：切卡片 → 翻到第 2 页 → 开卡片详情 → Back → 回第 2 页且锚点在视口（点 5）
"""
import subprocess, sys, time, os, signal, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8899
URL = f"http://localhost:{PORT}"
LIST_SEL = '.st-key-item_list_wrap [data-testid="stDataFrame"]'
CONT_LIST_SEL = '.st-key-container_list_wrap [data-testid="stDataFrame"]'
TOL = 150


def start_streamlit():
    env = dict(os.environ, WH_SKIP_AUTO_BACKUP="1")
    p = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(PORT),
         "--browser.gatherUsageStats", "false"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(URL, timeout=2)
            return p
        except Exception:
            time.sleep(1)
    raise RuntimeError("streamlit 未在 60s 内就绪")


def wait_df(sel, timeout=30000):
    pass


def get_scroller(page, sel=LIST_SEL):
    return page.evaluate("(sel) => {const df=document.querySelector(sel);"
                         "const g=df&&df.querySelector('.dvn-scroller');"
                         "return g?{top:g.scrollTop,max:g.scrollHeight-g.clientHeight}:null;}",
                         sel)


def test_list_scroll(page):
    page.wait_for_selector(LIST_SEL, timeout=30000)
    time.sleep(2)
    box = page.locator(LIST_SEL).first.bounding_box()
    page.evaluate("(sel)=>{const g=document.querySelector(sel+' .dvn-scroller');g.scrollTop=2500;}", LIST_SEL)
    time.sleep(0.6)
    got = int(page.evaluate("()=>window.localStorage.getItem('wh_items_list_scroll')") or -1)
    assert abs(got - 2500) < TOL, f"[A] 捕获失败: {got}"
    print(f"[A1] 捕获成功: localStorage={got}")
    page.mouse.click(box["x"] + 25, box["y"] + 35 + 35 * 3)
    time.sleep(1.5)
    # 列表工具栏的「查看详情」按钮是 items.view_detail（en: "View Details"），
    # 而卡片/容器条目里的「📄 Open Details」是 items.open_detail —— 二者不同，勿混
    page.get_by_text("View Details").first.click()
    time.sleep(2.5)
    assert page.get_by_text("🔙 Back").count() > 0
    print("[A2] 已进入详情页")
    page.get_by_text("🔙 Back").first.click()
    time.sleep(3)
    st = get_scroller(page)
    assert st and abs(st["top"] - 2500) < TOL, f"[A] 还原失败: {st}"
    print(f"[A3] 还原成功: scrollTop={st['top']}")


def test_list_stays_on_select(page):
    page.wait_for_selector(LIST_SEL, timeout=30000)
    time.sleep(1)
    box = page.locator(LIST_SEL).first.bounding_box()
    page.evaluate("(sel)=>{const g=document.querySelector(sel+' .dvn-scroller');g.scrollTop=1500;}", LIST_SEL)
    time.sleep(0.6)
    # 选中某行触发 on_select rerun（组件重挂载会跳顶，应被还原）
    page.mouse.click(box["x"] + 25, box["y"] + 35 + 35 * 5)
    time.sleep(2)
    st = get_scroller(page)
    assert st and abs(st["top"] - 1500) < TOL, f"[A2] 选中后未保位: {st}"
    print(f"[A2] 选中刷新后仍停原位: scrollTop={st['top']}")


def test_tab_switch_clears(page):
    # 列表滚到 1500，切到 Dashboard 再切回 → 应回顶部（点 6）
    page.evaluate("(sel)=>{const g=document.querySelector(sel+' .dvn-scroller');g.scrollTop=1500;}", LIST_SEL)
    time.sleep(0.6)
    page.locator('[data-testid="stTabs"] button[role="tab"]').nth(1).click()
    time.sleep(2)
    page.locator('[data-testid="stTabs"] button[role="tab"]').nth(0).click()
    time.sleep(2.5)
    st = get_scroller(page)
    assert st and st["top"] < 50, f"[A3] 切 Tab 未清记忆: {st}"
    print(f"[A3] 切 Tab 丢弃记忆成功: scrollTop={st['top']}")


def test_detail_at_top(page):
    # 容器详情滚到底 → 点开 item → 详情页应置顶（点 3）
    page.locator('[data-testid="stTabs"] button[role="tab"]').nth(5).click()
    time.sleep(2.5)
    # 找一个物品最多的容器并打开
    conn = sqlite3.connect(str(ROOT / "warehouse.db"))
    cname = conn.execute("SELECT c.name FROM containers c WHERE c.id IN "
                         "(SELECT container_id FROM items GROUP BY container_id ORDER BY COUNT(*) DESC LIMIT 1)").fetchone()[0]
    conn.close()
    page.get_by_text(cname).first.click()
    time.sleep(2.5)
    # 容器详情滚到底
    page.evaluate("()=>window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(0.5)
    # 点开第一行 item 的 Open Details
    page.evaluate("""()=>{const b=Array.from(document.querySelectorAll('button')).find(x=>x.textContent.includes('📄 Open Details'));if(b)b.click();}""")
    time.sleep(3)
    assert page.get_by_text("🔙 Back").count() > 0
    y = page.evaluate("()=>window.scrollY")
    assert y < 120, f"[E] 详情页未置顶: scrollY={y}"
    print(f"[E] 详情页进入置顶成功: scrollY={y}")
    # 返回容器详情，避免脏状态
    page.get_by_text("🔙 Back").first.click()
    time.sleep(3)


def test_container_anchor(page, item_id):
    page.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click()
    time.sleep(2.5)
    page.get_by_role("button", name="Expand all").click()
    time.sleep(2)
    page.evaluate("""(cname)=>{const tgl=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes(cname));
        let row=tgl.closest('[data-testid=\"stHorizontalBlock\"]');let vd=null;
        while(row&&!vd){vd=Array.from(row.querySelectorAll('button')).find(b=>b.textContent.includes('Detail'));
        if(!vd)row=row.parentElement&&row.parentElement.closest('[data-testid=\"stHorizontalBlock\"]');}
        if(vd)vd.click();}""", cname)
    time.sleep(2.5)
    anchor = f"cont-item-{item_id}"
    page.evaluate(f"""()=>{{const el=document.getElementById('{anchor}');if(el)el.scrollIntoView({{block:'center'}});}}""")
    time.sleep(1.5)
    page.evaluate(f"""()=>{{const el=document.getElementById('{anchor}');
        if(!el)throw new Error('锚点缺失');const row=el.closest('[data-testid=\"stHorizontalBlock\"]');
        const btn=row&&row.querySelector('button');if(btn)btn.click();}}""")
    time.sleep(3)
    assert page.get_by_text("🔙 Back").count() > 0
    print("[B2] 已打开物品详情")
    page.get_by_text("🔙 Back").first.click()
    time.sleep(4)
    vis = page.evaluate(f"""()=>{{const el=document.getElementById('{anchor}');if(!el)return{{found:false}};
        const r=el.getBoundingClientRect();return{{found:true,top:r.top,inView:r.top>=0&&r.top<=window.innerHeight}};}}""")
    assert vis.get("found") and vis["inView"], f"[B] 锚点未归位: {vis}"
    print(f"[B3] 锚点定位成功: top={vis['top']:.0f}px")


def test_container_list_restore(page):
    # 容器管理列表滚到 2000 → 开详情 → Back → 回 2000（点 5）
    page.locator('[data-testid="stTabs"] button[role="tab"]').nth(5).click()
    time.sleep(2.5)
    page.wait_for_selector(CONT_LIST_SEL, timeout=30000)
    time.sleep(1)
    box = page.locator(CONT_LIST_SEL).first.bounding_box()
    page.evaluate("(sel)=>{const g=document.querySelector(sel+' .dvn-scroller');g.scrollTop=2000;}", CONT_LIST_SEL)
    time.sleep(0.6)
    got = int(page.evaluate("()=>window.localStorage.getItem('wh_containers_list_scroll')") or -1)
    assert abs(got - 2000) < TOL, f"[C] 捕获失败: {got}"
    print(f"[C1] 容器列表捕获成功: {got}")
    # 选中一行再开详情
    page.mouse.click(box["x"] + 25, box["y"] + 35 + 35 * 3)
    time.sleep(1.5)
    page.get_by_text("Open Details").first.click()
    time.sleep(2.5)
    assert page.get_by_text("🔙 Back").count() > 0
    print("[C2] 已进入容器详情")
    page.get_by_text("🔙 Back").first.click()
    time.sleep(3)
    st = get_scroller(page, CONT_LIST_SEL)
    assert st and abs(st["top"] - 2000) < TOL, f"[C] 还原失败: {st}"
    print(f"[C3] 容器列表还原成功: scrollTop={st['top']}")


def test_card_restore(page):
    # 切卡片 → 第 2 页 → 开卡片详情 → Back → 回第 2 页且锚点在视口（点 5）
    page.locator('[data-testid="stTabs"] button[role="tab"]').nth(0).click()
    time.sleep(2)
    page.get_by_role("radio").nth(1).click()   # Cards
    time.sleep(2)
    page.get_by_text("Next ➡️").first.click()
    time.sleep(2)
    # 记录当前页首卡 id
    cid = page.evaluate("""()=>{const el=document.querySelector('[id^=\"card-item-\"]');return el?el.id:null;}""")
    assert cid, "[D] 未找到卡片锚点"
    print(f"[D1] 卡片页首卡: {cid}")
    page.evaluate("""()=>{const b=Array.from(document.querySelectorAll('button')).find(x=>x.textContent.includes('📄 Open Details'));if(b)b.click();}""")
    time.sleep(2.5)
    assert page.get_by_text("🔙 Back").count() > 0
    print("[D2] 已进入卡片详情")
    page.get_by_text("🔙 Back").first.click()
    time.sleep(3)
    # 验证仍处卡片视图且回到第 2 页、锚点在视口
    is_card = page.get_by_role("radio").nth(1).is_checked()
    vis = page.evaluate("""(cid)=>{const el=document.getElementById(cid);if(!el)return{found:false};
        const r=el.getBoundingClientRect();return{found:true,top:r.top,inView:r.top>=0&&r.top<=window.innerHeight};}""", cid)
    assert is_card, "[D] 返回后未处于卡片视图"
    assert vis.get("found") and vis["inView"], f"[D] 卡片未回原位: {vis}"
    print(f"[D3] 卡片还原成功: 卡片视图 + 锚点 top={vis['top']:.0f}px")


def main():
    proc = start_streamlit()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(URL, wait_until="load")
            test_list_scroll(page)
            test_list_stays_on_select(page)
            test_tab_switch_clears(page)
            test_detail_at_top(page)
            conn = sqlite3.connect(str(ROOT / "warehouse.db"))
            item_id = conn.execute(
                "SELECT id FROM items WHERE container_id = ("
                "  SELECT container_id FROM items GROUP BY container_id ORDER BY COUNT(*) DESC LIMIT 1"
                ") ORDER BY id DESC LIMIT 1").fetchone()[0]
            conn.close()
            test_container_anchor(page, item_id)
            test_container_list_restore(page)
            test_card_restore(page)
            browser.close()
        print("BROWSER TEST: PASS")
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
