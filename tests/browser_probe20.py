# -*- coding: utf-8 -*-
"""测量「My Warehouse 大标题底边」↔「下方第一个有效内容顶边」的竖向间距，
用于验证压缩标题下方空白带（Phase 10.5）。覆盖：列表 / 容器详情 / 容器编辑 /
物品详情 / 物品编辑 五种形态。

运行：python tests/browser_probe20.py
环境：自带 Streamlit + Playwright(msedge)。
"""
import subprocess, sys, time, os, re
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


MEASURE = """()=>{
  const title=document.querySelector('[data-testid="stHeadingWithActionElements"]');
  if(!title) return {err:'no-title'};
  const tr=title.getBoundingClientRect();
  const all=[...document.querySelectorAll('*')].filter(e=>{
    const r=e.getBoundingClientRect();
    return r.width>0 && r.height>0 && r.top>tr.bottom+1 && r.left>=tr.left-80 && r.left<tr.left+520;
  });
  all.sort((a,b)=>a.getBoundingClientRect().top-b.getBoundingClientRect().top);
  const f=all[0];
  const top=f?Math.round(f.getBoundingClientRect().top):null;
  let extra=null;
  if(f){
    const cs=getComputedStyle(f);
    extra={mt:cs.marginTop, pt:cs.paddingTop, h:Math.round(f.getBoundingClientRect().height),
           html:f.innerHTML.slice(0,120), cls:String(f.className).slice(0,50)};
  }
  const tcs=getComputedStyle(title);
  return {titleBottom:Math.round(tr.bottom), contentTop:top,
          gap: top!==null?Math.round(top-tr.bottom):null,
          tMargin: tcs.marginBottom,
          content: extra,
          label: f?(f.tagName+'.'+String(f.className).slice(0,34)):null};
}"""


MEASURE2 = """()=>{
  const h=[...document.querySelectorAll('[data-testid="stHeadingWithActionElements"]')].find(e=>e.querySelector('h3'));
  if(!h) return {err:'no-subheader'};
  const hr=h.getBoundingClientRect();
  const form=document.querySelector('[data-testid="stForm"]');
  if(!form) return {err:'no-form'};
  const fr=form.getBoundingClientRect();
  return {subBottom:Math.round(hr.bottom), formTop:Math.round(fr.top),
          gap:Math.round(fr.top-hr.bottom), overlap: fr.top<hr.bottom};
}"""


MEASURE_TABS = """()=>{
  const title=document.querySelector('[data-testid="stHeadingWithActionElements"]');
  if(!title) return {err:'no-title'};
  const tr=title.getBoundingClientRect();
  const tl=document.querySelector('[data-baseweb="tab-list"]');
  if(!tl) return {err:'no-tablist'};
  const ttr=tl.getBoundingClientRect();
  const chain=[];
  let el=tl;
  while(el && !el.contains(title) && chain.length<8){
    const r=el.getBoundingClientRect();
    const cs=getComputedStyle(el);
    chain.push({tag:el.tagName, tid:el.getAttribute('data-testid'), cls:String(el.className).slice(0,40),
                top:Math.round(r.top), h:Math.round(r.height), pt:cs.paddingTop, mt:cs.marginTop});
    el=el.parentElement;
  }
  return {titleBottom:Math.round(tr.bottom), tablistTop:Math.round(ttr.top),
          visGap: Math.round(ttr.top-tr.bottom), chain};
}"""


CHECK_BACK = """()=>{
  const m=document.querySelector('section[data-testid="stMain"]')||document.querySelector('[data-testid="stMain"]');
  const title=document.querySelector('[data-testid="stHeadingWithActionElements"]');
  const tl=document.querySelector('[data-baseweb="tab-list"]');
  const tr=title?title.getBoundingClientRect():null;
  return {scrollTop: m?Math.round(m.scrollTop):null,
          titleExists: !!title,
          titleVisible: title? !!title.offsetParent : null,
          titleTop: tr?Math.round(tr.top):null,
          titleH: tr?Math.round(tr.height):null,
          tablistTop: tl?Math.round(tl.getBoundingClientRect().top):null};
}"""


