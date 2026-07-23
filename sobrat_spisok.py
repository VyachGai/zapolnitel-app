#!/usr/bin/env python3
"""
Сборка локального снимка перечней (spisok.json).

Запускать вручную при изменении постановлений. Результат класть
в корень репозитория рядом с index.html.

    pip install requests beautifulsoup4
    python3 sobrat_spisok.py

Логика отбора повторяет checker.js: старые редакции и отменённые
позиции отбрасываются.
"""

import json
import re
import sys
from datetime import date

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Нужны зависимости: pip install requests beautifulsoup4")


POSTANOVLENIYA = [
    ("311", "https://www.alta.ru/tamdoc/22ps0311/"),
    ("312", "https://www.alta.ru/tamdoc/22ps0312/"),
    ("313", "https://www.alta.ru/tamdoc/22ps0313/"),
]

RE_ISKLUCHENA = re.compile(r"Позиция\s+исключена", re.I)
RE_PRED_RED = re.compile(r"См\.\s*пред\.\s*ред\.", re.I)
RE_NOV_RED = re.compile(r"Нов\.\s*ред\.", re.I)
RE_PRILOZHENIE = re.compile(r"Приложение\s+N\s*(\d+)", re.I)
RE_POZ_VVEDENA = re.compile(r"^\(позиция\s+введена", re.I)


def norm_kod(s):
    return re.sub(r"\D", "", str(s or ""))


def izvlech_kody(s):
    """Извлекает коды ТН ВЭД, отбрасывая годы и номера документов."""
    if not s:
        return []

    t = str(s)
    t = re.sub(r"постановлени[а-я]*\s+Правительств[а-я]*[^,;)]*", " ", t, flags=re.I)
    t = re.sub(r"от\s+\d{1,2}\s+[а-яё]+\s+\d{4}\s*г\.?", " ", t, flags=re.I)
    t = re.sub(r"\d{1,2}\.\d{1,2}\.\d{4}", " ", t)
    t = re.sub(r"\bN\s*\d+[\-/]?[а-яё\d]*", " ", t, flags=re.I)
    t = re.sub(r"\b\d{4}\s*г\.?\b", " ", t, flags=re.I)
    t = re.sub(r"(пункт|абзац|стать|раздел|част)[а-я]*\s+[^,;)]*", " ", t, flags=re.I)
    t = re.sub(r"Федерального\s+закона[^,;)]*", " ", t, flags=re.I)
    t = re.sub(r"приложени[а-я]*\s+N?\s*\d+", " ", t, flags=re.I)

    rez = []
    for chast in re.split(r"[,;\n]", t):
        for m in re.findall(r"\d[\d\s]*\d|\d", chast):
            k = norm_kod(m)
            if 4 <= len(k) <= 10:
                rez.append(k)
    return rez


def razbor_pozicii(kod_txt, naim):
    if not kod_txt:
        return None

    iskl, iskl_text = [], False
    m = re.search(r"\(\s*за\s+исключением([\s\S]*?)\)\s*$", kod_txt, re.I)
    if not m:
        m = re.search(r"\(\s*за\s+исключением([\s\S]*)$", kod_txt, re.I)

    osnovnaya = kod_txt
    if m:
        osnovnaya = kod_txt[: m.start()]
        body = m.group(1)
        if re.search(r"абзац|пункт|постановлени|товаров,\s*указанных", body, re.I):
            iskl_text = True
        iskl = izvlech_kody(body)

    kody = izvlech_kody(osnovnaya)
    if not kody:
        return None

    return {
        "kody": kody,
        "iskl": iskl,
        "isklText": iskl_text,
        "naim": re.sub(r"\s+", " ", (naim or "")).strip()[:300],
    }


def razbor_tablicy(table, pril):
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue

        kod_txt = cells[0].get_text(" ", strip=True)
        naim = cells[1].get_text(" ", strip=True) if len(cells) > 1 else ""

        if re.search(r"Код\s+ТН\s*ВЭД", kod_txt, re.I) and re.search(
            r"Наименование", naim, re.I
        ):
            continue
        if RE_ISKLUCHENA.search(naim) or RE_ISKLUCHENA.search(kod_txt):
            continue
        if RE_POZ_VVEDENA.match(kod_txt):
            continue

        poz = razbor_pozicii(kod_txt, naim)
        if poz:
            pril["pozicii"].append(poz)


def razbor_spiska(lst, pril):
    for li in lst.find_all("li"):
        txt = li.get_text(" ", strip=True)
        if not txt or RE_ISKLUCHENA.search(txt) or RE_POZ_VVEDENA.match(txt):
            continue

        m = re.match(r"^([\d\s]+(?:\([^)]*\)\s*)?(?:[\d\s]+)*)(.*)$", txt)
        if not m:
            continue
        poz = razbor_pozicii(m.group(1), m.group(2))
        if poz:
            pril["pozicii"].append(poz)


def parse_postanovlenie(html, id_post):
    soup = BeautifulSoup(html, "html.parser")
    for t in ["script", "style", "nav", "header", "footer"]:
        for el in soup.find_all(t):
            el.decompose()

    prilozheniya = []
    tek_pril = None
    v_staroy = False

    for el in soup.find_all(["p", "div", "table", "ul", "ol", "h1", "h2", "h3", "h4"]):
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue

        m = RE_PRILOZHENIE.search(txt)
        if m and len(txt) < 200:
            tek_pril = {"nomer": m.group(1), "pozicii": []}
            prilozheniya.append(tek_pril)
            v_staroy = False
            continue

        if RE_PRED_RED.search(txt) and len(txt) < 400:
            v_staroy = True
            continue
        if RE_NOV_RED.search(txt) and len(txt) < 400:
            v_staroy = False
            continue

        if tek_pril is None:
            continue

        # Маркер «См. пред. ред.» относится только к ближайшему следующему
        # блоку с позициями. Пропускаем ровно один блок и снимаем флаг,
        # иначе теряются действующие позиции, идущие сразу за старой редакцией.
        if el.name == "table":
            if v_staroy:
                v_staroy = False
                continue
            razbor_tablicy(el, tek_pril)
        elif el.name in ("ul", "ol"):
            if v_staroy:
                v_staroy = False
                continue
            razbor_spiska(el, tek_pril)

    prilozheniya = [p for p in prilozheniya if p["pozicii"]]
    return {"id": id_post, "prilozheniya": prilozheniya}


def main():
    dannye = {}
    headers = {"User-Agent": "Mozilla/5.0 (zapolnitel-app snapshot builder)"}

    for id_post, url in POSTANOVLENIYA:
        print(f"Загружаю постановление {id_post}…", flush=True)
        try:
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
        except Exception as e:
            print(f"  ошибка: {e}")
            continue

        rez = parse_postanovlenie(r.text, id_post)
        vsego = sum(len(p["pozicii"]) for p in rez["prilozheniya"])
        print(f"  приложений: {len(rez['prilozheniya'])}, позиций: {vsego}")

        for p in rez["prilozheniya"]:
            print(f"    прил. N{p['nomer']}: {len(p['pozicii'])} позиц.")

        dannye[id_post] = rez

    if not dannye:
        sys.exit("Ничего не загружено, файл не записан.")

    snimok = {
        "data": date.today().isoformat(),
        "istochnik": "alta.ru",
        "dannye": dannye,
    }

    with open("spisok.json", "w", encoding="utf-8") as f:
        json.dump(snimok, f, ensure_ascii=False, indent=1)

    print("\nЗаписан spisok.json")
    print("Проверьте выборочно несколько позиций перед коммитом.")


if __name__ == "__main__":
    main()
