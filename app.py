#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hohai TV 自动登录 + 每日签到"""

import json, os, re, subprocess, time
import requests
from seleniumbase import SB

EMAIL = os.environ.get("HOHAI_EMAIL") or os.environ.get("LUNES_EMAIL") or ""
PASSWORD = os.environ.get("HOHAI_PASSWORD") or os.environ.get("LUNES_PASSWORD") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
LOGIN_URL = "https://tv.hohai.eu.org/login"
DASHBOARD_URL = "https://tv.hohai.eu.org/dashboard"
CHECKIN_KEYWORDS = ["签到", "打卡", "每日签到", "check-in", "checkin", "立即签到"]
ALREADY_KEYWORDS = ["已签到", "已打卡", "今日已签到", "明日再来", "已经签到", "签到过"]
SUCCESS_KEYWORDS = ["签到成功", "打卡成功", "签到奖励", "已签到", "获得"]
LOGIN_BTN_KEYWORDS = ["登录", "登 录", "登入", "提交", "login", "log in", "sign in", "submit"]
POPUP_KEYWORDS = ["Accept", "同意", "我知道了", "知道了", "关闭"]
CONFIRM_KEYWORDS = ["确认签到", "立即签到", "确认", "确定", "好的", "OK"]

def js_build(template, **params):
    out = template
    for key, value in params.items():
        out = out.replace("__" + key + "__", json.dumps(value, ensure_ascii=False))
    return out

def js(sb, template, **params):
    try:
        return sb.execute_script(js_build(template, **params))
    except Exception as e:
        print("  JS异常: " + str(e)[:120])
        return None

def send_tg(msg_icon, msg_text, extra=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置TG推送")
        return
    t = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8*3600))
    m = EMAIL[:2] + "****" + EMAIL[-2:] + "@" + EMAIL.split("@")[1] if "@" in EMAIL and len(EMAIL.split("@")[0]) > 4 else EMAIL[:2] + "****"
    txt = f"Hohai TV 签到通知\n\n{msg_icon} {msg_text}\n账户: {m}\n时间: {t}"
    if extra: txt += f"\n\n{extra}"
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": txt}, timeout=10)
        print("TG成功" if r.status_code == 200 else f"TG失败: {r.text[:100]}")
    except Exception as e:
        print(f"TG异常: {e}")

def activate():
    for c in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", c], capture_output=True, text=True, timeout=3)
            ws = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if ws:
                subprocess.run(["xdotool", "windowactivate", "--sync", ws[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except: pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except: pass

def xclick(x, y):
    activate()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=3, stderr=subprocess.DEVNULL)
    except: pass

def xtype(t):
    activate()
    try:
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "60", t], timeout=40, stderr=subprocess.DEVNULL)
    except: pass

def xkey(k):
    activate()
    try:
        subprocess.run(["xdotool", "key", "--clearmodifiers", k], timeout=5, stderr=subprocess.DEVNULL)
    except: pass

def body(sb): return js(sb, "(function(){return document.body?document.body.innerText:'';})()") or ""
def etext(sb, s): return js(sb, r'(function(){var e=document.querySelector(__SEL__);return e?(e.innerText||e.textContent||"").replace(/\s+/g," ").trim():"";})()', SEL=s) or ""
def eexists(sb, s): return js(sb, r'(function(){return !!document.querySelector(__SEL__);})()', SEL=s) is True
def eclick(sb, s): return js(sb, r'(function(){var e=document.querySelector(__SEL__);if(!e)return false;try{e.scrollIntoView({block:"center"});}catch(err){}e.click();return true;})()', SEL=s) is True
def fill(sb, s, v, l):
    r = js(sb, r'(function(){var e=document.querySelector(__SEL__);if(!e)return"no-el";var val=__VAL__;e.focus();var p=(e.tagName==="TEXTAREA")?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;var d=Object.getOwnPropertyDescriptor(p,"value");if(d&&d.set){d.set.call(e,val);}else{e.value=val;}e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));e.dispatchEvent(new KeyboardEvent("keyup",{bubbles:true,key:"a"}));return e.value===val?"ok":"mismatch";})()', SEL=s, VAL=v)
    if r == "ok":
        print(f"  {l}已填入({len(v)}字符)")
        return True
    if r == "no-el":
        print(f"  {l}未找到: {s}")
        return False
    print(f"  {l}JS失败，用键盘...")
    js(sb, r'(function(){var e=document.querySelector(__SEL__);if(!e)return false;e.focus();if(e.select){e.select();}return true;})()', SEL=s)
    time.sleep(0.3)
    xkey("ctrl+a")
    xtype(v)
    time.sleep(0.5)
    g = js(sb, r'(function(){var e=document.querySelector(__SEL__);return e?e.value.length:-1;})()', SEL=s)
    ok = isinstance(g, int) and g == len(v)
    print(f"  {l}输入后长度:{g}(期望{len(v)})")
    return ok

