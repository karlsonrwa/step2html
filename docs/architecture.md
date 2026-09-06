# Архитектура step2html

## Как есть на 0.14.0 (6 сентября 2026)

Дерево после плана дробления ([refactoring-plan.md](refactoring-plan.md),
0.9.7 → 0.11.1) и трёх раундов ускорения (0.12 → 0.14, замеры в
[performance.md](performance.md)). Разбор 0.9.6, по которому план
составлялся, оставлен ниже как история.

| Модуль | Что делает | Без OCP |
|---|---|---|
| `step2html/__init__.py` | `__version__`, `ConvertError`; OCP не импортирует, чтобы окно успело показать диалог | да |
| `_occt.py` | все имена OCP за одним guard'ом с читаемым сообщением, и проверка, что есть numpy | — |
| `meta.py` | версия, короткий коммит, дата для подписи страницы | да |
| `xcaf.py` | чтение STEP, цвета XCAF по идентичности фигуры, `collect_parts`, `colour_lookup` | нет |
| `meshing.py` | автоматический допуск, `BRepMesh` (параллельный), починка отказанных граней по одной на копии | нет |
| `gltf.py` | `RWGltf_CafWriter` пишет замешенный документ в `.glb` рядом с результатом, numpy читает примитивы | нет |
| `tessellate.py` | грань берётся из экспорта после трёх проверок (числа, первый узел, обход первого треугольника), иначе по узлам; `vertex_normals` на numpy в порядке старого цикла; `collect_edges` по координатам граней; окружности для привязки | нет |
| `payload.py` | `pack`/`unpack` формата S3DH v4 через numpy | да |
| `page.py` | `TEXT`, шаблон из `viewer/` в одну подстановку, `build_page` | да |
| `budget.py` | поиск сетки под бюджет размера, чистая функция | да |
| `progress.py` | одна полоса на все сборки | да |
| `convert.py` | `Options`, `html_target`, `one_build`, `convert` — единственная точка входа | нет |
| `cli.py`, `__main__.py` | командная строка | — |
| `worker.py` | `convert` в дочернем процессе, без `Tk()` на уровне модуля | — |
| `gui/` | `app.py` виджеты и проводка; `job.py` процесс и канал, `logpane.py` лог, `geometry.py` где окну стоять, `settings.py` что помнит, `editing.py` меню и Ctrl+C/V в любой раскладке | все, кроме `app` |
| `viewer/` | `viewer.html`, `viewer.css` и 11 файлов JS в порядке `page.JS_ORDER`: payload, mat, camera, pick, gl, overlays, measure, png, hash, layout, boot | чистые — в node |

```mermaid
flowchart LR
  step[("board.step")] --> rs["xcaf: read_step,<br/>collect_parts"]
  rs --> rp["meshing.repair_parts<br/>мешит документ на месте"]
  rp --> ex["gltf.export_mesh<br/>RWGltf → .glb → numpy"]
  ex --> ts["tessellate<br/>сверка по граням,<br/>vertex_normals, collect_edges"]
  ts --> pk["payload.pack"] --> bp["page.build_page"] --> html[("board.html")]
  bs["budget.search"] -. "до 6 сборок,<br/>от repair_parts до build_page" .-> rp
```

В браузере: разметка со счётчиком «Opening the model… %» рисуется до
скрипта → base64 циклом кусками → `DecompressionStream` чанками, CRC по
ходу → `parsePayload` → WebGL. Что и сколько стоит на большой плате — в
[performance.md](performance.md).

## Как было на 0.9.6 — разбор для плана дробления

Снято 2 сентября 2026. Два вопроса: из чего это состоит (структура) и как
через это идёт работа (функция). Третий — что здесь монолит, а что можно
унести в другой проект как есть — в конце.

### Структурная схема

Три исполняемых файла, один из которых — 2670 строк и несёт в себе
одиннадцать разных вещей.

