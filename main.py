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

def download_and_locate_extension():
    """
    【智能寻址】下载插件并找到 manifest.json 的真实路径
    完美解决 'cf-autoclick-master/cf-autoclick-master' 这种多层嵌套问题
    """
    extract_root = "extensions"
    
    # 1. 只有当文件夹不存在时才下载，避免重复下载
    if not os.path.exists(extract_root):
        log(">>> [插件] 正在下载 cf-autoclick (Master)...")
        try:
            url = "https://codeload.github.com/tenacious6/cf-autoclick/zip/refs/heads/master"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, stream=True)
            if resp.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    zf.extractall(extract_root)
                log(">>> [插件] 解压完成")
            else:
                log(f"❌ [插件] 下载失败: {resp.status_code}")
                return None
        except Exception as e:
            log(f"❌ [插件] 异常: {e}")
            return None

    # 2. 【核心】遍历所有子目录，寻找 manifest.json
    # 无论它藏在第几层目录（例如 cf-autoclick-master/cf-autoclick-master），都能挖出来
    log(">>> [系统] 正在扫描 manifest.json 路径...")
    for root, dirs, files in os.walk(extract_root):
        if "manifest.json" in files:
            log(f"✅ [系统] 锁定插件真实路径: {root}")
            return os.path.abspath(root)
            
    log("❌ [系统] 找遍了也没找到 manifest.json，插件文件可能损坏")
    return None

# ==================== 核心逻辑 ====================

def pass_full_page_shield(page):
    """处理全屏盾"""
    for _ in range(3):
        if "just a moment" in page.title.lower():
            log("--- [门神] 等待插件通过全屏盾...")
            time.sleep(3)
        else:
            return True
    return False

def manual_click_checkbox(modal):
    """
    【双重保险】
    插件失效时的兜底方案：手动点 checkbox
    """
    log(">>> [补刀] 检查是否需要手动点击 Checkbox...")
    
    # 1. 进 iframe 找
    iframe = modal.ele('css:iframe[src*="cloudflare"], iframe[src*="turnstile"]', timeout=3)
    if iframe:
        # 很多时候 checkbox 是 hidden 的，但我们尝试找一下
        checkbox = iframe.ele('css:input[type="checkbox"]', timeout=2)
        if checkbox:
            log(">>> [补刀] 🎯 在 iframe 里点击 Checkbox！")
            # 强制 JS 点击，无视遮挡
            checkbox.click(by_js=True)
            return True
        else:
            # 如果找不到 checkbox，就点 iframe 身体中心
            log(">>> [补刀] 点击 iframe 主体...")
            iframe.ele('tag:body').click(by_js=True)
            return True
            
    # 2. 在外部找
    checkbox = modal.ele('css:input[type="checkbox"]', timeout=1)
    if checkbox:
        log(">>> [补刀] 🎯 在外部点击 Checkbox！")
        checkbox.click(by_js=True)
        return True
        
    log(">>> [补刀] 未找到可点击元素 (可能插件已经处理完毕)")
    return False

def analyze_page_alert(page):
    """解析结果"""
    log(">>> [系统] 检查结果...")
    
    danger = page.ele('css:.alert.alert-danger')
    if danger and danger.states.is_displayed:
        text = danger.text
        log(f"⬇️ 红色提示: {text}")
        if "can't renew" in text.lower():
            match = re.search(r'\(in (\d+) day', text)
            days = match.group(1) if match else "?"
            log(f"✅ [结果] 未到期 (等待 {days} 天)")
            return "SUCCESS_TOO_EARLY"
        elif "captcha" in text.lower():
            return "FAIL_CAPTCHA"
        return "FAIL_OTHER"

    success = page.ele('css:.alert.alert-success')
    if success and success.states.is_displayed:
        log(f"⬇️ 绿色提示: {success.text}")
        log("🎉 [结果] 续期成功！")
        return "SUCCESS"

    return "UNKNOWN"

# ==================== 主程序 ====================
def job():
    # 1. 智能加载插件
    ext_path = download_and_locate_extension()
    
    co = ChromiumOptions()
    co.set_argument('--headless=new')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--window-size=1920,1080')
    co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    
    if ext_path: 
        co.add_extension(ext_path)
        log(f">>> [浏览器] 已挂载插件，路径: {os.path.basename(ext_path)}")
    else:
        log("⚠️ [浏览器] 插件加载失败，将尝试纯脚本模式")
        
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
        
        # Step 2: 循环重试
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            log(f"\n🚀 [Step 2] 尝试续期 (第 {attempt} 次)...")
            page.get(target_url)
            pass_full_page_shield(page)
            
            renew_btn = None
            for _ in range(5):
                renew_btn = page.ele('css:button[data-bs-target="#renew-modal"]')
                if renew_btn and renew_btn.states.is_displayed: break
                time.sleep(1)

            if renew_btn:
                log(">>> 点击 Renew 按钮...")
                renew_btn.click(by_js=True)
                
                log(">>> 等待弹窗...")
                modal = page.ele('css:.modal-content', timeout=10)
                
                if modal:
                    log(">>> [操作] 弹窗出现，等待插件自动验证 (10s)...")
                    
                    # 确保验证码框架已加载
                    page.wait.ele_displayed('css:iframe[src*="cloudflare"], iframe[src*="turnstile"]', timeout=8)
                    
                    # 1. 插件表演时间
                    time.sleep(10)
                    
                    # 2. 补刀时间 (如果插件没搞定，脚本手动点)
                    manual_click_checkbox(modal)
                    
                    # 3. 缓冲时间
                    time.sleep(3)
                    
                    confirm_btn = modal.ele('css:button[type="submit"].btn-primary')
                    if confirm_btn:
                        log(">>> 点击 Confirm...")
                        confirm_btn.click(by_js=True)
                        log(">>> 等待响应 (5s)...")
                        time.sleep(5)
                        
                        result = analyze_page_alert(page)
                        
                        if result == "SUCCESS" or result == "SUCCESS_TOO_EARLY":
                            break 
                        
                        if result == "FAIL_CAPTCHA":
                            log("⚠️ 验证失败，准备重试...")
                            time.sleep(2)
                            continue
                    else:
                        log("❌ 找不到确认按钮")
                else:
                    log("❌ 弹窗未出")
            else:
                log("⚠️ 未找到按钮，检查状态...")
                result = analyze_page_alert(page)
                if result == "SUCCESS_TOO_EARLY":
                    break
            
            if attempt == max_retries:
                log("❌ 最大重试次数已达，任务终止。")
                exit(1)

    except Exception as e:
        log(f"❌ 异常: {e}")
        exit(1)
    finally:
        page.quit()

if __name__ == "__main__":
    job()