def click_btn(pg, pat):
    pg.evaluate("""(pat)=>{const re=new RegExp(pat,'i');const b=[...document.querySelectorAll('button')].find(x=>!x.disabled&&re.test(x.textContent));if(b)b.click();}""", pat)


def main():
    proc = start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge", headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(URL, wait_until="load")
            wait = lambda s=1800: pg.wait_for_timeout(s)

            out = {}
            def reload():
                pg.goto(URL, wait_until="load"); wait(2500)

            # 1) 列表浏览态
            reload()
            out["list"] = pg.evaluate(MEASURE)
            out["list_tabs"] = pg.evaluate(MEASURE_TABS)

            # 2) 容器树 → 容器详情，再由容器内物品「查看详情」进物品详情 → 编辑
            reload()
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); wait(1800)
            pg.get_by_role("button", name=re.compile(r"展开|Expand all")).click(); wait(1500)
            pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('详情')||/detail/i.test(x.textContent)));if(b)b.click();}""")
            wait(1500)
            out["container_detail"] = pg.evaluate(MEASURE)
            # 容器内物品「查看详情/Open Details」→ 物品详情
            try:
                click_btn(pg, "查看详情|open detail|details"); wait(1800)
                out["item_detail"] = pg.evaluate(MEASURE)
                click_btn(pg, "编辑|edit"); wait(1800)
                out["item_edit"] = pg.evaluate(MEASURE)
                out["item_edit_sub_form"] = pg.evaluate(MEASURE2)
            except Exception as e:
                out["item_detail"] = {"err": "item-nav-failed: %s" % e}
            # 容器编辑（重新进一次）
            reload()
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); wait(1800)
            pg.get_by_role("button", name=re.compile(r"展开|Expand all")).click(); wait(1500)
            pg.evaluate("""()=>{const ps=[...document.querySelectorAll('[role="tabpanel"]')].filter(p=>!p.hasAttribute('hidden')&&p.offsetParent!==null);const p=ps[0]||document;const b=[...p.querySelectorAll('button')].find(x=>!x.disabled&&(x.textContent.includes('详情')||/detail/i.test(x.textContent)));if(b)b.click();}""")
            wait(1500)
            click_btn(pg, "编辑|edit"); wait(1500)
            out["container_edit"] = pg.evaluate(MEASURE)
            out["container_edit_sub_form"] = pg.evaluate(MEASURE2)

            # 4) 物品新增页：布局应与编辑页一致（标题在表单外）
            reload()
            click_btn(pg, "Add Item|新增物品"); wait(2000)
            out["item_add"] = pg.evaluate(MEASURE)
            out["item_add_sub_form"] = pg.evaluate(MEASURE2)

            # 5) 编辑退出复现（列表直接编辑路径）：选中行→工具栏编辑→(滚动)→取消→回列表
            reload()
            box = pg.locator('.st-key-item_list_wrap [data-testid="stDataFrame"]').first.bounding_box()
            pg.mouse.click(box["x"] + 25, box["y"] + 35 + 35 * 5); wait(1500)
            click_btn(pg, "编辑|edit"); wait(2000)
            out["edit_entered"] = pg.evaluate(CHECK_BACK)
            pg.evaluate("""()=>{const m=document.querySelector('section[data-testid="stMain"]');if(m)m.scrollTop=800;}""")
            wait(500)
            click_btn(pg, "取消|cancel"); wait(2500)
            out["after_edit_exit"] = pg.evaluate(CHECK_BACK)
            out["after_edit_exit_tabs"] = pg.evaluate(MEASURE_TABS)

            for k, v in out.items():
                print(f"{k}: {v}")
            print("=== SUMMARY ===")
            for k, v in out.items():
                g = v.get("gap") if isinstance(v, dict) else None
                print(f"  {k}: gap={g}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
