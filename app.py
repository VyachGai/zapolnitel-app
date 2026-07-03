import streamlit as st
import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
import io
import requests
import pdfplumber

# --- Настройка страницы ---
st.set_page_config(page_title="Таможенный Заполнитель Pro", page_icon="🗃️", layout="wide")

st.title("📦 Автоматическая подготовка данных (с полной аналитикой)")
st.markdown("Загрузите исходные документы. Приложение автоматически считает данные, объединит позиции и пропорционально распределит вес брутто.")

# --- Умная функция поиска столбцов по ключевым словам ---
def find_col(columns, keywords):
    for col in columns:
        col_clean = str(col).lower().strip()
        if any(kw in col_clean for kw in keywords):
            return col
    return None

# --- Функция парсинга документов со смещенной шапкой ---
def parse_tabular_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file, header=None)
    else:
        df = pd.read_excel(uploaded_file, header=None)
        
    # Ищем строку, где начинается таблица (заголовок)
    header_row_idx = 0
    for idx, row in df.iterrows():
        row_str = " ".join(row.astype(str).lower())
        if any(kw in row_str for kw in ['код изделия', 'part number', 'наименование', 'goods name', '№ места', 'package no']):
            header_row_idx = idx
            break
            
    # Пересобираем DataFrame с правильным заголовком
    df_clean = df.iloc[header_row_idx:].copy()
    df_clean.columns = df_clean.iloc[0]
    df_clean = df_clean.iloc[1:].reset_index(drop=True)
    return df_clean

# --- Функция генерации Excel ---
def create_styled_excel(df_data, box_summary_data):
    wb = openpyxl.Workbook()
    
    # Стили
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
    
    # --- ЛИСТ 1: Данные для Заполнителя ---
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

    # --- ЛИСТ 2: Сводная аналитика ---
    ws_dash = wb.create_sheet(title="Сводная аналитика")
    ws_dash.views.sheetView[0].showGridLines = True
    
    ws_dash["A1"] = "Сводный отчет по товарной партии"
    ws_dash["A1"].font = TITLE_FONT
    
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
            
    # Диаграмма
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = "Распределение веса по грузовым местам (кг)"
    chart.y_axis.title = "Вес, кг"
    chart.x_axis.title = "Грузовое место"
    
    data = Reference(ws_dash, min_col=4, min_row=8, max_col=5, max_row=8+len(box_summary_data))
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

# --- Интерфейс приложения ---
col1, col2, col3 = st.columns(3)

with col1:
    spec_file = st.file_uploader("📋 Спецификация", type=["xlsx", "csv", "pdf", "jpg", "bmp"])
with col2:
    invoice_file = st.file_uploader("🧾 Инвойс", type=["xlsx", "csv", "pdf", "jpg", "bmp"])
with col3:
    pack_file = st.file_uploader("📦 Упаковочный лист", type=["xlsx", "csv", "pdf", "jpg", "bmp"])

