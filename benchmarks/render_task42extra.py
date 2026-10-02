"""Native isolated Firefox DOM/screenshots; run only in the task light supervisor."""

import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT = Path("/home/fenics/Projects/NN-Lab-V2")
OUT = ROOT / "tmp/task42extra/render" / sys.argv[1]
OUT.mkdir(parents=True)
profile = OUT / "profile"
profile.mkdir()
env = dict(os.environ)
env.update(
    MOZ_HEADLESS="1",
    MOZ_CRASHREPORTER_DISABLE="1",
    XDG_CACHE_HOME=str(OUT / "cache"),
    XDG_CONFIG_HOME=str(OUT / "config"),
    XDG_DATA_HOME=str(OUT / "data"),
    LIBGL_ALWAYS_SOFTWARE="1",
    GALLIUM_DRIVER="llvmpipe",
    LP_NUM_THREADS="1",
)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
log = (OUT / "driver.log").open("w")
driver = subprocess.Popen(
    [
        "/snap/firefox/current/usr/lib/firefox/geckodriver",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ],
    stdout=log,
    stderr=log,
    env=env,
)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
base = f"http://127.0.0.1:{port}"
session = None


def request(method, path, value=None, timeout=45):
    data = json.dumps(value).encode() if value is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener.open(req, timeout=timeout) as response:
            item = json.load(response)["value"]
    except urllib.error.HTTPError as error:
        detail = error.read(10000).decode("utf-8", errors="replace")
        raise RuntimeError(f"WebDriver HTTP {error.code}: {detail}") from error
    if isinstance(item, dict) and "error" in item:
        raise RuntimeError(str(item))
    return item


def script(source, *args):
    return request(
        "POST", f"/session/{session}/execute/sync", dict(script=source, args=list(args))
    )


def screenshot(name):
    path = OUT / (name + ".png")
    path.write_bytes(base64.b64decode(request("GET", f"/session/{session}/screenshot")))
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


