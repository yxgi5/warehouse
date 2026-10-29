import subprocess, sys, time, os, signal
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
            pg.goto(URL,wait_until="load"); time.sleep(2)
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(5).click(); time.sleep(2.5)
            print("after switch containers, active=",active(pg))
            box=pg.locator('.st-key-container_list_wrap [data-testid="stDataFrame"]').first.bounding_box()
            pg.mouse.click(box["x"]+25, box["y"]+35+35*3); time.sleep(2)
            print("after select row, active=",active(pg))
            # 再点一次别的 widget（不切tab）
            pg.mouse.click(box["x"]+25, box["y"]+35+35*5); time.sleep(2)
            print("after select another row, active=",active(pg))
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)
if __name__=="__main__":
    main()
