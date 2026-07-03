import streamlit as st
import pandas as pd

st.set_page_config(page_title="Таможенный Сборщик", layout="wide")
st.title("📦 Сборщик данных (Исправленная версия)")

# Список слов, которые гарантированно являются "мусором"
TRASH_KEYWORDS = [
    'consignee', 'shipper', 'address', 'грузо', 'покупатель', 
    'продавец', 'счет-фактура', 'итого', 'total', 'contract', 'контракт'
]

def clean_and_normalize(df):
    """Находит начало таблицы и очищает от мусора"""
    # 1. Поиск строки заголовка: ищем строку, где есть 'код' или 'part'
    header_row_idx = None
    for idx, row in df.iterrows():
        row_str = " ".join(row.astype(str).str.lower())
        if any(kw in row_str for kw in ['код', 'part', 'артикул', 'po number']):
            header_row_idx = idx
            break
    
    if header_row_idx is None:
        return None # Таблица не найдена

    # Читаем таблицу с нужной строки
    df = df.iloc[header_row_idx:].reset_index(drop=True)
    df.columns = df.iloc[0].astype(str).str.strip().str.lower()
    df = df.iloc[1:].reset_index(drop=True)
    
    # 2. Очистка строк: удаляем, где нет артикула или где есть мусорные слова
    # Предполагаем, что артикул в первой колонке с ключевым словом
    part_col = next((c for c in df.columns if any(k in c for k in ['код', 'part'])), df.columns[0])
    
    # Убираем пустые
    df = df[df[part_col].notna()]
    # Убираем строки с мусором
    for kw in TRASH_KEYWORDS:
        df = df[~df[part_col].astype(str).str.lower().str.contains(kw, na=False)]
        
    return df

# --- ИНТЕРФЕЙС ---
uploaded_files = st.file_uploader("Загрузите файлы Excel", accept_multiple_files=True, type=['xlsx', 'xls'])
dfs = []

if uploaded_files:
    for up in uploaded_files:
        try:
            xl = pd.ExcelFile(up)
            sheet = st.selectbox(f"Лист для {up.name}:", xl.sheet_names)
            raw = pd.read_excel(up, sheet_name=sheet, header=None)
            
            clean_df = clean_and_normalize(raw)
            if clean_df is not None:
                dfs.append(clean_df)
                st.write(f"✅ Файл {up.name} загружен, строк: {len(clean_df)}")
            else:
                st.error(f"❌ Не удалось найти таблицу в файле {up.name}")
        except Exception as e:
            st.error(f"Ошибка в файле {up.name}: {e}")

if dfs and st.button("Собрать таблицу"):
    try:
        # Объединяем все файлы по артикулу (part_no)
        # Приводим названия колонок к общему виду перед объединением
        final_df = dfs[0]
        for i in range(1, len(dfs)):
            final_df = pd.merge(final_df, dfs[i], on=list(final_df.columns[0:1]), how='outer')
        
        st.success("Таблица собрана!")
        st.dataframe(final_df)
        
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать чистый CSV", csv, "final_data.csv", "text/csv")
    except Exception as e:
        st.error(f"Ошибка сборки: {e}")
