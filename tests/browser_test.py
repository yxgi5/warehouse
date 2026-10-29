"""浏览器实测（Edge）：物品列表滚动还原 + 容器详情锚点定位。

用法:  python tests/browser_test.py
依赖:  playwright（pip install playwright），用系统 Edge（channel=msedge），不下载浏览器。
跳过自动备份：WH_SKIP_AUTO_BACKUP=1（否则 1.9GB photos 打包卡住首屏）。

场景 A（列表滚动还原）：
  1. 打开物品列表，把 .dvn-scroller（dataframe 真实滚动容器）滚到 2500px；
  2. 等 500ms 后读 localStorage['wh_items_list_scroll']，应≈2500（捕获成功）；
  3. 点击可见行选中 → 「View Details」→ 详情页 → 「Back」；
  4. 回列表后 .dvn-scroller.scrollTop 应≈2500（还原成功）。

场景 B（容器详情锚点定位）：
  1. 切到 Containers Tab，打开物品数最多的容器详情；
  2. 滚动页面让靠后的某件物品可见，点其「Open Details」；
  3. 物品详情页点「Back」→ 应回到该容器详情，且对应锚点行在视口内。
"""
import subprocess, sys, time, os, signal, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8899
URL = f"http://localhost:{PORT}"
SCROLL_Y = 2500
TOL = 120          # 滚动还原允许误差（glide 网格按行对齐）
KEY = "wh_items_list_scroll"
LIST_SEL = '.st-key-item_list_wrap [data-testid="stDataFrame"]'


def start_streamlit():
    env = dict(os.environ, WH_SKIP_AUTO_BACKUP="1")
    p = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(PORT),
         "--browser.gatherUsageStats", "false"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(60):
        try:
            import urllib.request
            urllib.request.urlopen(URL, timeout=2)
            return p
        except Exception:
            time.sleep(1)
    raise RuntimeError("streamlit 未在 60s 内就绪")


def get_scroller(page):
    return page.evaluate("""(sel) => {
        const df = document.querySelector(sel);
        const g = df && df.querySelector('.dvn-scroller');
        return g ? {top: g.scrollTop, max: g.scrollHeight - g.clientHeight} : null;
    }""", LIST_SEL)


def test_list_scroll(page):
    """场景 A：捕获 + 全流程还原。"""
    page.wait_for_selector(LIST_SEL, timeout=30000)
    time.sleep(2)
    box = page.locator(LIST_SEL).first.bounding_box()
    # 1) 滚动网格
    page.evaluate(f"""(sel) => {{
        const g = document.querySelector(sel + ' .dvn-scroller');
        g.scrollTop = {SCROLL_Y};
    }}""", LIST_SEL)
    time.sleep(0.6)
    stored = page.evaluate(f"() => window.localStorage.getItem('{KEY}')")
    got = int(stored) if stored else -1
    assert abs(got - SCROLL_Y) < TOL, f"捕获失败: localStorage={stored}"
    print(f"[A1] 捕获成功: localStorage={got}")

    # 2) 点击可见行的复选框列选中（实测：复选框列 x+25 有效，数据格点击不选中）
    page.mouse.click(box["x"] + 25, box["y"] + 35 + 35 * 3)
    time.sleep(1.5)
    # 3) View Details
    page.get_by_text("View Details").first.click()
    time.sleep(2.5)
    assert page.get_by_text("Back").count() > 0, "未进入详情页"
    print("[A2] 已进入详情页")
    # 4) Back
    page.get_by_text("Back").first.click()
    time.sleep(3)
    st = get_scroller(page)
    assert st is not None, "返回后 dataframe 不存在"
    assert abs(st["top"] - SCROLL_Y) < TOL, f"还原失败: scrollTop={st['top']} 期望≈{SCROLL_Y}"
    print(f"[A3] 还原成功: scrollTop={st['top']}")


def test_container_anchor(page, item_id):
    """场景 B：树详情 → item → Back 锚点回位。"""
    page.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click()
    time.sleep(2.5)
    conn = sqlite3.connect(str(ROOT / "warehouse.db"))
    row = conn.execute(
        "SELECT c.name FROM containers c WHERE c.id IN "
        "(SELECT container_id FROM items GROUP BY container_id ORDER BY COUNT(*) DESC LIMIT 1)"
    ).fetchone()
    conn.close()
    cname = row[0]
    print(f"[B1] 打开容器: {cname}")
    # 二级容器默认折叠：先「Expand all」再找目标容器行
    page.get_by_role("button", name="Expand all").click()
    time.sleep(2)
    # 树行：toggle 按钮（label 含容器名）+ 同行 View Detail 按钮
    page.evaluate(f"""(cname) => {{
        const tgl = Array.from(document.querySelectorAll('button'))
            .find(b => b.textContent.includes(cname));
        if (!tgl) throw new Error('树中未找到容器 ' + cname);
        // 树行是嵌套 columns：向上找到同时含 toggle 与 Detail 按钮的行块
        let rowEl = tgl.closest('[data-testid="stHorizontalBlock"]');
        let vd = null;
        while (rowEl && !vd) {{
            vd = Array.from(rowEl.querySelectorAll('button'))
                .find(b => b.textContent.includes('Detail'));
            if (!vd) rowEl = rowEl.parentElement &&
                rowEl.parentElement.closest('[data-testid="stHorizontalBlock"]');
        }}
        if (!vd) throw new Error('行内无 Detail 按钮');
        vd.click();
    }}""", cname)
    time.sleep(2.5)
    anchor = f"cont-item-{item_id}"
    page.evaluate(f"""() => {{
        const el = document.getElementById('{anchor}');
        if (el) el.scrollIntoView({{block: 'center'}});
    }}""")
    time.sleep(1.5)
    page.evaluate(f"""() => {{
        const el = document.getElementById('{anchor}');
        if (!el) throw new Error('锚点缺失 {anchor}');
        const rowEl = el.closest('[data-testid="stHorizontalBlock"]');
        const btn = rowEl && rowEl.querySelector('button');
        if (btn) btn.click(); else throw new Error('行内无按钮');
    }}""")
    time.sleep(3)
    assert page.get_by_text("Back").count() > 0, "未跳到物品详情页"
    print("[B2] 已打开物品详情")
    page.get_by_text("Back").first.click()
    time.sleep(4)
    vis = page.evaluate(f"""() => {{
        const el = document.getElementById('{anchor}');
        if (!el) return {{found: false}};
        const r = el.getBoundingClientRect();
        return {{found: true, top: r.top,
                 inView: r.top >= 0 && r.top <= window.innerHeight}};
    }}""")
    assert vis.get("found"), "返回后锚点元素不存在"
    assert vis["inView"], f"锚点未滚回视口: top={vis['top']}"
    print(f"[B3] 锚点定位成功: top={vis['top']:.0f}px 在视口内")


def main():
    proc = start_streamlit()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(URL, wait_until="load")
            test_list_scroll(page)
            conn = sqlite3.connect(str(ROOT / "warehouse.db"))
            row = conn.execute(
                "SELECT id FROM items WHERE container_id = ("
                "  SELECT container_id FROM items GROUP BY container_id "
                "  ORDER BY COUNT(*) DESC LIMIT 1"
                ") ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()
            test_container_anchor(page, row[0])
            browser.close()
        print("BROWSER TEST: PASS")
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
