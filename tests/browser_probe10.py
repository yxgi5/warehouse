import subprocess, sys, time, os, signal
from pathlib import Path
ROOT = Path(r"D:\repos\warehouse.git")
PORT=8899; URL=f"http://localhost:{PORT}"
LOG=ROOT/"wh_runs.log"
def start():
    env=dict(os.environ,WH_SKIP_AUTO_BACKUP="1")
    p=subprocess.Popen([sys.executable,"-m","streamlit","run","app.py","--server.headless","true","--server.port",str(PORT),"--browser.gatherUsageStats","false"],cwd=str(ROOT),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    import urllib.request
    for _ in range(60):
        try: urllib.request.urlopen(URL,timeout=2); return p
        except Exception: time.sleep(1)
    raise RuntimeError("no")
def count():
    try: return len(LOG.read_text().splitlines())
    except: return 0
def main():
    proc=start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b=pw.chromium.launch(channel="msedge",headless=True); pg=b.new_page(viewport={"width":1400,"height":900})
            pg.goto(URL,wait_until="load"); time.sleep(2)
            c0=count()
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(5).click(); time.sleep(2.5)
            c1=count()
            pg.locator('[data-testid="stTabs"] button[role="tab"]').nth(4).click(); time.sleep(2.5)
            c2=count()
            print(f"runs before tab clicks={c0}, after containers click={c1}, after tree click={c2}")
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)
if __name__=="__main__":
    main()
