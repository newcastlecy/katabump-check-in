import os
import time
from DrissionPage import ChromiumPage, ChromiumOptions

def handle_cloudflare(page):
    """处理 Cloudflare 5秒盾"""
    print("--- [检测] 正在检查 Cloudflare ---")
    for _ in range(10):
        try:
            # 如果没有盾，直接返回
            title = page.title.lower()
            if "just a moment" not in title and "cloudflare" not in title:
                return True
            
            # 寻找验证框 iframe
            iframe = page.get_frame('@src^https://challenges.cloudflare.com')
            if iframe:
                print("--- 发现 CF 验证框，点击... ---")
                iframe.ele('tag:body').click()
                time.sleep(3)
            else:
                time.sleep(1)
        except:
            time.sleep(1)
    return False

def job():
    # --- 1. 初始化 ---
    co = ChromiumOptions()
    co.headless(True) # GitHub Actions 必须开启无头模式
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--lang=zh-CN')
    co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    page = ChromiumPage(co)
    
    try:
        # ==================== 步骤 1: 使用 Token 登录 Discord ====================
        print(">>> [1/6] 正在注入 Discord Token...")
        token = os.environ.get("DISCORD_TOKEN")
        if not token:
            raise Exception("错误：未在 GitHub Secrets 中配置 DISCORD_TOKEN")

        # 1. 先打开 Discord 登录页
        page.get('https://discord.com/login', retry=2)
        handle_cloudflare(page)

        # 2. 通过 JS 注入 Token (这是核心黑科技)
        # 这一步会让浏览器认为"我已经登录了"
        js = f'window.localStorage.setItem("token", "\"{token}\"");'
        page.run_js(js)
        time.sleep(1)
        
        # 3. 刷新页面，验证是否生效
        print(">>> Token 注入完成，刷新页面验证...")
        page.refresh()
        time.sleep(5)
        
        # 如果还在登录页且有邮箱框，说明 Token 没生效
        if page.ele('css:input[name="email"]'):
            page.get_screenshot(path='token_failed.jpg')
            raise Exception("Token 注入失败：Discord 仍要求输入密码。请检查 Token 是否复制完整。")
        else:
            print(">>> Discord 登录成功！(已跳过密码输入)")

        # ==================== 步骤 2: 前往 Katabump ====================
        print(">>> [2/6] 前往 Katabump...")
        page.get('https://dashboard.katabump.com/auth/login', retry=2)
        handle_cloudflare(page)

        print(">>> 点击 'Login with Discord'...")
        # 模糊查找按钮，防止找不到
        discord_btn = page.ele('text:Login with Discord') or \
                      page.ele('css:a[href*="discord"]')
        
        if discord_btn:
            discord_btn.click()
        else:
            raise Exception("未找到登录按钮")

        print(">>> 跳转授权中...")
        time.sleep(5)

        # ==================== 步骤 3: 处理授权 ====================
        if "discord.com" in page.url:
            print(">>> [3/6] 处理 Discord 授权...")
            handle_cloudflare(page)
            
            # 寻找授权按钮
            time.sleep(3)
            auth_btn = page.ele('text:Authorize') or \
                       page.ele('text:授权') or \
                       page.ele('css:button div:contains("Authorize")')
            
            if auth_btn:
                print(">>> 点击授权按钮...")
                auth_btn.click()
            else:
                print(">>> 未找到授权按钮（可能已自动授权），等待跳转...")

        # ==================== 步骤 4: 验证是否进入面板 ====================
        print(">>> [4/6] 等待跳转回 Katabump...")
        for i in range(30):
            if "katabump.com" in page.url and "login" not in page.url:
                print("✅ 成功进入面板！")
                break
            time.sleep(1)
            
        if "login" in page.url:
             page.get_screenshot(path='login_loop_fail.jpg')
             raise Exception("登录循环失败：看起来又回到了登录页")

        # ==================== 步骤 5: 续期操作 ====================
        target_url = "https://dashboard.katabump.com/servers/edit?id=197288"
        print(f">>> [5/6] 进入服务器页面: {target_url}")
        page.get(target_url)
        time.sleep(5)
        handle_cloudflare(page)

        # 查找续期按钮 (支持英文 Renew 和中文 续期)
        main_renew = None
        for text in ['Renew', '续期', 'Extend']:
            btn = page.ele(f'text:{text}')
            # 确保它是按钮
            if btn and (btn.tag == 'button' or 'btn' in btn.attr('class', '')): 
                main_renew = btn
                break
        
        if main_renew:
            main_renew.click()
            print(">>> 点击 Renew，等待弹窗...")
            time.sleep(3)
            
            # ==================== 步骤 6: 弹窗确认 ====================
            print(">>> [6/6] 处理弹窗...")
            handle_cloudflare(page) # 处理弹窗里的验证码
            
            # 寻找弹窗里的确认按钮
            modal = page.ele('css:.modal-content')
            if modal:
                final_btn = modal.ele('text:Renew') or modal.ele('css:button.btn-primary')
                if final_btn:
                    final_btn.click()
                    print("✅✅✅ 续期任务完美完成！")
                else:
                    print("❌ 弹窗里没找到按钮")
            else:
                print("❌ 没看到弹窗")
        else:
            print("❌ 主界面没找到 Renew 按钮，可能服务器不需要续期或页面加载错误")
            # 打印页面文字用于调试
            print("页面文字预览:", page.ele('tag:body').text[:100])

    except Exception as e:
        print(f"❌ 运行失败: {e}")
        page.get_screenshot(path='final_error.jpg', full_page=True)
        exit(1)
    finally:
        page.quit()

if __name__ == "__main__":
    job()