```mermaid
flowchart LR
  subgraph core["step_to_html.py · 2670 строк"]
    direction TB
    A["A · окружение, версия, дата, TEXT<br/>41–197"]
    B["B · чтение STEP и цвета XCAF<br/>204–325"]
    C["C · допуск сетки и починка граней<br/>332–492"]
    D["D · тесселяция, рёбра, окружности<br/>499–758"]
    E["E · нагрузка S3DH v4 (pack)<br/>765–818"]
    F["F · PAGE: CSS 190 + HTML 65 + JS 1119<br/>825–2207"]
    G["G · build_page, _js<br/>2210–2289"]
    H["H · Options, html_target, Report,<br/>convert и поиск по бюджету<br/>2296–2596"]
    I["I · main, argparse<br/>2603–2670"]
  end
  gui["gui.py · 673<br/>App: раскладка, диалоги,<br/>процесс, лог, геометрия окна, конфиг"]
  worker["worker.py · 48<br/>run(opts, channel)"]
  launcher["packaging/launcher.py<br/>--selftest, диспетчер"]
  tests["tests/ · 4 набора + fixtures + run_all"]

  gui -- "Options · html_target · __version__" --> H
  gui -- "mp.Process(worker.run)" --> worker
  worker -- "convert()" --> H
  launcher -- "App, set_step, generate, pump" --> gui
  launcher -- "main()" --> I
  tests -- "read_step … build_page, 11 внутренних имён" --> core
  tests -- "App, COLOURS, CONFIG, _cannot_start" --> gui
```

Что видно по стрелкам: окно и воркер зависят только от секции H (и от
`__version__`), то есть граница между интерфейсом и конвейером уже
проведена — `Options` внутрь, `Report` наружу, `log`/`progress` как
колбэки. Зато тесты тянутся к одиннадцати внутренним именам сразу из
пяти секций: они тестируют не API, а внутренности, и при дроблении именно
они будут ломаться первыми. Это не аргумент против дробления — это
аргумент за шаг «тесты сначала» (план М5).

### Функциональная схема

Три независимых дорожки: конвейер в Python, окно с дочерним процессом,
и просмотрщик в браузере. Единственное, что связывает первую и третью, —
формат `S3DH` v4 и шаблон `PAGE`.

```mermaid
flowchart LR
  subgraph py["Конвейер · convert(Options, log, progress)"]
    direction LR
    step[("board.step")] --> rs["read_step<br/>XCAF-документ"]
    rs --> cp["collect_parts<br/>[(имя, rgb, shape, loc)]<br/>+ color_tool"]
    cp --> ad["auto_deflection<br/>диагональ / 2000"]
    ad --> loop
    subgraph loop["one_build(q) · от 1 до 6 раз"]
      direction LR
      rp["repair_parts<br/>BRepMesh + заплатки<br/>по одной грани"] --> ts["tessellate<br/>+ collect_edges<br/>+ окружности"]
      ts --> pk["pack<br/>S3DH v4 → deflate-raw<br/>→ base64, crc, len"]
      pk --> bp["build_page<br/>PAGE + TEXT + meta,<br/>один re.sub"]
    end
    loop -- "байты страницы" --> pr["predict(q)<br/>степенной закон<br/>по двум замерам"]
    pr -- "новое q" --> loop
    loop -- "лучшая, что влезла" --> wr["write_text<br/>± read-only"]
    wr --> rep["Report"]
  end
```

```mermaid
flowchart LR
  subgraph tk["Окно · gui.App"]
    direction LR
    w["виджеты"] --> o["options() → Options"]
    o --> p["mp.Process(worker.run)"]
    p -- "Queue: log / progress / done / error" --> pump["pump() каждые 80 мс"]
    pump --> lv["лог с цветом по первому слову,<br/>полоса, статус"]
    pump -- "done + галка" --> open["os.startfile"]
    p -. "умер молча, код ≠ 0" .-> pump
  end
```

