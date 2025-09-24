'''基于药智网进行靶点调研，并进行ADC药物筛选'''

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
    parser.add_argument('-t','--target',dest='target',help="drug target for quering in yaozhi,such as CCR8",required=True)
    parser.add_argument('-o','--odir',dest='odir',help="output path",required=True)
    parser.add_argument('-r','--rscript',dest='rscript',help="R software",default="/home/ubuntu/software/annoconda/bin/envs/r4.3/bin/Rscript")
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

## pie chart
def pie_chart(data_dict,title,file_prefix):
    '''pie chart visual'''
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import matplotlib as mpl

    ## 中文字体设置
    plt.rcParams['font.family'] = ['WenQuanYi Zen Hei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

    import matplotlib.colors as mcolors
    from matplotlib import patheffects as PathEffects

    labels = list(data_dict.keys())
    sizes = list(data_dict.values())
    label_num = len(labels)
    ## 获取颜色列表
    if label_num <= 10:
        # 使用 tab10（10种颜色）
        colors = plt.cm.tab10(np.linspace(0, 1, label_num))
    elif label_num > 10:
        # 使用 tab20（20种颜色）
        colors = plt.cm.tab20(np.linspace(0, 1, label_num))
    colors = [mcolors.to_hex(color) for color in colors]

    fig, ax = plt.subplots(figsize=(10, 8))
    # 绘制饼图 - 直接使用标签但优化参数
    wedges, texts, autotexts = ax.pie(sizes,
                                    labels=labels,  # 直接显示标签
                                    colors=colors,
                                    autopct=lambda pct: func(pct, sizes),
                                    startangle=90,
                                    shadow=False,
                                    pctdistance=0.8,    # 调整百分比文本位置
                                    labeldistance=1.05, # 调整标签位置
                                    textprops={'fontsize': 14})

    # 设置标题
    ax.set_title(title, fontsize=16, pad=20)
    ## 图例圆形
    ax.axis('equal')

    for autotext in autotexts:
        # 使用更深的颜色（接近黑色但略带棕色）
        autotext.set_color('black')  # 比纯黑色略浅的深灰色
        autotext.set_fontsize(12)
        autotext.set_weight('bold')
        
        # 添加轻微白色阴影/描边效果，增强对比度
        autotext.set_path_effects([
            PathEffects.withStroke(linewidth=4, foreground='white'),
        ])


    for text in texts:
        text.set_fontsize(14)

    # 特别处理小扇区的文本位置以避免重叠
    # 找到较小的扇区并调整其文本位置
    for i, (wedge, size) in enumerate(zip(wedges, sizes)):
        if size < 3:  # 对非常小的扇区进行特殊处理
            # 获取扇区的角度
            ang = (wedge.theta2 + wedge.theta1) / 2.
            # 将角度转换为坐标
            x = np.cos(np.deg2rad(ang))
            y = np.sin(np.deg2rad(ang))
            
            # 根据位置调整文本的对齐方式
            horizontal_alignment = 'left' if x >= 0 else 'right'
            
            # 稍微向外移动文本
            connection_ratio = 1.15  # 调整这个值可以控制文本距离圆心的距离
            
            # 更新文本位置
            texts[i].set_position((x * connection_ratio, y * connection_ratio))
            texts[i].set_ha(horizontal_alignment)
            texts[i].set_va('center')
            
            # 同样调整百分比文本
            autotexts[i].set_position((x * (connection_ratio - 0.2), y * (connection_ratio - 0.2)))
            autotexts[i].set_ha(horizontal_alignment)
            autotexts[i].set_va('center')

    plt.tight_layout()
    ## save pie charts
    plt.savefig("{}.png".format(file_prefix), dpi=300, bbox_inches='tight', facecolor='white')
    plt.savefig("{}.pdf".format(file_prefix), bbox_inches='tight', facecolor='white')

def func(pct, allvals):
    """
    自定义函数，用于在饼图扇区上同时显示百分比和绝对数量。
    
    参数:
    pct (float): 自动计算出的百分比
    allvals (list): 所有扇区数值的列表
    
    返回:
    str: 格式化的字符串
    """
    absolute = int(round(pct/100. * np.sum(allvals)))
    return f'{pct:.1f}%\n({absolute:d})'

def classify_drug_type(description):
    """
    根据药物描述字符串识别并标准化药物类别。
    
    参数:
    description (str): 原始的类别描述字符串，例如 "生物制品;单克隆抗体;人源化抗体"
    
    返回:
    str: 标准化后的类别名称。如果输入为"暂无"或类似空值，则返回"暂无"。
          无法识别的类型返回"原始字符串"。
    """
    # 检查输入是否为“暂无”、NaN或其他形式的空值
    if pd.isna(description) or description.strip() == "暂无" or description.strip() == "":
        return "暂无"
    # 统一转换为小写，便于匹配（提高鲁棒性）
    desc_lower = description.lower()
    if "双特异性抗体" in desc_lower:
        return "双特异性抗体"
    elif "抗体偶联药物" in desc_lower or "adc" in desc_lower:
        return "抗体偶联药物"
    elif "蛋白/多肽" in desc_lower:
        return "蛋白/多肽"
    elif "单克隆抗体" in desc_lower:
        return "单克隆抗体"
    elif "抗体" in desc_lower:
        return "抗体"
    elif "化药" in desc_lower:
        return "化药"
    else:
        desc_lower = desc_lower.replace("生物制品;","")
        return desc_lower

def convert_stage(stage_str):
    """转换临床阶段"""
    stage_mapping = {
        "临床前": "Preclinical",
        "临床申请": "IND",
        "早期临床": "Early-Phase Clinical",
        "临床0期":"Phase 0",
        "临床Ⅰ期": "Phase I",
        "临床Ⅱ期": "Phase II",
        "临床Ⅲ期": "Phase III",
        "临床Ⅳ期": "Phase IV",
        "批准上市":"Drug Approval and Marketing",
        "其他": "Others"
    }
    if pd.isna(stage_str) or stage_str == "-":
        return np.nan
    
    # 移除日期部分
    if "(" in stage_str:
        stage_str = stage_str.split("(")[0].strip()
    
    return stage_mapping[stage_str]

def extract_target_names(data_string):
    """
    从给定字符串中提取所有靶点名称，并用逗号分隔返回
    参数:
    data_string (str): 包含靶点信息的字符串，格式为"靶点简称：-靶点全称：-作用机制：-最高阶段：-靶点名称"
                      多个靶点用分号分隔
    
    返回:
    str: 逗号分隔的靶点名称字符串
    """
    # 如果输入是NaN或空字符串，返回空字符串
    if pd.isna(data_string) or data_string.strip() == "":
        return ""
    # 按分号分割字符串，得到多个靶点描述段
    target_segments = data_string.split(';')
    extracted_targets = []
    for segment in target_segments:
        # 按连字符"-"分割每个描述段
        parts = segment.split('-')
        # 提取最后一个部分作为靶点名称（去除可能的前后空格）
        if len(parts) > 0:
            target_name = parts[-1].strip()
            if target_name:  # 确保不是空字符串
                extracted_targets.append(target_name)
    return ', '.join(extracted_targets)

def global_drugs_format_and_visual(global_drugs_df,odir,target):
    '''format global drugs and visualize pie charts'''
    global_drugs_df['药物类别_标准化'] = global_drugs_df['药品类别'].apply(lambda x:classify_drug_type(x))
    drug_type_dict = dict(global_drugs_df['药物类别_标准化'].value_counts())
    pie_chart(drug_type_dict,"药物类别",f"{odir}/drug_type.{target}.piechart")

    global_drugs_df['全球最高阶段_标准化'] = global_drugs_df['全球最高阶段'].apply(lambda x:convert_stage(x))
    clinical_count_dict = dict(global_drugs_df['全球最高阶段_标准化'].value_counts())
    pie_chart(clinical_count_dict,"Clinical stage",f"{odir}/clinical_stage.{target}.piechart")

    global_drugs_df['靶点'] = global_drugs_df['靶点'].apply(lambda x:extract_target_names(x))

    
    global_drugs_df['更新日期'] = global_drugs_df['更新日期'].apply(lambda x:str(x).split('暂无')[0])
    global_drugs_df['药品类别'] = global_drugs_df['药物类别_标准化']
    global_drugs_df['全球最高阶段'] = global_drugs_df['全球最高阶段_标准化']
    del global_drugs_df['结构式']
    del global_drugs_df['药物类别_标准化']
    del global_drugs_df['全球最高阶段_标准化']
    global_drugs_df.to_excel(f'{odir}/results.globaldrugs.{target}.format.xlsx',header=True,index=False)
    return global_drugs_df

def map_clinical_stages(stage_str):
    """
    将临床试验阶段的中文描述映射为英文术语。
    支持单一阶段（如'1期'）和组合阶段（如'1期+2期'）。

    参数:
    stage_str (str): 要转换的字符串，例如"1期"或"1期+2期"
    stage_mapping (dict): 阶段映射字典

    返回:
    str: 转换后的英文阶段描述，例如"Phase I"或"Phase I+Phase II"
    """
    # 检查输入是否为字符串且非空
    if not isinstance(stage_str, str) or not stage_str.strip():
        return stage_str

    stage_mapping = {
        "临床前": "Preclinical",
        "临床申请": "IND",
        "0期":"Phase 0",
        "1期": "Phase I",
        "2期": "Phase II",
        "3期": "Phase III",
        "4期": "Phase IV",
        "其他": "Others"
    }

    stage_str = stage_str.strip()
    
    # 检查是否为组合阶段（包含加号）
    if '+' in stage_str:
        parts = stage_str.split('+')
        mapped_parts = []
        for part in parts:
            cleaned_part = part.strip()
            mapped_part = stage_mapping[part]
            mapped_parts.append(mapped_part)
        return '+'.join(mapped_parts)
    else:
        return stage_mapping[stage_str]

def clinical_analysis_visual(clinical_analysis_df,results_odir,target):
    '''clinical analysis visualizing by pie charts'''
    clinical_analysis_df['试验分期_标准化'] = clinical_analysis_df['试验分期'].apply(lambda x:map_clinical_stages(x))
    clinical_expre_count_dict = dict(clinical_analysis_df['试验分期_标准化'].value_counts())
    pie_chart(clinical_expre_count_dict,"Clinical stage",f"{results_odir}/clinical_assay_stage.{target}.piechart")
    return clinical_analysis_df

def adc_drugs_and_clinical_screen(global_drugs_df,clinical_analysis_df,results_odir,target):
    '''ADC drugs and clinical assay screening'''
    adc_drugs_df = global_drugs_df[global_drugs_df['药品类别']=="抗体偶联药物"]
    adc_drug_list = list(set(adc_drugs_df['药品名称'].tolist()))
    adc_clinical_df = clinical_analysis_df[clinical_analysis_df['药物'].isin(adc_drug_list)]
    del adc_clinical_df['试验分期_标准化']
    ## output
    adc_drugs_df.to_excel(f'{results_odir}/results.globaldrugs.{target}.ADC.format.xlsx',header=True,index=False)
    adc_clinical_df.to_excel(f'{results_odir}/results_with_links.clinical_analysis.{target}.ADC.format.xlsx',header=True,index=False)

def copy_file(source_file,destination_file):
    try:
        shutil.copy(source_file, destination_file)
    except FileNotFoundError:
        print("源文件不存在")
    except PermissionError:
        print("没有操作权限")
    except Exception as e:
        print(f"发生了未知错误: {e}")

def html_results_copy(results_odir,target,html_table_dir,html_img_dir):
    ## clinical analyis and global drugs table file
    copy_file(f'{results_odir}/results.globaldrugs.{target}.format.xlsx',
              f'{html_table_dir}/results_{target}.globaldrugs.format.xlsx')
    copy_file(f'{results_odir}/results_with_links.clinical_analysis.{target}.xlsx',
              f'{html_table_dir}/results_{target}.clinical_analysis.format.xlsx')

    ## ADC clinical analyis and global drugs table file
    copy_file(f'{results_odir}/results.globaldrugs.{target}.ADC.format.xlsx',
              f'{html_table_dir}/results_{target}.globaldrugs.ADC.format.xlsx')
    copy_file(f'{results_odir}/results_with_links.clinical_analysis.{target}.ADC.format.xlsx',
              f'{html_table_dir}/results_{target}.ADC.clinical_analysis.format.xlsx')

    ## clinical analysis and global drugs pie chart file
    copy_file(f'{results_odir}/drug_type.{target}.piechart.png',
              f'{html_img_dir}/global_drugs.drug_type.piechart.png')
    copy_file(f'{results_odir}/clinical_stage.{target}.piechart.png',
              f'{html_img_dir}/global_drugs.clinical_stage.piechart.png')  
    copy_file(f'{results_odir}/clinical_assay_stage.{target}.piechart.png',
              f'{html_img_dir}/clinical.clinical_stage.piechart.png')

## define AsyncTask
async def main():
    ## argument parsing
    argv = vars(get_args())
    target = argv['target']
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

            ## clinical assay included for query target 

            ### goto the clinical analysis page for querying target
            # 1. Define the query and construct the URL
            query_name = target
            target_url = f"https://vip.yaozh.com/clinicalresult?comprehensive=targets&searchwords={query_name}"

            # 2. Navigate to the page and wait for it to load
            print(f"Navigating to results for '{query_name}'...")
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
            await page.screenshot(path="screenshot/debug_06_clinical_analysis_page.all_options_displayed.png", full_page=True)
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
            await page.screenshot(path="screenshot/debug_06_clinical_analysis_page.items_per_page_set_to_50.png", full_page=True)
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
                output_path = 'screenshot/results_with_links.clinical_analysis.{}.json'.format(target)
                print(f"\nSaving {len(all_table_rows)} total rows to '{output_path}'...")
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_table_rows, f, ensure_ascii=False, indent=2)
                
                print("✅ All data, including hyperlinks, saved successfully.")
            else:
                print("No data was extracted.")

            ## global drugs included for query target 

            ### goto the global drugs page for querying target
            # 1. Define the query and construct the URL
            query_name = target
            target_url = f"https://vip.yaozh.com/globaldrugs/list?comprehensive=targets&searchwords={query_name}"

            # 2. Navigate to the page and wait for it to load
            print(f"Navigating to globaldrugs results for '{query_name}'...")
            await page.goto(target_url, wait_until="networkidle")
            print("Page loaded.")

            # 3. Take a "before" screenshot for debugging
            print("Taking 'before' screenshot...")
            await page.screenshot(path="screenshot/debug_07.global_drugs_page.before_guided.png")

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
                await page.screenshot(path="screenshot/debug_07.global_drugs_page.after_guided.png")
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
            await page.screenshot(path="screenshot/debug_07.global_drugs_page.options_displayed.png", full_page=True)
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
            await page.screenshot(path="screenshot/debug_07.global_drugs_page.items_per_page_set_to_50.png", full_page=True)
            print("✅ Successfully set items per page to 50.")

            ### --- Scrape All Table Pages of global drugs to a Single JSON File ---

            os.makedirs('screenshot', exist_ok=True)
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
                output_path = 'screenshot/results.globaldrugs.{}.json'.format(target)
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
    target = argv['target']
    odir = argv['odir']
    rscript = argv['rscript']

    ## transform json to excel
    clinical_analysis_json = '{0}/screenshot/results_with_links.clinical_analysis.{1}.json'.format(odir,target)
    global_drugs_json = '{0}/screenshot/results.globaldrugs.{1}.json'.format(odir,target)
    clinical_analysis_excel = '{0}/screenshot/results_with_links.clinical_analysis.{1}.xlsx'.format(odir,target)
    global_drugs_excel = '{0}/screenshot/results.globaldrugs.{1}.xlsx'.format(odir,target)
    json_to_excel(clinical_analysis_json,clinical_analysis_excel)
    json_to_excel(global_drugs_json,global_drugs_excel)

    results_odir = os.path.join(odir,"screenshot")
    ## clincai analysis visual
    clinical_analysis_df = pd.read_excel(clinical_analysis_excel,header=0)
    clinical_analysis_df = clinical_analysis_visual(clinical_analysis_df,results_odir,target)
    
    ## global drugs visual
    global_drugs_df = pd.read_excel(global_drugs_excel,header=0)
    global_drugs_df = global_drugs_format_and_visual(global_drugs_df,results_odir,target)

    ## ADC drugs screen
    adc_drugs_and_clinical_screen(global_drugs_df,clinical_analysis_df,results_odir,target)

    ## prepare for generating query report
    html_dir = os.path.join(odir,"html")
    html_table_dir = os.path.join(html_dir,"table")
    html_img_dir = os.path.join(html_dir,"img")
    if not os.path.exists(html_dir):
        os.makedirs(html_dir)
        os.makedirs(html_dir+"/table")
        os.makedirs(html_dir+"/img")
    html_results_copy(results_odir,target,html_table_dir,html_img_dir)

    ## generate final report
    copy_file(f'{script_dir}/yaozhi.target.var.Rmd',f'{html_dir}/yaozhi.target.var.Rmd')
    os.system(f"{rscript} {script_dir}/yaozhi.target.tohtml.R {html_dir}/yaozhi.target.var.Rmd {html_dir}/yaozhi.target.{target}.html {html_dir} {target}")
