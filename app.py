import streamlit as st
import pandas as pd

st.set_page_config(page_title="Таможенный Сборщик", layout="wide")
st.title("📦 Профессиональный сборщик данных")

# Функция чтения с объединением заголовков из нескольких строк
def read_data_pro(file, sheet, engine):
    file.seek(0)
    # Читаем первые 20 строк для анализа заголовков
    df_raw = pd.read_excel(file, sheet_name=sheet, header=None, nrows=20, engine=engine)
    
    # "Склеиваем" первые 5 строк в одну строку заголовков
    header_row = df_raw.iloc[0:5].fillna('').astype(str).agg(' '.join)
    header_row = header_row.str.lower().str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # Находим реальные данные, пропуская пустые строки
    df = pd.read_excel(file, sheet_name=sheet, header=None, engine=engine)
    df.columns = header_row
    
    # Удаляем строки, которые явно являются "мусором" из шапки
    trash_patterns = ['consignee', 'shipper', 'address', 'номер', 'packing', 'грузо']
    for pat in trash_patterns:
        df = df[~df.iloc[:, 0].astype(str).str.lower().str.contains(pat, na=False)]
    
    return df.dropna(how='all')

# Интерфейс
files = {}
cols = st.columns(3)
for i, name in enumerate(["Спецификация", "Инвойс", "Упаковочный"]):
    with cols[i]:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls"], key=name)
        if up:
            try:
                engine = 'openpyxl' if up.name.endswith('.xlsx') else 'xlrd'
                xl = pd.ExcelFile(up, engine=engine)
                s_sheet = st.selectbox(f"Лист для {name}:", xl.sheet_names, key=f"sel_{name}")
                files[name] = read_data_pro(up, s_sheet, engine)
            except Exception as e:
                st.error(f"Ошибка: {e}")

if files:
    if st.button("Сформировать таблицу"):
        try:
            # Объединяем все файлы в один
            merged = pd.concat(files.values(), axis=0, ignore_index=True)
            
            # Приводим все к нижнему регистру для удобства
            merged.columns = merged.columns.str.lower()
            
            st.success("Таблица успешно собрана!")
            st.dataframe(merged)
            
            csv = merged.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать CSV", csv, "final_clean_data.csv", "text/csv")
        except Exception as e:
            st.error(f"Ошибка при сборке таблицы: {e}")
            st.write("Список найденных колонок:", list(merged.columns) if 'merged' in locals() else "Файлы не объединены")
