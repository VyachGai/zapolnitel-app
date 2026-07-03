import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Таможенный Сборщик Pro", layout="wide")
st.title("📦 Сборка данных по нескольким ключам")

# Функция поиска колонок
def get_col(df, kws):
    for col in df.columns:
        if any(k in str(col).lower() for k in kws): return col
    return None

# Функция нормализации для создания ключа
def create_key(row, col_art, col_name, col_model):
    parts = []
    if col_art and pd.notnull(row.get(col_art)): parts.append(str(row[col_art]).strip())
    if col_name and pd.notnull(row.get(col_name)): parts.append(str(row[col_name]).strip().lower())
    if col_model and pd.notnull(row.get(col_model)): parts.append(str(row[col_model]).strip().lower())
    return "_".join(parts) if parts else None

# --- ИНТЕРФЕЙС ---
col1, col2, col3 = st.columns(3)
files = {}

for name, col in [("Спецификация", col1), ("Инвойс", col2), ("Упаковочный", col3)]:
    with col:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls", "csv"], key=name)
        if up:
            # Читаем данные (с учетом авто-определения заголовков)
            if up.name.endswith('.csv'): df = pd.read_csv(up)
            else:
                xl = pd.ExcelFile(up)
                s_sheet = st.selectbox(f"Лист для {name}:", xl.sheet_names, key=f"s_{name}")
                df = pd.read_excel(up, sheet_name=s_sheet)
            files[name] = df

if files:
    if st.button("Объединить все данные"):
        dfs_to_merge = []
        
        for name, df in files.items():
            # Находим ключи
            c_art = get_col(df, ['код', 'part', 'артикул'])
            c_name = get_col(df, ['наимен', 'name', 'description'])
            c_mod = get_col(df, ['модель', 'model'])
            
            # Создаем уникальный ключ для сборки
            df['merge_key'] = df.apply(lambda row: create_key(row, c_art, c_name, c_mod), axis=1)
            # Убираем дубликаты ключей внутри файла
            df = df.drop_duplicates(subset=['merge_key'])
            dfs_to_merge.append(df.set_index('merge_key'))
            
        # Объединяем все файлы в один по ключу
        merged_df = pd.concat(dfs_to_merge, axis=1).reset_index()
        
        st.success("Таблица собрана!")
        st.dataframe(merged_df)
        
        # Скачивание
        csv = merged_df.to_csv(index=False).encode('utf-8')
        st.download_button("Скачать результат", csv, "merged_final.csv", "text/csv")
