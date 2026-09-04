
`name`、`id`、`placeholder` **全是空的**,所以原脚本的 `input[name="email"]` 永远匹配不到。兜底逻辑(找可见密码框 → 往前找最近的文本框)起作用了。

修法:把参数用 `json.dumps` 直接内联进 JS 源码,不再用 `arguments`。同时给填充加了回读校验,JS 赋值不生效时改用 xdotool 真实键入。

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import subprocess
import requests
from seleniumbase import SB

# ============ 配置 ============
EMAIL        = os.environ.get("HOHAI_EMAIL") or os.environ.get("LUNES_EMAIL") or ""
PASSWORD     = os.environ.get("HOHAI_PASSWORD") or os.environ.get("LUNES_PASSWORD") or ""
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""

LOGIN_URL     = "https://tv.hohai.eu.org/login"
DASHBOARD_URL = "https://tv.hohai.eu.org/dashboard"

_CHECKIN_KEYWORDS   = ["签到", "打卡", "每日签到", "check-in", "checkin"]
_ALREADY_KEYWORDS   = ["已签到", "已打卡", "今日已签到", "明日再来", "已经签到"]
_SUCCESS_KEYWORDS   = ["签到成功", "打卡成功", "签到奖励", "已签到"]
_LOGIN_BTN_KEYWORDS = ["登录", "登 录", "登入", "提交", "login", "log in", "sign in", "submit"]
_POPUP_KEYWORDS     = ["Accept", "同意", "我知道了", "知道了", "关闭"]
_CONFIRM_KEYWORDS   = ["确认", "确定", "好的", "OK", "立即签到"]


