# -*- coding: utf-8 -*-
"""进入详情页后立即下滚不应被反复拽回顶部（用户反馈的"有点闪"）。

对三条路径：树→容器详情、容器详情→item详情、item列表(卡片)→item详情，
在置顶强制窗口(~700ms)内模拟用户立即下滚(wheel事件 + 直接设 scrollTop)，
断言：窗口结束后滚动位置仍保留(>0)，而非被拽回 0。

运行：python tests/browser_probe18.py
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


def stmain(pg):
    return pg.evaluate("""()=>{const m=document.querySelector('section[data-testid="stMain"]')||document.querySelector('[data-testid="stMain"]');return m?{top:m.scrollTop,sh:m.scrollHeight,ch:m.clientHeight}:null;}""")


results = []
def check(name, cond, extra=""):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def scroll_sim(pg):
    """模拟用户立即下滚：wheel 事件 + 直接设 scrollTop（二者都触发释放逻辑）。"""
    return pg.evaluate("""()=>{const m=document.querySelector('section[data-testid="stMain"]')||document.querySelector('[data-testid="stMain"]');if(!m)return false;const max=m.scrollHeight-m.clientHeight;if(max<=0)return false;m.dispatchEvent(new WheelEvent('wheel',{deltaY:600,bubbles:true,cancelable:true}));m.scrollTop=Math.min(400,max);return true;}""")


def chk(name, sc, s):
    """sc=scroll_sim 返回值(是否真的滚动了)；s=测量时刻 stMain 状态。
    不可滚动页面无闪烁可能 → 按 N/A 通过；可滚动则要求位置被保留(>0)。"""
    if s is None:
        check(name, False, "stMain 未取到"); return
    if s["sh"] - s["ch"] <= 0:
        check(name, True, "页面不可滚动(无闪烁可能, N/A)"); return
    check(name, (sc is not False) and s["top"] > 0, f"scrollable, stMain={s}")


def enter_and_test(pg, click_js, label):
    """点击某按钮进入详情页，等详情页真正出现(Back 可见)后，在置顶强制窗内立即下滚，
    跨过 700ms 窗口后测量：位置应保留(>0)而非被拽回 0。返回到来源由调用方负责。"""
    pg.evaluate(click_js)
    # 等详情页渲染完成（Back 文本出现），再滚动，确保滚动落在详情页自身（而非旧页面）
    try:
        pg.get_by_text("🔙 Back").first.wait_for(state="visible", timeout=8000)
    except Exception:
        try:
            pg.get_by_text("🔙 返回").first.wait_for(state="visible", timeout=8000)
        except Exception:
            pass
    time.sleep(0.12)            # 详情渲染后短暂等待，但仍在 ~700ms 强制窗内
    sc = scroll_sim(pg)         # 立即下滚（wheel + 直接设），触发释放
    time.sleep(1.0)             # 跨过 700ms 强制窗
    s = stmain(pg)
    chk(label, sc, s)


def main():
    proc = start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge", headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(URL, wait_until="load")
            wait = lambda s=1500: pg.wait_for_timeout(s)

            # ===== 路径1：树 → 容器详情，进入后立即下滚 =====
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); wait(1800)
            pg.get_by_role("button", name=re.compile(r"展开|Expand all")).click(); wait(1500)
            enter_and_test(pg,
                """()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('详情')||/detail/i.test(x.textContent)));if(b)b.click();}""",
                "P1 树→容器详情 立即下滚不被拽回")
            # 返回树（reset）
            pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('返回')||/back/i.test(x.textContent)));if(b)b.click();}""")
            wait(1800)

            # ===== 路径2：容器详情 → item 详情，进入后立即下滚 =====
            enter_and_test(pg,
                """()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('Open Details')||/open details/i.test(x.textContent)));if(b)b.click();}""",
                "P2 容器→item详情 立即下滚不被拽回")
            # 返回容器详情（reset）
            pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('返回')||/back/i.test(x.textContent)));if(b)b.click();}""")
            wait(1800)

            # ===== 路径3：item 列表(卡片) → item 详情，进入后立即下滚 =====
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(0).click(); wait(1800)
            pg.locator('[role="tabpanel"]:visible').get_by_text("Cards", exact=True).click(); wait(2000)
            enter_and_test(pg,
                """()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('Open Details')||/open details/i.test(x.textContent)));if(b)b.click();}""",
                "P3 item列表(卡片)→item详情 立即下滚不被拽回")

            passed = sum(1 for _, c in results if c)
            print(f"\nSUMMARY: {passed}/{len(results)} passed")
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
