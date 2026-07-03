import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Таможенный Сборщик Pro", layout="wide")
st.title("📦 Сборка таможенных данных")

# 1. Словарь для поиска колонок (все варианты названий)
COLS_MAP = {
    'part_no': ['код', 'part', 'артикул', 'po number', 'код изделия'],
    'name': ['наимен', 'name', 'description', 'описание', 'наименование'],
    'qty': ['кол', 'qty', 'quantity', 'количество'],
    'price': ['цена', 'price', 'стоимость'],
    'weight': ['вес', 'weight', 'нетто', 'net', 'gross']
}

def clean_df(df):
    """Приводит данные к чистому виду: очищает заголовки и удаляет мусорные строки"""
    # Сначала пытаемся найти строку с заголовками, где больше всего ключевых слов
    flat_cols = df.astype(str).apply(lambda x: ' '.join(x).lower(), axis=1)
    keywords = ['код', 'part', 'qty', 'кол', 'name', 'наимен']
    header_idx = flat_cols.str.contains('|'.join(keywords)).idxmax()
    
    df_clean = df.iloc[header_idx:].copy()
    df_clean.columns = df_clean.iloc[0].astype(str).str.strip().str.lower()
    df_clean = df_clean.iloc[1:].reset_index(drop=True)
    
    # Очистка мусора (строки, где в первом столбце какой-то текст, а не артикул)
    # Удаляем строки, где нет артикула
    part_col = next((c for c in df_clean.columns if any(k in c for k in COLS_MAP['part_no'])), None)
    if part_col:
        df_clean = df_clean[df_clean[part_col].notna()]
        df_clean = df_clean[~df_clean[part_col].astype(str).str.lower().str.contains('consignee|shipper|addr|упак|list|контракт')]
        
    return df_clean

def normalize_df(df):
    """Преобразует таблицу в стандартный вид"""
    res = pd.DataFrame()
    for std_name, vars in COLS_MAP.items():
        found = next((c for c in df.columns if any(v in c for v in vars)), None)
        if found:
            res[std_name] = df[found]
    return res

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
                s = st.selectbox(f"Лист для {name}:", xl.sheet_names, key=f"sel_{name}")
                raw_df = pd.read_excel(up, sheet_name=s, header=None, engine=engine)
                files[name] = normalize_df(clean_df(raw_df))
            except Exception as e:
                st.error(f"Ошибка загрузки {name}: {e}")

if files:
    if st.button("Собрать таблицу по артикулам"):
        try:
            # Магия объединения: берем все файлы и соединяем их по 'part_no'
            master_df = None
            for name, df in files.items():
                if master_df is None:
                    master_df = df
                else:
                    # Используем how='outer', чтобы сохранить все артикулы, даже если они есть только в 1 файле
                    master_df = pd.merge(master_df, df, on='part_no', how='outer', suffixes=('', f'_{name}'))
            
            st.success("Таблица собрана!")
            st.dataframe(master_df)
            
            csv = master_df.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать итоговый CSV", csv, "merged_report.csv", "text/csv")
        except Exception as e:
            st.error(f"Ошибка объединения: {e}")
