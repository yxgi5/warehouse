import subprocess, sys, time, os, signal, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PORT = 8899; URL=f"http://localhost:{PORT}"
def start():
    env=dict(os.environ,WH_SKIP_AUTO_BACKUP="1")
    p=subprocess.Popen([sys.executable,"-m","streamlit","run","app.py","--server.headless","true","--server.port",str(PORT),"--browser.gatherUsageStats","false"],cwd=str(ROOT),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    import urllib.request
    for _ in range(60):
        try: urllib.request.urlopen(URL,timeout=2); return p
        except Exception: time.sleep(1)
    raise RuntimeError("no")
def active(page):
    return page.evaluate("""()=>{const t=Array.from(document.querySelectorAll('[role=\"tab\"]'));let a=-1;t.forEach((x,i)=>{if(x.getAttribute('aria-selected')==='true')a=i;});return a;}""")
def main():
    proc=start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b=pw.chromium.launch(channel="msedge",headless=True); pg=b.new_page(viewport={"width":1400,"height":900})
            pg.goto(URL,wait_until="load")
            conn=sqlite3.connect(str(ROOT/"warehouse.db"))
            cname=conn.execute("SELECT c.name FROM containers c WHERE c.id IN (SELECT container_id FROM items GROUP BY container_id ORDER BY COUNT(*) DESC LIMIT 1)").fetchone()[0]
            conn.close()
            # 树 -> item 详情
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); time.sleep(2.5)
            pg.get_by_role("button",name="Expand all").click(); time.sleep(2)
            pg.evaluate(f"""("""+"cname"+""") => {{ const t=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes(cname)); let r=t.closest('[data-testid=\"stHorizontalBlock\"]'); let v=null; while(r&&!v){{v=Array.from(r.querySelectorAll('button')).find(b=>b.textContent.includes('Detail')); if(!v)r=r.parentElement&&r.parentElement.closest('[data-testid=\"stHorizontalBlock\"]');}} v.click(); }}""", cname)
            time.sleep(2.5)
            pg.evaluate("""()=>{const x=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('📄 Open Details'));x&&x.click();}"""); time.sleep(3)
            print("after item detail, active=",active(pg))
            # 切容器 tab
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(5).click(); time.sleep(2.5)
            print("after switch to containers, active=",active(pg))
            # 仅选中一个容器（checkbox），触发 on_select rerun
            box=pg.locator('.st-key-container_list_wrap [data-testid="stDataFrame"]').first.bounding_box()
            pg.mouse.click(box["x"]+25, box["y"]+35+35*3); time.sleep(2)
            print("after selecting a container row, active=",active(pg))
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)
if __name__=="__main__":
    main()