records = []
try:
    for _ in range(30):
        try:
            request("GET", "/status", timeout=1)
            break
        except Exception:
            if driver.poll() is not None:
                raise RuntimeError("native geckodriver exited before readiness")
            time.sleep(0.25)
    capabilities = request(
        "POST",
        "/session",
        dict(
            capabilities=dict(
                alwaysMatch={
                    "browserName": "firefox",
                    "pageLoadStrategy": "eager",
                    "moz:firefoxOptions": dict(
                        binary="/snap/firefox/current/usr/lib/firefox/firefox",
                        args=["-headless", "-no-remote", "-profile", str(profile)],
                        prefs={
                            "browser.shell.checkDefaultBrowser": False,
                            "browser.startup.homepage": "about:blank",
                            "datareporting.healthreport.uploadEnabled": False,
                            "toolkit.telemetry.enabled": False,
                            "layers.acceleration.disabled": True,
                            "gfx.webrender.software": True,
                            "webgl.disabled": True,
                            "dom.webgpu.enabled": False,
                            "gfx.canvas.accelerated": False,
                            "gfx.webrender.force-disabled": True,
                            "media.ffmpeg.vaapi.enabled": False,
                            "media.hardware-video-decoding.enabled": False,
                        },
                    ),
                }
            )
        ),
    )
    session = capabilities["sessionId"]
    request("POST", f"/session/{session}/timeouts", dict(pageLoad=60000, script=30000))
    request("POST", f"/session/{session}/window/rect", dict(width=1600, height=1200))
    urls = json.loads(Path(sys.argv[2]).read_text())
    for number, item in enumerate(urls):
        url = item if isinstance(item, str) else item["url"]
        heading = "" if isinstance(item, str) else item.get("heading_prefix", "")
        request("POST", f"/session/{session}/url", dict(url=url), timeout=65)
        dom = None
        for _ in range(40):
            dom = script(
                """
const a=document.querySelector('article.markdown-body');
if(!a) return null;
let nodes=[a],scope='entire task document';
window.__taskScopeHeading=null;
if(arguments[0]) {
 const h=[...a.querySelectorAll('h1,h2,h3,h4,h5,h6')].find(x=>x.innerText.startsWith(arguments[0]));
 if(!h) return null;
 window.__taskScopeHeading=h;
 const children=[...a.children];let first=h;
 while(first.parentElement!==a) first=first.parentElement;
 const start=children.indexOf(first),level=Number(h.tagName.slice(1));let end=children.length;
 for(let i=start+1;i<children.length;i++) {
  const hs=children[i].matches('h1,h2,h3,h4,h5,h6')?[children[i]]:[...children[i].querySelectorAll('h1,h2,h3,h4,h5,h6')];
  if(hs.some(x=>Number(x.tagName.slice(1))<=level)){end=i;break;}
 }
 nodes=children.slice(start,end);scope=h.innerText;
}
const collect=sel=>nodes.flatMap(e=>[...(e.matches(sel)?[e]:[]),...e.querySelectorAll(sel)]);
window.__taskTables=collect('table');window.__taskMath=collect('math-renderer');
return {title:document.title,scopeHeading:scope,articleText:nodes.map(x=>x.innerText).join(String.fromCharCode(10)).slice(0,220),ready:document.readyState,
fonts:document.fonts.status,
tables:window.__taskTables.map(e=>({columns:[...e.rows].map(r=>r.cells.length),
width:e.getBoundingClientRect().width,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth})),
math:window.__taskMath.map(e=>({html:e.outerHTML.slice(0,1800),
shadow:e.shadowRoot?.innerHTML?.slice(0,1800)||null,width:e.getBoundingClientRect().width,
height:e.getBoundingClientRect().height}))};
""",
                heading,
            )
            if dom and dom["fonts"] == "loaded" and dom["ready"] == "complete":
                time.sleep(2)
                break
            time.sleep(0.5)
        if dom is None:
            raise RuntimeError("actual GitHub markdown article not available")
        script(
            """
document.documentElement.style.scrollBehavior='auto';
document.body.style.scrollBehavior='auto';
const h=window.__taskScopeHeading;
if(h) {h.style.scrollMarginTop='180px';h.scrollIntoView({block:'start',inline:'nearest',behavior:'instant'});}
else document.scrollingElement.scrollTop=0;
return {scrollY:window.scrollY,scopeTop:h?.getBoundingClientRect().top??null};
"""
        )
        time.sleep(0.35)
        shots = [screenshot(f"{number:02d}_top")]
        for kind, count in [
            ("table", len(dom["tables"])),
            ("math-renderer", len(dom["math"])),
        ]:
            for index in range(count):
                script(
                    "const e=(arguments[0]==='table'?window.__taskTables:window.__taskMath)[arguments[1]]; e.style.scrollMarginTop='160px';e.scrollIntoView({block:'start',inline:'nearest',behavior:'instant'}); return e.getBoundingClientRect().top;",
                    kind,
                    index,
                )
                time.sleep(0.35)
                shots.append(screenshot(f"{number:02d}_{kind}_{index:02d}"))
                if kind == "table":
                    overflow = script(
                        "const t=window.__taskTables[arguments[0]]; const p=t.scrollWidth>t.clientWidth+1?t:t.parentElement; const full=p.scrollWidth>p.clientWidth+1; window.__taskHorizontalHost=p; if(full)p.scrollLeft=p.scrollWidth; return full;",
                        index,
                    )
                    if overflow:
                        shots.append(
                            screenshot(f"{number:02d}_{kind}_{index:02d}_right")
                        )
                        script(
                            "window.__taskHorizontalHost.scrollLeft=0;",
                            index,
                        )
        dom["mathAfterScroll"] = script(
            "return window.__taskMath.map(e=>({html:e.outerHTML.slice(0,2200),shadow:e.shadowRoot?.innerHTML?.slice(0,2200)||null,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}));"
        )
        records.append(
            dict(
                url=url,
                heading_prefix=heading,
                DOM=dom,
                screenshots=shots,
                visual_review="pending human/model image inspection",
            )
        )
        (OUT / "render_records.json").write_text(
            json.dumps(
                dict(
                    status="DOM_AND_SCREENSHOTS_CAPTURED_NOT_YET_VISUALLY_QUALIFIED",
                    browser=capabilities,
                    profile_scope=str(profile),
                    records=records,
                ),
                indent=2,
            )
            + "\n"
        )
    print(json.dumps(dict(output=str(OUT), pages=len(records))))
except Exception as error:
    failure_page = None
    if session is not None:
        try:
            failure_page = script(
                "return {title:document.title,url:location.href.split('?')[0],"
                "articleCount:document.querySelectorAll('article').length,"
                "bodyExcerpt:document.body?.innerText?.slice(0,1000)||''};"
            )
            failure_page["screenshot"] = screenshot("failure_page")
        except Exception as diagnostic_error:
            failure_page = {"diagnostic_error": str(diagnostic_error)}
    (OUT / "render_failure.json").write_text(
        json.dumps(
            dict(
                status="RENDERED_VIEW_BLOCKED",
                error=str(error),
                completed_records=records,
                failure_page=failure_page,
            ),
            indent=2,
        )
        + "\n"
    )
    raise
finally:
    if session:
        try:
            request("DELETE", f"/session/{session}", timeout=10)
        except Exception:
            pass
    driver.terminate()
    try:
        driver.wait(timeout=5)
    except subprocess.TimeoutExpired:
        driver.kill()
        driver.wait(timeout=5)
    log.close()
