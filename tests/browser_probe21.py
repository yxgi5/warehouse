# -*- coding: utf-8 -*-
"""「No purchase date 勾选框 ↔ Purchase Date 输入框」贴合度测量（用户反馈：
勾选框应紧贴日期输入框；数量→单位缝隙偏大）。

量三处缝 + dump 勾选框 DOM 祖先链（找 st-key 类以便 CSS 定位）：
  A. 勾选框容器底边 → Purchase Date label 顶边（期望 = 普通行距）
  B. 数量 input 底边 → Unit label 顶边（期望 = 普通行距）
  C. 参照行距：Container input 底边 → 勾选框行顶边
覆盖 物品编辑 / 物品新增 两页（同款布局机制）。

运行：python tests/browser_probe21.py
"""
import subprocess, sys, time, os, re
from pathlib import Path

ROOT = Path(r"D:\repos\warehouse.git")
PORT = 8901
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


GAP_JS = """()=>{
  const findLabel=(re)=>[...document.querySelectorAll('label')].find(l=>re.test(l.textContent.trim()));
  const cb = document.querySelector('.st-key-edit_no_date, .st-key-add_no_date')
             || findLabel(/no purchase date|没有购买日期/i);
  if(!cb) return {err:'no-checkbox'};
  const cell = (el)=>el.closest('.stElementContainer')||el;
  const cbCell = cell(cb.closest('.stElementContainer')?cb.closest('.stElementContainer'):cb);
  const dateL = findLabel(/^purchase date|^购买日期/i);
  const qtyL  = findLabel(/^quantity|^数量/i);
  const unitL = findLabel(/^unit|^单位/i);
  const contL = findLabel(/^container|^容器/i);
  if(!dateL||!qtyL||!unitL) return {err:'label-missing', dateL:!!dateL, qtyL:!!qtyL, unitL:!!unitL};
  const cellOfLabel=(l)=>l.closest('.stElementContainer')||l.parentElement;
  const qtyInput = qtyL.parentElement.querySelector('input')
                   || qtyL.nextElementSibling?.querySelector('input');
  const contInput = contL ? (contL.parentElement.querySelector('input')||contL.parentElement.querySelector('[data-baseweb="select"]')) : null;
  const R=e=>e.getBoundingClientRect();
  // 勾选框的可见盒子：input 所在 widget 本体（排除 element-container 的拉伸）
  const cbWidget = cb.closest('[data-testid="stCheckbox"]') || cb;
  const qtyWidget = qtyL.closest('[data-testid="stNumberInput"]') || qtyInput;
  const out = {
    cbBottom: Math.round(R(cbWidget).bottom),
    dateLabelTop: Math.round(R(dateL).top),
    gap_cb_date: Math.round(R(dateL).top - R(cbWidget).bottom),
    qtyBottom: Math.round(R(qtyWidget).bottom),
    unitLabelTop: Math.round(R(unitL).top),
    gap_qty_unit: Math.round(R(unitL).top - R(qtyWidget).bottom),
    contBottom: contInput?Math.round(R(contInput).bottom):null,
    cbCellTop: Math.round(R(cbCell).top),
    gap_cont_cb: (contInput&&R(cbCell))?Math.round(R(cbCell).top-R(contInput).bottom):null,
  };
  // DOM 祖先链（8 级）：找 st-key / data-testid 以便 CSS 定位
  const chain=[]; let el=cb;
  for(let i=0;i<8&&el;i++){
    chain.push({tag:el.tagName, tid:el.getAttribute('data-testid'),
                cls:String(el.className).slice(0,90),
                h:Math.round(R(el).height)});
    el=el.parentElement;
  }
  out.chain=chain;
  // DEBUG：CSS 是否到达 + 计算样式
  const cs = cbCell ? getComputedStyle(cbCell) : null;
  const styleHit = [...document.querySelectorAll('style')].filter(s=>s.textContent.includes('st-key-add_no_date')||s.textContent.includes('st-key-edit_no_date')).length;
  out.cssDebug = { marginTop: cs?cs.marginTop:null, display: cs?cs.display:null,
                   styleTagsWithRule: styleHit, inForm: cbCell?!!cbCell.closest('[data-testid="stForm"]'):null,
                   parentTid: cbCell.parentElement.getAttribute('data-testid'),
                   blockJc: getComputedStyle(cbCell.parentElement).justifyContent,
                   blockH: Math.round(cbCell.parentElement.getBoundingClientRect().height) };
  // 占位 spacer（勾选框容器的前一个兄弟 element-container）
  const prev = cbCell.previousElementSibling;
  if(prev){ const cs=getComputedStyle(prev.querySelector('div')||prev);
    out.spacer={h:Math.round(R(prev).height), styleH:cs.height}; }
  return out;
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

            # 编辑页：列表选中行 → 工具栏编辑（冷启动较慢，带重试）
            wait(3500)
            for _ in range(3):
                box = pg.locator('.st-key-item_list_wrap [data-testid="stDataFrame"]').first.bounding_box()
                pg.mouse.click(box["x"] + 25, box["y"] + 35 + 35 * 5); wait(1500)
                click_btn(pg, "编辑|edit"); wait(2200)
                if pg.evaluate("()=>!!document.querySelector('.st-key-edit_no_date')"):
                    break
            print("EDIT_PAGE:")
            print(pg.evaluate(GAP_JS))

            # 新增页
            pg.goto(URL, wait_until="load"); wait(2500)
            click_btn(pg, "新增物品|Add Item"); wait(2000)
            print("ADD_PAGE:")
            print(pg.evaluate(GAP_JS))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
