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

_CHECKIN_KEYWORDS = ["签到", "打卡", "每日签到", "check-in", "checkin"]
_ALREADY_KEYWORDS = ["已签到", "已打卡", "今日已签到", "明日再来", "已经签到"]
_SUCCESS_KEYWORDS = ["签到成功", "打卡成功", "签到奖励", "获得", "已签到"]
_LOGIN_BTN_KEYWORDS = ["登录", "登 录", "登入", "提交", "login", "log in", "sign in", "submit"]


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
        inputs: inputs, buttons: buttons.slice(0, 25), iframes: frames,
        bodyText: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 400)
    };
})()
"""


def dump_page(sb, tag: str):
    """打印页面结构 + 保存 HTML/截图，便于定位选择器"""
    try:
        info = sb.execute_script(_DUMP_JS)
        print(f"🧭 [{tag}] 页面结构诊断:")
        print(f"   URL: {info.get('url')}  readyState: {info.get('ready')}  form 数: {info.get('forms')}")
        print(f"   iframe: {info.get('iframes')}")
        print(f"   按钮文字: {info.get('buttons')}")
        for i, x in enumerate(info.get('inputs') or []):
            print(f"   input[{i}] {json.dumps(x, ensure_ascii=False)}")
        print(f"   正文摘要: {info.get('bodyText')}")
    except Exception as e:
        print(f"   ⚠️ 诊断脚本执行失败: {e}")
    try:
        with open(f"{tag}.html", "w", encoding="utf-8") as f:
            f.write(sb.get_page_source() or "")
        sb.save_screenshot(f"{tag}.png")
        print(f"   💾 已保存 {tag}.html / {tag}.png")
    except Exception:
        pass


# ============ 通用表单定位（核心修复） ============
# 找到账号框和密码框，并打上标记属性，Python 侧再用标记选择器操作
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
        'input[placeholder*="用户名"]','input[placeholder*="mail" i]','input[placeholder*="user" i]'
    ];
    var user = null;
    for (var i = 0; i < userSel.length && !user; i++) {
        var c = document.querySelectorAll(userSel[i]);
        for (var j = 0; j < c.length; j++) {
            if (c[j].type !== 'password' && vis(c[j])) { user = c[j]; break; }
        }
    }
    // 兜底：密码框之前最近的一个可见文本输入框
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

_FILL_JS = r"""
(function(sel, val){
    var el = document.querySelector(sel);
    if (!el) return false;
    el.focus();
    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    if (setter) { setter.call(el, val); } else { el.value = val; }
    el.dispatchEvent(new Event('input',  {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
    return true;
})(arguments[0], arguments[1])
"""

# 按文字找按钮并标记（SPA 里常常没有 type=submit）
_FIND_BTN_JS = r"""
(function(kws, mark){
    function norm(s){ return (s || '').replace(/\s+/g, ' ').trim(); }
    function vis(el){ return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length); }
    document.querySelectorAll('[' + mark + ']').forEach(function(e){ e.removeAttribute(mark); });

    var nodes = document.querySelectorAll('button, input[type=submit], a, div[role=button], span[role=button], div, li');
    var best = null;
    for (var i = 0; i < nodes.length; i++) {
        var el = nodes[i];
        var t = norm(el.innerText || el.value || el.textContent);
        if (!t || t.length > 24 || !vis(el)) continue;
        var hit = kws.some(function(k){ return t.toLowerCase().indexOf(k.toLowerCase()) >= 0; });
        if (!hit) continue;
        // 只取最内层节点，避免点到外层大容器
        var childHit = false;
        for (var j = 0; j < el.children.length; j++) {
            var ct = norm(el.children[j].innerText || el.children[j].textContent);
            if (ct && ct.length <= 24 && kws.some(function(k){ return ct.toLowerCase().indexOf(k.toLowerCase()) >= 0; })) {
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
})(arguments[0], arguments[1])
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
    if (i && i.value && i.value.length > 20) return true;
    // 无隐藏域的站点：验证成功后 iframe 一般会消失
    if (!document.querySelector('input[name="cf-turnstile-response"]')) {
        var fs = document.querySelectorAll('iframe');
        for (var k = 0; k < fs.length; k++) {
            var s = fs[k].src || '';
            if (s.indexOf('challenges.cloudflare.com') >= 0) return false;
        }
        return true;
    }
    return false;
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
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")


def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"  ⚠️ 获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("  ⚠️ 无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
    bar = wi["oh"] - wi["ih"]
    ax = coords["cx"] + wi["sx"]
    ay = coords["cy"] + wi["sy"] + bar
    print(f"  🖱️ 点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)


def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    if sb.execute_script(_SOLVED_JS):
        print("  ✅ 已静默通过")
        return True

    for _ in range(3):
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.5)

    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次）")
            return True
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.3)
        _click_turnstile(sb)
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次）")
                return True
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False


def wait_cf_interstitial(sb, timeout=40):
    """等待 CF 整页挑战（Just a moment / 5 秒盾）结束"""
    for i in range(timeout):
        try:
            title = (sb.get_title() or "").lower()
            body = (sb.execute_script("return document.body ? document.body.innerText : ''") or "").lower()
        except Exception:
            title, body = "", ""
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
        try:
            form = sb.execute_script(_FIND_FORM_JS)
        except Exception:
            form = None
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

    # Cookie / 公告弹窗
    try:
        for txt in ["Accept", "同意", "我知道了", "确定", "关闭"]:
            t = sb.execute_script(_FIND_BTN_JS, [txt], "data-kx-pop")
            if t:
                sb.execute_script("var e=document.querySelector('[data-kx-pop]'); if(e) e.click();")
                print(f"🍪 关闭弹窗: {t}")
                time.sleep(0.5)
                break
    except Exception:
        pass

    if form.get("user"):
        print("📧 填写账号...")
        sb.execute_script(_FILL_JS, '[data-kx-user]', EMAIL)
        time.sleep(0.4)
    else:
        print("ℹ️ 该站点无账号框，仅需密码")

    print("🔑 填写密码...")
    sb.execute_script(_FILL_JS, '[data-kx-pass]', PASSWORD)
    time.sleep(1)

    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("❌ 登录页 Turnstile 验证失败")
            dump_page(sb, "login_turnstile_fail")
            return False
    else:
        print("ℹ️ 登录页未检测到 Turnstile")

    print("🖱️ 提交登录...")
    submitted = False
    try:
        if sb.is_element_present('button[type="submit"]'):
            sb.click('button[type="submit"]')
            submitted = True
    except Exception:
        pass
    if not submitted:
        t = sb.execute_script(_FIND_BTN_JS, _LOGIN_BTN_KEYWORDS, "data-kx-login")
        if t:
            print(f"  按钮: {t}")
            sb.execute_script("var e=document.querySelector('[data-kx-login]'); if(e) e.click();")
            submitted = True
    if not submitted:
        print("  ⚠️ 未找到登录按钮，改用回车提交")
        try:
            sb.send_keys('[data-kx-pass]', "\n")
        except Exception:
            pass

    print("⏳ 等待登录跳转...")
    for _ in range(30):
        time.sleep(1)
        cur = sb.get_current_url().split('?')[0].lower()
        if "login" not in cur:
            break

    cur = sb.get_current_url()
    if "login" not in cur.split('?')[0].lower():
        print(f"✅ 登录成功！(URL: {cur}, Title: {sb.get_title()})")
        return True

    print(f"❌ 登录失败，仍在登录页。(URL: {cur}, Title: {sb.get_title()})")
    dump_page(sb, "login_failed")
    return False


# ============ 签到 ============
_FIND_CHECKIN_JS = _FIND_BTN_JS  # 复用同一套查找逻辑


def check_in(sb):
    print(f"🌐 打开签到页面: {DASHBOARD_URL}")
    if DASHBOARD_URL.rstrip('/') not in sb.get_current_url():
        sb.uc_open_with_reconnect(DASHBOARD_URL, reconnect_time=6)
    time.sleep(3)
    wait_cf_interstitial(sb)

    print("🔍 查找签到按钮...")
    btn_text = None
    for _ in range(20):
        try:
            btn_text = sb.execute_script(_FIND_CHECKIN_JS, _CHECKIN_KEYWORDS, "data-kx-checkin")
        except Exception:
            btn_text = None
        if btn_text:
            break
        time.sleep(1)

    if not btn_text:
        try:
            body = sb.execute_script("return document.body.innerText") or ""
        except Exception:
            body = ""
        if any(k in body for k in _ALREADY_KEYWORDS):
            return True, "今日已签到"
        print("❌ 未找到签到按钮")
        dump_page(sb, "checkin_not_found")
        return False, "未找到签到按钮"

    print(f"  找到: {btn_text}")
    if any(k in btn_text for k in _ALREADY_KEYWORDS):
        return True, f"今日已签到（按钮: {btn_text}）"

    print("🖱️ 点击签到...")
    try:
        sb.execute_script("var e=document.querySelector('[data-kx-checkin]'); if(e) e.click();")
    except Exception:
        try:
            sb.click('[data-kx-checkin]')
        except Exception:
            return False, "点击签到按钮失败"
    time.sleep(2)

    # 二次确认弹窗
    try:
        t = sb.execute_script(_FIND_BTN_JS, ["确认", "确定", "好的", "OK", "立即签到"], "data-kx-ok")
        if t:
            print(f"  确认弹窗: {t}")
            sb.execute_script("var e=document.querySelector('[data-kx-ok]'); if(e) e.click();")
            time.sleep(1.5)
    except Exception:
        pass

    # 签到触发的 Turnstile
    try:
        if sb.execute_script(_EXISTS_JS):
            print("🔍 签到触发了 Turnstile 验证")
            if not handle_turnstile(sb):
                dump_page(sb, "checkin_turnstile_fail")
                return False, "签到时 Turnstile 验证失败"
    except Exception:
        pass

    print("⏳ 等待签到结果...")
    for _ in range(40):
        time.sleep(0.5)
        try:
            body = sb.execute_script("return document.body.innerText") or ""
        except Exception:
            body = ""
        for kw in _SUCCESS_KEYWORDS:
            if kw in body:
                return True, f"签到成功（页面提示含「{kw}」）"
        try:
            now = sb.execute_script(
                "var e=document.querySelector('[data-kx-checkin]'); return e ? e.innerText.trim() : '';") or ""
        except Exception:
            now = ""
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
