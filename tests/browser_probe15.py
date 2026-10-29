# -*- coding: utf-8 -*-
"""诊断：容器卡片流程之后，切到树 Tab，观察活动 Tab 何时被翻回 Items(idx=0)。

阶段 A：goto_tab(4) 后什么都不点，轮询 3s——是否自发翻回？
阶段 B：点 ⬇️ Expand all（触发 rerun）后轮询——rerun 是否翻回？
"""
import subprocess, sys, time, os, signal
from pathlib import Path

ROOT = Path(r"D:\repos\warehouse.git")
PORT = 8899
URL = f"http://localhost:{PORT}"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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
    raise RuntimeError("streamlit 未就绪")


def active_idx(pg):
    return pg.evaluate("""()=>{
        const btns=document.querySelectorAll('[data-baseweb="tab-list"] button');
        for(let i=0;i<btns.length;i++) if(btns[i].getAttribute('aria-selected')==='true') return i;
        return -1; }""")


def main():
    proc = start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge", headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(URL, wait_until="load")
            pg.wait_for_timeout(2500)

            # 复现 probe14 状态：容器卡片 → 详情 → Back
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(5).click()
            pg.wait_for_timeout(2000)
            panel = pg.locator('[role="tabpanel"]:visible')
            panel.get_by_text("Cards", exact=True).click()
            pg.wait_for_timeout(2500)
            pg.evaluate("""()=>{
                const ps=[...document.querySelectorAll('[role="tabpanel"]')]
                    .filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);
                const bs=[...(ps[0]||document).querySelectorAll('button')]
                    .filter(x=>!x.disabled && x.textContent.includes('Open Details'));
                if(bs.length>10) bs[10].click(); }""")
            pg.wait_for_timeout(3000)
            pg.get_by_text("🔙 Back").first.click()
            pg.wait_for_timeout(3500)
            print("Back后 active:", active_idx(pg), "(期望5)")

            # 阶段 A：切树 Tab，不点任何东西
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click()
            for t in (300, 800, 1500, 2500, 3500):
                pg.wait_for_timeout(t)
                print(f"A +{t}ms active:", active_idx(pg))

            # 阶段 B：点 Expand all（rerun）
            try:
                pg.get_by_role("button", name="⬇️ Expand all").click(timeout=5000)
                print("B Expand all 已点击")
            except Exception as e:
                print("B Expand all 失败:", type(e).__name__)
            for t in (300, 800, 1500, 2500, 4000):
                pg.wait_for_timeout(t)
                print(f"B +{t}ms active:", active_idx(pg))
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
