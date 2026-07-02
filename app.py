import streamlit as st
import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
import io
import requests
import pdfplumber

st.set_page_config(page_title="Таможенный Заполнитель Pro", page_icon="🗃️", layout="wide")

st.title("📦 Автоматическая подготовка данных (с полной аналитикой)")
st.markdown("Загрузите исходные документы. Приложение сформирует Excel-файл с точным распределением веса и визуальным дашбордом, как в эталонном примере.")

# --- Функция извлечения текста (Облачное API + локальный PDF) ---
def extract_text_cloud(uploaded_file):
    text = ""
    file_type = uploaded_file.name.split('.')[-1].lower()
    
    try:
        if file_type == 'pdf':
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                        
        elif file_type in ['jpg', 'jpeg', 'bmp', 'png']:
            url = "https://api.ocr.space/parse/image"
            payload = {
                'apikey': 'helloworld', # Замените на свой бесплатный ключ для стабильной работы
                'language': 'rus',
                'isOverlayRequired': False
            }
            files = {uploaded_file.name: uploaded_file.getvalue()}
            response = requests.post(url, files=files, data=payload)
            result = response.json()
            
            if not result.get('IsErroredOnProcessing'):
                for item in result.get('ParsedResults', []):
                    text += item.get('ParsedText', '') + "\n"
            else:
                text = f"Ошибка сервера OCR: {result.get('ErrorMessage')}"
                
        elif file_type in ['xls', 'xlsx', 'csv']:
            text = f"[{uploaded_file.name}]: Таблица. Данные готовы к парсингу."
        else:
            text = "Формат не поддерживается."
            
    except Exception as e:
        text = f"Ошибка при чтении файла: {e}"
        
    return text

