import subprocess, sys, time, os, signal
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PORT = 8899
URL = f"http://localhost:{PORT}"
def start():
    env = dict(os.environ, WH_SKIP_AUTO_BACKUP="1")
    p = subprocess.Popen([sys.executable,"-m","streamlit","run","app.py","--server.headless","true","--server.port",str(PORT),"--browser.gatherUsageStats","false"],cwd=str(ROOT),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
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
            b=pw.chromium.launch(channel="msedge",headless=True)
            pg=b.new_page()
            pg.goto(URL,wait_until="load")
            time.sleep(2)
            # 探测 Streamlit rerun API
            res = pg.evaluate("""() => {
                const out={};
                out.hasParentStreamlit = !!(window.parent && window.parent.Streamlit);
                out.parentRerun = !!(out.hasParentStreamlit && window.parent.Streamlit.rerun);
                out.hasStreamlit = !!window.Streamlit;
                out.rerun = !!(window.Streamlit && window.Streamlit.rerun);
                try {
                  // 尝试调用 rerun 看是否报错/是否改变 URL
                  if (window.parent && window.parent.Streamlit && window.parent.Streamlit.rerun) {
                    window.parent.Streamlit.rerun();
                    out.calledParent=true;
                  }
                } catch(e){ out.err=String(e); }
                return out;
            }""")
            print("REPORT:", res)
            b.close()
    finally:
        proc.send_signal(signal.SIGTERM)
if __name__=="__main__":
    main()
