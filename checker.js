/* ============================================================
   Проверка ограничений по постановлениям 311, 312, 313
   Второй раздел приложения. От app.js не зависит.
   ============================================================ */

(function () {
  'use strict';

  /* ---------- Конфигурация ---------- */

  var POSTANOVLENIYA = [
    { id: '311', url: 'https://www.alta.ru/tamdoc/22ps0311/', name: 'ПП 311' },
    { id: '312', url: 'https://www.alta.ru/tamdoc/22ps0312/', name: 'ПП 312' },
    { id: '313', url: 'https://www.alta.ru/tamdoc/22ps0313/', name: 'ПП 313' }
  ];

  // Прокси пробуются по очереди, пока какой-нибудь не ответит.
  // У alta.ru нет заголовков CORS, поэтому напрямую из браузера нельзя.
  var PROXIES = [
    function (u) { return 'https://api.allorigins.win/raw?url=' + encodeURIComponent(u); },
    function (u) { return 'https://corsproxy.io/?' + encodeURIComponent(u); },
    function (u) { return 'https://thingproxy.freeboard.io/fetch/' + u; }
  ];

  var SNAPSHOT_URL = 'spisok.json';

  var RE_ISKLUCHENA = /Позиция\s+исключена/i;
  var RE_PRED_RED   = /См\.\s*пред\.\s*ред\./i;
  var RE_NOV_RED    = /Нов\.\s*ред\./i;
  var RE_PRILOZHENIE = /Приложение\s+N\s*(\d+)/i;

  /* ---------- Состояние ---------- */

  var spravochnik = null;
  var istochnik = '';
  var istochnikSvezhiy = false;
  var zagolovki = [];
  var rezultat = [];

  /* ---------- Нормализация кодов ---------- */

  // '8501 53 810 0' -> '8501538100'
  function normKod(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/\D/g, '');
  }

  // Красивый вид: '8501538100' -> '8501 53 810 0'
  function krasivyKod(k) {
    var c = normKod(k);
    if (c.length <= 4) return c;
    var out = c.slice(0, 4);
    if (c.length > 4) out += ' ' + c.slice(4, 6);
    if (c.length > 6) out += ' ' + c.slice(6, 9);
    if (c.length > 9) out += ' ' + c.slice(9);
    return out.trim();
  }

  /* ---------- Парсер страницы постановления ---------- */

  /*
     Разметка alta.ru перемешивает действующую и старые редакции.
     Правило отбора:
       - блок после «См. пред. ред.» игнорируется до следующего
         структурного маркера;
       - позиция с текстом «Позиция исключена» отбрасывается;
       - всё остальное считается действующим.
  */

  function parsePostanovlenie(html, idPost) {
    var doc = new DOMParser().parseFromString(html, 'text/html');

    // Убираем заведомо лишнее
    ['script', 'style', 'nav', 'header', 'footer'].forEach(function (t) {
      Array.prototype.slice.call(doc.getElementsByTagName(t)).forEach(function (el) {
        el.parentNode && el.parentNode.removeChild(el);
      });
    });

    var prilozheniya = [];
    var tekPril = null;
    var vStaroyRedakcii = false;

    // Идём по всем узлам документа в порядке появления
    var vse = doc.querySelectorAll('p, div, table, ul, ol, h1, h2, h3, h4');

    for (var i = 0; i < vse.length; i++) {
      var el = vse[i];
      var txt = (el.textContent || '').trim();
      if (!txt) continue;

      // Смена приложения
      var mPril = txt.match(RE_PRILOZHENIE);
      if (mPril && txt.length < 200) {
        tekPril = { nomer: mPril[1], pozicii: [] };
        prilozheniya.push(tekPril);
        vStaroyRedakcii = false;
        continue;
      }

      // Маркеры редакций
      if (RE_PRED_RED.test(txt) && txt.length < 400) {
        vStaroyRedakcii = true;
        continue;
      }
      if (RE_NOV_RED.test(txt) && txt.length < 400) {
        vStaroyRedakcii = false;
        continue;
      }

      if (!tekPril) continue;

      /*
         Маркер «См. пред. ред.» относится только к ближайшему следующему
         блоку с позициями. Пропускаем ровно один блок и снимаем флаг:
         иначе теряются действующие позиции, идущие сразу за старой
         редакцией, и товар получает ложное «нет».
      */
      if (el.tagName === 'TABLE') {
        if (vStaroyRedakcii) { vStaroyRedakcii = false; continue; }
        razborTablicy(el, tekPril);
      } else if (el.tagName === 'UL' || el.tagName === 'OL') {
        if (vStaroyRedakcii) { vStaroyRedakcii = false; continue; }
        razborSpiska(el, tekPril);
      }
    }

    // Приложения без позиций отбрасываем
    prilozheniya = prilozheniya.filter(function (p) { return p.pozicii.length > 0; });

    return { id: idPost, prilozheniya: prilozheniya };
  }

  function razborTablicy(table, pril) {
    var rows = table.querySelectorAll('tr');
    for (var i = 0; i < rows.length; i++) {
      var cells = rows[i].querySelectorAll('td, th');
      if (cells.length < 1) continue;

      var kodTxt = (cells[0].textContent || '').trim();
      var naimTxt = cells.length > 1 ? (cells[1].textContent || '').trim() : '';

      // Заголовок таблицы
      if (/Код\s+ТН\s*ВЭД/i.test(kodTxt) && /Наименование/i.test(naimTxt)) continue;
      // Отменённая позиция
      if (RE_ISKLUCHENA.test(naimTxt) || RE_ISKLUCHENA.test(kodTxt)) continue;
      // Служебная строка
      if (/^\(позиция\s+введена/i.test(kodTxt)) continue;

      var poz = razborPozicii(kodTxt, naimTxt);
      if (poz) pril.pozicii.push(poz);
    }
  }

  function razborSpiska(list, pril) {
    var items = list.querySelectorAll('li');
    for (var i = 0; i < items.length; i++) {
      var txt = (items[i].textContent || '').trim();
      if (!txt) continue;
      if (RE_ISKLUCHENA.test(txt)) continue;
      if (/^\(позиция\s+введена/i.test(txt)) continue;

      // В списке код и наименование в одной строке.
      // Отделяем: коды и скобка исключений идут в начале.
      var m = txt.match(/^([\d\s]+(?:\([^)]*\)\s*)?(?:[\d\s]+)*)(.*)$/);
      if (!m) continue;
      var poz = razborPozicii(m[1], m[2]);
      if (poz) pril.pozicii.push(poz);
    }
  }

  /*
     Разбирает текст позиции в структуру:
       { kody: ['8501'], iskl: ['8501200009','8501522001'],
         isklText: false, naim: '...' }
  */
  function razborPozicii(kodTxt, naim) {
    if (!kodTxt) return null;

    var iskl = [];
    var isklText = false;

    // Вытаскиваем скобку «(за исключением ...)»
    var mIskl = kodTxt.match(/\(\s*за\s+исключением([\s\S]*?)\)\s*$/i);
    if (!mIskl) mIskl = kodTxt.match(/\(\s*за\s+исключением([\s\S]*)$/i);

    var osnovnaya = kodTxt;
    if (mIskl) {
      osnovnaya = kodTxt.slice(0, mIskl.index);
      var isklBody = mIskl[1];
      // Есть ли в исключениях текст без кодов
      if (/абзац|пункт|постановлени|товаров,\s*указанных/i.test(isklBody)) {
        isklText = true;
      }
      iskl = izvlechKody(isklBody);
    }

    var kody = izvlechKody(osnovnaya);
    if (kody.length === 0) return null;

    return {
      kody: kody,
      iskl: iskl,
      isklText: isklText,
      naim: (naim || '').replace(/\s+/g, ' ').trim().slice(0, 300)
    };
  }

  /*
     Извлекает коды ТН ВЭД из текста.
     '8501 53 810 0, 8412 21 200 1' -> ['8501538100','8412212001']

     Осторожно с мусором: в тексте исключений встречаются годы и номера
     документов («от 9 марта 2022 г. N 312»), которые по форме неотличимы
     от товарной группы. Отбрасываем их по контексту.
  */
  function izvlechKody(s) {
    if (!s) return [];

    var tekst = String(s);

    // Вырезаем фрагменты, где числа заведомо не коды товаров:
    // ссылки на документы, даты, номера пунктов и абзацев.
    tekst = tekst
      .replace(/постановлени[а-я]*\s+Правительств[а-я]*[^,;)]*/gi, ' ')
      .replace(/от\s+\d{1,2}\s+[а-яё]+\s+\d{4}\s*г\.?/gi, ' ')
      .replace(/\d{1,2}\.\d{1,2}\.\d{4}/g, ' ')
      .replace(/\bN\s*\d+[\-\/]?[а-яё\d]*/gi, ' ')
      .replace(/\b\d{4}\s*г\.?\b/gi, ' ')
      .replace(/(пункт|абзац|стать|раздел|част)[а-я]*\s+[^,;)]*/gi, ' ')
      .replace(/Федерального\s+закона[^,;)]*/gi, ' ')
      .replace(/приложени[а-я]*\s+N?\s*\d+/gi, ' ');

    var rez = [];
    var chasti = tekst.split(/[,;\n]/);

    for (var i = 0; i < chasti.length; i++) {
      var ch = chasti[i];
      // Группы цифр, разделённые пробелами, идущие подряд
      var m = ch.match(/\d[\d\s]*\d|\d/g);
      if (!m) continue;
      for (var j = 0; j < m.length; j++) {
        var k = normKod(m[j]);
        // Коды ТН ВЭД: 4, 6, 8, 9 или 10 знаков.
        // Нечётные длины вроде 5 или 7 знаков в перечнях не встречаются,
        // но допускаем их, чтобы не потерять данные при опечатке в разметке.
        if (k.length >= 4 && k.length <= 10) rez.push(k);
      }
    }
    return rez;
  }

  /* ---------- Парсер таблицы перечней из XLSX ---------- */

  /*
     Формат таблицы: отдельный лист на каждое постановление,
     имя листа содержит номер («Постановление 311»).
     Колонка A — код ТН ВЭД, B — наименование, D — исключения.

     Исключения в такой таблице лежат отдельным списком и не привязаны
     к конкретной строке: это общий перечень исключений постановления.
     Поэтому храним их отдельно от позиций и проверяем против всего списка.
  */

  function parseXlsxPerechen(workbook) {
    var rez = {};
    var najdeno = 0;

    workbook.SheetNames.forEach(function (imyaLista) {
      // Из имени листа достаём номер постановления
      var m = imyaLista.match(/\b(311|312|313)\b/);
      if (!m) return;
      var idPost = m[1];

      var ws = workbook.Sheets[imyaLista];
      var stroki = XLSX.utils.sheet_to_json(ws, { header: 1, raw: false, defval: '' });
      if (stroki.length < 2) return;

      var pozicii = [];
      var iskluchenia = [];

      for (var i = 1; i < stroki.length; i++) {
        var str = stroki[i];

        // Колонка A — код позиции
        var kodyStroki = razobratYachejkuKodov(str[0]);
        if (kodyStroki.length) {
          var naim = String(str[1] === undefined ? '' : str[1])
            .replace(/\s+/g, ' ').trim().slice(0, 300);
          pozicii.push({
            kody: kodyStroki,
            iskl: [],
            isklText: false,
            naim: naim
          });
        }

        // Колонка D — общий список исключений
        var kodyIskl = razobratYachejkuKodov(str[3]);
        for (var j = 0; j < kodyIskl.length; j++) {
          if (iskluchenia.indexOf(kodyIskl[j]) === -1) {
            iskluchenia.push(kodyIskl[j]);
          }
        }
      }

      if (pozicii.length) {
        rez[idPost] = {
          id: idPost,
          obshieIskluchenia: iskluchenia,
          prilozheniya: [{ nomer: '—', pozicii: pozicii }]
        };
        najdeno++;
      }
    });

    if (najdeno === 0) {
      throw new Error(
        'в файле не найдено листов с названиями «Постановление 311», ' +
        '«Постановление 312», «Постановление 313»'
      );
    }

    /* Сводные таблицы иногда дублируют один перечень в нескольких листах.
       Тогда товар получит «да» сразу по двум постановлениям, хотя в
       первоисточнике позиция есть только в одном. Молча это пропускать
       нельзя — предупреждаем. */
    rez.__dubli = najtiDubli(rez);

    // Постановления, которых не было в файле, оставляем пустыми:
    // лучше честное «нет данных», чем молчаливое «нет ограничений»
    POSTANOVLENIYA.forEach(function (p) {
      if (!rez[p.id]) {
        rez[p.id] = { id: p.id, obshieIskluchenia: [], prilozheniya: [], netDannyh: true };
      }
    });

    return rez;
  }

  /*
     Ищет пары постановлений, чьи перечни сильно пересекаются.
     Возвращает список текстовых предупреждений.
  */
  function najtiDubli(sprav) {
    var predupr = [];
    var ids = ['311', '312', '313'];

    function kodyPost(id) {
      var s = sprav[id];
      if (!s || !s.prilozheniya) return [];
      var out = [];
      s.prilozheniya.forEach(function (pr) {
        pr.pozicii.forEach(function (p) {
          p.kody.forEach(function (k) {
            if (out.indexOf(k) === -1) out.push(k);
          });
        });
      });
      return out;
    }

    for (var i = 0; i < ids.length; i++) {
      for (var j = i + 1; j < ids.length; j++) {
        var a = kodyPost(ids[i]);
        var b = kodyPost(ids[j]);
        if (a.length < 10 || b.length < 10) continue;

        var obshie = 0;
        for (var k = 0; k < a.length; k++) {
          if (b.indexOf(a[k]) !== -1) obshie++;
        }
        var dolya = obshie / Math.min(a.length, b.length);

        if (dolya > 0.5) {
          predupr.push(
            'листы «Постановление ' + ids[i] + '» и «Постановление ' + ids[j] +
            '» совпадают на ' + Math.round(dolya * 100) + '% (' + obshie + ' кодов). ' +
            'Товары будут отмечены сразу по обоим постановлениям — сверьте с первоисточником.'
          );
        }
      }
    }
    return predupr;
  }

  /*
     Разбирает содержимое одной ячейки с кодами.
     Учитывает особенности выгрузки:
       - код может быть числом (300610), а не строкой;
       - две позиции могут слипнуться через точку или запятую
         («8424200000.84249»).
  */
  function razobratYachejkuKodov(znach) {
    if (znach === null || znach === undefined) return [];
    var s = String(znach).trim();
    if (!s) return [];

    // Заголовок таблицы
    if (/код|тнвэд|тн\s*вэд|наименован|исключен/i.test(s)) return [];

    var rez = [];
    var chasti = s.split(/[.,;\s/]+/);
    for (var i = 0; i < chasti.length; i++) {
      var k = normKod(chasti[i]);
      if (k.length >= 4 && k.length <= 10) rez.push(k);
    }
    return rez;
  }

  /* ---------- Загрузка ---------- */

  function zagruzitCherezProxy(url) {
    var popytki = PROXIES.map(function (p) {
      return function () {
        return fetch(p(url), { method: 'GET' }).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.text();
        });
      };
    });

    return popytki.reduce(function (chain, f) {
      return chain.catch(f);
    }, Promise.reject());
  }

  function zagruzitSpravochnik() {
    soobshchenie('Загружаю перечни с alta.ru…');
    pokazatBlokPerechnya(false);

    var zadachi = POSTANOVLENIYA.map(function (p) {
      return zagruzitCherezProxy(p.url)
        .then(function (html) { return parsePostanovlenie(html, p.id); })
        .catch(function (e) { return { id: p.id, oshibka: String(e), prilozheniya: [] }; });
    });

    return Promise.all(zadachi).then(function (rezultaty) {
      var udachno = rezultaty.filter(function (r) { return r.prilozheniya.length > 0; });

      if (udachno.length === POSTANOVLENIYA.length) {
        spravochnik = {};
        rezultaty.forEach(function (r) { spravochnik[r.id] = r; });
        istochnik = 'alta.ru, загружено ' + new Date().toLocaleString('ru-RU');
        istochnikSvezhiy = true;
        soobshchenie('Перечни загружены с alta.ru.');
        pokazatStatusSpravochnika();
        otkrytZagruzkuTovarov(true);
        return spravochnik;
      }

      // alta.ru не отдал данные — пробуем локальный снимок
      return zagruzitSnimok(rezultaty);
    });
  }

  function zagruzitSnimok(chastichnye) {
    return fetch(SNAPSHOT_URL)
      .then(function (r) {
        if (!r.ok) throw new Error('нет файла');
        return r.json();
      })
      .then(function (snim) {
        if (!snim.dannye) throw new Error('пустой снимок');

        spravochnik = snim.dannye;
        istochnik = 'локальный снимок от ' + (snim.data || 'неизвестной даты');
        istochnikSvezhiy = false;

        // Если часть постановлений всё же скачалась — берём свежее
        if (chastichnye) {
          chastichnye.forEach(function (r) {
            if (r.prilozheniya.length > 0) spravochnik[r.id] = r;
          });
        }

        soobshchenie(
          'alta.ru недоступен, работаю по локальному снимку от ' +
          (snim.data || 'неизвестной даты') +
          '. Снимок может быть неполным — надёжнее загрузить актуальную таблицу ограничений.'
        );
        pokazatStatusSpravochnika();
        pokazatBlokPerechnya(true);
        otkrytZagruzkuTovarov(true);
        return spravochnik;
      })
      .catch(function () {
        /* Ни сайт, ни снимок недоступны.
           Просим пользователя загрузить таблицу вручную —
           это единственный честный выход: проверка по пустому
           справочнику дала бы сплошные «нет». */
        soobshchenie(
          'Не удалось загрузить перечни с alta.ru. ' +
          'Загрузите актуальную таблицу ограничений — файл XLSX ' +
          'с листами «Постановление 311», «Постановление 312», «Постановление 313».',
          'error'
        );
        pokazatBlokPerechnya(true);
        otkrytZagruzkuTovarov(false);
        throw new Error('нужна таблица ограничений');
      });
  }

  /* ---------- Загрузка перечня из файла ---------- */

  function prinyatFajlPerechnya(file) {
    if (!file) return;
    soobshchenieOPerechne('Читаю таблицу ограничений…');

    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () { reject(new Error('не удалось прочитать файл')); };
      reader.onload = function (e) {
        try {
          var wb = XLSX.read(new Uint8Array(e.target.result), { type: 'array' });
          resolve(wb);
        } catch (err) {
          reject(new Error('файл не читается как XLSX'));
        }
      };
      reader.readAsArrayBuffer(file);
    })
      .then(function (wb) {
        spravochnik = parseXlsxPerechen(wb);
        istochnik = 'таблица «' + file.name + '», загружена ' +
                    new Date().toLocaleString('ru-RU');
        istochnikSvezhiy = false;

        var vsego = 0;
        POSTANOVLENIYA.forEach(function (p) {
          var s = spravochnik[p.id];
          if (s && s.prilozheniya) {
            s.prilozheniya.forEach(function (pr) { vsego += pr.pozicii.length; });
          }
        });

        var soobsh = 'Перечни приняты: ' + vsego + ' позиций. Теперь загрузите таблицу товаров.';
        var dubli = spravochnik.__dubli || [];
        if (dubli.length) {
          soobsh += ' Внимание: ' + dubli.join(' ');
        }
        soobshchenieOPerechne(soobsh, dubli.length ? 'warn' : '');
        soobshchenie('');
        pokazatStatusSpravochnika();
        otkrytZagruzkuTovarov(true);
        return spravochnik;
      })
      .catch(function (err) {
        soobshchenieOPerechne('Ошибка: ' + err.message, 'error');
        throw err;
      });
  }

  /* ---------- Логика сопоставления ---------- */

  /*
     Возвращает для одного кода товара и одного постановления:
       { podpadaet: 'да'|'нет'|'проверить',
         iskluchenie: 'да'|'нет'|'проверить'|'',
         detali: 'приложение N1: 8501' }
  */
  function proverit(kodTovara, post) {
    var kt = normKod(kodTovara);
    if (!kt) return { podpadaet: '', iskluchenie: '', detali: 'код не указан' };
    if (!post || !post.prilozheniya) return { podpadaet: 'нет', iskluchenie: 'нет', detali: '' };
    if (post.netDannyh) {
      return { podpadaet: 'нет данных', iskluchenie: '',
               detali: 'в загруженном перечне нет листа по этому постановлению' };
    }

    var sovpadeniya = [];
    var isklSovpadeniya = [];
    var nadoProverit = [];
    var estTextIskl = false;

    for (var i = 0; i < post.prilozheniya.length; i++) {
      var pril = post.prilozheniya[i];
      var podpis = pril.nomer === '—' ? 'перечень' : 'прил. N' + pril.nomer;

      for (var j = 0; j < pril.pozicii.length; j++) {
        var poz = pril.pozicii[j];

        for (var k = 0; k < poz.kody.length; k++) {
          var pk = poz.kody[k];

          if (kt.indexOf(pk) === 0) {
            // Код товара попадает в позицию перечня
            sovpadeniya.push(podpis + ': ' + krasivyKod(pk));

            // Исключения, привязанные к самой позиции (парсинг сайта)
            for (var m = 0; m < poz.iskl.length; m++) {
              if (kt.indexOf(poz.iskl[m]) === 0) {
                isklSovpadeniya.push(podpis + ': ' + krasivyKod(poz.iskl[m]));
              }
            }
            if (poz.isklText) estTextIskl = true;

          } else if (pk.indexOf(kt) === 0 && kt.length < pk.length) {
            // Обратная ситуация: код товара короче кода перечня.
            // Автоматика решить не может.
            nadoProverit.push(podpis + ': ' + krasivyKod(pk));
          }
        }
      }
    }

    /* Общий список исключений постановления (из загруженной таблицы XLSX).
       Он не привязан к конкретной строке, поэтому проверяется целиком. */
    if (post.obshieIskluchenia && post.obshieIskluchenia.length) {
      for (var n = 0; n < post.obshieIskluchenia.length; n++) {
        var oi = post.obshieIskluchenia[n];
        if (kt.indexOf(oi) === 0) {
          var podpisIskl = 'исключение ' + krasivyKod(oi);
          if (isklSovpadeniya.indexOf(podpisIskl) === -1) {
            isklSovpadeniya.push(podpisIskl);
          }
        }
      }
    }

    var podpadaet, iskluchenie, detali;

    if (sovpadeniya.length > 0) {
      podpadaet = 'да';
      detali = sovpadeniya.slice(0, 6).join('; ');
      if (sovpadeniya.length > 6) detali += ' и ещё ' + (sovpadeniya.length - 6);

      if (isklSovpadeniya.length > 0) {
        iskluchenie = 'да';
        detali += ' | ' + isklSovpadeniya.join('; ');
      } else if (estTextIskl) {
        iskluchenie = 'проверить';
        detali += ' | в позиции есть текстовое исключение — проверить вручную';
      } else {
        iskluchenie = 'нет';
      }
    } else if (nadoProverit.length > 0) {
      podpadaet = 'проверить';
      iskluchenie = '';
      detali = 'код товара короче кода перечня — ' + nadoProverit.slice(0, 4).join('; ');
    } else {
      podpadaet = 'нет';
      iskluchenie = 'нет';
      detali = '';
    }

    return { podpadaet: podpadaet, iskluchenie: iskluchenie, detali: detali };
  }

  /* ---------- Поиск колонки с кодом ТН ВЭД ---------- */

  var KLYUCHI_TNVED = [
    'тн вэд', 'тнвэд', 'тн-вэд', 'код тн', 'тн.вэд',
    'hs code', 'hs-code', 'hscode', 'hs код', 'tnved',
    'товарный код', 'код тнвед', 'commodity code'
  ];

  /* Заголовки, которые похожи на код, но означают артикул.
     Если такой встретился, графу пропускаем: перепутать артикул
     с кодом ТН ВЭД — значит молча проверить не то. */
  var KLYUCHI_NE_TNVED = [
    'артикул', 'item code', 'код изделия', 'part number', 'парт номер',
    'номер детали', 'sku', 'код позиции'
  ];

  function najtiKolonkuTnved(zagolovki) {
    for (var i = 0; i < zagolovki.length; i++) {
      var z = String(zagolovki[i] || '').toLowerCase().replace(/\s+/g, ' ').trim();
      if (!z) continue;

      // Графа артикула не подходит, даже если рядом стоит слово «код»
      var etoArtikul = false;
      for (var n = 0; n < KLYUCHI_NE_TNVED.length; n++) {
        if (z.indexOf(KLYUCHI_NE_TNVED[n]) !== -1) { etoArtikul = true; break; }
      }
      if (etoArtikul) continue;

      for (var j = 0; j < KLYUCHI_TNVED.length; j++) {
        if (z.indexOf(KLYUCHI_TNVED[j]) !== -1) return i;
      }
    }
    return -1;
  }

  /*
     Ищет строку заголовков.

     В реальных спецификациях таблица редко начинается с первой строки:
     сверху бывает название документа, номер, дата, подпись «Список
     товаров». Берём первую строку, где встречается заголовок с кодом
     ТН ВЭД, — она и есть шапка таблицы.
  */
  function najtiStrokuZagolovkov(dannye) {
    var predel = Math.min(dannye.length, 30);

    for (var i = 0; i < predel; i++) {
      var iKod = najtiKolonkuTnved(dannye[i]);
      if (iKod === -1) continue;

      // Под шапкой должна быть хотя бы одна строка с кодом
      for (var j = i + 1; j < dannye.length; j++) {
        var k = normKod(dannye[j][iKod]);
        if (k.length >= 6) return { strokaZagolovkov: i, kolonkaKoda: iKod };
      }
    }
    return null;
  }

  /*
     Отрезает хвост после списка товаров.

     Ниже таблицы обычно идут «Итого», сводные веса, количество мест,
     подписи. Эти строки не товары, и попадание их в результат
     засоряет таблицу.

     Правило: строка считается товарной, пока в ней есть код ТН ВЭД.
     Первая строка без кода после начала товаров обрывает список,
     если дальше кодов больше нет.
  */
  var RE_ITOGO = /^\s*(итого|всего|total|подытог|subtotal|сумма)\b/i;

  function otsechHvost(stroki, iKod) {
    var poslednyaya = -1;

    for (var i = 0; i < stroki.length; i++) {
      var k = normKod(stroki[i][iKod]);
      if (k.length >= 6) poslednyaya = i;
    }

    if (poslednyaya === -1) return [];

    var tovary = stroki.slice(0, poslednyaya + 1);

    /* Внутри диапазона могли остаться строки без кода —
       промежуточные «Итого» или пустые разделители. Убираем и их. */
    return tovary.filter(function (str) {
      var k = normKod(str[iKod]);
      if (k.length >= 6) return true;

      // Строка без кода: оставляем, только если в ней есть хоть что-то
      // осмысленное и это не итоговая строка
      var tekst = str.map(function (c) { return String(c === undefined ? '' : c); })
                     .join(' ').trim();
      if (!tekst) return false;
      if (RE_ITOGO.test(tekst)) return false;
      return false;
    });
  }

  /*
     Угадывает колонку с кодом, когда заголовка нет.

     Осторожность здесь важнее полноты: рядом с кодом ТН ВЭД почти
     всегда стоит артикул, который тоже выглядит как длинное число.
     Если перепутать, проверка пойдёт по артикулам и молча выдаст
     сплошные «нет» — худший вид ошибки.

     Поэтому колонку принимаем, только если она уверенно похожа на
     ТН ВЭД и заметно обходит остальные кандидатуры.
  */
  function ugadatKolonkuTnved(stroki) {
    if (!stroki.length) return { indeks: -1, prichina: 'нет строк' };

    var kolvo = 0;
    stroki.forEach(function (r) { if (r.length > kolvo) kolvo = r.length; });

    var kandidaty = [];

    for (var c = 0; c < kolvo; c++) {
      var podhodyat = 0, vsego = 0, desyatiznachnyh = 0;

      for (var r = 0; r < stroki.length; r++) {
        var v = stroki[r][c];
        if (v === null || v === undefined || String(v).trim() === '') continue;
        vsego++;
        var s = String(v).trim();
        var k = normKod(s);

        // Код ТН ВЭД — только цифры. Артикулы часто содержат буквы
        // («300513672E»), это надёжный признак не-кода.
        if (/[^\d\s.]/.test(s)) continue;
        if (k.length >= 6 && k.length <= 10) {
          podhodyat++;
          if (k.length === 10) desyatiznachnyh++;
        }
      }

      if (vsego === 0) continue;
      var dolya = podhodyat / vsego;
      // Полные 10-значные коды — сильный признак ТН ВЭД
      var bonus = vsego ? (desyatiznachnyh / vsego) * 0.3 : 0;
      kandidaty.push({ indeks: c, ball: dolya + bonus, dolya: dolya });
    }

    kandidaty.sort(function (a, b) { return b.ball - a.ball; });

    if (!kandidaty.length || kandidaty[0].dolya < 0.6) {
      return { indeks: -1, prichina: 'ни одна колонка не похожа на коды ТН ВЭД' };
    }

    // Несколько похожих колонок — угадывать опасно
    if (kandidaty.length > 1 && (kandidaty[0].ball - kandidaty[1].ball) < 0.15) {
      return {
        indeks: -1,
        prichina: 'несколько колонок похожи на коды (например, ' +
                  'колонки №' + (kandidaty[0].indeks + 1) + ' и №' +
                  (kandidaty[1].indeks + 1) + ') — не берусь выбирать'
      };
    }

    return { indeks: kandidaty[0].indeks, prichina: '' };
  }

  /* ---------- Чтение файла товаров ---------- */

  function prochitatFajl(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () { reject(new Error('не удалось прочитать файл')); };
      reader.onload = function (e) {
        try {
          var wb = XLSX.read(new Uint8Array(e.target.result), { type: 'array' });
          var ws = wb.Sheets[wb.SheetNames[0]];
          var dannye = XLSX.utils.sheet_to_json(ws, { header: 1, raw: false, defval: '' });

          // Отбрасываем пустые строки
          dannye = dannye.filter(function (r) {
            return r.some(function (c) { return String(c).trim() !== ''; });
          });

          if (dannye.length < 2) {
            reject(new Error('в файле меньше двух строк'));
            return;
          }
          resolve(dannye);
        } catch (err) {
          reject(err);
        }
      };
      reader.readAsArrayBuffer(file);
    });
  }

  /* ---------- Обработка ---------- */

  function obrabotat(dannye) {
    var iKod, poZagolovku, iShapki;

    // Сначала ищем настоящую строку заголовков
    var najdeno = najtiStrokuZagolovkov(dannye);

    if (najdeno) {
      iShapki = najdeno.strokaZagolovkov;
      iKod = najdeno.kolonkaKoda;
      poZagolovku = true;
    } else {
      // Заголовка нет — считаем шапкой первую строку и угадываем колонку
      iShapki = 0;
      poZagolovku = false;
      var dogadka = ugadatKolonkuTnved(dannye.slice(1));
      if (dogadka.indeks === -1) {
        soobshchenie(
          'Не нашёл колонку с кодом ТН ВЭД: ' + dogadka.prichina + '. ' +
          'Назовите графу «Код ТН ВЭД» или «HS code» — тогда она определится точно.',
          'error'
        );
        return;
      }
      iKod = dogadka.indeks;
    }

    zagolovki = (dannye[iShapki] || []).map(function (z) {
      return String(z === undefined ? '' : z).trim();
    });

    var vseStroki = dannye.slice(iShapki + 1);
    var stroki = otsechHvost(vseStroki, iKod);

    if (!stroki.length) {
      soobshchenie(
        'В таблице не найдено строк с кодами ТН ВЭД. ' +
        'Проверьте, что коды состоят из 6–10 цифр.',
        'error'
      );
      return;
    }

    rezultat = stroki.map(function (str) {
      var kod = str[iKod];
      var p311 = proverit(kod, spravochnik['311']);
      var p312 = proverit(kod, spravochnik['312']);
      var p313 = proverit(kod, spravochnik['313']);

      return {
        ishodnaya: str,
        kod: kod,
        p311: p311,
        p312: p312,
        p313: p313,
        itog: sformirovatItog(p311, p312, p313)
      };
    });

    /* Сообщаем, что именно программа сочла таблицей: пользователь
       должен видеть границы разбора, а не доверять им вслепую. */
    var imyaGrafy = zagolovki[iKod] || ('графа №' + (iKod + 1));
    imyaGrafy = imyaGrafy.replace(/\s+/g, ' ').slice(0, 40);

    var chasti = ['Проверено товаров: ' + rezultat.length];
    chasti.push('код ТН ВЭД взят из графы «' + imyaGrafy + '»');
    if (iShapki > 0) {
      chasti.push('шапка таблицы найдена в строке ' + (iShapki + 1));
    }
    var otbrosheno = vseStroki.length - stroki.length;
    if (otbrosheno > 0) {
      chasti.push('строк без кода отброшено: ' + otbrosheno);
    }
    if (!poZagolovku) {
      chasti.push('графа определена по содержимому — проверьте');
    }

    soobshchenie(chasti.join('; ') + '.');
    pokazatTablicu();
  }

  /*
     Итоговая колонка. Смысл:
       подпадает = попал в перечень И не попал в исключение
  */
  function sformirovatItog(p311, p312, p313) {
    // Код не указан — проверка не проводилась. Молчаливое
    // «ограничений не найдено» здесь было бы обманом.
    if (p311.podpadaet === '' && p312.podpadaet === '' && p313.podpadaet === '') {
      return 'код ТН ВЭД не указан — проверка не проводилась';
    }

    var pary = [['311', p311], ['312', p312], ['313', p313]];
    var podpadaet = [];
    var proverit_ = [];
    var netDannyh = [];

    pary.forEach(function (par) {
      var nomer = par[0], p = par[1];
      if (p.podpadaet === 'да') {
        if (p.iskluchenie === 'да') return;            // исключён — не подпадает
        if (p.iskluchenie === 'проверить') proverit_.push(nomer);
        else podpadaet.push(nomer);
      } else if (p.podpadaet === 'проверить') {
        proverit_.push(nomer);
      } else if (p.podpadaet === 'нет данных') {
        netDannyh.push(nomer);
      }
    });

    var chasti = [];
    if (podpadaet.length) chasti.push('подпадает под ' + podpadaet.join(', '));
    if (proverit_.length) chasti.push('проверить вручную: ' + proverit_.join(', '));
    if (netDannyh.length) chasti.push('нет перечня по ' + netDannyh.join(', '));

    if (!chasti.length) return 'ограничений не найдено';
    return chasti.join('; ');
  }

  /* ---------- Отрисовка ---------- */

  var NOVYE_KOLONKI = [
    { zag: 'ПП 311',        klass: 'col-chk' },
    { zag: 'Искл. из 311',  klass: 'col-chk' },
    { zag: 'ПП 312',        klass: 'col-chk' },
    { zag: 'Искл. из 312',  klass: 'col-chk' },
    { zag: 'ПП 313',        klass: 'col-chk' },
    { zag: 'Искл. из 313',  klass: 'col-chk' },
    { zag: 'Итог проверки', klass: 'col-itog' }
  ];

  function klassYachejki(znach) {
    if (znach === 'да') return 'chk-da';
    if (znach === 'нет') return 'chk-net';
    if (znach === 'проверить') return 'chk-prov';
    if (znach === 'нет данных') return 'chk-prov';
    return 'chk-pusto';
  }

  function klassItoga(itog) {
    if (itog.indexOf('проверить') !== -1 || itog.indexOf('не указан') !== -1 ||
        itog.indexOf('нет перечня') !== -1) {
      return 'chk-prov';
    }
    if (itog.indexOf('подпадает') !== -1) return 'chk-da';
    return '';
  }

  function pokazatTablicu() {
    var host = document.getElementById('chk-tablica');
    var panel = document.getElementById('chk-result-panel');
    if (!host) return;

    var html = '<table><thead><tr>';
    zagolovki.forEach(function (z) {
      html += '<th>' + ekran(z) + '</th>';
    });
    NOVYE_KOLONKI.forEach(function (k) {
      html += '<th class="' + k.klass + '">' + ekran(k.zag) + '</th>';
    });
    html += '</tr></thead><tbody>';

    rezultat.forEach(function (r) {
      html += '<tr>';
      for (var i = 0; i < zagolovki.length; i++) {
        var v = r.ishodnaya[i] === undefined ? '' : r.ishodnaya[i];
        html += '<td class="cell-sm">' + ekran(v) + '</td>';
      }
      [r.p311, r.p312, r.p313].forEach(function (p) {
        html += '<td class="' + klassYachejki(p.podpadaet) + '"' +
                (p.detali ? ' title="' + ekran(p.detali) + '"' : '') + '>' +
                ekran(p.podpadaet || '—') + '</td>';
        html += '<td class="' + klassYachejki(p.iskluchenie) + '">' +
                ekran(p.iskluchenie || '—') + '</td>';
      });
      html += '<td class="cell-itog ' + klassItoga(r.itog) + '">' +
              ekran(r.itog) + '</td>';
      html += '</tr>';
    });

    html += '</tbody></table>';
    host.innerHTML = html;
    if (panel) panel.hidden = false;
  }

  function ekran(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ---------- Выгрузка в XLSX ---------- */

  function vygruzit() {
    if (!rezultat.length) return;

    var wb = new ExcelJS.Workbook();
    wb.creator = 'Таблица товаров для Заполнителя';
    var ws = wb.addWorksheet('Проверка 311-312-313');

    var vseZagolovki = zagolovki.concat(NOVYE_KOLONKI.map(function (k) { return k.zag; }));
    ws.addRow(vseZagolovki);

    var hdr = ws.getRow(1);
    hdr.font = { bold: true, size: 10 };
    hdr.alignment = { vertical: 'middle', horizontal: 'center', wrapText: true };
    hdr.height = 30;
    hdr.eachCell(function (cell, n) {
      cell.border = {
        top: { style: 'thin' }, left: { style: 'thin' },
        bottom: { style: 'thin' }, right: { style: 'thin' }
      };
      cell.fill = {
        type: 'pattern', pattern: 'solid',
        fgColor: { argb: n > zagolovki.length ? 'FFE6E4F6' : 'FFF2F4F1' }
      };
    });

    rezultat.forEach(function (r) {
      var stroka = [];
      for (var i = 0; i < zagolovki.length; i++) {
        stroka.push(r.ishodnaya[i] === undefined ? '' : r.ishodnaya[i]);
      }
      stroka.push(r.p311.podpadaet, r.p311.iskluchenie);
      stroka.push(r.p312.podpadaet, r.p312.iskluchenie);
      stroka.push(r.p313.podpadaet, r.p313.iskluchenie);
      stroka.push(r.itog);

      var row = ws.addRow(stroka);
      row.alignment = { vertical: 'top' };

      var baza = zagolovki.length;
      [r.p311, r.p312, r.p313].forEach(function (p, idx) {
        var cPod = row.getCell(baza + idx * 2 + 1);
        var cIsk = row.getCell(baza + idx * 2 + 2);
        zalit(cPod, p.podpadaet);
        zalit(cIsk, p.iskluchenie);
        cPod.alignment = { horizontal: 'center' };
        cIsk.alignment = { horizontal: 'center' };
        if (p.detali) {
          cPod.note = { texts: [{ text: p.detali }] };
        }
      });

      var cItog = row.getCell(baza + 7);
      cItog.alignment = { vertical: 'top', wrapText: true };
      var ki = klassItoga(r.itog);
      if (ki === 'chk-prov') {
        cItog.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFFE45C' } };
      } else if (ki === 'chk-da') {
        cItog.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFFE0E0' } };
      }
    });

    ws.columns.forEach(function (col, i) {
      col.width = i < zagolovki.length ? 20 : 13;
    });
    ws.getColumn(vseZagolovki.length).width = 38;
    ws.views = [{ state: 'frozen', ySplit: 1 }];

    /* Лист с источником данных: без него неясно,
       по какой редакции перечней сделана проверка */
    var info = wb.addWorksheet('Источник данных');
    info.addRow(['Источник перечней', istochnik]);
    info.addRow(['Дата проверки', new Date().toLocaleString('ru-RU')]);
    info.addRow([]);
    info.addRow(['ВНИМАНИЕ']);
    info.addRow(['Предварительная проверка, а не замена работе с первоисточником.']);
    info.addRow(['Перед подачей ДТ сверяйте позиции с действующей редакцией постановлений.']);
    info.addRow([]);
    info.addRow(['Проверяется только код ТН ВЭД. Исключения по происхождению товара,']);
    info.addRow(['направлению вывоза, таможенной процедуре и статусу отправителя']);
    info.addRow(['приложению неизвестны. «Нет» означает отсутствие совпадения по коду,']);
    info.addRow(['а не отсутствие ограничений.']);
    info.addRow([]);
    info.addRow(['Как читать']);
    info.addRow(['ПП = да, Искл. = нет', 'товар подпадает под ограничение']);
    info.addRow(['ПП = да, Искл. = да', 'позиция выведена из-под ограничения, товар НЕ подпадает']);
    info.addRow(['ПП = нет', 'совпадений в перечне не найдено']);
    info.addRow(['проверить', 'автоматика решить не может, нужен ручной разбор']);
    info.getColumn(1).width = 30;
    info.getColumn(2).width = 62;
    info.getRow(4).font = { bold: true };
    info.getRow(13).font = { bold: true };

    wb.xlsx.writeBuffer().then(function (buf) {
      var blob = new Blob([buf], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'proverka_311_312_313.xlsx';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    }).catch(function (e) {
      soobshchenie('Не удалось сформировать файл: ' + e.message, 'error');
    });
  }

  function zalit(cell, znach) {
    if (znach === 'да') {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFFE0E0' } };
      cell.font = { bold: true };
    } else if (znach === 'проверить') {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFFE45C' } };
      cell.font = { bold: true };
    }
  }

  /* ---------- Сообщения и статус ---------- */

  function soobshchenie(tekst, tip) {
    var el = document.getElementById('chk-soobshchenie');
    if (!el) return;
    el.textContent = tekst;
    el.className = 'status' + (tip === 'error' ? ' is-error' : '');
  }

  function soobshchenieOPerechne(tekst, tip) {
    var el = document.getElementById('chk-perechen-soobshchenie');
    if (!el) return;
    el.textContent = tekst;
    el.className = 'status' +
      (tip === 'error' ? ' is-error' : (tip === 'warn' ? ' is-warn' : ''));
  }

  // Блок ручной загрузки перечня показываем только когда он нужен
  function pokazatBlokPerechnya(nuzhen) {
    var blok = document.getElementById('chk-perechen-blok');
    if (blok) blok.hidden = !nuzhen;
  }

  // Шаг с таблицей товаров недоступен, пока нет перечней
  function otkrytZagruzkuTovarov(dostupno) {
    var shag = document.getElementById('chk-shag-tovary');
    if (!shag) return;
    shag.classList.toggle('is-locked', !dostupno);
    var zona = document.getElementById('chk-drop');
    if (zona) {
      zona.setAttribute('aria-disabled', dostupno ? 'false' : 'true');
      zona.tabIndex = dostupno ? 0 : -1;
    }
  }

  function pokazatStatusSpravochnika() {
    var el = document.getElementById('chk-status');
    if (!el || !spravochnik) return;

    var chasti = [];
    POSTANOVLENIYA.forEach(function (p) {
      var s = spravochnik[p.id];
      var kolvo = 0, pril = 0;
      if (s && s.prilozheniya) {
        pril = s.prilozheniya.length;
        s.prilozheniya.forEach(function (pr) { kolvo += pr.pozicii.length; });
      }
      chasti.push(p.name + ' — ' + kolvo + ' позиц. / ' + pril + ' прил.');
    });

    el.innerHTML = '<b>Источник:</b> ' + ekran(istochnik) + '<br>' + chasti.join(' · ');
    el.hidden = false;
    el.classList.toggle('is-stale', !istochnikSvezhiy);
  }

  /* ---------- Инициализация ---------- */

  /* Общая обвязка drop-зоны: клик, клавиатура, перетаскивание */
  function podklyuchitZonu(zona, vhod, obrabotchik) {
    if (!zona || !vhod) return;

    zona.addEventListener('click', function () {
      if (zona.getAttribute('aria-disabled') === 'true') return;
      vhod.click();
    });
    zona.addEventListener('keydown', function (e) {
      if (zona.getAttribute('aria-disabled') === 'true') return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); vhod.click(); }
    });
    ['dragenter', 'dragover'].forEach(function (t) {
      zona.addEventListener(t, function (e) {
        e.preventDefault(); e.stopPropagation();
        if (zona.getAttribute('aria-disabled') !== 'true') zona.classList.add('is-over');
      });
    });
    ['dragleave', 'drop'].forEach(function (t) {
      zona.addEventListener(t, function (e) {
        e.preventDefault(); e.stopPropagation();
        zona.classList.remove('is-over');
      });
    });
    zona.addEventListener('drop', function (e) {
      if (zona.getAttribute('aria-disabled') === 'true') return;
      var f = e.dataTransfer && e.dataTransfer.files[0];
      obrabotchik(f);
    });
    vhod.addEventListener('change', function (e) {
      obrabotchik(e.target.files[0]);
      e.target.value = '';
    });
  }

  function init() {
    var vhod = document.getElementById('chk-fajl');
    var zona = document.getElementById('chk-drop');
    var vhodPerechnya = document.getElementById('chk-perechen-fajl');
    var zonaPerechnya = document.getElementById('chk-perechen-drop');
    var knopkaObnovit = document.getElementById('chk-obnovit');
    var knopkaSkachat = document.getElementById('chk-skachat');
    var knopkaRuchnoy = document.getElementById('chk-ruchnoy-perechen');

    if (!vhod) return;

    function pustitVRabotu(file) {
      if (!file) return;

      if (!spravochnik) {
        soobshchenie(
          'Сначала нужны перечни кодов. Нажмите «Обновить перечни с alta.ru» ' +
          'или загрузите таблицу ограничений.',
          'error'
        );
        pokazatBlokPerechnya(true);
        return;
      }

      soobshchenie('Читаю файл…');
      prochitatFajl(file)
        .then(obrabotat)
        .catch(function (err) {
          soobshchenie('Ошибка: ' + err.message, 'error');
        });
    }

    podklyuchitZonu(zona, vhod, pustitVRabotu);
    podklyuchitZonu(zonaPerechnya, vhodPerechnya, function (f) {
      prinyatFajlPerechnya(f).catch(function () {});
    });

    if (knopkaObnovit) {
      knopkaObnovit.addEventListener('click', function () {
        spravochnik = null;
        knopkaObnovit.disabled = true;
        zagruzitSpravochnik()
          .catch(function () {})
          .then(function () { knopkaObnovit.disabled = false; });
      });
    }

    // Ручная загрузка перечня доступна и без сбоя сети
    if (knopkaRuchnoy) {
      knopkaRuchnoy.addEventListener('click', function () {
        pokazatBlokPerechnya(true);
        var b = document.getElementById('chk-perechen-blok');
        if (b) b.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
    }

    if (knopkaSkachat) {
      knopkaSkachat.addEventListener('click', vygruzit);
    }

    // До получения перечней шаг с товарами закрыт
    otkrytZagruzkuTovarov(false);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Точки входа для отладки и для скрипта сборки снимка
  window.ProverkaOgranicheniy = {
    parsePostanovlenie: parsePostanovlenie,
    proverit: proverit,
    normKod: normKod,
    izvlechKody: izvlechKody,
    razborPozicii: razborPozicii,
    poluchitSpravochnik: function () { return spravochnik; }
  };

})();