# --- Функция для генерации Excel (Стилизация + Дашборд + Графики) ---
def create_styled_excel(df_data, box_summary_data):
    wb = openpyxl.Workbook()
    
    # --- Стили ---
    HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    TITLE_FONT = Font(name="Calibri", size=16, bold=True, color="1F497D")
    SUBTITLE_FONT = Font(name="Calibri", size=11, italic=True, color="595959")
    BOLD_FONT = Font(name="Calibri", size=11, bold=True)
    REGULAR_FONT = Font(name="Calibri", size=11)
    ZEBRA_FILL = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
    TOTAL_FILL = PatternFill(start_color="E9EDF4", end_color="E9EDF4", fill_type="solid")
    
    thin_side = Side(border_style="thin", color="D9D9D9")
    border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    border_total = Border(top=Side(border_style="thin", color="1F497D"), bottom=Side(border_style="double", color="1F497D"), left=thin_side, right=thin_side)
    
    # ==========================================
    # ЛИСТ 1: ДАННЫЕ ДЛЯ ЗАПОЛНИТЕЛЯ
    # ==========================================
    ws_data = wb.active
    ws_data.title = "Данные для Заполнителя"
    ws_data.views.sheetView[0].showGridLines = True
    
    ws_data["A1"] = "Таблица данных для программы 'Заполнитель' (Альта-Софт)"
    ws_data["A1"].font = TITLE_FONT
    ws_data["A2"] = "Сформировано автоматически на основе загруженных документов"
    ws_data["A2"].font = SUBTITLE_FONT
    
    headers = [
        "Порядковый номер", "Наименование товара", "Числовой код ед. изм.", 
        "Буквенный код ед. изм.", "Количество товара", "Цена за единицу, USD", 
        "Общая стоимость, USD", "Код изделия / артикул", "Вес нетто за ед., кг", 
        "Общий вес нетто, кг", "Общий вес брутто, кг", "Номер грузового места"
    ]
    
    for col_idx, text in enumerate(headers, 1):
        cell = ws_data.cell(row=4, column=col_idx, value=text)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws_data.row_dimensions[4].height = 40
    
    start_row = 5
    for i, row in df_data.iterrows():
        current_row = start_row + i
        
        ws_data.cell(row=current_row, column=1, value=i+1).alignment = Alignment(horizontal="center")
        ws_data.cell(row=current_row, column=2, value=row["name"]).alignment = Alignment(horizontal="left")
        ws_data.cell(row=current_row, column=3, value=row["code_num"]).alignment = Alignment(horizontal="center")
        ws_data.cell(row=current_row, column=4, value=row["code_str"]).alignment = Alignment(horizontal="center")
        ws_data.cell(row=current_row, column=5, value=row["qty"]).alignment = Alignment(horizontal="right")
        ws_data.cell(row=current_row, column=6, value=row["price"]).alignment = Alignment(horizontal="right")
        ws_data.cell(row=current_row, column=7, value=f"=E{current_row}*F{current_row}").alignment = Alignment(horizontal="right")
        ws_data.cell(row=current_row, column=8, value=str(row["part_no"])).alignment = Alignment(horizontal="center")
        ws_data.cell(row=current_row, column=9, value=row["net_unit"]).alignment = Alignment(horizontal="right")
        ws_data.cell(row=current_row, column=10, value=f"=E{current_row}*I{current_row}").alignment = Alignment(horizontal="right")
        ws_data.cell(row=current_row, column=11, value=row["gross_total"]).alignment = Alignment(horizontal="right")
        ws_data.cell(row=current_row, column=12, value=row["box_num"]).alignment = Alignment(horizontal="center")
        
        for col_idx in range(1, 13):
            cell = ws_data.cell(row=current_row, column=col_idx)
            cell.font = REGULAR_FONT
            cell.border = border_all
            if i % 2 == 1:
                cell.fill = ZEBRA_FILL
                
        # Форматы чисел
        ws_data.cell(row=current_row, column=5).number_format = '#,##0'
        ws_data.cell(row=current_row, column=6).number_format = '#,##0.00'
        ws_data.cell(row=current_row, column=7).number_format = '#,##0.00'
        ws_data.cell(row=current_row, column=9).number_format = '#,##0.00'
        ws_data.cell(row=current_row, column=10).number_format = '#,##0.00'
        ws_data.cell(row=current_row, column=11).number_format = '#,##0.000'
        ws_data.cell(row=current_row, column=3).number_format = '@'
        ws_data.cell(row=current_row, column=8).number_format = '@'
        
    tot_row = start_row + len(df_data)
    ws_data.cell(row=tot_row, column=2, value="ИТОГО:").font = BOLD_FONT
    ws_data.cell(row=tot_row, column=2).alignment = Alignment(horizontal="right")
    ws_data.cell(row=tot_row, column=5, value=f"=SUM(E5:E{tot_row-1})").number_format = '#,##0'
    ws_data.cell(row=tot_row, column=7, value=f"=SUM(G5:G{tot_row-1})").number_format = '#,##0.00'
    ws_data.cell(row=tot_row, column=10, value=f"=SUM(J5:J{tot_row-1})").number_format = '#,##0.00'
    ws_data.cell(row=tot_row, column=11, value=f"=SUM(K5:K{tot_row-1})").number_format = '#,##0.000'
    
    for col_idx in range(1, 13):
        cell = ws_data.cell(row=tot_row, column=col_idx)
        cell.font = BOLD_FONT
        cell.border = border_total
        cell.fill = TOTAL_FILL
        if col_idx in [5, 7, 10, 11]:
            cell.alignment = Alignment(horizontal="right")
            
    for col in ws_data.columns:
        max_len = max(len(str(cell.value or '')) for cell in col if cell.row > 2)
        col_letter = get_column_letter(col[0].column)
        ws_data.column_dimensions[col_letter].width = max(max_len + 3, 12)
    ws_data.column_dimensions['B'].width = 45

    # ==========================================
    # ЛИСТ 2: СВОДНАЯ АНАЛИТИКА (Дашборд)
    # ==========================================
    ws_dash = wb.create_sheet(title="Сводная аналитика")
    ws_dash.views.sheetView[0].showGridLines = True
    
    ws_dash["A1"] = "Сводный отчет по товарной партии"
    ws_dash["A1"].font = TITLE_FONT
    
    # --- Блоки KPI ---
    kpis = [
        ("Общая стоимость партии", f"='Данные для Заполнителя'!G{tot_row}", "#,##0.00 USD", "B3", "B4"),
        ("Общий вес нетто", f"='Данные для Заполнителя'!J{tot_row}", "#,##0.00 кг", "D3", "D4"),
        ("Общий вес брутто", f"='Данные для Заполнителя'!K{tot_row}", "#,##0.00 кг", "F3", "F4")
    ]
    
    kpi_label_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    kpi_val_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
    
    for label, formula, num_fmt, l_cell, v_cell in kpis:
        ws_dash[l_cell] = label
        ws_dash[l_cell].font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        ws_dash[l_cell].fill = kpi_label_fill
        ws_dash[l_cell].alignment = Alignment(horizontal="center", vertical="center")
        
        ws_dash[v_cell] = formula
        ws_dash[v_cell].font = Font(name="Calibri", size=14, bold=True, color="1F497D")
        ws_dash[v_cell].fill = kpi_val_fill
        ws_dash[v_cell].alignment = Alignment(horizontal="center", vertical="center")
        ws_dash[v_cell].number_format = num_fmt
        ws_dash[v_cell].border = border_all
        
    ws_dash.row_dimensions[3].height = 20
    ws_dash.row_dimensions[4].height = 30
    
    # --- Таблица мест ---
    ws_dash["B7"] = "Сводка по грузовым местам"
    ws_dash["B7"].font = BOLD_FONT
    
    dash_headers = ["Грузовое место", "Кол-во позиций", "Вес нетто, кг", "Вес брутто, кг"]
    for col_idx, text in enumerate(dash_headers, 2):
        cell = ws_dash.cell(row=8, column=col_idx, value=text)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        
    d_idx = 0
    for box, info in box_summary_data.items():
        r = 9 + d_idx
        ws_dash.cell(row=r, column=2, value=box).alignment = Alignment(horizontal="center")
        ws_dash.cell(row=r, column=3, value=info["items_count"]).alignment = Alignment(horizontal="right")
        ws_dash.cell(row=r, column=4, value=info["net_total"]).alignment = Alignment(horizontal="right")
        ws_dash.cell(row=r, column=5, value=info["gross_total"]).alignment = Alignment(horizontal="right")
        
        for c in range(2, 6):
            cell = ws_dash.cell(row=r, column=c)
            cell.font = REGULAR_FONT
            cell.border = border_all
            if c >= 4: cell.number_format = '#,##0.00'
        d_idx += 1
        
    r_tot = 9 + d_idx
    ws_dash.cell(row=r_tot, column=2, value="Всего").font = BOLD_FONT
    ws_dash.cell(row=r_tot, column=2).alignment = Alignment(horizontal="center")
    ws_dash.cell(row=r_tot, column=3, value=f"=SUM(C9:C{r_tot-1})")
    ws_dash.cell(row=r_tot, column=4, value=f"=SUM(D9:D{r_tot-1})")
    ws_dash.cell(row=r_tot, column=5, value=f"=SUM(E9:E{r_tot-1})")
    
    for c in range(2, 6):
        cell = ws_dash.cell(row=r_tot, column=c)
        cell.font = BOLD_FONT
        cell.fill = TOTAL_FILL
        cell.border = border_total
        if c >= 3:
            cell.alignment = Alignment(horizontal="right")
            if c >= 4: cell.number_format = '#,##0.00'
            
    # --- Диаграмма (BarChart) ---
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = "Распределение веса по грузовым местам (кг)"
    chart.y_axis.title = "Вес, кг"
    chart.x_axis.title = "Грузовое место"
    
    # Указываем, откуда брать данные (столбцы Нетто и Брутто)
    data = Reference(ws_dash, min_col=4, min_row=8, max_col=5, max_row=8+len(box_summary_data))
    # Указываем, откуда брать подписи оси X (названия мест)
    cats = Reference(ws_dash, min_col=2, min_row=9, max_row=8+len(box_summary_data))
    
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    ws_dash.add_chart(chart, "B14")
    chart.width = 16
    chart.height = 10
            
    for col in ws_dash.columns:
        ws_dash.column_dimensions[get_column_letter(col[0].column)].width = 18
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

# --- Блок интерфейса ---
col1, col2, col3 = st.columns(3)

with col1:
