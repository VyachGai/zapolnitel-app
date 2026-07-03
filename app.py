import streamlit as st
import pandas as pd

st.set_page_config(page_title="Таможенный Сборщик Pro", layout="wide")
st.title("📦 Профессиональный сборщик данных")

# Словарь для унификации названий (после этого программа будет знать, где артикул, а где цена)
COL_MAP = {
    'part_no': ['код', 'part', 'артикул', 'po number', 'код изделия'],
    'name': ['наимен', 'name', 'description', 'описание'],
    'qty': ['кол', 'qty', 'quantity'],
    'price': ['цена', 'price'],
    'weight': ['вес', 'weight', 'нетто', 'net']
}

def normalize_columns(df):
    """Приводит все колонки к единым именам из COL_MAP"""
    new_df = pd.DataFrame()
    for standard_name, variants in COL_MAP.items():
        # Ищем колонку, содержащую любое из ключевых слов
        for col in df.columns:
            if any(v in str(col).lower() for v in variants):
                new_df[standard_name] = df[col]
                break
    return new_df

def read_file(file, sheet, engine):
    file.seek(0)
    # Читаем первые 50 строк, чтобы найти заголовок
    df_raw = pd.read_excel(file, sheet_name=sheet, header=None, nrows=50, engine=engine)
    
    # Ищем "умный" заголовок
    header_idx = 0
    for idx, row in df_raw.iterrows():
        if sum(1 for kw in ['код', 'part', 'qty', 'кол', 'name'] if kw in str(row).lower()) >= 2:
            header_idx = idx
            break
            
    df = pd.read_excel(file, sheet_name=sheet, header=header_idx, engine=engine)
    # Очищаем имена колонок
    df.columns = df.columns.astype(str).str.lower().str.strip()
    
    # Удаляем "мусорные" строки (шапку, адреса)
    trash = ['consignee', 'shipper', 'contract', 'address']
    for t in trash:
        df = df[~df.iloc[:, 0].astype(str).str.lower().str.contains(t, na=False)]
        
    return normalize_columns(df)

# --- ИНТЕРФЕЙС ---
files = {}
cols = st.columns(3)
for i, name in enumerate(["Спецификация", "Инвойс", "Упаковочный"]):
    with cols[i]:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls"], key=name)
        if up:
            try:
                engine = 'openpyxl' if up.name.endswith('.xlsx') else 'xlrd'
                xl = pd.ExcelFile(up, engine=engine)
                s = st.selectbox(f"Лист для {name}:", xl.sheet_names, key=f"s_{name}")
                files[name] = read_file(up, s, engine)
            except Exception as e:
                st.error(f"Ошибка чтения {name}: {e}")

if st.button("Собрать таблицу"):
    if files:
        try:
            # Склеиваем все файлы
            merged = pd.concat(files.values(), axis=0, ignore_index=True)
            # Удаляем полные дубликаты
            merged = merged.drop_duplicates()
            
            st.success("Таблица готова!")
            st.dataframe(merged)
            
            csv = merged.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать CSV", csv, "result.csv", "text/csv")
        except Exception as e:
            st.error(f"Ошибка: {e}")
    else:
        st.warning("Загрузите хотя бы один файл.")
