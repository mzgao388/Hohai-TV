#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
import re
from seleniumbase import SB

# ============ 配置区 ============
EMAIL        = os.environ.get("HOHAI_EMAIL") or os.environ.get("LUNES_EMAIL") or ""     # 登录邮箱
PASSWORD     = os.environ.get("HOHAI_PASSWORD") or os.environ.get("LUNES_PASSWORD") or ""  # 登录密码
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""      # chat id,可选
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""    # bot token,可选

LOGIN_URL     = "https://tv.hohai.eu.org/login"
DASHBOARD_URL = "https://tv.hohai.eu.org/dashboard"

# 签到按钮候选关键字
_CHECKIN_KEYWORDS = ["签到", "打卡", "每日签到", "check-in", "check in", "checkin"]
# 已签到状态关键字
_ALREADY_KEYWORDS = ["已签到", "已打卡", "今日已签到"]
# 签到成功关键字
_SUCCESS_KEYWORDS = ["签到成功", "打卡成功", "今日签到", "签到奖励"]

#  Telegram 推送
def send_tg_message(status_icon, status_text, extra_text=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****'

    text = (
        f"📺 Hohai TV 保活通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 登录账户: {masked_email}\n"
        f"⏱️ 执行时间: {current_time_str}"
    )
    if extra_text:
        text += f"\n\n{extra_text}"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("📩 Telegram 通知发送成功！")
        else:
            print(f"  ⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  ⚠️ Telegram 通知发送异常: {e}")

# ============ Cloudflare Turnstile 相关 JS ============
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"⚠️ 获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("⚠️ 无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}

    bar = wi["oh"] - wi["ih"]
    ax  = coords["cx"] + wi["sx"]
    ay  = coords["cy"] + wi["sy"] + bar
    print(f"🖱️ 尝试点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)

def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)

    if sb.execute_script(_SOLVED_JS):
        print("✅ 已静默通过")
        return True

    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)

    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
            return True
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)

        _click_turnstile(sb)

        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False

# ============ 登录 ============
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)

    # 该站点登录页不存在 Cloudflare 人机验证，只是前端 SPA 需要时间渲染表单。
    # 这里改为直接轮询等待表单元素出现，不再假设存在 CF challenge。
    print("⏳ 等待前端页面渲染出登录表单...")
    form_ready = False
    for i in range(30):
        try:
            page_src = sb.get_page_source() or ""
        except Exception:
            page_src = ""
        if 'name="email"' in page_src.lower():
            form_ready = True
            print(f"✅ 登录表单已渲染（{i+1}s）")
            break
        time.sleep(1)

    if not form_ready:
        try:
            sb.wait_for_element('input[name="email"]', timeout=15)
            form_ready = True
        except Exception:
            try:
                sb.wait_for_element('input[name="Email"]', timeout=5)
                form_ready = True
            except Exception:
                pass

    if not form_ready:
        print("❌ 页面未加载出登录表单")
        cur_url = sb.get_current_url()
        page_title = sb.get_title() or ""
        print(f" 当前 URL: {cur_url}")
        print(f" 当前标题: {page_title}")
        sb.save_screenshot("login_load_fail.png")
        return False

    print("🍪 关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    print("📧 填写邮箱...")
    js_fill_input(sb, 'input[name="email"]', EMAIL)
    time.sleep(0.3)

    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="password"]', PASSWORD)
    time.sleep(1)

    # 仅当页面上确实存在 Turnstile 元素时才尝试处理，避免误判导致流程卡死
    if sb.execute_script(_EXISTS_JS):
        print("🔍 检测到 Turnstile 元素，开始处理...")
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile，直接提交登录")

    print("🖱️ 点击登录按钮提交登录...")
    sb.click('button[type="submit"]')

    print("⏳ 等待登录跳转...")
    for _ in range(30):
        time.sleep(1)
        cur_url = sb.get_current_url().split('?')[0].lower()
        if "login" not in cur_url:
            break

    cur_url = sb.get_current_url().split('?')[0].lower()
    page_title = sb.get_title() or ""
    if "login" not in cur_url:
        print(f"✅ 登录成功！(URL: {sb.get_current_url()}, Title: {page_title})")
        return True

    print(f"❌ 登录失败，页面未跳转。(URL: {sb.get_current_url()}, Title: {page_title})")
    sb.save_screenshot("login_failed.png")
    return False

