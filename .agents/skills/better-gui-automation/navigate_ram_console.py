#!/usr/bin/env python3
"""
Navigate to Alibaba Cloud RAM Console (public) and capture screenshots 
to guide the user to find/create AccessKey.
"""
import os
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ram_console_screenshots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def save_screenshot(page, filename, description):
    """Take a screenshot and print description."""
    path = os.path.join(OUTPUT_DIR, filename)
    page.screenshot(path=path, full_page=True)
    print(f"[Screenshot] {filename} - {description}")
    print(f"  Path: {path}")
    return path

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=['--window-size=1440,900']
        )
        context = browser.new_context(
            viewport={'width': 1440, 'height': 900},
            locale='zh-CN',
        )
        page = context.new_page()

        # Step 1: Navigate to RAM console (public Alibaba Cloud)
        print("\n=== Step 1: Navigate to RAM Console ===")
        page.goto("https://ram.console.aliyun.com", wait_until="networkidle", timeout=60000)
        time.sleep(3)
        save_screenshot(page, "01_ram_console_home.png", "RAM Console 首页")

        # Check URL and title
        url = page.url
        title = page.title()
        print(f"Current URL: {url}")
        print(f"Page title: {title}")

        # Step 2: Check if login is needed
        if "login" in url.lower() or "signin" in url.lower():
            print("\n=== Login Page Detected ===")
            save_screenshot(page, "02_login_page.png", "登录页面 - 需要用户登录")
            print("\n>> 页面已打开，请在浏览器中完成登录")
            print(">> 登录后按 Enter 继续...")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                print("Waiting 15 seconds for manual login...")
                time.sleep(15)
            
            save_screenshot(page, "03_after_login.png", "登录后的页面")
            url = page.url
            title = page.title()
            print(f"After login URL: {url}")
            print(f"After login title: {title}")
        
        # Step 3: Capture the main console page
        print("\n=== Step 3: Console Page ===")
        time.sleep(2)
        save_screenshot(page, "04_console_overview.png", "控制台概览")
        
        # Step 4: Try to find the left navigation menu
        print("\n=== Step 4: Finding Navigation ===")
        
        # Get page text content
        body_text = page.inner_text("body")
        lines = [l.strip() for l in body_text.split('\n') if l.strip()]
        
        # Look for navigation related text
        nav_keywords = ['用户', '身份管理', 'AccessKey', '认证管理', 'RAM', '角色', '权限']
        found_keywords = []
        for keyword in nav_keywords:
            if keyword in body_text:
                found_keywords.append(keyword)
        
        print(f"Found navigation keywords: {found_keywords}")
        
        save_screenshot(page, "05_console_with_menu.png", "控制台带左侧菜单")
        
        # Step 5: Try clicking on common navigation elements
        print("\n=== Step 5: Try Navigation Actions ===")
        
        # Try to find and click "用户" in the left menu
        click_targets = [
            ('a:has-text("用户")', '点击"用户"链接'),
            ('span:has-text("用户")', '点击"用户"文本'),
            ('button:has-text("用户")', '点击"用户"按钮'),
            ('li:has-text("用户")', '点击"用户"列表项'),
            ('.menu-item:has-text("用户")', '点击"用户"菜单项'),
            ('.nav-item:has-text("用户")', '点击"用户"导航项'),
            ('div:has-text("身份管理")', '点击"身份管理"'),
        ]
        
        for selector, desc in click_targets:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    print(f"Found: {desc} (selector: {selector})")
                    el.click()
                    time.sleep(2)
                    save_screenshot(page, "06_after_click_users.png", f"点击后的页面 - {desc}")
                    break
            except Exception as e:
                print(f"Failed: {desc} - {e}")
                continue
        
        # Step 6: Look for AccessKey elements
        print("\n=== Step 6: Find AccessKey Section ===")
        time.sleep(1)
        
        # Look for AccessKey related elements
        ak_targets = [
            ('text=AccessKey', 'AccessKey文本'),
            ('button:has-text("AccessKey")', 'AccessKey按钮'),
            ('a:has-text("AccessKey")', 'AccessKey链接'),
            ('text="创建 AccessKey"', '创建AccessKey'),
            ('button:has-text("创建 AccessKey")', '创建AccessKey按钮'),
            ('text="认证管理"', '认证管理文本'),
            ('a:has-text("认证管理")', '认证管理链接'),
        ]
        
        for selector, desc in ak_targets:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    print(f"Found: {desc}")
            except:
                pass
        
        save_screenshot(page, "07_accesskey_section.png", "AccessKey 相关区域")
        
        # Step 7: Full page screenshot for final reference
        save_screenshot(page, "08_full_page_reference.png", "完整页面参考截图")
        
        # List all clickable elements for manual guidance
        print("\n=== All Links on Page (top 50) ===")
        all_links = page.query_selector_all('a, button, [role="button"], [role="link"], [role="treeitem"]')
        for i, el in enumerate(all_links[:50]):
            try:
                text = el.inner_text().strip()
                href = el.get_attribute('href') or ''
                if text:
                    print(f"  [{i}] {text[:60]} | href: {href[:60]}")
            except:
                pass
        
        # Summary
        print(f"\n{'='*60}")
        print(f"All screenshots saved to: {OUTPUT_DIR}")
        print(f"{'='*60}")
        
        # Keep browser open for user interaction
        print("\n浏览器将保持打开，您可以手动探索页面...")
        print("按 Ctrl+C 关闭浏览器并退出")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            browser.close()

if __name__ == "__main__":
    main()
