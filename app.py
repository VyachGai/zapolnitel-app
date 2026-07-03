import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Таможенный Сборщик Pro", layout="wide")
st.title("📦 Сборщик данных в структурированную таблицу")

# Словарь для маппинга заголовков в нужные нам колонки
COLUMN_MAPPING = {
    'part_no': ['код', 'part', 'артикул', 'po number'],
    'name': ['наимен', 'name', 'description', 'описание'],
    'model': ['модель', 'model'],
    'qty': ['кол', 'qty', 'quantity'],
    'price': ['цена', 'price'],
    'weight': ['вес', 'weight', 'нетто', 'net']
}

def find_best_col(df, keywords):
    for col in df.columns:
        col_str = str(col).lower()
        if any(kw in col_str for kw in keywords):
            return col
    return None

def process_file(file):
    # Авто-определение типа файла
    if file.name.endswith('.csv'): df = pd.read_csv(file)
    else: df = pd.read_excel(file, header=0) # Или используйте вашу логику поиска заголовков
    
    # Создаем временный DF с нормализованными колонками
    new_df = pd.DataFrame()
    for target_col, keywords in COLUMN_MAPPING.items():
        found = find_best_col(df, keywords)
        if found:
            new_df[target_col] = df[found]
    
    # Удаляем строки, где совсем нет данных
    return new_df.dropna(how='all')

# --- ИНТЕРФЕЙС ---
col1, col2, col3 = st.columns(3)
file_inputs = [("Спецификация", col1), ("Инвойс", col2), ("Упаковочный", col3)]
uploaded_dfs = []

for name, col in file_inputs:
    with col:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls", "csv"], key=name)
        if up:
            uploaded_dfs.append(process_file(up))

if uploaded_dfs:
    if st.button("Сформировать итоговую таблицу"):
        # Объединяем все файлы в один список строк
        final_df = pd.concat(uploaded_dfs, axis=0, ignore_index=True)
        
        # Удаляем полные дубликаты строк (если данные дублируются в разных файлах)
        final_df = final_df.drop_duplicates()
        
        st.success("Таблица успешно собрана!")
        st.dataframe(final_df)
        
        # Скачивание
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать сводную таблицу", csv, "final_report.csv", "text/csv")
