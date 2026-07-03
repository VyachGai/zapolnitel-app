import streamlit as st
import pandas as pd
import openpyxl
import io

st.set_page_config(page_title="Таможенный Заполнитель", layout="wide")

# Функция поиска нужной колонки по списку ключевых слов
def find_col(columns, keywords):
    for col in columns:
        col_str = str(col).lower()
        for kw in keywords:
            if kw in col_str:
                return col
    return None

def get_sheets(file):
    file.seek(0)
    try:
        xl = pd.ExcelFile(file, engine='openpyxl')
        return xl.sheet_names, 'openpyxl'
    except:
        file.seek(0)
        xl = pd.ExcelFile(file, engine='xlrd')
        return xl.sheet_names, 'xlrd'

# --- ИНТЕРФЕЙС ---
st.title("📦 Формирование таблицы данных")
col1, col2, col3 = st.columns(3)

files_dfs = {}
for name, col in [("Спецификация", col1), ("Инвойс", col2), ("Упаковочный", col3)]:
    with col:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls"], key=name)
        if up:
            sheets, engine = get_sheets(up)
            s_sheet = st.selectbox(f"Лист для {name}:", sheets, key=f"sel_{name}")
            up.seek(0)
            files_dfs[name] = pd.read_excel(up, sheet_name=s_sheet, engine=engine)

if len(files_dfs) == 3:
    if st.button("Сформировать таблицу"):
        try:
            df_p = files_dfs["Упаковочный"]
            
            # --- УМНЫЙ ПОИСК ЗАГОЛОВКОВ ---
            # Ищем колонки с похожими именами
            col_part = find_col(df_p.columns, ['part', 'код', 'артикул'])
            col_qty = find_col(df_p.columns, ['qty', 'кол', 'количество'])
            col_name = find_col(df_p.columns, ['name', 'наименов', 'description'])
            
            st.write("Найденные колонки:", {"Артикул": col_part, "Кол-во": col_qty, "Имя": col_name})
            
            if None in [col_part, col_qty, col_name]:
                st.error("Не удалось найти все колонки. Убедитесь, что таблица начинается сразу под заголовками.")
            else:
                # Формируем новую таблицу
                result = df_p[[col_part, col_name, col_qty]].copy()
                result.columns = ['part_no', 'name', 'qty']
                st.dataframe(result)
                
                # Кнопка скачивания
                csv = result.to_csv(index=False).encode('utf-8')
                st.download_button("Скачать CSV", csv, "result.csv", "text/csv")
                
        except Exception as e:
            st.error(f"Ошибка обработки: {e}")
            st.write("Отладочная информация: имена колонок в вашем файле:", list(files_dfs["Упаковочный"].columns))
