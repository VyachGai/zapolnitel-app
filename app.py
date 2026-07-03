import streamlit as st
import pandas as pd

st.set_page_config(page_title="Customs Parser Pro", layout="wide")
st.title("📦 Стабильный сборщик данных")

def get_clean_table(file, sheet, engine):
    file.seek(0)
    # Читаем сырые данные
    raw_df = pd.read_excel(file, sheet_name=sheet, header=None, engine=engine)
    
    # 1. ПОИСК ЗАГОЛОВКА: ищем строку с максимальным количеством ключевых слов
    keywords = ['код', 'part', 'no', 'наимен', 'name', 'qty', 'кол', 'description']
    max_matches = 0
    header_idx = None
    
    for idx, row in raw_df.iterrows():
        row_str = " ".join(row.astype(str).str.lower())
        matches = sum(1 for kw in keywords if kw in row_str)
        if matches > max_matches:
            max_matches = matches
            header_idx = idx
            
    if header_idx is None or max_matches < 2:
        return None, "Не удалось найти заголовок таблицы (попробуйте другой лист)"

    # 2. ОБРЕЗКА: делаем заголовок и удаляем мусор
    df = raw_df.iloc[header_idx:].reset_index(drop=True)
    df.columns = df.iloc[0].astype(str).str.strip().str.lower()
    df = df.iloc[1:].reset_index(drop=True)
    
    # 3. ФИЛЬТРАЦИЯ: Удаляем строки с мусором (адреса, подписи)
    # Оставляем только те строки, где в колонке с артикулом есть данные
    part_col = next((c for c in df.columns if any(k in str(c) for k in ['код', 'part', 'no'])), df.columns[0])
    
    # Удаляем пустые строки и строки с мусорными словами
    trash = ['consignee', 'shipper', 'contract', 'addr', 'итого', 'total', 'signature']
    df = df[df[part_col].notna()]
    df = df[~df[part_col].astype(str).str.lower().str.contains('|'.join(trash), na=False)]
    
    return df, "OK"

# --- ИНТЕРФЕЙС ---
uploaded_files = st.file_uploader("Загрузите Excel файлы", accept_multiple_files=True, type=['xlsx', 'xls'])
dfs = {}

if uploaded_files:
    for up in uploaded_files:
        try:
            engine = 'openpyxl' if up.name.endswith('.xlsx') else 'xlrd'
            xl = pd.ExcelFile(up, engine=engine)
            sheet = st.selectbox(f"Лист для {up.name}:", xl.sheet_names, key=up.name)
            
            df, status = get_clean_table(up, sheet, engine)
            if df is not None:
                dfs[up.name] = df
                st.write(f"✅ {up.name}: нашел {len(df)} строк.")
            else:
                st.error(f"❌ {up.name}: {status}")
        except Exception as e:
            st.error(f"Ошибка чтения {up.name}: {e}")

if dfs and st.button("Собрать таблицу"):
    try:
        # Объединяем все файлы в один
        final_df = pd.concat(dfs.values(), axis=0, ignore_index=True)
        final_df = final_df.drop_duplicates()
        
        st.success(f"Готово! Собрано строк: {len(final_df)}")
        st.dataframe(final_df)
        
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать результат", csv, "final_data.csv", "text/csv")
    except Exception as e:
        st.error(f"Ошибка сборки: {e}")
