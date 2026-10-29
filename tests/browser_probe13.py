# -*- coding: utf-8 -*-
"""全屏子页面回归探针：验证各详情/编辑/新增子页面（渲染在 st.tabs 之外）均能正常打开与返回，无回归。

覆盖路由（容器测试前置，以复现 probe11 中可用的卡片视图切换前提）：
  C1 容器详情（卡片 Open Details）→ 打开
  C2 容器编辑（详情页 Edit）→ 打开；Cancel → 离开表单
  C3 容器新增（➕ Add Container）→ 打开；Cancel → 离开表单
  I1 物品详情（卡片 Open Details）→ 打开
  I2 物品编辑（详情页 Edit）→ 打开；Cancel → 离开表单
  I3 物品新增（📝 Add New Item）→ 打开；Cancel → 离开表单
  T1 树详情（Detail）→ 打开；Back → 回到树列表
"""
import subprocess, sys, time, os, signal
from pathlib import Path

ROOT = Path(r"D:\repos\warehouse.git")
PORT = 8899
URL = f"http://localhost:{PORT}"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def start():
    env = dict(os.environ, WH_SKIP_AUTO_BACKUP="1")
    p = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(PORT),
         "--browser.gatherUsageStats", "false"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    import urllib.request
    for _ in range(90):
        try:
            urllib.request.urlopen(URL, timeout=2)
            return p
        except Exception:
            time.sleep(1)
    raise RuntimeError("streamlit 未在 90s 内就绪")


def visible_text(page):
    return page.evaluate("""()=>{
        const ps=Array.from(document.querySelectorAll('[role="tabpanel"]'));
        for(const p of ps){ if(!p.hasAttribute('hidden') && p.offsetParent!==null) return p.innerText; }
        const m=document.querySelector('[data-testid="stMain"]');
        return m?m.innerText:'';
    }""")


def to_card(pg, tab_label):
    """切到当前可见 Tab 的卡片视图；验证出现卡片的 Open Details 按钮，失败则重试。

    必须用「真实点击」Cards 文本，触发 Streamlit React 的 onChange。
    先点 List 让原生 radio 与 Python 端重新对齐，再点 Cards 触发真正的变更。
    """
    panel = pg.locator('[role="tabpanel"]:visible')
    for _ in range(5):
        try:
            pg.get_by_label(tab_label).get_by_text("List", exact=True).click()
        except Exception:
            panel.get_by_text("List", exact=True).click()
        pg.wait_for_timeout(600)
        try:
            pg.get_by_label(tab_label).get_by_text("Cards", exact=True).click()
        except Exception:
            panel.get_by_text("Cards", exact=True).click()
        pg.wait_for_timeout(2200)
        btns = panel.locator("button:not([disabled])").filter(has_text="Open Details")
        if btns.count() > 0:
            return
    npanels = pg.locator('[role="tabpanel"]:visible').count()
    all_od = pg.locator("button").filter(has_text="Open Details").count()
    vis_txt = visible_text(pg)[:200]
    raise RuntimeError(f"{tab_label} 未能切换卡片视图; visible_panels={npanels} global_OpenDetails={all_od}; txt={vis_txt!r}")


def card_open_details(pg, idx=0):
    panel = pg.locator('[role="tabpanel"]:visible')
    btns = panel.locator("button:not([disabled])").filter(has_text="Open Details")
    btns.nth(idx).click()
    pg.wait_for_timeout(2500)


results = []
def check(name, cond, extra=""):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def ensure_browse(pg, entry_text, wait, tab_index=None):
    """确保处于某 Tab 的浏览态（可见 entry_text 按钮）。
    - 若仍在全屏详情/编辑态（无 entry 按钮但有 Back），点 Back 返回；
    - 若因 st.tabs 重置落在了别的 Tab（如详情返回后回到 Items），显式点回 tab_index。
    """
    for _ in range(3):
        txt = visible_text(pg)
        if entry_text in txt:
            break
        back = pg.get_by_text("🔙 Back")
        if back.count() > 0:
            back.first.click()
            wait(2000)
        else:
            break
    if tab_index is not None:
        pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(tab_index).click()
        wait(1500)
    return entry_text in visible_text(pg)


