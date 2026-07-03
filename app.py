import streamlit as st
import pandas as pd

st.set_page_config(page_title="Таможенный Сборщик Pro", layout="wide")
st.title("📦 Профессиональный сборщик данных")

def clean_file(file, sheet, engine):
    file.seek(0)
    # Читаем весь файл
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
        st.warning(f"В листе '{sheet}' не найдены заголовки с ключевыми словами: {keywords}")
        return None

    # 2. Обрезаем до заголовка
    df = df.iloc[header_idx:].reset_index(drop=True)
    df.columns = df.iloc[0].astype(str).str.strip().str.lower()
    df = df.iloc[1:].reset_index(drop=True)
    
    # 3. Очистка от мусора
    # Удаляем строки, где название колонки артикула пустое
    part_col = next((c for c in df.columns if any(k in c for k in ['код', 'part'])), df.columns[0])
    df = df[df[part_col].notna()]
    
    # Удаляем строки-подписи (Грузоотправитель и т.д.)
    trash = ['consignee', 'shipper', 'contract', 'addr', 'упак', 'лист', 'итого']
    for t in trash:
        df = df[~df[part_col].astype(str).str.lower().str.contains(t, na=False)]
        
    return df

# --- ИНТЕРФЕЙС ---
files_to_merge = []
cols = st.columns(3)
for i, name in enumerate(["Спецификация", "Инвойс", "Упаковочный"]):
    with cols[i]:
        up = st.file_uploader(f"Загрузить {name}", type=["xlsx", "xls"], key=name)
        if up:
            try:
                engine = 'openpyxl' if up.name.endswith('.xlsx') else 'xlrd'
                xl = pd.ExcelFile(up, engine=engine)
                s = st.selectbox(f"Лист для {name}:", xl.sheet_names, key=f"s_{name}")
                df = clean_file(up, s, engine)
                if df is not None:
                    files_to_merge.append(df)
            except Exception as e:
                st.error(f"Ошибка загрузки {name}: {e}")

if st.button("Сформировать таблицу"):
    if files_to_merge:
        try:
            # Склеиваем всё в одну таблицу
            final_df = pd.concat(files_to_merge, axis=0, ignore_index=True)
            
            # Удаляем дубликаты строк
            final_df = final_df.drop_duplicates()
            
            st.success(f"Таблица собрана! Всего строк: {len(final_df)}")
            st.dataframe(final_df)
            
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button("Скачать CSV", csv, "merged_result.csv", "text/csv")
        except Exception as e:
            st.error(f"Ошибка при сборке: {e}")
    else:
        st.warning("Данные не загружены.")