# ============ 查找签到按钮 ============
def find_checkin_button(sb):
    for tag in ["button", "a", "span", "div"]:
        try:
            elems = sb.find_elements(tag)
        except Exception:
            continue
        for el in elems:
            try:
                text = (el.text or "").strip()
            except Exception:
                text = ""
            if not text or len(text) > 20:
                continue
            if any(k.lower() in text.lower() for k in _CHECKIN_KEYWORDS):
                return el, text
    return None, ""

# ============ 等待签到成功 ============
def wait_checkin_success(sb, btn, btn_text):
    for _ in range(40):  # 最长约 20 秒
        time.sleep(0.5)
        try:
            src = sb.get_page_source() or ""
        except Exception:
            src = ""
        for kw in _SUCCESS_KEYWORDS:
            if kw in src:
                return True, f"成功（匹配关键字: {kw}）"
        try:
            new_text = (btn.text or "").strip()
        except Exception:
            new_text = ""
        if new_text and any(k in new_text for k in _ALREADY_KEYWORDS):
            return True, f"成功（按钮变为: {new_text}）"
        try:
            for sel in ['.el-message', '.el-notification', '.toast', '.el-message__content']:
                for t in sb.find_elements(sel):
                    txt = (t.text or "")
                    if any(k in txt for k in _SUCCESS_KEYWORDS):
                        return True, f"成功（提示: {txt.strip()}）"
        except Exception:
            pass
    return False, ""

# ============ 签到(含 CF 验证处理) ============
def check_in(sb) -> (bool, str):
    print(f"🌐 打开签到页面: {DASHBOARD_URL}")
    sb.uc_open_with_reconnect(DASHBOARD_URL, reconnect_time=5)
    time.sleep(4)

    # 等待 CF 整页验证自动通过
    for i in range(30):
        try:
            title = sb.get_title() or ""
        except Exception:
            title = ""
        if "just a moment" in title.lower() or "attention required" in title.lower():
            print(f"⚠️ 检测到 CF 验证页，等待自动通过... ({i+1}s)")
            time.sleep(1)
            continue
        break

    btn, btn_text = find_checkin_button(sb)
    if not btn:
        try:
            src = sb.get_page_source() or ""
            if any(k in src for k in _ALREADY_KEYWORDS):
                return True, "今日已签到"
        except Exception:
            pass
        return False, "未找到签到按钮"

    if any(k in btn_text for k in _ALREADY_KEYWORDS):
        return True, f"今日已签到（按钮: {btn_text}）"

    print(f"🖱️ 点击签到按钮: {btn_text}")
    try:
        sb.execute_script("arguments[0].click();", btn)
    except Exception:
        try:
            btn.click()
        except Exception:
            return False, "点击签到按钮失败"
    time.sleep(2)

    # 处理可能的确认弹窗
    try:
        for b in sb.find_elements("button"):
            t = (b.text or "").strip()
            if t in ("确认", "确定", "好的", "OK", "同意"):
                b.click()
                time.sleep(1)
                break
    except Exception:
        pass

    # 处理点击签到后弹出的 Turnstile 验证
    try:
        if sb.execute_script(_EXISTS_JS):
            print("🔍 检测到 Turnstile，开始处理...")
            if not handle_turnstile(sb):
                return False, "签到时的 Turnstile 验证失败"
    except Exception:
        pass

    # 等待签到成功
    print("⏳ 等待签到结果...")
    ok, msg = wait_checkin_success(sb, btn, btn_text)
    if ok:
        print(f"✅ {msg}")
        return True, msg

    return False, msg or "未检测到签到成功提示"

# ============ 主流程 ============
def main():
    print("#" * 25)
    print("   Hohai TV 自动签到")
    print("#" * 25)

    is_proxy = os.environ.get("IS_PROXY", "false").lower() == "true"
    sb_kwargs = {"uc": True, "headless": False}

    if is_proxy:
        proxy_str = "http://127.0.0.1:1081"
        print(f"🔗 挂载sing-box代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")

    with SB(**sb_kwargs) as sb:
        print("✅ 浏览器已启动")
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"🌐 当前出口真实 IP: {sb.get_text('body')}")
        except Exception:
            pass

        if login(sb):
            success, msg = check_in(sb)
            if success:
                send_tg_message("✅", "签到成功", msg)
            else:
                error_msg = msg or "未知错误"
                print(f"❌ 签到失败: {error_msg}")
                send_tg_message("❌", "签到失败", error_msg)
        else:
            print("\n❌ 登录失败，终止后续签到操作。")
            send_tg_message("❌", "登录失败", "")

if __name__ == "__main__":
    main()
