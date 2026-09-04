#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
import re
from seleniumbase import SB

# ============ 配置区 ============
# 从环境变量获取账号密码和 TG 配置
EMAIL        = os.environ.get("HOHAI_EMAIL") or os.environ.get("LUNES_EMAIL") or ""     # 登录邮箱
PASSWORD     = os.environ.get("HOHAI_PASSWORD") or os.environ.get("LUNES_PASSWORD") or ""  # 登录密码
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""      # chat id,可选
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""    # bot token,可选

LOGIN_URL     = "https://tv.hohai.eu.org/login"
DASHBOARD_URL = "https://tv.hohai.eu.org/dashboard"

# 签到按钮候选关键字
_CHECKIN_KEYWORDS  = ["签到", "打卡", "每日签到", "check-in", "check in", "checkin"]
# 已签到状态关键字（用于检测“今天已经签过”）
_ALREADY_KEYWORDS  = ["已签到", "已打卡", "今日已签到"]
# 签到成功关键字（页面/提示中出现任意一个即认为成功）
_SUCCESS_KEYWORDS  = ["签到成功", "打卡成功", "今日签到", "签到奖励"]

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

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage
