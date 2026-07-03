import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Таможенный Заполнитель Pro", layout="wide")
st.title("📦 Автоматическая обработка документов")

def get_sheets(file):
    file.seek(0)
    for engine in ['openpyxl', 'xlrd']:
        try:
            xl = pd.ExcelFile(file, engine=engine)
            return xl.sheet_names, engine
        except: continue
    return None, None

def read_data(file, sheet, engine):
    file.seek(0)
    # Читаем файл как текст, чтобы найти реальную строку с заголовками
    df_full = pd.read_excel(file, sheet_name=sheet, header=None, engine=engine)
    
    # Ищем строку с заголовками (там, где много ключевых слов)
    header_idx = 0
    keywords = ['код', 'part', 'наимен', 'name', 'qty', 'кол', 'мест', 'box', 'упак']
    max_matches = 0
    
    for idx, row in df_full.iterrows():
        row_str = " ".join(row.astype(str).str.lower())
        matches = sum(1 for kw in keywords if kw in row_str)
        if matches > max_matches:
            max_matches = matches
            header_idx = idx
            
    df = df_full.iloc[header_idx:].copy()
    df.columns = df.iloc[0].astype(str).str.strip().str.lower()
    return df.iloc[1:].reset_index(drop=True)

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
        df_p = files["Упаковочный"]
        
        def find_col(df, kws):
            for col in df.columns:
                if any(k in col for k in kws): return col
            return None

        # Поиск
        c_part = find_col(df_p, ['код', 'part'])
        c_name = find_col(df_p, ['наимен', 'name', 'descr'])
        c_qty = find_col(df_p, ['кол', 'qty'])
        
        # Проверка
        if c_part and c_name and c_qty:
            df_res = pd.DataFrame({
                'part_no': df_p[c_part].astype(str).str.replace('.0', '', regex=False),
                'name': df_p[c_name],
                'qty': pd.to_numeric(df_p[c_qty], errors='coerce')
            })
            st.success("Данные успешно извлечены!")
            st.dataframe(df_res)
        else:
            st.error("Не удалось найти необходимые колонки (Код/Наименование/Кол-во).")
            st.write("Найденные в файле заголовки:", list(df_p.columns))