if spec_file and invoice_file and pack_file:
    if st.button("Распознать текст и сформировать отчет", type="primary"):
        with st.spinner('Анализируем загруженные файлы и рассчитываем веса...'):
            try:
                # Проверяем форматы. Полноценный динамический разбор делаем для табличных форматов.
                if not (pack_file.name.endswith(('.xlsx', '.xls', '.csv'))):
                    st.warning("⚠️ Для полной автоматизации расчетов загружайте файлы в форматах Excel (.xlsx) или CSV.")
                    st.stop()

                # 1. Читаем и очищаем Упаковочный лист
                df_p = parse_tabular_file(pack_file)
                
                c_box = find_col(df_p.columns, ['мест', 'package'])
                c_part = find_col(df_p.columns, ['код изделия', 'part no', 'артикул'])
                c_name = find_col(df_p.columns, ['наименование', 'goods name', 'description'])
                c_qty = find_col(df_p.columns, ['кол', 'qty', 'quantity'])
                c_net = find_col(df_p.columns, ['нетто', 'net weight'])
                c_gross = find_col(df_p.columns, ['брутто', 'gross weight'])
                
                if not c_box or not c_part or not c_qty:
                    st.error("Не удалось найти обязательные столбцы (Номер места, Артикул или Количество) в Упаковочном листе. Проверьте структуру файла.")
                    st.stop()
                    
                # Заполняем пустые ячейки мест (объединенные ячейки в Excel)
                df_p[c_box] = df_p[c_box].ffill()
                
                # Приводим типы к числовым
                df_p[c_qty] = pd.to_numeric(df_p[c_qty], errors='coerce')
                df_p[c_net] = pd.to_numeric(df_p[c_net], errors='coerce')
                df_p[c_gross] = pd.to_numeric(df_p[c_gross], errors='coerce')
                
                # Удаляем мусорные строки
                df_p = df_p.dropna(subset=[c_part, c_qty])
                
                # Запоминаем общий брутто-вес для каждой коробки (он указан в первой строчке места)
                box_gross_weights = df_p.groupby(c_box)[c_gross].max().to_dict()
                
                # Группируем упаковочный лист, чтобы сложить повторяющиеся товары ВНУТРИ одного места
                df_p_grouped = df_p.groupby([c_box, c_part, c_name], as_index=False).agg({c_qty: 'sum', c_net: 'sum'})

                # 2. Собираем цены из Спецификации или Инвойса
                price_dict = {}
                for doc in [spec_file, invoice_file]:
                    if doc.name.endswith(('.xlsx', '.xls', '.csv')):
                        df_doc = parse_tabular_file(doc)
                        c_doc_part = find_col(df_doc.columns, ['код', 'part', 'артикул'])
                        c_doc_price = find_col(df_doc.columns, ['цена', 'price', 'тариф'])
                        if c_doc_part and c_doc_price:
                            df_doc[c_doc_price] = pd.to_numeric(df_doc[c_doc_price], errors='coerce')
                            extracted_prices = df_doc.dropna(subset=[c_doc_part, c_doc_price]).set_index(c_doc_part)[c_doc_price].to_dict()
                            price_dict.update(extracted_prices)

                # 3. Основной цикл сборки данных и распределения весов брутто
                final_rows = []
                box_summary = {}
                unique_boxes = df_p_grouped[c_box].unique()
                
                for box in unique_boxes:
                    box_df = df_p_grouped[df_p_grouped[c_box] == box]
                    box_gross = float(box_gross_weights.get(box, 0.0))
                    box_net_total = float(box_df[c_net].sum())
                    
                    indices = box_df.index.tolist()
                    running_gross = 0.0
                    
                    for idx in indices[:-1]:
                        row = box_df.loc[idx]
                        item_net = float(row[c_net])
                        
                        # Расчет пропорционального брутто
                        calc_gross = round(item_net * (box_gross / box_net_total), 3) if box_net_total > 0 else 0.0
                        running_gross += calc_gross
                        
                        part_val = str(row[c_part]).strip()
                        qty_val = int(row[c_qty])
                        
                        final_rows.append({
                            "name": str(row[c_name]),
                            "code_num": "796",
                            "code_str": "шт",
                            "qty": qty_val,
                            "price": float(price_dict.get(part_val, 0.0)),
                            "part_no": part_val,
                            "net_unit": round(item_net / qty_val, 3) if qty_val > 0 else 0.0,
                            "box_num": str(box),
                            "gross_total": calc_gross
                        })
                        
                    # Последний элемент в коробке забирает хвостовой остаток
                    if indices:
                        last_idx = indices[-1]
                        row = box_df.loc[last_idx]
                        item_net = float(row[c_net])
                        calc_gross = round(box_gross - running_gross, 3)
                        
                        part_val = str(row[c_part]).strip()
                        qty_val = int(row[c_qty])
                        
                        final_rows.append({
                            "name": str(row[c_name]),
                            "code_num": "796",
                            "code_str": "шт",
                            "qty": qty_val,
                            "price": float(price_dict.get(part_val, 0.0)),
                            "part_no": part_val,
                            "net_unit": round(item_net / qty_val, 3) if qty_val > 0 else 0.0,
                            "box_num": str(box),
                            "gross_total": calc_gross
                        })
                        
                    # Заполняем данные для сводного дашборда
                    box_summary[f"Место {box}"] = {
                        "items_count": len(indices),
                        "net_total": box_net_total,
                        "gross_total": box_gross
                    }

                df_final_result = pd.DataFrame(final_rows)
                
                if df_final_result.empty:
                    st.error("Не удалось сопоставить данные из файлов. Убедитесь, что артикулы в упаковочном листе и инвойсе совпадают.")
                    st.stop()

                # Строим итоговый стилизованный файл
                excel_output = create_styled_excel(df_final_result, box_summary)
                
                st.success("🎉 Обработка завершена! Новый файл успешно сформирован на основе ваших данных.")
                st.download_button(
                    label="📥 Скачать Excel (Таблица + Дашборд)",
                    data=excel_output,
                    file_name="Tamozhnya_Zapolnitel_Pro.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
            except Exception as e:
                st.error(f"Ошибка при обработке файлов: {e}")
                st.info("Проверьте, что файлы не повреждены и содержат стандартные таблицы.")
