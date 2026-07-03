import streamlit as st
import pandas as pd

st.set_page_config(page_title="Customs Parser", layout="wide")
st.title("📦 Стабильный сборщик данных")

# 1. Сюда добавьте все варианты названий колонок, которые встречаются в ваших файлах
COLUMN_MAPPING = {
    'part_no': ['код', 'part', 'артикул', 'po number', 'код изделия'],
    'name': ['наимен', 'name', 'description', 'описание', 'наименование'],
    'qty': ['кол', 'qty', 'quantity', 'количество'],
    'price': ['цена', 'price', 'стоимость'],
    'weight': ['вес', 'weight', 'нетто', 'net']
}

def clean_and_extract(df):
    # Пытаемся найти "голову" таблицы
    # Ищем строку, где есть хотя бы 2 слова из списка
    keywords = ['код', 'part', 'qty', 'кол', 'name', 'артикул']
    header_idx = None
    for idx, row in df.iterrows():
        row_str = " ".join(row.astype(str).str.lower())
        if sum(1 for kw in keywords if kw in row_str) >= 2:
            header_idx = idx
            break
            
    if header_idx is None: return None
    
    # Режем таблицу
    df = df.iloc[header_idx:].reset_index(drop=True)
    df.columns = df.iloc[0].astype(str).str.lower().str.strip()
    df = df.iloc[1:].reset_index(drop=True)
    
    # ПЕРЕИМЕНОВЫВАЕМ КОЛОНКИ В СТАНДАРТ
    new_df = pd.DataFrame()
    for std_name, variants in COLUMN_MAPPING.items():
        found_col = next((c for c in df.columns if any(v in c for v in variants)), None)
        if found_col:
            new_df[std_name] = df[found_col]
            
    # УДАЛЯЕМ МУСОР (оставляем только строки, где в part_no что-то есть)
    if 'part_no' in new_df.columns:
        new_df = new_df[new_df['part_no'].notna()]
        new_df = new_df[~new_df['part_no'].astype(str).str.lower().str.contains('consignee|shipper|addr|итого|total|№|всего')]
    
    return new_df

# --- ИНТЕРФЕЙС ---
uploaded_files = st.file_uploader("Загрузите файлы", accept_multiple_files=True, type=['xlsx', 'xls'])
dfs = []

if uploaded_files:
    for up in uploaded_files:
        try:
            xl = pd.ExcelFile(up)
            sheet = st.selectbox(f"Лист для {up.name}:", xl.sheet_names, key=up.name)
            raw_df = pd.read_excel(up, sheet_name=sheet, header=None)
            
            clean_df = clean_and_extract(raw_df)
            if clean_df is not None and not clean_df.empty:
                dfs.append(clean_df)
                st.write(f"✅ {up.name}: собрано {len(clean_df)} строк.")
            else:
                st.error(f"❌ {up.name}: Не удалось найти таблицу. Проверьте лист.")
        except Exception as e:
            st.error(f"Ошибка чтения {up.name}: {e}")

if st.button("Собрать таблицу"):
    if dfs:
        # Объединяем
        final_df = pd.concat(dfs, axis=0, ignore_index=True)
        # Удаляем дубликаты
        final_df = final_df.drop_duplicates()
        
        st.success(f"Готово! Строк: {len(final_df)}")
        st.dataframe(final_df)
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать CSV", csv, "result.csv", "text/csv")
    else:
        st.warning("Нет данных для сборки.")
