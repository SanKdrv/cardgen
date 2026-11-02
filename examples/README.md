# Примеры карточек

17 товаров из разных ситуаций: полные данные, пропуски, placeholder-значения,
пустые `specs`, факты только в описании, длинный набор характеристик и
латинские единицы. Для каждого товара — JSON и Markdown в `output/`.

| № | Товар | Ситуация | Режим | Описание | Пропуски | Результат |
|---|---|---|---:|---:|---|
| 1 | Манометр показывающий DM 02 | Полный набор данных, базовый сценарий | LLM | 828 | — | [MD](output/01-manometr-pokazyvayuschiy-dm-02.md) · [JSON](output/01-manometr-pokazyvayuschiy-dm-02.json) |
| 2 | Термометр биметаллический ТБ-1 | Нет класса точности — явный missing_fields | LLM | 852 | класс точности | [MD](output/02-termometr-bimetallicheskiy-tb-1.md) · [JSON](output/02-termometr-bimetallicheskiy-tb-1.json) |
| 3 | Манометр электроконтактный ЭКМ 1У | Дополнительная характеристика: напряжение питания | LLM | 812 | — | [MD](output/03-manometr-elektrokontaktnyy-ekm-1u.md) · [JSON](output/03-manometr-elektrokontaktnyy-ekm-1u.json) |
| 4 | Манометр вакуумметр МВ-1 | Вакуумметр с отрицательным диапазоном | LLM | 845 | — | [MD](output/04-manometr-vakuummetr-mv-1.md) · [JSON](output/04-manometr-vakuummetr-mv-1.json) |
| 5 | Термометр биметаллический ТБ-2 | Полный термометр с классом точности | LLM | 906 | — | [MD](output/05-termometr-bimetallicheskiy-tb-2.md) · [JSON](output/05-termometr-bimetallicheskiy-tb-2.json) |
| 6 | Термометр манометрический ТКМ-1 | Нет длины монтажной части | LLM | 850 | длина монтажной части | [MD](output/06-termometr-manometricheskiy-tkm-1.md) · [JSON](output/06-termometr-manometricheskiy-tkm-1.json) |
| 7 | Преобразователь давления измерительный | Преобразователь с питанием и выходным сигналом | LLM | 958 | — | [MD](output/07-preobrazovatel-davleniya-izmeritelnyy.md) · [JSON](output/07-preobrazovatel-davleniya-izmeritelnyy.json) |
| 8 | Преобразователь давления компактный | Нет питания — частичный набор | LLM | 866 | питание | [MD](output/08-preobrazovatel-davleniya-kompaktnyy.md) · [JSON](output/08-preobrazovatel-davleniya-kompaktnyy.json) |
| 9 | Расходомер электромагнитный | Расходомер с DN50 и выходом 4–20 мА | LLM | 895 | — | [MD](output/09-rashodomer-elektromagnitnyy.md) · [JSON](output/09-rashodomer-elektromagnitnyy.json) |
| 10 | Уровнемер ультразвуковой | Уровнемер с питанием | LLM | 921 | — | [MD](output/10-urovnemer-ultrazvukovoy.md) · [JSON](output/10-urovnemer-ultrazvukovoy.json) |
| 11 | Калибратор давления | Калибратор с RS-485 | LLM | 858 | — | [MD](output/11-kalibrator-davleniya.md) · [JSON](output/11-kalibrator-davleniya.json) |
| 12 | Индикатор давления ИД-1 | Нет specs, только короткое описание | template (validation_failed) | 828 | диапазон измерений, класс точности, присоединение, диаметр корпуса, технические характеристики | [MD](output/12-indikator-davleniya-id-1.md) · [JSON](output/12-indikator-davleniya-id-1.json) |
| 13 | Прибор контроля давления | Нет specs и описания — крайний случай | LLM | 893 | диапазон измерений, класс точности, присоединение, диаметр корпуса, технические характеристики, назначение и область применения | [MD](output/13-pribor-kontrolya-davleniya.md) · [JSON](output/13-pribor-kontrolya-davleniya.json) |
| 14 | Манометр показывающий с placeholder-полями | Placeholder «—» и «н/д» отброшены | template (validation_failed) | 813 | диапазон измерений, класс точности | [MD](output/14-manometr-pokazyvayuschiy-s-placeholder-polyami.md) · [JSON](output/14-manometr-pokazyvayuschiy-s-placeholder-polyami.json) |
| 15 | Манометр с расширенным набором характеристик | 12 характеристик, длинный блок | LLM | 850 | — | [MD](output/15-manometr-s-rasshirennym-naborom-harakteristik.md) · [JSON](output/15-manometr-s-rasshirennym-naborom-harakteristik.json) |
| 16 | Термометр с латинскими единицами | Латинские mm и M20x1.5 | LLM | 850 | — | [MD](output/16-termometr-s-latinskimi-edinitsami.md) · [JSON](output/16-termometr-s-latinskimi-edinitsami.json) |
| 17 | Манометр с фактами только в описании | Факты в описании, specs пустые | LLM | 819 | диапазон измерений, класс точности, присоединение, диаметр корпуса, технические характеристики | [MD](output/17-manometr-s-faktami-tolko-v-opisanii.md) · [JSON](output/17-manometr-s-faktami-tolko-v-opisanii.json) |

`Режим` показывает, ответила ли модель или включился безопасный шаблон
(`template`). Даже шаблон проходит тот же guard и не добавляет факты.

Воспроизвести живой прогон:

```bash
cardgen generate --input examples/products.json --output examples/output --overwrite
```

Без ключа и сети:

```bash
CARDGEN_PROVIDER=fixture cardgen generate \
  --input examples/products.json --output artifacts
```
