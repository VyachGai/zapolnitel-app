import streamlit as st
import pandas as pd

st.set_page_config(page_title="Customs Parser Pro", layout="wide")
st.title("📦 Стабильный сборщик данных")

def clean_file(file, sheet, engine):
    file.seek(0)
    # Читаем весь файл
    df = pd.read_excel(file, sheet_name=sheet, header=None, engine=engine)
    
    # 1. Поиск строки с заголовками
    keywords = ['код', 'part', 'артикул', 'name', 'qty', 'кол', 'price', 'вес']
    header_idx = None
    for idx, row in df.iterrows():
        # Превращаем строку в текст для поиска
        row_str = " ".join(row.astype(str).str.lower())
        if sum(1 for kw in keywords if kw in row_str) >= 2:
            header_idx = idx
            break
            
    if header_idx is None:
        return None

    # 2. Обрезка и нормализация
    df = df.iloc[header_idx:].reset_index(drop=True)
    df.columns = df.iloc[0].astype(str).str.strip().str.lower()
    df = df.iloc[1:].reset_index(drop=True)
    
    # 3. Фильтрация (удаляем мусор)
    # Оставляем строки, где в первой колонке НЕ содержатся стоп-слова
    trash = ['consignee', 'shipper', 'contract', 'addr', 'упак', 'итого', 'total', 'signature']
    # Используем .astype(str) чтобы избежать ошибок с NaN
    mask = ~df.iloc[:, 0].astype(str).str.lower().str.contains('|'.join(trash), na=False)
    df = df[mask]
    
    # Удаляем пустые строки
    df = df.dropna(how='all')
    
    return df

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
            # ПРОВЕРКА ЧЕРЕЗ .empty ВМЕСТО if df:
            if clean_df is not None and not clean_df.empty:
                dfs.append(clean_df)
                st.write(f"✅ {up.name}: обработано, строк: {len(clean_df)}")
            else:
                st.warning(f"⚠️ {up.name}: Таблица не найдена или пуста.")
        except Exception as e:
            st.error(f"Ошибка чтения {up.name}: {e}")

if st.button("Собрать таблицу"):
    # ПРОВЕРКА ЧЕРЕЗ len(dfs) > 0
    if len(dfs) > 0:
        try:
            final_df = pd.concat(dfs, axis=0, ignore_index=True)
            final_df = final_df.drop_duplicates()
            
            st.success(f"Готово! Собрано строк: {len(final_df)}")
            st.dataframe(final_df)
            
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать CSV", csv, "result.csv", "text/csv")
        except Exception as e:
            st.error(f"Ошибка при сборке: {e}")
    else:
        st.error("Нет данных для сборки. Проверьте файлы.")
