import streamlit as st
import pandas as pd

st.set_page_config(page_title="Таможенный Сборщик Pro", layout="wide")
st.title("📦 Профессиональный сборщик данных")

# Функция безопасного чтения с выбором листа
def get_file_data(uploaded_file):
    xl = pd.ExcelFile(uploaded_file)
    sheet = st.selectbox(f"Выберите лист для {uploaded_file.name}:", xl.sheet_names)
    df = pd.read_excel(uploaded_file, sheet_name=sheet, header=None)
    
    # Умный поиск начала таблицы
    # Ищем строку, где есть хотя бы два ключевых слова из списка
    keywords = ['код', 'part', 'qty', 'кол', 'наимен', 'name']
    header_idx = 0
    for idx, row in df.iterrows():
        row_str = " ".join(row.astype(str).str.lower())
        matches = sum(1 for kw in keywords if kw in row_str)
        if matches >= 2:
            header_idx = idx
            break
            
    df = df.iloc[header_idx:].copy()
    df.columns = df.iloc[0].astype(str).str.strip().str.lower()
    df = df.iloc[1:].reset_index(drop=True)
    
    # ГЛАВНОЕ: Удаляем строки, где нет артикула или наименования
    df = df.dropna(subset=[df.columns[1]]) # Предполагаем, что артикул во 2-й колонке
    return df

# Интерфейс
files = {}
cols = st.columns(3)
for i, name in enumerate(["Спецификация", "Инвойс", "Упаковочный"]):
    with cols[i]:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls"], key=name)
        if up: files[name] = get_file_data(up)

if st.button("Сформировать чистую таблицу"):
    try:
        # Объединяем только те файлы, что были загружены
        merged = pd.concat(files.values(), axis=0, ignore_index=True)
        
        # Очистка от строк-дублей шапки, если они попали в середину
        merged = merged[~merged.iloc[:, 0].astype(str).str.lower().str.contains('код|part', na=False)]
        
        st.success("Таблица успешно очищена от мусора!")
        st.dataframe(merged)
        
        csv = merged.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать чистый CSV", csv, "clean_data.csv", "text/csv")
    except Exception as e:
        st.error(f"Ошибка при склейке: {e}")