def main():
    proc = start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge", headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(URL, wait_until="load")
            wait = lambda s=1500: pg.wait_for_timeout(s)

            # ================= 容器（前置，复现卡片视图可用前提） =================
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(5).click(); wait()
            to_card(pg, "📦 Containers")
            card_open_details(pg)
            txt = visible_text(pg)
            check("C1 容器详情打开", "Container Details" in txt)

            pg.get_by_text("✏️ Edit").first.click(); wait(2500)
            txt = visible_text(pg)
            check("C2 容器编辑打开", "Edit Container" in txt)
            pg.get_by_text("❌ Cancel").first.click(); wait(2500)
            txt = visible_text(pg)
            check("C2 编辑Cancel离开表单", "Edit Container" not in txt)
            ensure_browse(pg, "Add Container", wait, tab_index=5)
            txt = visible_text(pg)
            check("C2 Cancel回浏览", "Add Container" in txt and "Edit Container" not in txt)

            pg.get_by_label("📦 Containers").get_by_text("➕ Add Container").click(); wait(2500)
            txt = visible_text(pg)
            check("C3 容器新增打开", "Add Container" in txt)
            pg.get_by_text("❌ Cancel").first.click(); wait(2500)
            txt = visible_text(pg)
            check("C3 新增Cancel离开表单", "Upload Images" not in txt)
            ensure_browse(pg, "Add Container", wait, tab_index=5)
            txt = visible_text(pg)
            check("C3 Cancel回浏览", "Add Container" in txt)

            # ================= 物品 =================
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(0).click(); wait()
            to_card(pg, "📦 Items")
            card_open_details(pg)
            txt = visible_text(pg)
            check("I1 物品详情打开", "📦" in txt and ("Open Details" in txt or "Edit" in txt) and "Add Item" not in txt,
                  "len=%d" % len(txt))

            pg.get_by_text("✏️ Edit").first.click(); wait(2500)
            txt = visible_text(pg)
            check("I2 物品编辑打开", "Edit Item" in txt)
            pg.get_by_text("❌ Cancel").first.click(); wait(2500)
            txt = visible_text(pg)
            check("I2 编辑Cancel离开表单", "Edit Item" not in txt)
            ensure_browse(pg, "Add Item", wait, tab_index=0)
            txt = visible_text(pg)
            check("I2 Cancel回浏览", "Add Item" in txt and "Edit Item" not in txt)

            pg.get_by_label("📦 Items").get_by_text("➕ Add Item").click(); wait(2500)
            txt = visible_text(pg)
            check("I3 物品新增打开", "Add New Item" in txt)
            pg.get_by_text("❌ Cancel").first.click(); wait(2500)
            txt = visible_text(pg)
            check("I3 新增Cancel离开表单", "Add New Item" not in txt)
            ensure_browse(pg, "Add Item", wait, tab_index=0)
            txt = visible_text(pg)
            check("I3 Cancel回浏览", "Add Item" in txt)

            # ================= 树 =================
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); wait()
            pg.get_by_role("button", name="⬇️ Expand all").click(); wait(1500)
            # 树里部分 Detail 按钮在折叠节点内（Playwright 判定不可见），用 JS 点第一个可见的
            clicked = pg.evaluate("""()=>{
                const btns=[...document.querySelectorAll('button')]
                    .filter(b=>b.textContent.includes('Detail') && b.offsetParent!==null);
                if(btns.length){ btns[0].click(); return btns.length; }
                return 0;
            }""")
            wait(2500)
            txt = visible_text(pg)
            check("T1 树详情打开", "Container Details" in txt, f"detailBtns={clicked}")
            pg.get_by_text("🔙 Back").first.click(); wait(2500)
            txt = visible_text(pg)
            check("T1 Back回树列表", "Container Details" not in txt and ("Expand all" in txt or "Container Tree" in txt))

            passed = sum(1 for _, c in results if c)
            print(f"\nSUMMARY: {passed}/{len(results)} passed")
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
