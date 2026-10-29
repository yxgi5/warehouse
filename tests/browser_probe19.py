# -*- coding: utf-8 -*-
"""容器树打开的容器详情应带 编辑/删除 按钮，并与容器管理 Tab 入口一致。

运行：python tests/browser_probe19.py
"""
import subprocess, sys, time, os, signal, re
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


def btn_info(pg):
    return pg.evaluate("""()=>{const bs=[...document.querySelectorAll('button')].map(b=>b.textContent.trim());return {n:bs.length, edit:bs.some(t=>t.includes('编辑')||/edit/i.test(t)), del:bs.some(t=>t.includes('删除')||/delete/i.test(t)), back:bs.some(t=>t.includes('返回')||/back/i.test(t))};}""")


def click_btn(pg, pat):
    pg.evaluate("""(pat)=>{const re=new RegExp(pat,'i');const b=[...document.querySelectorAll('button')].find(x=>!x.disabled&&re.test(x.textContent));if(b)b.click();}""", pat)


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
            pg.get_by_role("button", name=re.compile(r"展开|Expand all")).click(); wait(1500)
            # 点第一个容器「详情」(tree_btn)
            pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('详情')||/detail/i.test(x.textContent)));if(b)b.click();}""")
            wait(1500)
            info = btn_info(pg)
            check("树详情含编辑按钮", info["edit"], str(info))
            check("树详情含删除按钮", info["del"], str(info))
            check("树详情含返回按钮", info["back"], str(info))

            # 点 编辑 → 进入编辑表单
            click_btn(pg, "编辑|edit"); wait(1500)
            form = pg.evaluate("""()=>{const t=document.body.innerText;return /更新|Update|编辑容器|Edit Container/.test(t);}""")
            check("树详情点编辑进入编辑表单", form)
            # 点 取消 → 回到树详情（编辑/删除仍在）
            click_btn(pg, "取消|cancel"); wait(1500)
            info2 = btn_info(pg)
            check("取消后回到树详情(编辑仍在)", info2["edit"] and info2["del"], str(info2))

            # 点 返回 → 回到树 Tab
            click_btn(pg, "返回|back"); wait(1800)
            on_tree = pg.evaluate("""()=>{const b=document.querySelectorAll('[data-baseweb=\"tab-list\"] button');for(const x of b){if(x.getAttribute('aria-selected')==='true')return x.textContent;}return '';}""")
            check("返回后停在树Tab", ('树' in on_tree) or ('Tree' in on_tree), f"active={on_tree}")

            passed = sum(1 for _, c in results if c)
            print(f"\nSUMMARY: {passed}/{len(results)} passed")
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
