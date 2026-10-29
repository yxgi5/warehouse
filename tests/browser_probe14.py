# -*- coding: utf-8 -*-
"""回归探针：本轮 4 个 UI 修复的浏览器验证。

L1  物品 Tab list 视图：页面本体锁定滚动（body.wh-lock-scroll + stMain overflow:hidden）
T1  树列表滚到底再点容器 Detail：容器详情应打开在顶部（stMain.scrollTop==0，点 3）
T2  容器详情里点 item「Open Details」：物品详情同样置顶，且滚动锁解除（详情页可滚，点 3）
T3  返回树列表：非物品/容器 Tab 不加锁
C1  容器 Tab list 视图：加锁；切卡片视图：锁解除
C2  卡片视图滚到底 → 点卡片 Open Details → Back：应滚回原卡附近（stMain.scrollTop 明显 >0，点 5）

运行：python tests/browser_probe14.py（自动起 streamlit :8899，WH_SKIP_AUTO_BACKUP=1）
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


def stmain_state(page):
    """返回 {scrollTop, scrollHeight, clientHeight, overflow, locked}（主页面滚动容器状态）"""
    return page.evaluate("""()=>{
        const doc=document;
        const m=doc.querySelector('section[data-testid="stMain"]')||doc.querySelector('[data-testid="stMain"]');
        if(!m) return null;
        return {scrollTop:m.scrollTop, scrollHeight:m.scrollHeight, clientHeight:m.clientHeight,
                overflow:getComputedStyle(m).overflow,
                locked:doc.body.classList.contains('wh-lock-scroll')};
    }""")


results = []
def check(name, cond, extra=""):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def goto_tab(pg, idx, tries=4):
    """点 Tab 后校验 aria-selected 确实切换成功；Streamlit 自动化偶发吞点击，重试。"""
    for _ in range(tries):
        pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(idx).click()
        pg.wait_for_timeout(1800)
        cur = pg.evaluate("""(i)=>{
            const b=document.querySelectorAll('[data-baseweb="tab-list"] button')[i];
            return b?b.getAttribute('aria-selected'):null; }""", idx)
        if cur == "true":
            return
    raise RuntimeError(f"Tab {idx} 未能激活")


def to_card(pg):
    """当前可见面板切卡片视图（List→Cards 重同步 + 重试，见 probe13 教训）"""
    panel = pg.locator('[role="tabpanel"]:visible')
    for _ in range(4):
        try:
            panel.get_by_text("List", exact=True).click()
            pg.wait_for_timeout(600)
        except Exception:
            pass
        try:
            panel.get_by_text("Cards", exact=True).click()
        except Exception:
            panel.locator('label').filter(has_text="Cards").first.click(force=True)
        pg.wait_for_timeout(2500)
        if panel.locator("button:not([disabled])").filter(has_text="Open Details").count() > 0:
            return
    raise RuntimeError("未能切换到卡片视图")


def main():
    proc = start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge", headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(URL, wait_until="load")
            wait = lambda s=1500: pg.wait_for_timeout(s)

            # ---------- L1 物品 list 视图：页面锁定 ----------
            wait(2500)
            st_ = stmain_state(pg)
            check("L1 物品list页面锁定", bool(st_) and st_["locked"] and st_["overflow"] == "hidden",
                  str(st_))

            # ---------- C1/C2 容器流程放最前（probe13 教训：容器 Tab 在树/物品交互之后
            # 操作时 radio/点击易被自动化抖动吞掉；先做容器最稳） ----------
            goto_tab(pg, 5)
            st_ = stmain_state(pg)
            check("C1a 容器list页面锁定", bool(st_) and st_["locked"] and st_["overflow"] == "hidden",
                  str(st_))
            to_card(pg)
            wait(800)
            st_ = stmain_state(pg)
            btns = pg.locator('[role="tabpanel"]:visible').locator("button:not([disabled])").filter(has_text="Open Details")
            check("C1b 容器card解锁", bool(st_) and not st_["locked"] and btns.count() > 0,
                  f"st={st_} cards={btns.count()}")

            # ---------- C2 卡片 → 详情 → Back 回原卡附近 ----------
            # 点第 11 张卡（索引 10，约第 3 行）——Back 后锚点应把它滚回视口，scrollTop 明显 >0。
            # （不预先滚动：JS 点的是 DOM 顺序第 N 个按钮，与视口无关）
            txt = visible_text(pg)
            for _ in range(3):
                if "Container Details" in txt:
                    break
                pg.evaluate("""()=>{
                    const ps=[...document.querySelectorAll('[role="tabpanel"]')]
                        .filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);
                    const p=ps[0]; if(!p) return;
                    const bs=[...p.querySelectorAll('button')]
                        .filter(x=>!x.disabled && x.textContent.includes('Open Details'));
                    if(bs.length>10) bs[10].click(); }""")
                wait(3000)
                txt = visible_text(pg)
            check("C2a 卡片→容器详情", "Container Details" in txt, repr(txt[:120]))
            pg.get_by_text("🔙 Back").first.click(); wait(3500)
            st_ = stmain_state(pg)
            txt = visible_text(pg)
            check("C2b Back回原卡位置", ("Open Details" in txt) and bool(st_) and st_["scrollTop"] > 100,
                  f"st={st_} txt={txt[:80]!r}")

            # ---------- T1 树列表滚到底 → 容器详情置顶 ----------
            goto_tab(pg, 4)
            pg.get_by_role("button", name="⬇️ Expand all").click(); wait(1500)
            pg.evaluate("""()=>{const m=document.querySelector('section[data-testid="stMain"]');
                                if(m) m.scrollTop=m.scrollHeight;}""")
            wait(500)
            clicked = pg.evaluate("""()=>{
                const btns=[...document.querySelectorAll('button')]
                    .filter(b=>b.textContent.includes('Detail') && b.offsetParent!==null);
                if(btns.length){ btns[0].click(); return btns.length; } return 0; }""")
            wait(3000)
            st_ = stmain_state(pg)
            txt = visible_text(pg)
            dbg = pg.evaluate("""()=>{
                const btns=[...document.querySelectorAll('[data-baseweb="tab-list"] button')];
                let idx=-1; btns.forEach((b,i)=>{ if(b.getAttribute('aria-selected')==='true') idx=i; });
                const cs=getComputedStyle(document.documentElement);
                return JSON.stringify({n:btns.length, idx,
                    act:btns[idx]?btns[idx].textContent:null,
                    items:cs.getPropertyValue('--wh-items-lock'),
                    conts:cs.getPropertyValue('--wh-containers-lock'),
                    locked:document.body.classList.contains('wh-lock-scroll')}); }""")
            print("DBG T1:", dbg)
            check("T1 容器详情置顶打开", "Container Details" in txt and bool(st_) and st_["scrollTop"] <= 5,
                  f"detailBtns={clicked} st={st_}")

            # ---------- T2 容器详情 → item 详情：置顶 + 锁解除 ----------
            pg.locator("button:not([disabled])").filter(has_text="Open Details").first.click(); wait(3000)
            st_ = stmain_state(pg)
            txt = visible_text(pg)
            in_detail = ("🔙 Back" in txt) and ("Container Details" not in txt)
            check("T2 物品详情置顶且解锁", in_detail and bool(st_) and st_["scrollTop"] <= 5
                  and not st_["locked"], f"st={st_}")

            # ---------- T3 返回树列表：不加锁 ----------
            pg.get_by_text("🔙 Back").first.click(); wait(2200)
            pg.get_by_text("🔙 Back").first.click(); wait(2200)
            st_ = stmain_state(pg)
            check("T3 树Tab不加锁", bool(st_) and not st_["locked"], f"st={st_}")

            passed = sum(1 for _, c in results if c)
            print(f"\nSUMMARY: {passed}/{len(results)} passed")
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
