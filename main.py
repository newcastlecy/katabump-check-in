import os
import time
import requests
import zipfile
import io
import datetime
import re
from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 基础工具 ====================
def log(message):
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] {message}", flush=True)

def download_silk():
    extract_dir = "silk_ext"
    if os.path.exists(extract_dir): return os.path.abspath(extract_dir)
    try:
        url = "https://clients2.google.com/service/update2/crx?response=redirect&prodversion=122.0&acceptformat=crx2,crx3&x=id%3Dajhmfdgkijocedmfjonnpjfojldioehi%26uc"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, stream=True)
        if resp.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                zf.extractall(extract_dir)
            return os.path.abspath(extract_dir)
    except: pass
    return None

# ==================== 核心逻辑 ====================

def pass_full_page_shield(page):
    """处理全屏盾"""
    for _ in range(3):
        if "just a moment" in page.title.lower():
            log("--- [门神] 正在通过全屏盾...")
            iframe = page.ele('css:iframe[src*="cloudflare"]', timeout=2)
            if iframe: 
                iframe.ele('tag:body').click(by_js=True)
                time.sleep(3)
        else:
            return True
    return False

def pass_modal_captcha(modal):
    """
    【增强版】处理弹窗验证码
    现在会扫描所有 iframe，防止漏网之鱼
    """
    log(">>> [弹窗] 正在深度扫描验证码...")
    
    # 1. 尝试精准定位 Cloudflare/Turnstile
    # 扩大搜索范围，timeout 给足 10秒
    target_iframe = modal.ele('css:iframe[src*="cloudflare"], iframe[src*="turnstile"]', timeout=10)
    
    # 2. 如果没找到，扫描弹窗内所有 iframe (盲狙)
    if not target_iframe:
        log("⚠️ 精准定位失败，尝试扫描弹窗内所有 iframe...")
        all_iframes = modal.eles('tag:iframe')
        for frame in all_iframes:
            # 排除太小的不可见 iframe
            if frame.states.is_displayed and frame.rect.size[0] > 50:
                target_iframe = frame
                break
    
    if target_iframe:
        log(">>> [弹窗] 👁️ 锁定验证码 iframe，准备点击...")
        try:
            # 点击 body
            target_iframe.ele('tag:body').click(by_js=True)
            log(">>> [弹窗] 👆 已点击，强制等待 5 秒 (让它变绿)...")
            time.sleep(5)
            return True
        except Exception as e:
            log(f"⚠️ 点击失败: {e}")
    else:
        log(">>> [弹窗] 实在没找到 iframe (可能真的没有，或者加载失败)")
    
    return False

def analyze_page_alert(page):
    """解析提示结果"""
    log(">>> [系统] 读取提示信息...")
    
    # 1. 红色警告 (Fail)
    danger_alert = page.ele('css:.alert.alert-danger')
    if danger_alert and danger_alert.states.is_displayed:
        text = danger_alert.text
        log(f"⬇️ 红色提示: {text}")
        
        if "can't renew" in text.lower():
            match = re.search(r'\(in (\d+) day', text)
            days = match.group(1) if match else "?"
            log(f"✅ [结果] 未到期 (等待 {days} 天)")
            return "SUCCESS_TOO_EARLY"
        elif "captcha" in text.lower():
            log("❌ [失败] 验证码未通过！")
            return "FAIL_CAPTCHA" # 返回特定错误代码，触发重试
        else:
            return "FAIL_OTHER"

    # 2. 绿色成功 (Success)
    success_alert = page.ele('css:.alert.alert-success')
    if success_alert and success_alert.states.is_displayed:
        text = success_alert.text
        log(f"⬇️ 绿色提示: {text}")
        log("🎉 [结果] 续期成功！")
        return "SUCCESS"

    return "UNKNOWN"

# ==================== 主程序 ====================
def job():
    ext_path = download_silk()
    
    co = ChromiumOptions()
    co.set_argument('--headless=new')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--window-size=1920,1080')
    co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    
    if ext_path: co.add_extension(ext_path)
    co.auto_port()

    page = ChromiumPage(co)
    page.set.timeouts(15)

    try:
        email = os.environ.get("KB_EMAIL")
        password = os.environ.get("KB_PASSWORD")
        target_url = os.environ.get("KB_RENEW_URL")
        
        if not all([email, password, target_url]): 
            log("❌ 配置缺失")
            exit(1)

        # Step 1: 登录
        log(">>> [Step 1] 登录...")
        page.get('https://dashboard.katabump.com/auth/login')
        pass_full_page_shield(page)

        if page.ele('css:input[name="email"]'):
            page.ele('css:input[name="email"]').input(email)
            page.ele('css:input[name="password"]').input(password)
            page.ele('css:button#submit').click()
            page.wait.url_change('login', exclude=True, timeout=20)
        
        # ==================== 重试循环 ====================
        # 如果遇到验证码错误，最多重试 3 次
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            log(f"\n🚀 [Step 2] 进入服务器页面 (第 {attempt} 次尝试)...")
            page.get(target_url)
            pass_full_page_shield(page)
            
            # 寻找按钮
            renew_btn = None
            for _ in range(5):
                renew_btn = page.ele('css:button[data-bs-target="#renew-modal"]')
                if renew_btn and renew_btn.states.is_displayed: break
                time.sleep(1)

            if renew_btn:
                log(">>> 点击 Renew 按钮...")
                renew_btn.click(by_js=True)
                
                modal = page.ele('css:.modal-content', timeout=10)
                if modal:
                    # 尝试过盾
                    pass_modal_captcha(modal)
                    
                    confirm_btn = modal.ele('css:button[type="submit"].btn-primary')
                    if confirm_btn:
                        log(">>> 点击 Confirm...")
                        confirm_btn.click(by_js=True)
                        log(">>> 等待响应 (5s)...")
                        time.sleep(5)
                        
                        # 分析结果
                        result = analyze_page_alert(page)
                        
                        if result == "SUCCESS" or result == "SUCCESS_TOO_EARLY":
                            log("🎉 任务完成，退出循环。")
                            break # 成功，结束！
                        
                        if result == "FAIL_CAPTCHA":
                            log("⚠️ 检测到验证码错误，准备刷新重试...")
                            time.sleep(3)
                            continue # 触发下一次循环
                    else:
                        log("❌ 找不到确认按钮")
                else:
                    log("❌ 弹窗未出")
            else:
                log("⚠️ 未找到按钮，检查是否已有提示...")
                result = analyze_page_alert(page)
                if result == "SUCCESS_TOO_EARLY":
                    break
                else:
                    log("❌ 页面加载异常或无按钮")
            
            # 如果是最后一次还没成功，报错退出
            if attempt == max_retries:
                log("❌ 已达到最大重试次数，任务失败。")
                exit(1)

    except Exception as e:
        log(f"❌ 异常: {e}")
        exit(1)
    finally:
        page.quit()

if __name__ == "__main__":
    job()
