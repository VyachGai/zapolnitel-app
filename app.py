import streamlit as st
import pandas as pd
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
import io

st.set_page_config(page_title="Таможенный Заполнитель Pro", layout="wide")
st.title("📦 Автоматическая обработка документов")

# --- Вспомогательные функции ---
def get_sheets(file):
    file.seek(0)
    try:
        xl = pd.ExcelFile(file, engine='openpyxl')
        return xl.sheet_names, 'openpyxl'
    except:
        file.seek(0)
        try:
            xl = pd.ExcelFile(file, engine='xlrd')
            return xl.sheet_names, 'xlrd'
        except:
            return None, None

def read_data(file, sheet, engine):
    file.seek(0)
    # Читаем без заголовков, чтобы найти их вручную
    df = pd.read_excel(file, sheet_name=sheet, header=None, engine=engine)
    
    # Ищем строку с заголовками
    header_idx = 0
    for idx, row in df.iterrows():
        row_str = " ".join(row.astype(str)).lower()
        if any(kw in row_str for kw in ['код', 'part', 'наименование', 'name', 'qty', 'кол']):
            header_idx = idx
            break
    
    df_clean = df.iloc[header_idx:].copy()
    df_clean.columns = df_clean.iloc[0].astype(str).str.strip().str.lower()
    return df_clean.iloc[1:].reset_index(drop=True)

# --- ИНТЕРФЕЙС ---
col1, col2, col3 = st.columns(3)
files = {}

for name, col in [("Спецификация", col1), ("Инвойс", col2), ("Упаковочный", col3)]:
    with col:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls"], key=name)
        if up:
            sheets, engine = get_sheets(up)
            if sheets:
                s_sheet = st.selectbox(f"Лист для {name}:", sheets, key=f"sel_{name}")
                files[name] = read_data(up, s_sheet, engine)

if len(files) == 3:
    if st.button("Сформировать таблицу"):
        try:
            df_p = files["Упаковочный"]
            
            # Авто-поиск колонок по ключевым словам в нижнем регистре
            def get_col(df, kws):
                for col in df.columns:
                    if any(k in col for k in kws): return col
                return None

            c_part = get_col(df_p, ['код', 'part'])
            c_name = get_col(df_p, ['наимен', 'name', 'descr'])
            c_qty = get_col(df_p, ['кол', 'qty'])
            c_net = get_col(df_p, ['нетто', 'net'])
            c_gross = get_col(df_p, ['брутто', 'gross'])
            c_box = get_col(df_p, ['мест', 'box', 'package'])

            # Создаем унифицированный DataFrame
            df_res = pd.DataFrame({
                'part_no': df_p[c_part].astype(str).str.replace('.0', ''),
                'name': df_p[c_name],
                'qty': pd.to_numeric(df_p[c_qty], errors='coerce'),
                'net': pd.to_numeric(df_p[c_net], errors='coerce'),
                'gross': pd.to_numeric(df_p[c_gross], errors='coerce'),
                'box': df_p[c_box].ffill()
            })
            
            st.success("Данные успешно нормализованы!")
            st.dataframe(df_res)
            
            # Выгрузка
            csv = df_res.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать CSV", csv, "final_data.csv", "text/csv")
            
        except Exception as e:
            st.error(f"Ошибка логики: {e}")
            st.write("Колонки, которые я вижу в Упаковочном листе:", list(df_p.columns))
