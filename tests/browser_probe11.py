# -*- coding: utf-8 -*-
"""验证全屏详情方案下，从树→item详情→返回 之后，打开容器详情不会被之前残留的
item 详情劫持（即打开的是 Container Details，而非旧的 item 详情）。

复现路径（与用户报告一致）：
  树(Tree)→点某容器「Detail」→ 在树详情里点某 item「Open Details」打开物品详情
  → 连续 Back 回树列表 → 打开另一个容器的详情 → 应当显示该容器的 Container Details，
  且不应再出现之前那件物品的 item_no（A2623）。

说明：本探针用「树里的容器 Detail」来打开容器详情（render_detail_readonly，与
容器 Tab 的卡片 Open Details 走同一套全屏 dispatch，且同样以 container_detail_id /
tree_detail_id 之外的只读渲染呈现）。容器 Tab 卡片视图的切换本身在浏览器自动化里
偶发不稳定（radio 不触发 onChange），其「容器详情 / 编辑 / 新增」三条路由已由
browser_probe13.py 完整覆盖（C1/C2/C3 均 PASS），故此处不再依赖该 radio。
"""
import subprocess, sys, time, os, signal, re, sqlite3
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


def main():
    proc = start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge", headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(URL, wait_until="load")

            # ---- 选测试数据 ----
            conn = sqlite3.connect(str(ROOT / "warehouse.db"))
            c1 = conn.execute(
                "SELECT c.id, c.name FROM containers c "
                "JOIN items i ON i.container_id=c.id "
                "GROUP BY c.id ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
            item_no = conn.execute(
                "SELECT item_no FROM items WHERE container_id=? LIMIT 1", (c1[0],)).fetchone()[0]
            conn.close()
            c1_name = c1[1]

            # ---- 树 Tab（index 4） ----
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click()
            pg.wait_for_timeout(1500)
            pg.get_by_role("button", name="⬇️ Expand all").click()
            pg.wait_for_timeout(1500)

            # ---- 树里点 C1 的 Detail → 树详情 ----
            r = pg.evaluate("""(nm)=>{
                const btn=[...document.querySelectorAll('button')].find(b=>b.textContent.includes(nm));
                if(!btn) return 'no-toggle';
                let row=btn.closest('[data-testid=\"stHorizontalBlock\"]');
                while(row){
                    const d=[...row.querySelectorAll('button')].find(b=>b.textContent.trim()==='Detail');
                    if(d){ d.click(); return 'ok'; }
                    row=row.parentElement && row.parentElement.closest('[data-testid=\"stHorizontalBlock\"]');
                }
                return 'no-detail';
            }""", c1_name)
            assert r == "ok", f"树中未找到 {c1_name} 的 Detail 按钮: {r}"
            pg.wait_for_timeout(2200)
            txt = visible_text(pg)
            print("树详情打开:", "Container Details" in txt, "| 含容器名:", c1_name in txt)

            # ---- 树详情里点某 item 的 Open Details → 物品详情 ----
            pg.locator("button:not([disabled])").filter(has_text="Open Details").first.click()
            pg.wait_for_timeout(2500)
            txt = visible_text(pg)
            print("物品详情打开:", item_no in txt, "| 含 item_no:", item_no)

            # ---- 连续 Back 回树列表 ----
            pg.get_by_text("🔙 Back").first.click()
            pg.wait_for_timeout(2000)
            pg.get_by_text("🔙 Back").first.click()
            pg.wait_for_timeout(2000)

            # ---- 打开「另一个容器」的详情（避开 C1，因其内含 A2623） ----
            # 确保位于树 Tab 并展开
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click()
            pg.wait_for_timeout(1500)
            pg.get_by_role("button", name="⬇️ Expand all").click()
            pg.wait_for_timeout(1500)
            clicked = pg.evaluate("""(c1)=>{
                const rows=[...document.querySelectorAll('[data-testid=\"stHorizontalBlock\"]')];
                for(const row of rows){
                    const t=row.querySelector('button');
                    const d=[...row.querySelectorAll('button')].find(b=>b.textContent.trim()==='Detail');
                    if(t && d && !t.textContent.includes(c1)){ d.click(); return true; }
                }
                return false;
            }""", c1_name)
            pg.wait_for_timeout(2500)
            txt = visible_text(pg)

            has_container = "Container Details" in txt
            no_hijack = item_no not in txt
            print("容器详情头条:", txt.replace("\n", " | ")[:160])
            print("含 Container Details:", has_container)
            print(f"未劫持(无旧 item_no {item_no}):", no_hijack)
            print("RESULT:", has_container and no_hijack)
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
