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
        return spravochnik;
      }

      // Частичная или полная неудача — падаем на снимок
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
        spravochnik = snim.dannye;
        istochnik = 'локальный снимок от ' + (snim.data || 'неизвестной даты');
        istochnikSvezhiy = false;

        // Если что-то всё же скачалось — берём свежее
        if (chastichnye) {
          chastichnye.forEach(function (r) {
            if (r.prilozheniya.length > 0) spravochnik[r.id] = r;
          });
        }

        soobshchenie(
          'alta.ru недоступен. Работаю по локальному снимку от ' +
          (snim.data || 'неизвестной даты') + ' — проверьте актуальность перед подачей ДТ.'
        );
        pokazatStatusSpravochnika();
        return spravochnik;
      })
      .catch(function () {
        soobshchenie(
          'Перечни недоступны: alta.ru не отвечает через прокси, локального снимка нет. ' +
          'Проверка невозможна.',
          'error'
        );
        throw new Error('нет справочника');
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

    var sovpadeniya = [];
    var isklSovpadeniya = [];
    var nadoProverit = [];
    var estTextIskl = false;

    for (var i = 0; i < post.prilozheniya.length; i++) {
      var pril = post.prilozheniya[i];
      for (var j = 0; j < pril.pozicii.length; j++) {
        var poz = pril.pozicii[j];

        for (var k = 0; k < poz.kody.length; k++) {
          var pk = poz.kody[k];

          if (kt.indexOf(pk) === 0) {
            // Код товара попадает в позицию перечня
            sovpadeniya.push('прил. N' + pril.nomer + ': ' + krasivyKod(pk));

            // Проверяем исключения этой позиции
            for (var m = 0; m < poz.iskl.length; m++) {
              if (kt.indexOf(poz.iskl[m]) === 0) {
                isklSovpadeniya.push('прил. N' + pril.nomer + ': ' + krasivyKod(poz.iskl[m]));
              }
            }
            if (poz.isklText) estTextIskl = true;

          } else if (pk.indexOf(kt) === 0 && kt.length < pk.length) {
            // Обратная ситуация: код товара короче кода перечня.
            // Автоматика решить не может.
            nadoProverit.push('прил. N' + pril.nomer + ': ' + krasivyKod(pk));
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
        detali += ' | исключение: ' + isklSovpadeniya.join('; ');
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
    'тн вэд', 'тнвэд', 'тн-вэд', 'код тн', 'hs code', 'hs-code', 'hscode',
    'код товара', 'товарный код', 'tnved'
  ];

  function najtiKolonkuTnved(zagolovki) {
    for (var i = 0; i < zagolovki.length; i++) {
      var z = String(zagolovki[i] || '').toLowerCase().replace(/\s+/g, ' ').trim();
      for (var j = 0; j < KLYUCHI_TNVED.length; j++) {
        if (z.indexOf(KLYUCHI_TNVED[j]) !== -1) return i;
      }
    }
    return -1;
  }

  // Если заголовка нет — ищем колонку, где большинство значений похоже на код
  function ugadatKolonkuTnved(stroki) {
    if (!stroki.length) return -1;
    var kolvo = stroki[0].length;
    var luchshaya = -1, luchshiyBall = 0;

    for (var c = 0; c < kolvo; c++) {
      var podhodyat = 0, vsego = 0;
      for (var r = 0; r < stroki.length; r++) {
        var v = stroki[r][c];
        if (v === null || v === undefined || v === '') continue;
        vsego++;
        var k = normKod(v);
        if (k.length >= 6 && k.length <= 10) podhodyat++;
      }
      if (vsego === 0) continue;
      var ball = podhodyat / vsego;
      if (ball > luchshiyBall && ball > 0.6) {
        luchshiyBall = ball;
        luchshaya = c;
      }
    }
    return luchshaya;
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
    zagolovki = dannye[0].map(function (z) { return String(z).trim(); });
    var stroki = dannye.slice(1);

    var iKod = najtiKolonkuTnved(zagolovki);
    var poZagolovku = iKod !== -1;

    if (iKod === -1) {
      iKod = ugadatKolonkuTnved(stroki);
      if (iKod === -1) {
        soobshchenie(
          'Не нашёл колонку с кодом ТН ВЭД. Назовите её «Код ТН ВЭД» ' +
          'или проверьте, что коды состоят из 6–10 цифр.',
          'error'
        );
        return;
      }
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

    var soobsh = 'Проверено строк: ' + rezultat.length + '. ' +
      'Колонка с кодом ТН ВЭД: «' + (zagolovki[iKod] || ('№' + (iKod + 1))) + '»' +
      (poZagolovku ? '' : ' (определена по содержимому — проверьте)') + '.';
    soobshchenie(soobsh);

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

    pary.forEach(function (par) {
      var nomer = par[0], p = par[1];
      if (p.podpadaet === 'да') {
        if (p.iskluchenie === 'да') return;            // исключён — не подпадает
        if (p.iskluchenie === 'проверить') proverit_.push(nomer);
        else podpadaet.push(nomer);
      } else if (p.podpadaet === 'проверить') {
        proverit_.push(nomer);
      }
    });

    var chasti = [];
    if (podpadaet.length) chasti.push('подпадает под ' + podpadaet.join(', '));
    if (proverit_.length) chasti.push('проверить вручную: ' + proverit_.join(', '));
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
    return 'chk-pusto';
  }

  function klassItoga(itog) {
    if (itog.indexOf('проверить') !== -1 || itog.indexOf('не указан') !== -1) {
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

  function init() {
    var vhod = document.getElementById('chk-fajl');
    var zona = document.getElementById('chk-drop');
    var knopkaObnovit = document.getElementById('chk-obnovit');
    var knopkaSkachat = document.getElementById('chk-skachat');

    if (!vhod) return;

    function pustitVRabotu(file) {
      if (!file) return;
      soobshchenie('Читаю файл…');

      var gotovnost = spravochnik ? Promise.resolve(spravochnik) : zagruzitSpravochnik();

      gotovnost
        .then(function () { return prochitatFajl(file); })
        .then(obrabotat)
        .catch(function (err) {
          soobshchenie('Ошибка: ' + err.message, 'error');
        });
    }

    vhod.addEventListener('change', function (e) {
      pustitVRabotu(e.target.files[0]);
      e.target.value = '';
    });

    if (zona) {
      zona.addEventListener('click', function () { vhod.click(); });
      zona.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); vhod.click(); }
      });
      ['dragenter', 'dragover'].forEach(function (t) {
        zona.addEventListener(t, function (e) {
          e.preventDefault(); e.stopPropagation();
          zona.classList.add('is-over');
        });
      });
      ['dragleave', 'drop'].forEach(function (t) {
        zona.addEventListener(t, function (e) {
          e.preventDefault(); e.stopPropagation();
          zona.classList.remove('is-over');
        });
      });
      zona.addEventListener('drop', function (e) {
        var f = e.dataTransfer && e.dataTransfer.files[0];
        pustitVRabotu(f);
      });
    }

    if (knopkaObnovit) {
      knopkaObnovit.addEventListener('click', function () {
        spravochnik = null;
        knopkaObnovit.disabled = true;
        zagruzitSpravochnik()
          .catch(function () {})
          .then(function () { knopkaObnovit.disabled = false; });
      });
    }

    if (knopkaSkachat) {
      knopkaSkachat.addEventListener('click', vygruzit);
    }
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
