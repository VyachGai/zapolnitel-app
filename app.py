import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Customs Parser", layout="wide")
st.title("📦 Таможенный Сборщик (Hardened Version)")

# 1. Функция поиска ключевых слов в строках для отсева мусора
def is_trash(row):
    text = " ".join(row.astype(str).str.lower())
    trash_patterns = ['consignee', 'shipper', 'address', 'грузо', 'покупатель', 'продав', 'итого', 'total', 'contract', 'контракт', 'signature']
    return any(p in text for p in trash_patterns)

# 2. Функция поиска заголовков (самая важная часть)
def find_header_row(df):
    keywords = ['код', 'part', 'артикул', 'name', 'наимен', 'qty', 'кол-во']
    for idx, row in df.iterrows():
        row_str = " ".join(row.astype(str).str.lower())
        # Если в строке 2 и более ключевых слова — это 99% заголовок таблицы
        if sum(1 for kw in keywords if kw in row_str) >= 2:
            return idx
    return None

def process_file(file):
    # Читаем файл как сырые данные
    df = pd.read_excel(file, header=None)
    
    # Ищем начало таблицы
    h_idx = find_header_row(df)
    if h_idx is None:
        return None, "Заголовок не найден"
    
    # Отрезаем всё сверху
    df = df.iloc[h_idx:].reset_index(drop=True)
    df.columns = df.iloc[0].astype(str).str.lower()
    df = df.iloc[1:]
    
    # Удаляем строки, где артикул пустой (NaN)
    # Ищем колонку с кодом/артикулом
    part_col = next((c for c in df.columns if any(k in str(c) for k in ['код', 'part', 'art'])), df.columns[0])
    df = df[df[part_col].notna()]
    
    return df, "OK"

# --- ИНТЕРФЕЙС ---
uploaded_files = st.file_uploader("Загрузите файлы", accept_multiple_files=True, type=['xlsx', 'xls'])
dfs = []

if uploaded_files:
    for up in uploaded_files:
        try:
            res_df, msg = process_file(up)
            if res_df is not None:
                dfs.append(res_df)
                st.write(f"✅ {up.name}: обработано ({len(res_df)} строк)")
            else:
                st.error(f"❌ {up.name}: {msg}")
        except Exception as e:
            st.error(f"❌ {up.name}: Ошибка - {e}")

if dfs and st.button("Собрать таблицу"):
    try:
        final_df = pd.concat(dfs, axis=0, ignore_index=True)
        st.dataframe(final_df)
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать", csv, "result.csv", "text/csv")
    except Exception as e:
        st.error(f"Ошибка сборки: {e}")
