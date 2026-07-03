import streamlit as st
import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
import io

# --- Настройка ---
st.set_page_config(page_title="Таможенный Заполнитель", layout="wide")
st.title("📦 Автоматизация таможенных деклараций")

# --- Улучшенный загрузчик с выбором движка ---
def get_excel_sheets(uploaded_file):
    uploaded_file.seek(0)
    # Пытаемся открыть через openpyxl, если падает — через xlrd
    try:
        xl = pd.ExcelFile(uploaded_file, engine='openpyxl')
        return xl.sheet_names
    except:
        try:
            uploaded_file.seek(0)
            xl = pd.ExcelFile(uploaded_file, engine='xlrd')
            return xl.sheet_names
        except Exception as e:
            st.error(f"Файл {uploaded_file.name} поврежден или имеет неверный формат: {e}")
            return []

def parse_selected_sheet(uploaded_file, sheet_name=None):
    uploaded_file.seek(0)
    try:
        # Пробуем openpyxl первым (для .xlsx)
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None, engine='openpyxl')
    except:
        uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None, engine='xlrd')
    
    # Поиск строки с заголовками
    header_row = 0
    for idx, row in df.iterrows():
        row_str = " ".join(row.astype(str)).lower()
        if any(kw in row_str for kw in ['код', 'part', 'наименование', 'qty']):
            header_row = idx
            break
    
    df_clean = df.iloc[header_row:].copy()
    df_clean.columns = df_clean.iloc[0]
    return df_clean.iloc[1:].reset_index(drop=True)

# --- Интерфейс ---
col1, col2, col3 = st.columns(3)

with col1:
    spec_file = st.file_uploader("Спецификация", type=["xlsx", "xls"])
with col2:
    invoice_file = st.file_uploader("Инвойс", type=["xlsx", "xls"])
with col3:
    pack_file = st.file_uploader("Упаковочный лист", type=["xlsx", "xls"])

if spec_file and invoice_file and pack_file:
    if st.button("Обработать файлы"):
        # Здесь идет ваша логика парсинга (упрощенно для примера)
        try:
            df_p = parse_selected_sheet(pack_file)
            st.write("Данные успешно считаны!")
            st.dataframe(df_p.head())
            # Далее ваша логика расчета...
        except Exception as e:
            st.error(f"Ошибка обработки: {e}")
            st.info("Убедитесь, что файлы не открыты в Excel в момент загрузки.")