def fbtn(sb, kws, mark):
    return js(sb, r'''(function(){var kws=__KWS__,mark=__MARK__;function n(s){return(s||"").replace(/\s+/g," ").trim();}function v(el){var s=window.getComputedStyle(el);if(s.display==="none"||s.visibility==="hidden"||s.opacity==="0")return false;if(s.pointerEvents==="none")return false;return !!(el.offsetWidth||el.offsetHeight||el.getClientRects().length);}function h(t){if(!t||t.length>24)return false;var l=t.toLowerCase();for(var i=0;i<kws.length;i++){if(l.indexOf(String(kws[i]).toLowerCase())>=0)return true;}return false;}document.querySelectorAll("["+mark+"]").forEach(function(e){e.removeAttribute(mark);});var ns=document.querySelectorAll("button,input[type=submit],input[type=button],a,[role=button],div,span,li,p");var b=null;for(var i=0;i<ns.length;i++){var el=ns[i],t=n(el.innerText||el.value||el.textContent);if(!h(t)||!v(el))continue;var ch=false;for(var j=0;j<el.children.length;j++){if(h(n(el.children[j].innerText||el.children[j].textContent))){ch=true;break;}}if(ch)continue;var tg=el.tagName.toLowerCase(),sc=(tg==="button"||tg==="input")?3:(tg==="a"?2:1);if(!b||sc>b.score)b={el:el,score:sc,text:t};}if(!b)return null;b.el.setAttribute(mark,"1");return b.text;})()''', KWS=kws, MARK=mark)

def dump(sb, tag):
    info = js(sb, r'''(function(){function v(el){return !!(el.offsetWidth||el.offsetHeight||el.getClientRects().length);}var inputs=[];document.querySelectorAll("input,textarea").forEach(function(el){inputs.push({type:el.type||"",name:el.name||"",id:el.id||"",ph:el.placeholder||"",cls:(el.className||"").toString().slice(0,50),visible:v(el)});});var buttons=[];document.querySelectorAll("button,input[type=submit],a,[role=button]").forEach(function(b){var t=(b.innerText||b.value||"").replace(/\s+/g," ").trim();if(t&&t.length<=24&&buttons.indexOf(t)<0)buttons.push(t);});var frames=[];document.querySelectorAll("iframe").forEach(function(f){frames.push((f.src||"").slice(0,60));});return{url:location.href,ready:document.readyState,forms:document.querySelectorAll("form").length,inputs:inputs,buttons:buttons.slice(0,25),iframes:frames,bodyText:(document.body?document.body.innerText:"").replace(/\s+/g," ").slice(0,400)};})()''')
    if info:
        print(f"[{tag}]诊断:")
        print(f"  URL:{info.get('url')} ready:{info.get('ready')} forms:{info.get('forms')}")
        print(f"  iframes:{info.get('iframes')}")
        print(f"  buttons:{info.get('buttons')}")
        for i,x in enumerate(info.get("inputs") or []): print(f"  input[{i}] {json.dumps(x,ensure_ascii=False)}")
        print(f"  body:{info.get('bodyText')}")
    try:
        with open(tag+".html","w",encoding="utf-8") as f: f.write(sb.get_page_source() or "")
        sb.save_screenshot(tag+".png")
        print(f"  已保存{tag}.html / {tag}.png")
    except: pass

