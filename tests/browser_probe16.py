# -*- coding: utf-8 -*-
"""滚动稳定性探针：验证置顶/还原改成"短窗(700ms)+用户滚动即释放"后不再闪/弹回/晚跳。

复现用户场景：树 → 容器详情(底部) → 点 item 进 item 详情 → 返回容器详情。
全程采样 stMain.scrollTop 时间序列，捕捉"闪/弹回/晚跳"。

运行：python tests/browser_probe16.py
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
    p = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.headless", "true", "--server.port", str(PORT),
        "--browser.gatherUsageStats", "false"], cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    import urllib.request
    for _ in range(90):
        try:
            urllib.request.urlopen(URL, timeout=2); return p
        except Exception:
            time.sleep(1)
    raise RuntimeError("streamlit 未就绪")


def scroll_sample(pg):
    return pg.evaluate("""()=>{const m=document.querySelector('section[data-testid="stMain"]')||document.querySelector('[data-testid="stMain"]');return m?m.scrollTop:-1;}""")


results = []
def check(name, cond, extra=""):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def sample_series(pg, offsets):
    series, t0 = [], time.time()
    for off in offsets:
        while (time.time() - t0) * 1000 < off:
            time.sleep(0.02)
        series.append(scroll_sample(pg))
    return series


def main():
    proc = start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge", headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(URL, wait_until="load")
            wait = lambda s=1500: pg.wait_for_timeout(s)

            # ---- 树 → 容器详情（先滚到详情页底部，模拟"在底部进入 item 详情"前态）----
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); wait(1800)
            pg.get_by_role("button", name="⬇️ Expand all").click(); wait(1500)
            pg.evaluate("""()=>{const btns=[...document.querySelectorAll('button')].filter(b=>b.textContent.includes('Detail')&&b.offsetParent!==null);if(btns.length)btns[0].click();}""")
            wait(2500)
            # 容器详情页滚到底（模拟"在底部"）
            pg.evaluate("""()=>{const m=document.querySelector('section[data-testid="stMain"]');if(m)m.scrollTop=m.scrollHeight;}""")
            wait(400)
            ser = sample_series(pg, [300, 700, 1100, 1600, 2600, 3600])
            check("C-detail 置顶稳定(进入即顶)", all(s <= 5 for s in ser), f"series={ser}")

            # ---- 容器详情底部 → 点 item 进 item 详情 ----
            pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&x.textContent.includes('Open Details'));if(b)b.click();}""")
            wait(300)
            ser = sample_series(pg, [300, 700, 1100, 1600, 2600, 3600])
            check("I-detail 置顶稳定(底部进入)", all(s <= 5 for s in ser), f"series={ser}")

            # ---- 返回容器详情 ----
            pg.get_by_text("🔙 Back").first.click(); wait(300)
            ser = sample_series(pg, [300, 700, 1100, 1600, 2600, 3600])
            check("返回C-detail 无晚跳/闪烁", all(s <= 5 for s in ser), f"series={ser}")

            passed = sum(1 for _, c in results if c)
            print(f"\nSUMMARY: {passed}/{len(results)} passed")
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
