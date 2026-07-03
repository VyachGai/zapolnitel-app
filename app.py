import streamlit as st
import pandas as pd
import openpyxl
import io

# Настройка страницы
st.set_page_config(page_title="Таможенный Заполнитель", layout="wide")
st.title("📦 Автоматическая обработка документов")

# Функция безопасного получения списка листов
def get_sheets_safely(file):
    file.seek(0)
    # Пытаемся открыть через оба движка по очереди
    for engine in ['openpyxl', 'xlrd']:
        try:
            xl = pd.ExcelFile(file, engine=engine)
            return xl.sheet_names, engine
        except:
            continue
    return None, None

# Функция чтения данных
def read_data(file, sheet_name, engine):
    file.seek(0)
    return pd.read_excel(file, sheet_name=sheet_name, engine=engine, header=None)

# --- ИНТЕРФЕЙС ---
col1, col2, col3 = st.columns(3)
files_data = {}

for name, col in [("Спецификация", col1), ("Инвойс", col2), ("Упаковочный", col3)]:
    with col:
        uploaded = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls"])
        if uploaded:
            sheets, engine = get_sheets_safely(uploaded)
            if sheets:
                selected_sheet = st.selectbox(f"Лист для {name}:", sheets, key=f"sel_{name}")
                # Читаем данные и сохраняем в словарь
                df = read_data(uploaded, selected_sheet, engine)
                files_data[name] = df
            else:
                st.error(f"Не удалось прочитать файл {name}. Возможно, он поврежден или это не Excel.")

# Кнопка обработки
if len(files_data) == 3:
    if st.button("Сформировать данные"):
        st.success("Все файлы считаны успешно!")
        # Здесь ваша логика обработки, например:
        # df_spec = files_data["Спецификация"]
        # ...
else:
    st.info("Пожалуйста, загрузите все 3 файла и выберите листы.")
