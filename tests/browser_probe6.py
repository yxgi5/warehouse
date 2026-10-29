"""复现 bug：树→item详情 → 切容器Tab → 列表选容器 → 查看详情 → 显示的是旧item详情。
打印：当前激活 Tab、可见 tabpanel 文本前 600 字符、是否含 item/container 特征。
"""
import subprocess, sys, time, os, signal, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8899
URL = f"http://localhost:{PORT}"
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
            urllib.request.urlopen(URL, timeout=2); return p
        except Exception:
            time.sleep(1)
    raise RuntimeError("streamlit 未就绪")


def dump_visible(page, tag):
    info = page.evaluate("""() => {
        const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
        let active = -1;
        tabs.forEach((t,i)=>{ if(t.getAttribute('aria-selected')==='true') active=i; });
        const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));
        let txt = '';
        panels.forEach(p=>{ if(!p.hasAttribute('hidden') && p.offsetParent!==null) txt = p.innerText.slice(0,600); });
        return {active, txt};
    }""")
    print(f"--- {tag} --- active_tab={info['active']}")
    print(info["txt"].replace("\n", " | ")[:600])
    return info


def main():
    proc = start_streamlit()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(URL, wait_until="load")

            # 1) 树 Tab（4），展开全部，找 C0020 行点 Detail
            page.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click()
            time.sleep(2.5)
            conn = sqlite3.connect(str(ROOT / "warehouse.db"))
            cname = conn.execute(
                "SELECT c.name FROM containers c WHERE c.id IN "
                "(SELECT container_id FROM items GROUP BY container_id ORDER BY COUNT(*) DESC LIMIT 1)").fetchone()[0]
            conn.close()
            page.get_by_role("button", name="Expand all").click()
            time.sleep(2)
            page.evaluate(f"""(""" + "cname" + """) => {
                const tgl = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes(cname));
                let rowEl = tgl.closest('[data-testid=\"stHorizontalBlock\"]');
                let vd=null;
                while(rowEl && !vd){ vd=Array.from(rowEl.querySelectorAll('button')).find(b=>b.textContent.includes('Detail'));
                  if(!vd) rowEl = rowEl.parentElement && rowEl.parentElement.closest('[data-testid=\"stHorizontalBlock\"]'); }
                vd.click();
            }""", cname)
            time.sleep(2.5)
            dump_visible(page, "树详情打开后")

            # 2) 点 item 的 Open Details
            page.evaluate("""() => { const b=Array.from(document.querySelectorAll('button')).find(x=>x.textContent.includes('📄 Open Details')); if(b)b.click(); }""")
            time.sleep(3)
            dump_visible(page, "item详情打开后")

            # 3) 切容器 Tab（5）
            page.locator('[data-testid="stTabs"] button[role="tab"]').nth(5).click()
            time.sleep(2.5)
            dump_visible(page, "切到容器Tab后")

            # 4) 选容器 + 查看详情
            page.wait_for_selector('.st-key-container_list_wrap [data-testid="stDataFrame"]', timeout=30000)
            box = page.locator('.st-key-container_list_wrap [data-testid="stDataFrame"]').first.bounding_box()
            page.mouse.click(box["x"] + 25, box["y"] + 35 + 35 * 3)
            time.sleep(1.5)
            # 只点「可见」的 Open Details（容器内有多处同名按钮，.first 可能命中隐藏的）
            page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'))
                    .filter(b => b.textContent.trim()==='Open Details' && b.offsetParent!==null);
                if (btns.length) btns[0].click();
            }""")
            time.sleep(3)
            try:
                dump_visible(page, "点容器查看详情后（BUG 现场）")
            except Exception as e:
                print("dump err", e)

            browser.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