def find_form(sb):
    return js(sb, r'''(function(){function v(el){if(!el)return false;var s=window.getComputedStyle(el);if(s.display==="none"||s.visibility==="hidden")return false;return !!(el.offsetWidth||el.offsetHeight||el.getClientRects().length);}document.querySelectorAll("[data-kx-user],[data-kx-pass]").forEach(function(e){e.removeAttribute("data-kx-user");e.removeAttribute("data-kx-pass");});var all=Array.prototype.slice.call(document.querySelectorAll("input"));var pass=null;for(var p=0;p<all.length;p++){if(all[p].type==="password"&&v(all[p])){pass=all[p];break;}}var sels=["input[name=\"email\"]","input[name=\"Email\"]","input[name=\"username\"]","input[name=\"user\"]","input[name=\"account\"]","input[name=\"login\"]","input#email","input#username","input#account","input#user","input[type=\"email\"]","input[autocomplete=\"email\"]","input[autocomplete=\"username\"]","input[placeholder*=\"邮箱\"]","input[placeholder*=\"账号\"]","input[placeholder*=\"帐号\"]","input[placeholder*=\"用户名\"]"];var user=null;for(var i=0;i<sels.length&&!user;i++){var c=document.querySelectorAll(sels[i]);for(var j=0;j<c.length;j++){if(c[j].type!=="password"&&v(c[j])){user=c[j];break;}}}if(!user&&pass){var idx=all.indexOf(pass);for(var k=idx-1;k>=0;k--){var t=all[k].type;if((t==="text"||t==="email"||t===""||t==="tel")&&v(all[k])){user=all[k];break;}}}if(user)user.setAttribute("data-kx-user","1");if(pass)pass.setAttribute("data-kx-pass","1");return{user:!!user,pass:!!pass,userInfo:user?{type:user.type,name:user.name,id:user.id,ph:user.placeholder}:null,passInfo:pass?{type:pass.type,name:pass.name,id:pass.id,ph:pass.placeholder}:null};})()''')

def wait_cf(sb, timeout=40):
    for i in range(timeout):
        try:
            title = (sb.get_title() or "").lower()
        except: title = ""
        body_l = body(sb).lower()
        blocked = ("just a moment" in title or "attention required" in title or "checking your browser" in body_l or "verify you are human" in body_l)
        if not blocked:
            has_if = js(sb, r'(function(){var fs=document.querySelectorAll("iframe");for(var i=0;i<fs.length;i++){var s=fs[i].src||"";if(s.indexOf("challenges.cloudflare.com")>=0)return true;}return false;})()')
            if not has_if: return True
        if i % 5 == 0: print(f"  CF验证中...({i}s)")
        try: sb.uc_gui_click_captcha()
        except: pass
        time.sleep(1)
    return False

