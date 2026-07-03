import streamlit as st
import pandas as pd

st.set_page_config(page_title="Таможенный Сборщик Pro", layout="wide")
st.title("📦 Профессиональный сборщик данных")

# Функция безопасного чтения с авто-поиском заголовка
def read_data_clean(file, sheet, engine):
    file.seek(0)
    df_raw = pd.read_excel(file, sheet_name=sheet, header=None, engine=engine)
    
    # 1. Поиск строки с заголовками
    keywords = ['код', 'part', 'наимен', 'name', 'qty', 'кол']
    header_idx = 0
    for idx, row in df_raw.iterrows():
        row_str = " ".join(row.astype(str).str.lower())
        if sum(1 for kw in keywords if kw in row_str) >= 2:
            header_idx = idx
            break
            
    df = df_raw.iloc[header_idx:].copy()
    df.columns = df.iloc[0].astype(str).str.strip().str.lower()
    df = df.iloc[1:].reset_index(drop=True)
    
    # 2. Очистка от "мусора" (удаляем строки с CONSIGNEE, SHIPPER и т.д.)
    trash_words = ['consignee', 'shipper', 'contract', 'packing list', 'address']
    for kw in trash_words:
        df = df[~df.iloc[:, 0].astype(str).str.lower().str.contains(kw, na=False)]
    
    # 3. Удаляем строки, где совсем нет данных
    return df.dropna(how='all')

# --- ИНТЕРФЕЙС ---
files = {}
cols = st.columns(3)
for i, name in enumerate(["Спецификация", "Инвойс", "Упаковочный"]):
    with cols[i]:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls"], key=name)
        if up:
            try:
                # Определяем движок
                engine = 'openpyxl' if up.name.endswith('.xlsx') else 'xlrd'
                xl = pd.ExcelFile(up, engine=engine)
                s_sheet = st.selectbox(f"Лист для {name}:", xl.sheet_names, key=f"sel_{name}")
                files[name] = read_data_clean(up, s_sheet, engine)
            except Exception as e:
                st.error(f"Ошибка чтения {name}: {e}")

# Исправленная проверка наличия файлов
if len(files) > 0:
    if st.button("Сформировать чистую таблицу"):
        try:
            # Объединяем все загруженные файлы
            merged = pd.concat(files.values(), axis=0, ignore_index=True)
            
            st.success("Таблица успешно очищена от мусора!")
            st.dataframe(merged)
            
            csv = merged.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать чистый CSV", csv, "clean_data.csv", "text/csv")
        except Exception as e:
            st.error(f"Ошибка склейки данных: {e}")
else:
    st.info("Пожалуйста, загрузите хотя бы один файл.")
