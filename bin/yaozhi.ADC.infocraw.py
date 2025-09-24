'''基于药智网进行ADC药物筛选'''

import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError, expect, Page
import json
from bs4 import BeautifulSoup
import xlsxwriter
import pandas as pd
import numpy as np
import sys
import re
import glob
import shutil
from pathlib import Path
import argparse
from argparse import RawTextHelpFormatter

# Load credentials from the .env file
script_dir = Path(__file__).resolve().parent
script_dir = str(script_dir)
env_path = script_dir+'/.env'
load_dotenv(dotenv_path=env_path, override=True)
username = os.getenv("YAOZHI_USERNAME")
password = os.getenv("YAOZHI_PASSWORD")

if not all([username, password]):
    raise ValueError("Error: Username or password not set in the .env file.")

print("Libraries imported and configuration loaded.")

def get_args():
    '''Parameter setting'''
    parser = argparse.ArgumentParser(description=__doc__,formatter_class=RawTextHelpFormatter)
    parser.add_argument('-o','--odir',dest='odir',help="output path",required=True)
    args = parser.parse_args()
    return args

def json_to_excel(outout_json,output_excel):
    '''transform json to excel and output'''
    # --- Convert JSON with Links to an Excel File ---

    # Define the input and output file paths
    json_file_path = outout_json
    excel_file_path = output_excel

    try:
        # 1. Load the JSON data from the file
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data:
            print(f"'{json_file_path}' is empty. No Excel file created.")
        else:
            # 2. Create a new Excel workbook and add a worksheet
            workbook = xlsxwriter.Workbook(excel_file_path)
            worksheet = workbook.add_worksheet()
            
            # 3. Get headers from the keys of the first record and write them to the first row
            headers = list(data[0].keys())
            for col_num, header in enumerate(headers):
                worksheet.write(0, col_num, header)
                
            # 4. Write the data row by row, starting from the second row (index 1)
            for row_num, row_data in enumerate(data, 1):
                for col_num, header in enumerate(headers):
                    cell_value = row_data.get(header, '')

                    # If the cell's value is a dictionary, it's a hyperlink
                    if isinstance(cell_value, dict) and 'text' in cell_value and 'link' in cell_value:
                        url = cell_value['link']
                        text = cell_value['text']
                        worksheet.write_url(row_num, col_num, url, string=text)
                    else:
                        # Otherwise, write it as a plain value
                        worksheet.write(row_num, col_num, str(cell_value) if cell_value is not None else '')

            # 5. Close the workbook to save the file
            workbook.close()
            print(f"✅ Data successfully converted to '{excel_file_path}'")

    except FileNotFoundError:
        print(f"Error: The file '{json_file_path}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

## define AsyncTask
async def main():
    ## argument parsing
    argv = vars(get_args())
    odir = argv['odir']
    async with async_playwright() as p:
        #Start Playwright and launch the browser
        browser = await p.chromium.launch(headless=False)  # You can set headless=False to watch the browser actions in real-time
        page = await browser.new_page()
        print("✅ Browser session started. You can now use the 'page' object.")
        try:
            os.chdir(odir)
            if not os.path.exists("./screenshot"):
                os.makedirs("./screenshot")

            # --- Navigation ---
            print("Navigating to the login page...")
            await page.goto("https://vip.yaozh.com/login", wait_until="domcontentloaded")
            await page.screenshot(path="screenshot/debug_01_page_loaded.png")

            # --- Fill Login Form ---
            print("Entering username and password...")

            # Locate, CLICK to activate, then fill the username
            username_field = page.get_by_placeholder("手机号/用户名/邮箱")
            await username_field.click()
            await username_field.fill(username)

            # Locate, CLICK to activate, then fill the password
            password_field = page.get_by_placeholder("密码")
            await password_field.click()
            await password_field.fill(password)

            await page.screenshot(path="screenshot/debug_02_after_pass_fill.png")

            # --- Check Agreement & Click Login ---
            print("Checking agreement and clicking login...")
            await page.get_by_role("checkbox", name="我同意").locator(".el-checkbox__inner").click()
            await page.get_by_role("button", name="登录").click()
            await page.wait_for_timeout(2000) # Wait for page to react
            await page.screenshot(path="screenshot/debug_03_after_login_click.png")

            # --- Conditional CAPTCHA ---
            captcha_input = page.get_by_placeholder("验证码", exact=True)
            if await captcha_input.is_visible(timeout=2000):
                await page.screenshot(path="screenshot/debug_04_captcha_detected.png")
                print("\n>>> ACTION REQUIRED: CAPTCHA Detected <<<")
                captcha_code = input("Please open screenshot/debug_04_captcha_detected.png and enter the code: ")
                await captcha_input.fill(captcha_code)
                
                print("Re-clicking the login button...")
                await page.get_by_role("button", name="登录").click()
                await page.wait_for_timeout(2000)
            else:
                print("No CAPTCHA detected.")

            # --- ✅ New Conditional Check for "Continue Login" ---
            print("Checking for 'Continue Login' prompt...")
            continue_login_button = page.get_by_role("button", name="继续登录")

            # Check if the button is visible for up to 3 seconds
            if await continue_login_button.is_visible(timeout=3000):
                print("'Continue Login' button detected. Clicking it...")
                await page.screenshot(path="screenshot/debug_05_before_continue_login_click.png")
                await continue_login_button.click()
                # Wait for the page to react after clicking
                await page.wait_for_timeout(3000) 
            else:
                print("'Continue Login' button not found. Proceeding...")


            # --- Verification ---
            print("Verifying login...")
            await page.wait_for_selector("#search-input, .user-name, #header-search-input", timeout=10000)

            print("✅ Login successful! Dashboard is visible.")
            await page.screenshot(path="screenshot/debug_06_final_success_dashboard.png")

            ## global drugs search for ADC

            ### goto the global drugs page for querying ADC
            # 1. Define the query and construct the URL
            target_url = f"https://vip.yaozh.com/globaldrugs/list?comprehensive=drug"

            # 2. Navigate to the page and wait for it to load
            print(f"Navigating to results...")
            await page.goto(target_url, wait_until="networkidle")
            print("Page loaded.")

            # 3. Take a "before" screenshot for debugging
            print("Taking 'before' screenshot...")
            await page.screenshot(path="screenshot/debug_06_clinical_analysis_page.png")

            # 4. Conditionally check for and close the tutorial overlay
            # CORRECTED: Use get_by_text() which is more flexible than get_by_role()
            skip_element = page.get_by_text("跳过引导")

            # Use a short timeout to quickly check for visibility without slowing down the script
            if await skip_element.is_visible(timeout=5000):
                print("Tutorial overlay detected. Clicking 'Skip Tutorial'...")
                await skip_element.click()
                
                # Wait for the overlay to fully disappear
                await page.locator("div.search-guide").wait_for(state="hidden")
                
                print("Overlay closed. Taking 'after' screenshot...")
                await page.screenshot(path="screenshot/debug_06_clinical_analysis_page.after_guided.png")
                print("✅ Overlay handled successfully.")
            else:
                print("No tutorial overlay was found. Proceeding normally.")

            # 5 由于引导框去除后出现了了一个遮罩层，尝试各种办法失败，使用下述方案用js，移除
            try:
                await page.evaluate('''() => {
                    // 查找可能的遮罩层容器（通常是全屏的div）
                    const overlays = document.querySelectorAll('div');
                    for (let overlay of overlays) {
                        // 通过样式特征判断是否是遮罩层
                        const style = window.getComputedStyle(overlay);
                        if (style.position === 'fixed' && 
                            (style.zIndex > 1000 || style.backgroundColor !== 'rgba(0, 0, 0, 0)') &&
                            (overlay.offsetWidth === window.innerWidth && overlay.offsetHeight === window.innerHeight)) {
                            
                            overlay.parentNode.removeChild(overlay);
                            console.log('移除全屏遮罩层');
                        }
                    }
                    
                    // 同时移除所有包含弹窗文本的元素
                    const elements = document.querySelectorAll('*');
                    for (let el of elements) {
                        if (el.textContent && el.textContent.includes('高级检索全新模式')) {
                            el.style.display = 'none';
                            // 同时尝试移除其父元素（可能是一个模态框容器）
                            let parent = el.closest('div[class*="modal"], div[class*="popup"], div[class*="overlay"]');
                            if (parent) {
                                parent.style.display = 'none';
                                parent.parentNode.removeChild(parent);
                            }
                            break;
                        }
                    }
                }''')
                print("尝试移除遮罩层和弹窗")
                await page.screenshot(path="screenshot/debug_07.global_drugs_page.after_masklayer_closed.png")    
            except Exception as e:
                print(f"执行JS移除失败: {e}")

            ### --- Select ADC (抗体偶联药物)输出 ---
            condition_filter = page.locator('div.item-title:has-text("条件筛选")')
            await condition_filter.click()
            # wait for the next page appear
            await page.wait_for_timeout(1000)
            drug_category_arrow = page.locator('div.el-collapse-item__header:has-text("药品类别") i.el-icon-arrow-right')
            await drug_category_arrow.click()
            await page.screenshot(path="screenshot/debug_08.global_drugs_page.drugtype_1.png")

            # search ADC and wait for check box to appear
            drug_section = page.locator('div.el-collapse-item:has-text("药品类别")')
            search_input = drug_section.locator('input[placeholder="输入关键字进行过滤"]')
            await search_input.wait_for(state="visible")
            await search_input.scroll_into_view_if_needed()
            await search_input.click(force=True)
            print("已点击搜索框")
            await search_input.fill('')
            await search_input.type('抗体偶联药物', delay=100)
            print("已输入'抗体偶联药物'")
            await page.wait_for_timeout(5000)
            await page.screenshot(path="screenshot/debug_08.global_drugs_page.drugtype_2.png")

            # Click the complicated check box including tree structure owing to failure for each direct method
            try:
                # 使用JavaScript直接操作DOM
                await page.evaluate('''() => {
                    // 查找包含"抗体偶联药物"文本的元素
                    const elements = document.querySelectorAll('span.custom-tree-node');
                    for (let el of elements) {
                        if (el.textContent.includes('抗体偶联药物')) {
                            // 找到最近的复选框
                            const contentDiv = el.closest('.el-tree-node__content');
                            if (contentDiv) {
                                const checkbox = contentDiv.querySelector('input[type="checkbox"].el-checkbox__original');
                                if (checkbox) {
                                    checkbox.checked = !checkbox.checked;
                                    
                                    // 触发change事件
                                    const changeEvent = new Event('change', { bubbles: true });
                                    checkbox.dispatchEvent(changeEvent);
                                    
                                    // 触发click事件
                                    const clickEvent = new Event('click', { bubbles: true });
                                    checkbox.dispatchEvent(clickEvent);
                                    
                                    console.log("已通过JavaScript操作复选框");
                                    return true;
                                }
                            }
                        }
                    }
                    return false;
                }''')   
                print("已通过JavaScript尝试操作复选框")
                await page.wait_for_timeout(3000)
                await page.screenshot(path="screenshot/debug_08.global_drugs_page.drugtype_3.png")
            except Exception as js_e:
                print(f"JavaScript操作也失败: {js_e}")

            # click search button and display ADC drug results
            search_button = page.locator('div.advanced-btn.advanced-btn2[style*="background: rgb(0, 47, 167)"]')
            if await search_button.count() == 0:
                search_button = page.locator('div:has-text("搜索")').filter(has=page.locator('[style*="background: rgb(0, 47, 167)"]'))
            await search_button.wait_for(state="visible")
            await search_button.scroll_into_view_if_needed()
            await search_button.click()
            print("已点击底部搜索按钮")
            await page.wait_for_timeout(10000)
            await page.screenshot(path="screenshot/debug_08.global_drugs_page.drugtype_4.png")

            ### --- Select All Display Options ---
            # 1. Click the "显示" (Display) element to open the options
            print("Clicking '显示' to open display options...")
            # Using a locator that finds a span with the class 'action-btn' containing the text
            display_element = page.locator('span.action-btn:has-text("显示")')
            await display_element.click()
            # Wait a moment for the options dialog to appear
            await page.wait_for_timeout(1000)

            # 2. Click the "全选" (Select All) checkbox label
            print("Clicking '全选' (Select All)...")
            # get_by_text is a reliable way to find the checkbox by its visible label
            select_all_checkbox = page.get_by_text("全选")
            await select_all_checkbox.click()
            await page.wait_for_timeout(500)

            # 3. Click the "确 认" (Confirm) button
            print("Clicking '确 认' (Confirm)...")
            # get_by_role is the best choice here since the text is inside a proper <button> element
            confirm_button = page.get_by_role("button", name="确 认")
            await confirm_button.click()

            # Wait for the page to update after confirming
            await page.wait_for_timeout(2000)
            print("Display options confirmed. Taking a final screenshot...")

            # 4. Take a screenshot of the result
            await page.screenshot(path="screenshot/debug_08_clinical_analysis_page.all_options_displayed.png", full_page=True)
            print("✅ Sequence complete. Final screenshot saved.")       

            ### --- Change Items per Page to 50 (Corrected Locator) ---
            # 1. Click the dropdown trigger to open the list of options
            print("Opening the 'items per page' dropdown...")
            dropdown_trigger = page.locator("span.el-pagination__sizes input.el-input__inner")
            await dropdown_trigger.click()

            # Wait for the options to become visible
            await page.wait_for_timeout(1000)

            # 2. Click the "50条/页" option using get_by_text()
            print("Selecting '50条/页'...")
            # CORRECTED: get_by_text is more flexible for custom dropdowns
            items_50_per_page = page.get_by_text("50条/页")
            await items_50_per_page.click()

            # 3. Wait for the page to reload the data and take a screenshot
            print("Waiting for page to update with 50 items per page...")
            await page.wait_for_timeout(10000) # Give the page time to update
            await page.screenshot(path="screenshot/debug_09_clinical_analysis_page.items_per_page_set_to_50.png", full_page=True)
            print("✅ Successfully set items per page to 50.")

            ### --- Scrape All Table Pages with Hyperlinks to a Single JSON File ---
            BASE_URL = "https://vip.yaozh.com"
            # --- Step 1: Extract Correct Headers from the Page ---
            print("Extracting table headers...")
            full_table_locator = page.locator("div.el-table") 
            full_table_html = await full_table_locator.inner_html()

            soup = BeautifulSoup(full_table_html, 'lxml')
            headers = [th.get_text(strip=True) for th in soup.find_all('th')]
            headers = [h for h in headers if h] 
            print(f"Found headers: {headers}")

            # --- Step 2: Loop Through Pages and Scrape Data ---
            all_table_rows = []
            page_number = 1

            while True:
                print(f"--- Processing Page {page_number} ---")

                table_body_locator = page.locator('table.el-table__body')
                try:
                    await table_body_locator.wait_for(state="visible", timeout=10000)
                except TimeoutError:
                    print("Could not find the results table on this page. Stopping.")
                    break

                # Get the HTML of the table body for parsing
                table_body_html = await table_body_locator.inner_html()
                soup = BeautifulSoup(table_body_html, 'lxml')
                
                # Find all table rows in the current page's table
                rows = soup.find_all('tr')
                page_rows = []
                
                for row in rows:
                    row_data = {}
                    # Find all cells, but exclude the last one which is a checkbox
                    cells = row.find_all('td')[:-1] 
                    
                    for i, cell in enumerate(cells):
                        header = headers[i]
                        # Check if the cell contains a hyperlink (<a> tag)
                        link = cell.find('a')
                        
                        if link and link.has_attr('href'):
                            # If a link is found, store its text and the full URL
                            href = link['href']
                            full_url = href if href.startswith('http') else BASE_URL + href
                            row_data[header] = {
                                "text": link.get_text(strip=True),
                                "link": full_url
                            }
                        else:
                            # Otherwise, just store the plain text
                            row_data[header] = cell.get_text(strip=True)
                    
                    page_rows.append(row_data)

                all_table_rows.extend(page_rows)
                print(f"Extracted {len(page_rows)} rows from page {page_number}.")

                # Find and click the "next page" button
                next_button_locator = page.locator('button.btn-next')
                if not await next_button_locator.is_enabled():
                    print("Last page reached. Scraping complete.")
                    break

                print("Navigating to the next page...")
                await next_button_locator.click()
                await page.wait_for_load_state('networkidle', timeout=20000)
                page_number += 1

            # --- Step 3: Save the Final, Rich JSON ---
            if all_table_rows:
                output_path = 'results.global_drugs.ADC.json'
                print(f"\nSaving {len(all_table_rows)} total rows to '{output_path}'...")
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_table_rows, f, ensure_ascii=False, indent=2)
                
                print("✅ All data, including hyperlinks, saved successfully.")
            else:
                print("No data was extracted.")         
        except TimeoutError as e:
            print(f"An operation timed out: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main()) # 运行异步任务保存数据
    # syncing tasks(同步任务)
    ## argument parsing
    argv = vars(get_args())
    odir = argv['odir']

    ## transform json to excel
    global_drugs_json = f'{odir}/results.global_drugs.ADC.json'
    global_drugs_excel = f'{odir}/results.global_drugs.ADC.xlsx'
    json_to_excel(global_drugs_json,global_drugs_excel)