def handle_cf(sb):
    print("🔍处理Turnstile...")
    time.sleep(2)
    if js(sb, r'(function(){var i=document.querySelector("input[name=\"cf-turnstile-response\"]");if(i)return !!(i.value&&i.value.length>20);var fs=document.querySelectorAll("iframe");for(var k=0;k<fs.length;k++){if((fs[k].src||"").indexOf("challenges.cloudflare.com")>=0)return false;}return true;})()') is True:
        print("  ✅已静默通过")
        return True
    for rnd in range(4):
        if js(sb, r'(function(){var i=document.querySelector("input[name=\"cf-turnstile-response\"]");if(i)return !!(i.value&&i.value.length>20);var fs=document.querySelectorAll("iframe");for(var k=0;k<fs.length;k++){if((fs[k].src||"").indexOf("challenges.cloudflare.com")>=0)return false;}return true;})()') is True:
            print(f"  ✅通过(第{rnd+1}轮)")
            return True
        print(f"  🎯尝试点击({rnd+1}/4)...")
        info = js(sb, r'(function(){var ms=[].slice.call(document.querySelectorAll("iframe")),b=document.querySelector(".cf-turnstile,[data-sitekey]"),rs=[];for(var i=0;i<ms.length;i++){var s=ms[i].src||"";if(s.indexOf("cloudflare")>=0||s.indexOf("turnstile")>=0||s.indexOf("challenges")>=0){var r=ms[i].getBoundingClientRect();if(r.width>0&&r.height>0)rs.push({x:Math.round(r.left+30),y:Math.round(r.top+r.height/2),w:Math.round(r.width),h:Math.round(r.height),src:s});}}if(b){var rb=b.getBoundingClientRect();if(rb.width>0&&rb.height>0)rs.push({x:Math.round(rb.left+30),y:Math.round(rb.top+rb.height/2),w:Math.round(rb.width),h:Math.round(rb.height)});if(rs.length)return rs[0];}return null;})()')
        if info:
            print(f"    位置:{info['x']},{info['y']} {info.get('w')}x{info.get('h')}")
            wi = js(sb, r'(function(){return{x:window.screenX||window.screenLeft||0,y:window.screenY||window.screenTop||0,oh:window.outerHeight,ih:window.innerHeight,aw:window.screen.availHeight};})()') or {"x":0,"y":0,"oh":800,"ih":768,"aw":800}
            bar = wi["oh"] - wi["ih"]
            aw = wi.get("aw", 800)
            eff = aw - bar if aw > 0 else wi["oh"]
            bar2 = max(0, wi["oh"] - eff)
            bx = info["x"] + wi["x"]
            by = info["y"] + wi["y"] + bar2
            for a in range(12):
                if js(sb, r'(function(){var i=document.querySelector("input[name=\"cf-turnstile-response\"]");if(i)return !!(i.value&&i.value.length>20);var fs=document.querySelectorAll("iframe");for(var k=0;k<fs.length;k++){if((fs[k].src||"").indexOf("challenges.cloudflare.com")>=0)return false;}return true;})()') is True:
                    print(f"    ✅通过(第{a+1}次)")
                    return True
                for dx,dy in [(0,0),(15,0),(-15,0),(0,15),(0,-15)]:
                    xclick(bx+dx, by+dy)
                    time.sleep(0.3)
                    if js(sb, r'(function(){var i=document.querySelector("input[name=\"cf-turnstile-response\"]");if(i)return !!(i.value&&i.value.length>20);var fs=document.querySelectorAll("iframe");for(var k=0;k<fs.length;k++){if((fs[k].src||"").indexOf("challenges.cloudflare.com")>=0)return false;}return true;})()') is True:
                        print(f"    ✅通过(点{bx+dx},{by+dy})")
                        return True
                js(sb, r'(function(){var ts=document.querySelector("input[name=\"cf-turnstile-response\"]");if(ts){var el=ts;for(var i=0;i<20;i++){el=el.parentElement;if(!el)break;var s=window.getComputedStyle(el);if(s.overflow==="hidden"||s.overflowX==="hidden"||s.overflowY==="hidden")el.style.overflow="visible";el.style.minWidth="max-content";}}document.querySelectorAll("iframe").forEach(function(f){if(f.src&&f.src.indexOf("challenges.cloudflare.com")>=0){f.style.width="300px";f.style.height="65px";f.style.minWidth="300px";f.style.visibility="visible";f.style.opacity="1";}});return"done";})()')
                if a == 0:
                    sb.save_screenshot("cf_debug.png")
                    print("    📸已保存cf_debug.png")
        else:
            print("    ⚠️未找到CF元素")
            sb.save_screenshot("cf_debug.png")
        print(f"    ⏳等待...")
        time.sleep(2)
    print("  ❌CF验证失败")
    return False