# ============ Telegram ============
def send_tg_message(status_icon, status_text, extra_text=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        masked = f"{name[:2]}****{name[-2:]}@{domain}" if len(name) > 4 else f"{name}@{domain}"
    else:
        masked = (EMAIL[:2] + '****') if EMAIL else "(未设置)"

    text = (
        f"📺 Hohai TV 签到通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 账户: {masked}\n"
        f"⏱️ 时间: {current_time_str}"
    )
    if extra_text:
        text += f"\n\n{extra_text}"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        print("📩 Telegram 通知发送成功！" if r.status_code == 200
              else f"  ⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  ⚠️ Telegram 通知发送异常: {e}")


# ============ xdotool 底层操作 ============
def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls],
                               capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]],
                               timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"],
                       timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)],
                       timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _xdotool_type(text: str):
    """真实键盘输入（列表传参，无 shell，避免注入）"""
    _activate_window()
    try:
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "60", text],
                       timeout=30, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _xdotool_key(key: str):
    _activate_window()
    try:
        subprocess.run(["xdotool", "key", "--clearmodifiers", key],
                       timeout=5, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ============ JS 执行封装（CDP 模式不支持传参，全部内联） ============
def js(sb, script):
    """执行 JS 表达式，失败返回 None"""
    try:
        return sb.execute_script(script)
    except Exception as e:
        print(f"  ⚠️ JS 执行异常: {str(e)[:120]}")
        return None


def js_click(sb, selector) -> bool:
    script = r"""
    (function(){
        var e = document.querySelector(%s);
        if (!e) return false;
        try { e.scrollIntoView({block:'center'}); } catch(err) {}
        e.click();
        return true;
    })()
    """ % json.dumps(selector)
    return js(sb, script) is True


def js_text(sb, selector) -> str:
    script = r"""
    (function(){
        var e = document.querySelector(%s);
        return e ? (e.innerText || e.textContent || '').replace(/\s+/g,' ').trim() : '';
    })()
    """ % json.dumps(selector)
    return js(sb, script) or ""


def js_body_text(sb) -> str:
    return js(sb, "(function(){return document.body ? document.body.innerText : '';})()") or ""


def js_fill(sb, selector, value, label="") -> bool:
    """先用 React 兼容的 native setter 赋值，回读校验；失败则真实键入"""
    script = r"""
    (function(){
        var sel = %s, val = %s;
        var el = document.querySelector(sel);
        if (!el) return 'no-el';
        el.focus();
        var d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
        if (d && d.set) { d.set.call(el, val); } else { el.value = val; }
        el.dispatchEvent(new Event('input',  {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
        el.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
        return el.value === val ? 'ok' : 'mismatch';
    })()
    """ % (json.dumps(selector), json.dumps(value))
    r = js(sb, script)

    if r == 'ok':
        print(f"  ✅ {label}已填入（JS，{len(value)} 字符）")
        return True
    if r == 'no-el':
        print(f"  ❌ {label}未找到元素: {selector}")
        return False

    print(f"  ⚠️ {label} JS 赋值未生效，改用键盘输入...")
    js(sb, r"""
    (function(){
        var el = document.querySelector(%s);
        if (el) { el.focus(); el.select && el.select(); }
    })()
    """ % json.dumps(selector))
    time.sleep(0.3)
    _xdotool_key("ctrl+a")
    _xdotool_type(value)
    time.sleep(0.5)

    got = js(sb, r"""
    (function(){
        var el = document.querySelector(%s);
        return el ? el.value.length : -1;
    })()
    """ % json.dumps(selector))
    ok = isinstance(got, int) and got == len(value)
    print(f"  {'✅' if ok else '❌'} {label}键盘输入后长度: {got}（期望 {len(value)}）")
    return ok


def js_find_btn(sb, keywords, mark):
    """按文字找可点击元素并打标记，返回按钮文字"""
    script = r"""
    (function(){
        var kws = %s, mark = %s;
        function norm(s){ return (s || '').replace(/\s+/g, ' ').trim(); }
        function vis(el){
            var s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
            return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
        }
        function hit(t){
            if (!t || t.length > 24) return false;
            var low = t.toLowerCase();
            for (var i = 0; i < kws.length; i++) {
                if (low.indexOf(String(kws[i]).toLowerCase()) >= 0) return true;
            }
            return false;
        }
        document.querySelectorAll('[' + mark + ']').forEach(function(e){ e.removeAttribute(mark); });

        var nodes = document.querySelectorAll(
            'button, input[type=submit], input[type=button], a, ' +
            '[role=button], div, span, li, p');
        var best = null;
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var t = norm(el.innerText || el.value || el.textContent);
            if (!hit(t) || !vis(el)) continue;
            var childHit = false;
            for (var j = 0; j < el.children.length; j++) {
                if (hit(norm(el.children[j].innerText || el.children[j].textContent))) {
                    childHit = true; break;
                }
            }
            if (childHit) continue;
            var tag = el.tagName.toLowerCase();
            var score = (tag === 'button' || tag === 'input') ? 3 : (tag === 'a' ? 2 : 1);
            if (!best || score > best.score) best = {el: el, score: score, text: t};
        }
        if (!best) return null;
        best.el.setAttribute(mark, '1');
        return best.text;
    })()
    """ % (json.dumps(keywords), json.dumps(mark))
    return js(sb, script)


# ============ 页面结构诊断 ============
_DUMP_JS = r"""
(function(){
    function vis(el){ return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length); }
    var inputs = [];
    document.querySelectorAll('input, textarea').forEach(function(el){
        inputs.push({
            type: el.type || '', name: el.name || '', id: el.id || '',
            ph: el.placeholder || '', cls: (el.className || '').toString().slice(0, 60),
            ac: el.getAttribute('autocomplete') || '', visible: vis(el)
        });
    });
    var buttons = [];
    document.querySelectorAll('button, input[type=submit], a').forEach(function(b){
        var t = (b.innerText || b.value || '').replace(/\s+/g, ' ').trim();
        if (t && t.length <= 24) buttons.push(t);
    });
    var frames = [];
    document.querySelectorAll('iframe').forEach(function(f){ frames.push((f.src || '').slice(0, 80)); });
    return {
        url: location.href, ready: document.readyState,
        forms: document.querySelectorAll('form').length,
        inputs: inputs, buttons: buttons.slice(0, 30), iframes: frames,
        bodyText: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 500)
    };
})()
"""


def dump_page(sb, tag: str):
    info = js(sb, _DUMP_JS)
    if info:
        print(f"🧭 [{tag}] 页面结构诊断:")
        print(f"   URL: {info.get('url')}  readyState: {info.get('ready')}  form 数: {info.get('forms')}")
        print(f"   iframe: {info.get('iframes')}")
        print(f"   按钮文字: {info.get('buttons')}")
        for i, x in enumerate(info.get('inputs') or []):
            print(f"   input[{i}] {json.dumps(x, ensure_ascii=False)}")
        print(f"   正文摘要: {info.get('bodyText')}")
    try:
        with open(f"{tag}.html", "w", encoding="utf-8") as f:
            f.write(sb.get_page_source() or "")
        sb.save_screenshot(f"{tag}.png")
        print(f"   💾 已保存 {tag}.html / {tag}.png")
    except Exception:
        pass


# ============ 表单定位 ============
_FIND_FORM_JS = r"""
(function(){
    function vis(el){
        if (!el) return false;
        var s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }
    document.querySelectorAll('[data-kx-user],[data-kx-pass]').forEach(function(e){
        e.removeAttribute('data-kx-user'); e.removeAttribute('data-kx-pass');
    });

    var all = Array.prototype.slice.call(document.querySelectorAll('input'));
    var pass = all.filter(function(e){ return e.type === 'password' && vis(e); })[0] || null;

    var userSel = [
        'input[name="email"]','input[name="Email"]','input[name="username"]','input[name="user"]',
        'input[name="account"]','input[name="login"]','input[name="userName"]',
        'input#email','input#username','input#account','input#user',
        'input[type="email"]','input[autocomplete="email"]','input[autocomplete="username"]',
        'input[placeholder*="邮箱"]','input[placeholder*="账号"]','input[placeholder*="帐号"]',
        'input[placeholder*="用户名"]'
    ];
    var user = null;
    for (var i = 0; i < userSel.length && !user; i++) {
        var c = document.querySelectorAll(userSel[i]);
        for (var j = 0; j < c.length; j++) {
            if (c[j].type !== 'password' && vis(c[j])) { user = c[j]; break; }
        }
    }
    if (!user && pass) {
        var idx = all.indexOf(pass);
        for (var k = idx - 1; k >= 0; k--) {
            var t = all[k].type;
            if ((t === 'text' || t === 'email' || t === '' || t === 'tel') && vis(all[k])) { user = all[k]; break; }
        }
    }
    if (user) user.setAttribute('data-kx-user', '1');
    if (pass) pass.setAttribute('data-kx-pass', '1');
    return {
        user: !!user, pass: !!pass,
        userInfo: user ? {type:user.type, name:user.name, id:user.id, ph:user.placeholder} : null,
        passInfo: pass ? {type:pass.type, name:pass.name, id:pass.id, ph:pass.placeholder} : null
    };
})()
"""


# ============ Turnstile ============
_EXPAND_JS = r"""
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (ts) {
        var el = ts;
        for (var i = 0; i < 20; i++) {
            el = el.parentElement;
            if (!el) break;
            var s = window.getComputedStyle(el);
            if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
                el.style.overflow = 'visible';
            el.style.minWidth = 'max-content';
        }
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.indexOf('challenges.cloudflare.com') >= 0) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = r"""
(function(){
    if (document.querySelector('input[name="cf-turnstile-response"]')) return true;
    if (document.querySelector('.cf-turnstile, #cf-turnstile, [data-sitekey]')) return true;
    var fs = document.querySelectorAll('iframe');
    for (var i = 0; i < fs.length; i++) {
        var s = fs[i].src || '';
        if (s.indexOf('challenges.cloudflare.com') >= 0 || s.indexOf('turnstile') >= 0) return true;
    }
    return false;
})()
"""

_SOLVED_JS = r"""
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    if (i) return !!(i.value && i.value.length > 20);
    var fs = document.querySelectorAll('iframe');
    for (var k = 0; k < fs.length; k++) {
        if ((fs[k].src || '').indexOf('challenges.cloudflare.com') >= 0) return false;
    }
    return true;
})()
"""

_COORDS_JS = r"""
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.indexOf('cloudflare') >= 0 || src.indexOf('turnstile') >= 0 || src.indexOf('challenges') >= 0) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var box = document.querySelector('.cf-turnstile, [data-sitekey]');
    if (box) {
        var rb = box.getBoundingClientRect();
        if (rb.width > 0 && rb.height > 0)
            return {cx: Math.round(rb.x + 30), cy: Math.round(rb.y + rb.height / 2)};
    }
    return null;
})()
"""

_WININFO_JS = r"""
(function(){
    return {sx: window.screenX || 0, sy: window.screenY || 0,
            oh: window.outerHeight, ih: window.innerHeight};
})()
"""


def _click_turnstile(sb):
    coords = js(sb, _COORDS_JS)
    if not coords:
        print("  ⚠️ 无法定位 Turnstile 坐标")
        return
    wi = js(sb, _WININFO_JS) or {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
    bar = wi["oh"] - wi["ih"]
    ax = coords["cx"] + wi["sx"]
    ay = coords["cy"] + wi["sy"] + bar
    print(f"  🖱️ 点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)


def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    if js(sb, _SOLVED_JS) is True:
        print("  ✅ 已静默通过")
        return True

    for _ in range(3):
        js(sb, _EXPAND_JS)
        time.sleep(0.5)

    for attempt in range(6):
        if js(sb, _SOLVED_JS) is True:
            print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次）")
            return True
        js(sb, _EXPAND_JS)
        time.sleep(0.3)
        _click_turnstile(sb)
        for _ in range(8):
            time.sleep(0.5)
            if js(sb, _SOLVED_JS) is True:
                print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次）")
                return True
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False


def wait_cf_interstitial(sb, timeout=40) -> bool:
    """等待 CF 整页挑战结束"""
    for i in range(timeout):
        try:
            title = (sb.get_title() or "").lower()
        except Exception:
            title = ""
        body = js_body_text(sb).lower()
        blocked = ("just a moment" in title or "attention required" in title
                   or "checking your browser" in body or "verify you are human" in body)
        if not blocked:
            return True
        if i % 5 == 0:
            print(f"  ⏳ CF 整页验证中... ({i}s)")
        try:
            sb.uc_gui_click_captcha()
        except Exception:
            pass
        time.sleep(1)
    return False


# ============ 登录 ============
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=6)
    time.sleep(3)
    wait_cf_interstitial(sb)

    print("⏳ 等待登录表单渲染（SPA 需要时间）...")
    form = None
    for i in range(40):
        form = js(sb, _FIND_FORM_JS)
        if form and form.get("pass"):
            print(f"  ✅ 已找到表单（{i + 1}s）")
            print(f"     账号框: {form.get('userInfo')}")
            print(f"     密码框: {form.get('passInfo')}")
            break
        time.sleep(1)
    else:
        print("❌ 页面未渲染出登录表单")
        dump_page(sb, "login_load_fail")
        return False

    # 关闭 Cookie / 公告弹窗
    t = js_find_btn(sb, _POPUP_KEYWORDS, "data-kx-pop")
    if t:
        print(f"🍪 关闭弹窗: {t}")
        js_click(sb, "[data-kx-pop]")
        time.sleep(0.5)
        js(sb, _FIND_FORM_JS)  # 弹窗关闭后重新标记

    if form.get("user"):
        print("📧 填写账号...")
        if not js_fill(sb, "[data-kx-user]", EMAIL, "账号"):
            dump_page(sb, "fill_user_fail")
            return False
        time.sleep(0.4)
    else:
        print("ℹ️ 该站点无账号框，仅需密码")

    print("🔑 填写密码...")
    if not js_fill(sb, "[data-kx-pass]", PASSWORD, "密码"):
        dump_page(sb, "fill_pass_fail")
        return False
    time.sleep(1)

    if js(sb, _EXISTS_JS) is True:
        if not handle_turnstile(sb):
            print("❌ 登录页 Turnstile 验证失败")
            dump_page(sb, "login_turnstile_fail")
            return False
    else:
        print("ℹ️ 登录页未检测到 Turnstile")

    print("🖱️ 提交登录...")
    submitted = False
    if js(sb, "(function(){return !!document.querySelector('button[type=\"submit\"]');})()") is True:
        submitted = js_click(sb, 'button[type="submit"]')
        if submitted:
            print("  已点击 submit 按钮")
    if not submitted:
        t = js_find_btn(sb, _LOGIN_BTN_KEYWORDS, "data-kx-login")
        if t:
            print(f"  按钮文字: {t}")
            submitted = js_click(sb, "[data-kx-login]")
    if not submitted:
        print("  ⚠️ 未找到登录按钮，改用回车提交")
        js(sb, "(function(){var e=document.querySelector('[data-kx-pass]'); if(e) e.focus();})()")
        time.sleep(0.3)
        _xdotool_key("Return")

    print("⏳ 等待登录跳转...")
    for _ in range(30):
        time.sleep(1)
        if "login" not in sb.get_current_url().split('?')[0].lower():
            break

    cur = sb.get_current_url()
    if "login" not in cur.split('?')[0].lower():
        print(f"✅ 登录成功！(URL: {cur}, Title: {sb.get_title()})")
        return True

    print(f"❌ 登录失败，仍在登录页。(URL: {cur}, Title: {sb.get_title()})")
    dump_page(sb, "login_failed")
    return False


# ============ 签到 ============
def check_in(sb):
    if DASHBOARD_URL.rstrip('/') not in sb.get_current_url():
        print(f"🌐 打开签到页面: {DASHBOARD_URL}")
        sb.uc_open_with_reconnect(DASHBOARD_URL, reconnect_time=6)
    else:
        print(f"🌐 已在签到页面: {sb.get_current_url()}")
    time.sleep(3)
    wait_cf_interstitial(sb)

    print("🔍 查找签到按钮...")
    btn_text = None
    for _ in range(20):
        btn_text = js_find_btn(sb, _CHECKIN_KEYWORDS, "data-kx-checkin")
        if btn_text:
            break
        time.sleep(1)

    if not btn_text:
        body = js_body_text(sb)
        if any(k in body for k in _ALREADY_KEYWORDS):
            return True, "今日已签到"
        print("❌ 未找到签到按钮")
        dump_page(sb, "checkin_not_found")
        return False, "未找到签到按钮"

    print(f"  找到: {btn_text}")
    if any(k in btn_text for k in _ALREADY_KEYWORDS):
        return True, f"今日已签到（按钮: {btn_text}）"

    print("🖱️ 点击签到...")
    if not js_click(sb, "[data-kx-checkin]"):
        return False, "点击签到按钮失败"
    time.sleep(2)

    t = js_find_btn(sb, _CONFIRM_KEYWORDS, "data-kx-ok")
    if t:
        print(f"  确认弹窗: {t}")
        js_click(sb, "[data-kx-ok]")
        time.sleep(1.5)

    if js(sb, _EXISTS_JS) is True:
        print("🔍 签到触发了 Turnstile 验证")
        if not handle_turnstile(sb):
            dump_page(sb, "checkin_turnstile_fail")
            return False, "签到时 Turnstile 验证失败"

    print("⏳ 等待签到结果...")
    for _ in range(40):
        time.sleep(0.5)
        body = js_body_text(sb)
        for kw in _SUCCESS_KEYWORDS:
            if kw in body:
                return True, f"签到成功（页面提示含「{kw}」）"
        now = js_text(sb, "[data-kx-checkin]")
        if now and any(k in now for k in _ALREADY_KEYWORDS):
            return True, f"签到成功（按钮变为「{now}」）"

    dump_page(sb, "checkin_no_result")
    return False, "未检测到签到成功提示"


# ============ 主流程 ============
def main():
    print("#" * 25)
    print("   Hohai TV 自动签到")
    print("#" * 25)

    if not PASSWORD:
        print("❌ 未设置密码环境变量 HOHAI_PASSWORD")
        send_tg_message("❌", "配置错误", "未设置 HOHAI_PASSWORD")
        return

    is_proxy = os.environ.get("IS_PROXY", "false").lower() == "true"
    sb_kwargs = {"uc": True, "headless": False}
    if is_proxy:
        proxy_str = "http://127.0.0.1:1081"
        print(f"🔗 挂载 sing-box 代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")

    with SB(**sb_kwargs) as sb:
        print("✅ 浏览器已启动")
        try:
            sb.set_window_size(1600, 1000)
        except Exception:
            pass
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"🌐 当前出口 IP: {sb.get_text('body').strip()}")
        except Exception:
            pass

        if login(sb):
            ok, msg = check_in(sb)
            if ok:
                print(f"✅ {msg}")
                send_tg_message("✅", "签到成功", msg)
            else:
                print(f"❌ 签到失败: {msg}")
                send_tg_message("❌", "签到失败", msg)
        else:
            print("\n❌ 登录失败，终止后续签到操作。")
            send_tg_message("❌", "登录失败", "详见 Actions 日志与截图")


if __name__ == "__main__":
    main()