```mermaid
flowchart LR
  subgraph browser["Просмотрщик · boot()"]
    direction LR
    html[("board.html")] --> b64["atob"] --> ds["DecompressionStream<br/>deflate-raw"]
    ds --> crc{"len == RAW<br/>crc32 == CRC?"}
    crc -- нет --> fail["fail(): ничего не рисуем"]
    crc -- да --> parse["DataView: pos f32, nrm u8,<br/>col u8, idx u32, epos, eidx,<br/>faceAt, cir"]
    parse --> gl["WebGL2: программа граней,<br/>программа рёбер, VAO"]
    gl --> draw["draw() по событиям:<br/>камера-матрица, LEQUAL для рёбер,<br/>подсветка грани"]
    draw --> ov["накладки: pivot, SVG измерения,<br/>тройка осей, табличка"]
    ov --> png["Save PNG: canvas 2D<br/>поверх WebGL"]
    draw --> hash["#v= в адресе, 16 чисел"]
  end
```

### Что монолит, а что переиспользуемо

Критерий монолита здесь — не размер, а **сколько разных причин меняться
собрано в одном месте** и **можно ли проверить часть, не поднимая всё**.

| Код | Строк | Причин меняться | Проверяется отдельно? | Вердикт |
|---|---|---|---|---|
| `step_to_html.py` целиком | 2670 | 11 (формат, шейдер, CSS, XCAF, мешер, поиск, CLI…) | нет — любой тест тянет OCP | **Монолит М1** |
| `PAGE`, функция `boot()` | 1119 JS | 9 (рендер, камера, ввод, выбор, измерение, привязка, PNG, раскладка, адрес) | нет — 40 замыканий на общие `let` | **Монолит М2** |
| `convert()` | 230 | 5 (валидация, прогресс, поиск, запись, лог) | нет — поиск по бюджету без STEP не запустить | **Монолит М3** |
| `gui.App` | 560 | 5 (раскладка, процесс, лог, геометрия, конфиг) | частично — только через полный прогон | **Монолит М4** |
| `tests/` | 935 | — | — | дубли `check()` ×4, `_faces`, `_area` — **М5** |
| README.md | 1444 | 2 языка × 3 жанра (руководство, журнал решений, журнал ревью) | — | **М6**: каждая правка пишется дважды |

Переиспользуемое — как есть или с одним швом:

| Кусок | Где | Что нужно, чтобы унести |
|---|---|---|
| `html_target(out, step)` | H | ничего, чистая функция |
| `build_page` / `_js` — подстановка одним проходом | G | ничего |
| Обход XCAF с цветами: `collect_parts`, `get_color`, `instance_color`, `_srgb_byte`, `label_name` | B | ничего; это готовый «прочитай STEP с цветами» для любого OCP-проекта |
| Починка: `_patch_face`, `repair_parts`, `_empty_faces`, `_meshed_ok` | C | ничего |
| `collect_edges` — рёбра из `Poly_PolygonOnTriangulation` + `note_circle` | D | принимает `parts`; шов — заменить `color_tool` на `colour_of(face)` |
| `tessellate` | D | тот же шов `colour_of(face)` |
| Формат `S3DH` + `pack` | E | нужен парный `unpack` в Python (сейчас читалка есть только в JS и inline в `test_page.py`) |
| Поиск по бюджету (степенной закон, отказ дыр) | H, внутри `convert` | вынуть в функцию `search(build, budget)` — становится чистой и тестируемой без OCP |
| `phase()` — одна полоса на сборку с весами фаз | H | то же |
| JS: `mul/rotX/rotY/orthonormalise`, `basis/VIEWS/fitDist`, `pick`, `snapAt/rimPath`, `paintSvgOnto/savePng`, `chooseLayout`, `rememberView/restoreView` | F | вынуть из `boot()`, передавать состояние явно |
| `_cannot_start`, `severity_of` + `COLOURS`, `_virtual_screen/_reachable`, цикл `generate/cancel/pump/_finish`, `_load_config/save_config` | gui | вынуть из класса |
| `worker.run` | worker | ничего |
| `fixtures.coloured_assembly` | tests | ничего; это готовая цветная STEP-фикстура для любого OCP-теста |
| `launcher.selftest`, spec с заметкой про VTK | packaging | ничего |

Целевая структура и порядок работ — в [refactoring-plan.md](refactoring-plan.md).