def login(sb):
    print(f"🌐登录: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=6)
    time.sleep(3)
    wait_cf(sb)
    print("⏳等待表单...")
    form = None
    for i in range(40):
        form = find_form(sb)
        if form and form.get("pass"):
            print(f"  ✅找到表单({i+1}s)")
            print(f"     账号:{form.get('userInfo')}")
            print(f"     密码:{form.get('passInfo')}")
            break
        time.sleep(1)
    if not form or not form.get("pass"):
        print("❌未找到表单")
        dump(sb, "login_fail")
        return False
    pop = fbtn(sb, POPUP_KEYWORDS, "dpop")
    if pop:
        print(f"🍪关闭:{pop}")
        eclick(sb, "[data-dpop]")
        time.sleep(0.5)
        find_form(sb)
    if form.get("user"):
        print("📧填账号...")
        if not fill(sb, "[data-kx-user]", EMAIL, "账号"): return False
        time.sleep(0.4)
    else:
        print("ℹ️仅密码")
    print("🔑填密码...")
    if not fill(sb, "[data-kx-pass]", PASSWORD, "密码"): return False
    time.sleep(1)
    if js(sb, r'(function(){if(document.querySelector("input[name=\"cf-turnstile-response\"]"))return true;if(document.querySelector(".cf-turnstile,[data-sitekey]"))return true;var fs=document.querySelectorAll("iframe");for(var i=0;i<fs.length;i++){var s=fs[i].src||"";if(s.indexOf("challenges.cloudflare.com")>=0||s.indexOf("turnstile")>=0)return true;}return false;})()') is True:
        if not handle_cf(sb):
            print("❌CF失败")
            dump(sb, "login_cf_fail")
            return False
    else:
        print("ℹ️无CF")
    print("🖱️提交...")
    sub = False
    if eexists(sb, 'button[type="submit"]'):
        sub = eclick(sb, 'button[type="submit"]')
    if not sub:
        t = fbtn(sb, LOGIN_BTN_KEYWORDS, "dlogin")
        if t:
            print(f"  按钮:{t}")
            sub = eclick(sb, "[data-dlogin]")
    if not sub:
        print("  回车提交...")
        js(sb, r'(function(){var e=document.querySelector("[data-kx-pass]");if(e){e.focus();if(e.select){e.select();}}})()')
        time.sleep(0.3)
        xkey("Return")
    print("⏳等待跳转...")
    for _ in range(30):
        time.sleep(1)
        if "login" not in sb.get_current_url().split("?")[0].lower(): break
    cur = sb.get_current_url()
    if "login" not in cur.split("?")[0].lower():
        print(f"✅成功 {cur} {sb.get_title()}")
        return True
    print(f"❌失败 {cur} {sb.get_title()}")
    dump(sb, "login_fail")
    return False

def check_in(sb):
    if DASHBOARD_URL.rstrip("/") not in sb.get_current_url():
        print(f"🌐签到页: {DASHBOARD_URL}")
        sb.uc_open_with_reconnect(DASHBOARD_URL, reconnect_time=6)
    else:
        print(f"🌐已在: {sb.get_current_url()}")
    time.sleep(3)
    wait_cf(sb)
    print("🔍找签到...")
    btn = None
    for _ in range(20):
        btn = fbtn(sb, CHECKIN_KEYWORDS, "dcheck")
        if btn:
            print(f"  找到:{btn}")
            break
        time.sleep(1)
    if not btn:
        print("  未找到")
        dump(sb, "checkin_nofind")
        return False, "未找到签到按钮", False
    for k in ALREADY_KEYWORDS:
        if k in btn:
            return True, f"今日已签到({btn})", True
    print(f"🖱️点击:{btn}")
    js(sb, f'''(function(){{var kws={json.dumps(CHECKIN_KEYWORDS)},mark="data-dcheck";function n(s){{return(s||"").replace(/\s+/g," ").trim();}}function h(t){{if(!t)return false;var l=t.toLowerCase();for(var i=0;i<kws.length;i++){{if(l.indexOf(String(kws[i]).toLowerCase())>=0)return true;}}return false;}}document.querySelectorAll("["+mark+"]").forEach(function(e){{e.removeAttribute(mark);}});var ns=document.querySelectorAll("button,a,div,span,li");for(var i=0;i<ns.length;i++){{var el=ns[i],t=n(el.innerText||el.value||el.textContent);if(h(t)&&t.length<=20){{el.setAttribute(mark,"1");el.scrollIntoView({{block:"center",behavior:"instant"}});return;}}}})()''')
    time.sleep(0.5)
    ok = eclick(sb, "[data-dcheck]")
    if not ok:
        print("  JS失败，xdotool...")
        pos = js(sb, r'(function(){var e=document.querySelector("[data-dcheck]");if(!e)return null;var r=e.getBoundingClientRect();return{x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};})()')
        if pos:
            wi = js(sb, r'(function(){return{x:window.screenX||0,y:window.screenY||0,oh:window.outerHeight,ih:window.innerHeight,aw:window.screen.availHeight};})()') or {"x":0,"y":0,"oh":800,"ih":768,"aw":800}
            bar = wi["oh"] - wi["ih"]
            aw = wi.get("aw", 800)
            eff = aw - bar if aw > 0 else wi["oh"]
            bar2 = max(0, wi["oh"] - eff)
            xclick(pos["x"] + wi["x"], pos["y"] + wi["y"] + bar2)
            time.sleep(1)
    print("⏳等待...")
    time.sleep(2)
    cfm = fbtn(sb, CONFIRM_KEYWORDS, "dok")
    if cfm:
        print(f"  确认:{cfm}")
        eclick(sb, "[data-dok]")
        time.sleep(1)
    if js(sb, r'(function(){if(document.querySelector("input[name=\"cf-turnstile-response\"]"))return true;if(document.querySelector(".cf-turnstile,[data-sitekey]"))return true;var fs=document.querySelectorAll("iframe");for(var i=0;i<fs.length;i++){var s=fs[i].src||"";if(s.indexOf("challenges.cloudflare.com")>=0||s.indexOf("turnstile")>=0)return true;}return false;})()') is True:
        print("  ⚠️CF验证中...")
        if not handle_cf(sb):
            dump(sb, "checkin_cf_fail")
            return False, "CF验证失败", False
        print("  ✅CF通过")
    print("⏳等待结果...")
    for _ in range(120):
        time.sleep(0.5)
        if js(sb, r'(function(){if(document.querySelector("input[name=\"cf-turnstile-response\"]"))return false;if(document.querySelector(".cf-turnstile,[data-sitekey]"))return false;var fs=document.querySelectorAll("iframe");for(var i=0;i<fs.length;i++){var s=fs[i].src||"";if(s.indexOf("challenges.cloudflare.com")>=0)return false;}return true;})()') is False:
            print("  ⏳CF还在...")
            continue
        t = body(sb)
        if "已到账" in t or "本次获得" in t:
            print("  ✅签到成功(已到账)")
            amt = ""
            idx = t.find("已到账") if "已到账" in t else t.find("本次获得")
            if idx >= 0:
                m = re.search(r'(\+?\d+\.?\d*)', t[idx:idx+30])
                if m: amt = " +" + m.group(1)
            return True, f"今日已签到{amt}", True
        for k in SUCCESS_KEYWORDS:
            if k in t:
                print(f"  ✅{k}")
                return True, f"签到成功({k})", False
        now = js(sb, 'return document.querySelector("[data-dcheck]")?document.querySelector("[data-dcheck]").innerText:"";') or ""
        if now and any(k in now for k in ALREADY_KEYWORDS):
            return True, f"今日已签到(按钮:{now})", True
        cur = sb.get_current_url()
        if "success" in cur.lower() or "done" in cur.lower():
            return True, "签到成功(url)", False
    print("❌超时")
    dump(sb, "checkin_fail")
    return False, "未检测到成功", False

def main():
    print("#" * 25)
    print("   Hohai TV 自动签到")
    print("#" * 25)
    if not PASSWORD:
        print("❌未设置密码")
        send_tg("[X]", "配置错误", "未设置HOHAI_PASSWORD")
        return
    sp = os.environ.get("IS_PROXY", "false").lower() == "true"
    kwargs = {"uc": True, "headless": False}
    if sp:
        print("🔗代理: 127.0.0.1:1081")
        kwargs["proxy"] = "http://127.0.0.1:1081"
    with SB(**kwargs) as sb:
        print("✅浏览器启动")
        try:
            sb.set_window_size(1600, 1000)
        except: pass
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"🌐IP: {sb.get_text('body').strip()}")
        except: pass
        if login(sb):
            ok, msg, already = check_in(sb)
            if ok:
                print(f"✅{msg}")
                send_tg("[OK]", "今日已签到" if already else "签到成功", msg)
            else:
                print(f"❌{msg}")
                send_tg("[X]", "签到失败", msg)
        else:
            print("❌登录失败")
            send_tg("[X]", "登录失败", "详见日志")

if __name__ == "__main__":
    main()
