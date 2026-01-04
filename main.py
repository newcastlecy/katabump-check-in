import os
import time
import requests
import zipfile
import io
import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 实时日志工具 ====================
def log(message):
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] {message}", flush=True)

# ==================== 核心逻辑 ====================

def download_and_extract_silk_extension():
    extension_id = "ajhmfdgkijocedmfjonnpjfojldioehi"
    crx_path = "silk.crx"
    extract_dir = "silk_ext"
    
    if os.path.exists(extract_dir) and os.listdir(extract_dir):
        log(f">>> [系统] 插件已就绪")
        return os.path.abspath(extract_dir)
        
    log(">>> [系统] 正在下载 Silk 隐私插件...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
    download_url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=122.0&acceptformat=crx2,crx3&x=id%3D{extension_id}%26uc"
    
    try:
        resp = requests.get(download_url, headers=headers, stream=True)
        if resp.status_code == 200:
            content = resp.content
            zip_start = content.find(b'PK\x03\x04')
            if zip_start == -1: return None
            with zipfile.ZipFile(io.BytesIO(content[zip_start:])) as zf:
                if not os.path.exists(extract_dir): os.makedirs(extract_dir)
                zf.extractall(extract_dir)
            return os.path.abspath(extract_dir)
        return None
    except: return None

def handle_captcha(context_ele, name=""):
    """
    通用验证码处理器
    """
    # 优先找 Cloudflare 验证码 iframe
    iframe = context_ele.ele('css:iframe[src*="cloudflare"]', timeout=2)
    if not iframe:
        iframe = context_ele.ele('css:iframe[title*="Widget"]', timeout=2)
        
    # 关键修改：必须是可见的 (displayed) 才点
    if iframe and iframe.states.is_displayed:
        log(f">>> [{name}盾] 👁️ 发现可见的验证码，尝试点击...")
        try:
            iframe.ele('tag:body', timeout=2).click(by_js=True)
            log(f">>> [{name}盾] 👆 已点击，等待生效 (5s)...")
            time.sleep(5) 
            return True
        except Exception as e:
            log(f"⚠️ [{name}盾] 点击异常: {e}")
    else:
        pass
        
    return False

def ensure_page_ready(page, target_selector):
    """
    【通用门神】确保真正进入了页面
    target_selector: 成功的标志 (比如登录页是 input，服务器页是 button)
    """
    log(f"--- [门神] 正在检查页面 (目标: {target_selector})...")
    
    for i in range(1, 15): 
        # 1. 检查目标元素是否存在 (快速检查，2秒超时)
        if page.ele(target_selector, timeout=2):
            log(f"--- [门神] 发现目标元素，通过！")
            return True

        title = page.title.lower()
        
        # 2. 显式拦截：标题是 Just a moment
        if "just a moment" in title or "attention" in title:
            log(f"--- [拦截] 全屏盾阻挡 ({i}/15)，尝试点击...")
            if not handle_captcha(page, "全屏"):
                log("--- [操作] 没找到验证码但被拦截，刷新页面...")
                page.refresh()
                time.sleep(5)
            continue
            
        # 3. 隐式拦截：标题正常，但找不到目标，且有验证码 iframe
        iframe = page.ele('css:iframe[src*="cloudflare"]', timeout=2)
        if iframe and iframe.states.is_displayed:
             log(f"--- [拦截] 发现页面中有残留验证码 ({i}/15)，清理中...")
             handle_captcha(page, "残留")
             time.sleep(3)
        else:
            log(f"--- [等待] 页面看似正常但未找到目标... ({i}/15)")
            
            # 只有在多次尝试后才刷新，避免频繁刷新导致加载不出来
            if i % 5 == 0:
                log("--- [操作] 加载超时，主动刷新...")
                page.refresh()
                time.sleep(5)
            else:
                time.sleep(2)

    return False

def robust_click(ele):
    try:
        ele.scroll.to_see()
        log(f">>> [动作] 点击按钮: {ele.text}")
        ele.click(by_js=True)
        return True
    except:
        return False

def check_result(page):
    log(">>> [检测] 读取结果回显...")
    time.sleep(2)
    full_text = page.html.lower()
    
    iframe = page.ele('css:iframe[src*="cloudflare"]', timeout=2)
    if iframe and iframe.states.is_displayed:
        log("❌ 结果: 验证码拦截")
        return "FAIL"
        
    if "can't renew" in full_text or "too early" in full_text:
        log("✅ 结果: 还没到时间")
        return "SUCCESS"
    if "success" in full_text or "extended" in full_text:
        log("✅ 结果: 续期成功")
        return "SUCCESS"
    
    log("⚠️ 未捕捉到明确结果")
    return "UNKNOWN"

def job():
    ext_path = download_and_extract_silk_extension()
    co = ChromiumOptions()
    co.set_argument('--headless=new')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
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
            log("❌ Secrets 配置缺失")
            exit(1)

        # ==================== 1. 登录 ====================
        log(">>> [Step 1] 登录...")
        page.get('https://dashboard.katabump.com/auth/login')
        
        # 【修正】登录页的目标是找到 email 输入框，而不是 Renew 按钮
        ensure_page_ready(page, 'css:input[name="email"]')
        
        if page.ele('css:input[name="email"]', timeout=5):
            log(">>> 输入账号密码...")
            page.ele('css:input[name="email"]').input(email)
            page.ele('css:input[name="password"]').input(password)
            page.ele('css:button[type="submit"]').click()
            page.wait.url_change('login', exclude=True, timeout=15)

        # ==================== 2. 循环尝试 ====================
        for attempt in range(1, 4):
            log(f"\n🚀 [Step 2] 第 {attempt}/3 次尝试...")
            try:
                page.get(target_url)
                
                # 【修正】续期页的目标是找到 Renew 按钮
                # 如果 check_page_ready 返回 True，说明按钮找到了
                ensure_page_ready(page, 'css:button:contains("Renew")')
                
                # 寻找主按钮
                renew_btn = page.ele('css:button:contains("Renew")', timeout=5)
                if not renew_btn:
                    log("⚠️ 经过检查仍无 Renew 按钮，可能已续期...")
                    if check_result(page) == "SUCCESS": break
                    continue

                # 点击主按钮
                robust_click(renew_btn)
                
                # 等待弹窗
                log(">>> 等待弹窗加载...")
                modal = page.wait.ele_displayed('css:.modal-content', timeout=8)
                
                if modal:
                    # 【核心】处理弹窗里的盾
                    log(">>> [弹窗] 检查内部验证码...")
                    
                    # 先尝试处理验证码
                    handle_captcha(modal, "弹窗")
                    
                    # 再找确认按钮
                    confirm = modal.ele('css:button.btn-primary', timeout=2)
                    if confirm:
                        log(">>> [弹窗] 点击最终确认！")
                        robust_click(confirm)
                        
                        time.sleep(5)
                        if check_result(page) == "SUCCESS":
                            break
                    else:
                        log("⚠️ 没找到确认按钮")
                else:
                    log("❌ 弹窗未出现")
            
            except Exception as e:
                log(f"❌ 异常: {e}")
            
            if attempt < 3: 
                log("⏳ 冷却 5 秒...")
                time.sleep(5)

        log("\n🏁 脚本运行结束")

    except Exception as e:
        log(f"❌ 崩溃: {e}")
        exit(1)
    finally:
        page.quit()

if __name__ == "__main__":
    job()
