# -*- coding: utf-8 -*-
"""树视图滚动还原探针：展开多层→滚动到底部→进详情→返回，应回到原位置而非顶部。

运行：python tests/browser_probe17.py
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


def stmain(pg):
    return pg.evaluate("""()=>{const m=document.querySelector('section[data-testid="stMain"]')||document.querySelector('[data-testid="stMain"]');return m?m.scrollTop:-1;}""")


results = []
def check(name, cond, extra=""):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def main():
    proc = start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge", headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(URL, wait_until="load")
            wait = lambda s=1500: pg.wait_for_timeout(s)

            # 树 Tab
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); wait(1800)
            # 全部展开 → 树变高（语言无关：中/英正则）
            pg.get_by_role("button", name=__import__("re").compile(r"展开|Expand all")).click(); wait(1500)
            # 滚到底部，记住位置
            pg.evaluate("""()=>{const m=document.querySelector('section[data-testid="stMain"]');if(m)m.scrollTop=m.scrollHeight;}""")
            wait(500)
            y_before = stmain(pg)
            check("树已滚到底部", y_before > 50, f"y_before={y_before}")

            # 进详情：点第一个可见的「详情/Detail」按钮（语言无关）
            clicked = pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('详情')||/detail/i.test(x.textContent)));if(b){b.click();return 1;}return 0;}""")
            wait(2500)
            txt = pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);for(const p of ps)return p.innerText;return document.body.innerText;}""")
            check("树详情已打开", ("Back" in txt) or ("返回" in txt), f"clicked={clicked}")

            # 返回（语言无关：🔙 返回 / 🔙 Back）
            pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('返回')||/back/i.test(x.textContent)));if(b)b.click();}""")
            wait(2500)
            y_after = stmain(pg)
            # 等待还原窗口(700ms)后稳定再读一次
            wait(1200)
            y_after2 = stmain(pg)
            check("返回后还原树位置(非顶部)", y_after > 50 and y_after2 > 50,
                  f"y_after={y_after}, y_after2={y_after2}, y_before={y_before}")
            # 误差范围：允许抖动
            check("还原偏差小", abs(y_after2 - y_before) < 120,
                  f"diff={abs(y_after2 - y_before)}")

            passed = sum(1 for _, c in results if c)
            print(f"\nSUMMARY: {passed}/{len(results)} passed")
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
