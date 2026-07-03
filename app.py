import streamlit as st
import pandas as pd

st.set_page_config(page_title="Таможенный Сборщик", layout="wide")
st.title("📦 Сборщик данных (Максимально надежный)")

def clean_file(file, sheet, engine):
    file.seek(0)
    # Читаем файл без заголовков
    df = pd.read_excel(file, sheet_name=sheet, header=None, engine=engine)
    
    # 1. Поиск строки с заголовками
    keywords = ['код', 'part', 'артикул', 'наимен', 'name', 'qty', 'кол']
    header_idx = None
    for idx, row in df.iterrows():
        row_str = " ".join(row.astype(str).str.lower())
        if any(kw in row_str for kw in keywords):
            header_idx = idx
            break
            
    if header_idx is None:
        st.error(f"Не удалось найти строку с заголовками (искали: {keywords})")
        return None

    # 2. Безопасная нарезка таблицы
    # Проверяем, есть ли вообще данные после строки с заголовком
    if len(df) <= header_idx + 1:
        st.warning("Заголовок найден, но под ним нет данных.")
        return None

    df_clean = df.iloc[header_idx + 1:].copy()
    df_clean.columns = df.iloc[header_idx].astype(str).str.strip().str.lower()
    df_clean = df_clean.reset_index(drop=True)
    
    # 3. Фильтрация мусора
    # Удаляем строки, где пустой первый столбец
    df_clean = df_clean[df_clean.iloc[:, 0].notna()]
    
    # Удаляем явно мусорные строки (по ключевым словам)
    trash = ['consignee', 'shipper', 'contract', 'addr', 'упак', 'лист', 'итого', 'total']
    # Проверяем только первый столбец, чтобы не удалить случайно данные
    df_clean = df_clean[~df_clean.iloc[:, 0].astype(str).str.lower().str.contains('|'.join(trash), na=False)]
        
    return df_clean

# --- ИНТЕРФЕЙС ---
uploaded_files = st.file_uploader("Загрузите файлы Excel", accept_multiple_files=True, type=['xlsx', 'xls'])
dfs = []

if uploaded_files:
    for up in uploaded_files:
        try:
            engine = 'openpyxl' if up.name.endswith('.xlsx') else 'xlrd'
            xl = pd.ExcelFile(up, engine=engine)
            sheet = st.selectbox(f"Лист для {up.name}:", xl.sheet_names, key=up.name)
            
            clean_df = clean_file(up, sheet, engine)
            if clean_df is not None:
                dfs.append(clean_df)
                st.write(f"✅ Файл {up.name} обработан, найдено строк: {len(clean_df)}")
        except Exception as e:
            st.error(f"Ошибка чтения {up.name}: {e}")

if dfs and st.button("Собрать таблицу"):
    try:
        # Объединяем все найденные данные
        final_df = pd.concat(dfs, axis=0, ignore_index=True)
        final_df = final_df.drop_duplicates()
        
        st.success(f"Готово! Собрано строк: {len(final_df)}")
        st.dataframe(final_df)
        
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать CSV", csv, "final_data.csv", "text/csv")
    except Exception as e:
        st.error(f"Ошибка при сборке: {e}")
