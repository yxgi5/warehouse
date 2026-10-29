import subprocess, sys, time, os, signal
from pathlib import Path
ROOT = Path(r"D:\repos\warehouse.git")
PORT=8899; URL=f"http://localhost:{PORT}"
def start():
    env=dict(os.environ,WH_SKIP_AUTO_BACKUP="1")
    p=subprocess.Popen([sys.executable,"-m","streamlit","run","app.py","--server.headless","true","--server.port",str(PORT),"--browser.gatherUsageStats","false"],cwd=str(ROOT),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    import urllib.request
    for _ in range(60):
        try: urllib.request.urlopen(URL,timeout=2); return p
        except Exception: time.sleep(1)
    raise RuntimeError("no")
def main():
    proc=start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b=pw.chromium.launch(channel="msedge",headless=True); pg=b.new_page(viewport={"width":1400,"height":900})
            pg.goto(URL,wait_until="load"); time.sleep(2)
            # 打印全部 tab 文本（含隐藏），看是否有错误
            alltxt = pg.evaluate("""()=>Array.from(document.querySelectorAll('[role=\"tabpanel\"]')).map(p=>p.innerText.slice(0,200)).join(' ||| ')""")
            print("ALL PANELS:", alltxt[:800])
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); time.sleep(3)
            vis = pg.evaluate("""()=>{const ps=Array.from(document.querySelectorAll('[role=\"tabpanel\"]'));for(const x of ps){if(!x.hasAttribute('hidden')&&x.offsetParent!==null)return x.innerText.slice(0,400);}return 'NONE';}""")
            print("TREE VISIBLE:", vis[:400])
            has_expand = pg.get_by_text("Expand all").count()
            print("Expand all count:", has_expand)
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)
if __name__=="__main__":
    main()
