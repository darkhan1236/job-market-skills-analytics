"""Rebuild Russian PDF report and PDF slides from measured pipeline results."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
import pandas as pd
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from .config import ROOT, OUTPUT, SOURCE

TEAL=colors.HexColor('#166f75')
INK=colors.HexColor('#172c3a')
GRAY=colors.HexColor('#536674')

def register_fonts():
    candidates=[(Path('C:/Windows/Fonts/arial.ttf'),Path('C:/Windows/Fonts/arialbd.ttf')),
                (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))]
    for regular,bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont('Body',str(regular)))
            pdfmetrics.registerFont(TTFont('BodyBold',str(bold)))
            pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
            return
    raise FileNotFoundError('Install Arial or DejaVu Sans with Cyrillic support to generate PDFs.')

def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def num(value,decimals=0):
    return f'{value:,.{decimals}f}'.replace(',',' ')

def contributors(metadata):
    people=metadata.get('participants',[])
    if not people:
        return ''
    names = ', '.join(p['name'] for p in people)
    group = metadata.get('group','').strip()
    return names + ('. Группа: ' + group if group else '')

def make_er_diagram():
    """Schema diagram as editable SVG and a PDF-compatible raster preview."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    fig,ax=plt.subplots(figsize=(11,4.4))
    ax.set_xlim(0,11); ax.set_ylim(0,4.4); ax.axis('off')
    boxes=[(.1,1.5,2.5,2.2,'companies','PK company_id\nname\ncountry\ncompany_size'),
           (3.1,.6,3.1,3.5,'jobs','PK job_id\nFK company_id (nullable)\ntitle, location, region\ncategory, experience\nposted_date\nannual_salary\nviews, applies'),
           (6.7,1.5,1.8,2.2,'job_skills','PK FK job_id\nPK FK skill_id'),
           (9,1.5,1.9,2.2,'skills','PK skill_id\nname\nsource')]
    for x,y,w,h,title,text in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.025',edgecolor='#166f75',facecolor='#f0f7f7'))
        ax.text(x+.12,y+h-.3,title,weight='bold',fontsize=12,color='#172c3a')
        ax.text(x+.12,y+h-.66,text,va='top',fontsize=10,linespacing=1.6)
    for x1,x2,label in [(2.6,3.1,'1 : N'),(6.2,6.7,'1 : N'),(8.5,9,'N : 1')]:
        ax.plot([x1,x2],[2.3,2.3],color='#166f75'); ax.text((x1+x2)/2,2.5,label,ha='center',fontsize=8)
    fig.tight_layout()
    for ext in ['png','svg']:
        fig.savefig(OUTPUT/'figures'/f'er_diagram.{ext}',dpi=180,bbox_inches='tight')
    plt.close(fig)

def create_report(summary,audit,metadata,metrics,storage):
    styles={
        'title':ParagraphStyle('title',fontName='BodyBold',fontSize=25,leading=31,textColor=INK,spaceAfter=16),
        'h':ParagraphStyle('h',fontName='BodyBold',fontSize=17,leading=22,textColor=INK,spaceAfter=13),
        'p':ParagraphStyle('p',fontName='Body',fontSize=10.5,leading=15,spaceAfter=9,textColor=INK),
        'small':ParagraphStyle('small',fontName='Body',fontSize=8.4,leading=11.5,spaceAfter=6,textColor=GRAY),
    }
    story=[]
    def p(text,style='p'):
        story.append(Paragraph(text,styles[style]))
    def title(text): p(text,'h')
    def page(): story.append(PageBreak())
    def chart(file,width=480,height=235):
        image=Image(str(OUTPUT/'figures'/file))
        ratio=min(width/image.imageWidth,height/image.imageHeight)
        image.drawWidth=image.imageWidth*ratio; image.drawHeight=image.imageHeight*ratio
        story.append(image); story.append(Spacer(1,7))
    def table(rows,widths=None):
        cells=[[Paragraph(escape(str(c)),styles['small']) for c in row] for row in rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7f2f3')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('TOPPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.6,TEAL),
            ('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dbe3e7'))]))
        story.append(t);story.append(Spacer(1,10))
    top=summary['top_skill_mentions'][0]
    protocol=summary['forecast']
    selected=metrics.loc[metrics['model'].eq(protocol['selected_on_validation'])].iloc[0]
    baseline=metrics.loc[metrics['model'].eq('Naive')].iloc[0]
    p('Job Market Skills Analytics','title')
    p('Анализ навыков и зарплат в вакансиях LinkedIn','h')
    p('Итоговый проект по дисциплине '+escape(metadata['course'])+'. Образовательная программа '+escape(metadata['programme'])+'.')
    p(escape(contributors(metadata)))
    title('Цель и основные результаты')
    p('Проект помогает исследовать, какие навыки упоминают работодатели, как распределяются предлагаемые зарплаты и чем отличаются группы должностей и регионы. Программа объединяет загрузку данных, проверку качества, SQLite, SQL-аналитику, графики и дашборд Streamlit.')
    p(f"Проанализировано <b>{num(summary['jobs'])}</b> уникальных вакансий. Сопоставимая зарплата доступна для <b>{num(summary['salary_coverage_pct'],1)}%</b> вакансий. Медиана этой подвыборки составляет <b>{num(summary['salary_median_usd_year'])} USD в год</b>.")
    p(f"Самое частое упоминание в используемом словаре: <b>{escape(top['name'])}</b>, {num(top['jobs'])} вакансий ({num(top['pct_all_jobs'],2)}% всего набора). Это результат словарного поиска, а не оценка всех возможных навыков.")
    p(f"На validation выбран метод <b>{escape(protocol['selected_on_validation'])}</b>. Его MAE на последующих семи тестовых днях: <b>{num(selected['test_mae'],2)}</b> вакансии в день.")
    p('Данные представляют исторические снимки и зависят от процесса сбора. Выводы описывают этот набор, не весь рынок труда и не текущие вакансии. Прогноз служит учебной проверкой методов.')
    p('Полный цикл: python main.py all. Дашборд: python -m streamlit run app.py. Установка и запуск описаны в README.md.','small')
    page();title('Данные и проверка качества')
    p('Источник: Arsh Koneru, LinkedIn Job Postings (2023–2024), Kaggle, версия 13. Лицензия CC BY-SA 4.0. Входные файлы включают postings.csv, companies.csv, job_skills.csv и skills.csv. SHA-256 архива и размеры всех исходных CSV фиксируются в data/raw/manifest.json.')
    table([['Показатель','Результат'],['Строк в postings.csv',num(audit['raw_rows'])],
           ['Уникальных очищенных вакансий',num(summary['jobs'])],['Отброшено строк с неверным или повторным ID',num(audit['dropped_invalid_or_duplicate_id'])],
           ['Размер postings.csv',f"{num(audit['postings_source_bytes']/1e6,2)} MB"],
           ['Даты первоначальной публикации',summary['date_min']+' — '+summary['date_max']],
           ['Дат с наблюдениями',summary['observed_days']],['Связей вакансия и навык',num(audit['job_skill_links'])]], [275,205])
    missing=sorted(audit['raw_missing_pct'].items(),key=lambda x:x[1],reverse=True)
    table([['Поле источника','Пропуски %']]+[[k,num(v,2)] for k,v in missing[:7]],[330,150])
    p('Пропуски зарплаты не заменяются средним. Неизвестный remote_allowed не считается офисной работой. Строки без company_id сохраняются, связь с компанией допускает NULL. Если компания отсутствует в справочнике, внешний ключ становится NULL. Повторные job_id удаляются по правилу первого появления в закреплённом архиве.')
    p('Типы признаков: ID и числовые счётчики; категориальные регион, опыт и тип занятости; временная дата; исходный текст описания. Все типы и доли пропусков сохраняются в audit.json, описательная статистика — в descriptive_statistics.csv.')
    page(); title('Архитектура и база данных')
    p('main.py управляет этапами download, build, analyze и documents. Пакет jobmarket содержит независимые модули для загрузки, очистки, извлечения навыков, SQL, прогноза и документов. app.py читает SQLite и показывает результаты с фильтрами.')
    chart('er_diagram.png',480,220)
    p('Компании связаны с вакансиями отношением один ко многим. Навыки и вакансии связаны отношением многие ко многим через job_skills. Составной первичный ключ предотвращает повтор одного навыка внутри вакансии. Префиксы platform: и dict: разделяют источники навыков.')
    p('Включены внешние ключи SQLite и проверка foreign_key_check. Индексы ускоряют запросы по дате, региону, категории, компании и навыку. Зарплата, валюта и период сохраняются как атрибуты вакансии. Тексты описаний остаются в исходном архиве, аналитическая база хранит только их длину и извлечённые признаки.')
    p('Чтение postings.csv идёт блоками по 10 000 строк. Текст каждого блока обрабатывается и освобождается; компактные признаки объединяются для Parquet. Тип category сокращает повторяющиеся строки, float32 применяется к счётчикам views и applies. Оперативная память не должна вмещать весь исходный CSV, но компактная аналитическая таблица помещается в память.')
    p(f"Измеренное время ETL на этой машине: {num(audit['elapsed_seconds'],1)} с. Это локальное измерение, его нельзя переносить на другой компьютер без проверки.")
    page();title('Навыки и группы должностей')
    chart('01_skills.png',480,240)
    chart('04_roles.png',480,200)
    p('Регулярные выражения ищут 32 словарных навыка в title, description и skills_desc. Границы слов отличают Java от JavaScript, отдельно обрабатываются C++, C# и R. Один навык учитывается один раз на вакансию. Доли используют все вакансии как знаменатель и не обязаны суммироваться до 100%.')
    p('Категории должностей задаются последовательными правилами: Data Science / AI, Data Engineering, Analytics, Software, Other. Это прозрачная эвристика. Категория Other включает вакансии вне выбранных технических групп и не означает некорректные данные. Широкие функциональные категории LinkedIn показаны отдельно в SQL-таблице 02.')
    page();title('Зарплаты и региональные различия')
    chart('02_salary_histogram.png',480,225)
    chart('03_salary_regions.png',480,225)
    p('Для сопоставления используются только USD и BASE_SALARY. Положительная med_salary имеет приоритет; иначе берётся середина диапазона при наличии двух корректных границ. Коэффициенты YEARLY 1, MONTHLY 12, WEEKLY 52, BIWEEKLY 26, HOURLY 2080. Почасовой перевод предполагает 40 часов в неделю и 52 недели в год; фактическая занятость может отличаться.')
    p(f"IQR-границы: {num(summary['salary_iqr_lower'])} и {num(summary['salary_iqr_upper'])} USD. За пределами находятся {num(summary['salary_iqr_outliers'])} зарплат. На рисунках показана подвыборка n={num(summary['salary_display_n'])}; исходные выбросы сохранены в базе и отдельном CSV. Медиана на первой странице рассчитана по всем допустимым зарплатам.")
    p('Регион определяется по двухбуквенному суффиксу location. Неоднозначные и иные форматы попадают в Other / unspecified. Геокодирование и пересчёт валют не выполняются. Различия зарплат не доказывают причинное влияние региона или навыка.')
    page();title('Временные ряды и сезонная декомпозиция')
    chart('06_time_series.png',480,215)
    chart('07_decomposition.png',480,305)
    p(f"Для временных методов выбран самый длинный сегмент последовательных дат с наблюдениями. Первая и последняя даты сегмента исключены как потенциально неполные. Получен интервал {protocol['segment_start']} — {protocol['segment_end']}, {protocol['segment_days']} дней. Правило выбора фиксировано до сравнения методов.")
    p('Пропущенные даты не заполняются нулём. resample формирует недельные и месячные сводки, rolling(7) — скользящее среднее. STL с периодом 7 описывает недельную структуру внутри сегмента. Она не доказывает годовую сезонность и не используется при прогнозировании. Разрывы сбора видны в интерактивной HTML-визуализации.','small')
    page();title('Сравнение методов прогноза')
    p(f"Начальная история: {protocol['train_days']} дней. Validation: 7 дней с {protocol['validation_start']}. Test: 7 дней с {protocol['test_start']}. На каждом шаге прогнозируется следующий день, затем в историю добавляется фактическое наблюдение. Это последовательный однодневный прогноз, а не прогноз сразу на неделю.")
    p('Baseline Naive повторяет последнее наблюдение. Moving average 7 усредняет последние 7 дней. Linear regression оценивает линейный тренд по последним 14 наблюдениям. Окна фиксированы заранее. Метод для итогового вывода выбирается по MAE validation; тест не участвует в выборе.')
    rows=[['Метод','MAE val','MAE test','Время мс','Память KiB']]
    rows += [[r['model'],num(r['validation_mae'],2),num(r['test_mae'],2),num(r['test_runtime_ms_median_5'],3),num(r['python_peak_kib'],2)] for r in metrics.to_dict('records')]
    table(rows,[160,75,75,85,85])
    chart('08_forecast.png',480,255)
    p(f"Выбор по validation: {escape(protocol['selected_on_validation'])}. Его тестовая MAE {num(selected['test_mae'],2)} означает среднюю абсолютную ошибку количества наблюдаемых вакансий за день. При таком коротком тесте нельзя заключать, что этот метод устойчиво лучше в другие периоды.")
    if selected['test_mae'] > baseline['test_mae']:
        p(f"На тесте Naive точнее выбранного по validation метода: MAE {num(baseline['test_mae'],2)} против {num(selected['test_mae'],2)}. Значит, выигрыш на validation не перенёсся на следующую неделю. Простого baseline достаточно для этого теста; надёжность прогноза на неоднородных снимках не подтверждена.")
    p('Время — медиана пяти запусков полного тестового прохода. Память — пиковые выделения Python по tracemalloc; часть нативной памяти не учитывается, это не RSS процесса. Графики и сохранение файлов не включены в измерение.','small')
    page();title('SQL и корреляционный анализ')
    chart('05_correlation.png',480,250)
    p('Используется ранговая корреляция Спирмена: зарплаты и счётчики имеют асимметричные распределения. Расчёт попарный по доступным значениям. Число наблюдений каждой пары сохранено в correlation_pair_counts.csv. Корреляция сама по себе не устанавливает причинность.')
    table([['SQL','Что возвращает'],['01–02 JOIN и GROUP BY','Рейтинги словарных навыков и функций LinkedIn'],
           ['03 GROUP BY и HAVING','Зарплаты регионов при n ≥ 100'],['04 JOIN','20 работодателей по числу вакансий'],
           ['05 GROUP BY','Наблюдаемые дневные количества'],['06 CTE и ROW_NUMBER','Три самых частых названия в каждом регионе'],
           ['07 CTE и JOIN','Число зарплат выше среднего своей категории'],['08 CTE и LAG','Месячные количества и предыдущий наблюдаемый месяц'],
           ['09 JOIN и HAVING','Зарплата при упоминании навыка, n ≥ 50'],['10 GROUP BY','Покрытие зарплат по опыту']],[175,305])
    p('Все 10 запросов загружаются в Pandas через read_sql_query и сохраняются в outputs/tables. Запросы 01, 03, 05 и 10 участвуют в основных результатах. LAG сравнивает наблюдаемые месяцы; месяцы с неполным покрытием нельзя считать полноценными рыночными периодами.','small')
    page();title('Хранение и воспроизводимость')
    p('Дополнительное сравнение использует одинаковые столбцы job_id, region и annual_salary из одной очищенной таблицы. CSV является baseline, Parquet и SQLite — альтернативами. Для всех применяется одинаковая агрегация Pandas по региону. Равенство результатов проверяется с числовым допуском 1e-8.')
    table([['Подход','Время с','Python MiB','Результат одинаков']]+[[r['approach'],num(r['seconds_median_3'],4),num(r['python_peak_mib'],2),'Да'] for r in storage.to_dict('records')],[170,100,100,110])
    chunks=audit['memory_chunks']
    before=sum(x['before_bytes'] for x in chunks); after=sum(x['after_bytes'] for x in chunks)
    p(f"Сумма памяти компактных блоков до оптимизации типов: {num(before/1024**2,2)} MiB, после: {num(after/1024**2,2)} MiB. Снижение: {num((1-after/before)*100,1)}%. Это сумма memory_usage(deep=True) по блокам, а не пиковый RSS. Текст исходных описаний в это сравнение не входит.")
    table([['Файл очищенной таблицы','Размер MB'],['CSV',num(audit['analytical_csv_bytes']/1e6,2)],['Parquet zstd',num(audit['parquet_bytes']/1e6,2)]],[330,150])
    p('Время чтения — медиана трёх запусков после прогрева; файловый кэш ОС не очищался. Python-память измеряется отдельным проходом tracemalloc. Parquet полезен для компактного обмена аналитической таблицей, SQLite — для связей и запросов дашборда. Эти измерения характеризуют выбранную операцию, а не универсальное превосходство формата.')
    p('В README приведены команды установки, загрузки версии 13, сборки и запуска. requirements.txt закрепляет проверенные версии библиотек. Тесты проверяют расчёт зарплаты, границы поиска, отсутствие утечки будущих наблюдений, разрывы календаря, внешние ключи и исполнение всех SQL-запросов.')
    page();title('Выводы и ограничения')
    p(f"Получен воспроизводимый инструмент анализа {num(summary['jobs'])} вакансий с нормализованной базой и интерактивными фильтрами. Упоминания навыков показывают профиль требований в выбранной выборке. Зарплатные оценки относятся к {num(summary['salary_n'])} объявлениям с сопоставимой оплатой и не описывают доход всех работников.")
    p('Основные ограничения: неполное и неоднородное покрытие LinkedIn; пропуски зарплат; возможная ошибка почасового пересчёта; эвристические роли и регионы; ограниченный словарь навыков; отсутствие ручной разметки качества извлечения. Слова могут встречаться в описании работодателя или желательных требованиях. Показатель спроса означает число наблюдаемых объявлений, а не число нанятых сотрудников.')
    p('Будущие улучшения: ручная разметка независимой выборки для precision/recall извлечения, геокодирование, дедупликация похожих объявлений по тексту, более длинный непрерывный временной ряд, последовательная проверка на нескольких временных блоках. Эти улучшения в текущие результаты не включены.')
    title('Источники')
    for source in [SOURCE+' (версия 13, Arsh Koneru)',
                   'https://creativecommons.org/licenses/by-sa/4.0/',
                   'https://pandas.pydata.org/docs/',
                   'https://www.sqlite.org/lang_select.html',
                   'https://www.statsmodels.org/stable/generated/statsmodels.tsa.seasonal.STL.html',
                   'https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LinearRegression.html',
                   'https://docs.streamlit.io/']:
        p(escape(source),'small')
    page();title('Участники и вклад в проект')
    for person in metadata.get('participants',[]):
        p(escape(person['name']),'h')
        p(escape(person['contribution']))
        story.append(Spacer(1,12))
    p('Совместная работа: интеграция модулей и проверка результатов.')
    def footer(canvas,doc):
        canvas.setFont('Body',8);canvas.setFillColor(GRAY)
        canvas.drawString(52,30,'Job Market Skills Analytics · исходные данные Kaggle v13')
        canvas.drawRightString(A4[0]-52,30,str(doc.page))
    doc=SimpleDocTemplate(str(ROOT/'deliverables/report_ru.pdf'),pagesize=A4,rightMargin=52,leftMargin=52,topMargin=42,bottomMargin=48,title='Job Market Skills Analytics — отчёт',author=contributors(metadata))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)

def create_slides(summary,audit,metadata,metrics,storage):
    """Landscape PDF presentation built from the analysis results."""
    width,height=960,540
    output=ROOT/'deliverables/presentation_ru.pdf'
    c=canvas.Canvas(str(output),pagesize=(width,height))
    c.setTitle('Job Market Skills Analytics — презентация')
    c.setAuthor(contributors(metadata))
    body=ParagraphStyle('slide',fontName='Body',fontSize=19,leading=27,textColor=INK)
    small=ParagraphStyle('source',fontName='Body',fontSize=10,leading=14,textColor=GRAY)
    index=0
    def text(content,x,y,w=840,style=body):
        para=Paragraph(content,style); _,h=para.wrap(w,500)
        para.drawOn(c,x,y-h)
        return y-h
    def start(title):
        nonlocal index
        index+=1
        c.setFillColor(colors.white);c.rect(0,0,width,height,fill=1,stroke=0)
        c.setFont('BodyBold',30);c.setFillColor(INK)
        c.drawString(52,480,title)
        c.setFont('Body',10);c.setFillColor(GRAY)
        c.drawString(52,22,'Job Market Skills Analytics · Kaggle v13')
        c.drawRightString(910,22,f'{index:02d}')
    def end():c.showPage()
    def chart(file,x=48,y=90,w=640,h=340):
        c.drawImage(str(OUTPUT/'figures'/file),x,y,width=w,height=h,preserveAspectRatio=True,anchor='c',mask='auto')
    def note(content):text(content,52,62,850,small)
    start('Job Market Skills Analytics')
    text('Навыки и зарплаты в вакансиях LinkedIn',52,400)
    text(f"{num(summary['jobs'])} вакансий<br/>{num(audit['postings_source_bytes']/1e6,1)} MB исходных данных<br/>SQLite, Python и интерактивный анализ",52,310)
    text(escape(contributors(metadata)),52,155,850,body)
    note(escape(metadata['course'])+' · Applied Artificial Intelligence');end()
    start('Данные и вопросы исследования')
    text('Какие навыки встречаются чаще?<br/>Как зарплаты различаются по регионам и ролям?<br/>Можно ли предсказать число объявлений на следующий день?',52,420)
    text(f"Kaggle, Arsh Koneru, версия 13<br/>Период наблюдений: {summary['date_min']} — {summary['date_max']}<br/>Сопоставимая зарплата: {num(summary['salary_coverage_pct'],1)}% вакансий",52,270)
    note(SOURCE+' · CC BY-SA 4.0. Исторические снимки не описывают весь рынок.');end()
    start('Архитектура и связи данных')
    chart('er_diagram.png',48,170,860,245)
    text('CSV читается блоками по 10 000 строк.<br/>SQLite хранит связи, Parquet — компактные признаки.<br/>Streamlit получает данные через SQL с параметрами.',52,155,850,ParagraphStyle('arch',parent=body,fontSize=17,leading=23))
    note('Исходный код: jobmarket/pipeline.py, sql/schema.sql. ER-диаграмма также сохранена в SVG.');end()
    start('Наиболее частые упоминания навыков')
    chart('01_skills.png',40,95,650,335)
    text('32 навыка в словаре.<br/><br/>Одна вакансия учитывается один раз для каждого навыка.<br/><br/>Категории LinkedIn показаны отдельно.',705,410,205,ParagraphStyle('side',parent=body,fontSize=17,leading=23))
    note('Источник: SQL 01. Упоминание слова не подтверждает обязательность требования.');end()
    start('Группы должностей')
    chart('04_roles.png',45,95,655,330)
    text('Категория определяется по названию.<br/><br/>Правила доступны в skills.py.<br/><br/>Other включает остальные профессии.',710,400,200,ParagraphStyle('side2',parent=body,fontSize=17,leading=23))
    note('Источник: очищенная таблица jobs, title-based category. Категоризация эвристическая.');end()
    start('Распределение зарплат')
    chart('02_salary_histogram.png',40,95,650,335)
    text(f"Медиана всей допустимой подвыборки<br/><b>{num(summary['salary_median_usd_year'])} USD в год</b><br/><br/>Покрытие {num(summary['salary_coverage_pct'],1)}%<br/><br/>График ограничен IQR",705,410,210,ParagraphStyle('salary',parent=body,fontSize=17,leading=24))
    note('USD BASE_SALARY. Почасовая ставка × 2080. Исходные выбросы сохранены.');end()
    start('Региональные различия зарплат')
    chart('03_salary_regions.png',70,105,820,320)
    note('10 наиболее частых регионов IQR-подвыборки. Регион — суффикс location. Выборка зарплат неполная.');end()
    start('Наблюдаемые публикации во времени')
    chart('06_time_series.png',60,105,830,320)
    note('Самый длинный непрерывный сегмент, граничные дни исключены. Пропуски сбора не считаются нулём.');end()
    start('Недельная декомпозиция STL')
    chart('07_decomposition.png',45,85,600,355)
    text('Период равен 7 дням.<br/><br/>Компоненты описывают этот сегмент.<br/><br/>STL не используется для признаков прогноза.',680,410,230,ParagraphStyle('stl',parent=body,fontSize=17,leading=24))
    note('Источник: statsmodels STL, robust=True. Вывод о годовой сезонности не делается.');end()
    start('Baseline и два метода прогноза')
    x_positions=[52,380,520,675,800]
    headers=['Метод','MAE val','MAE test','мс','KiB']
    c.setFont('BodyBold',16);c.setFillColor(TEAL)
    for x,h in zip(x_positions,headers):c.drawString(x,413,h)
    for i,row in enumerate(metrics.to_dict('records')):
        c.setFont('Body',17);c.setFillColor(INK)
        vals=[row['model'],num(row['validation_mae'],2),num(row['test_mae'],2),num(row['test_runtime_ms_median_5'],3),num(row['python_peak_kib'],2)]
        for x,v in zip(x_positions,vals):c.drawString(x,365-i*45,v)
    text('На каждом шаге прогноз на один день.<br/>Выбор по validation: <b>'+escape(summary['forecast']['selected_on_validation'])+'</b>.<br/>На последующем тесте Naive оказался точнее.',52,205)
    note('MAE — вакансии в день. Время: медиана 5 запусков. KiB: tracemalloc, не RSS. Короткий тест ограничивает выводы.');end()
    start('CSV Parquet и SQLite')
    c.setFont('BodyBold',18);c.setFillColor(TEAL)
    c.drawString(52,410,'Подход');c.drawString(480,410,'Секунды');c.drawString(700,410,'Python MiB')
    for i,row in enumerate(storage.to_dict('records')):
        c.setFont('Body',19);c.setFillColor(INK)
        for x,v in zip([52,480,700],[row['approach'],num(row['seconds_median_3'],4),num(row['python_peak_mib'],2)]):c.drawString(x,355-i*48,v)
    text('Одинаковые столбцы и агрегация Pandas.<br/>Результаты совпадают с допуском 1e-8.<br/>Форматы решают разные задачи хранения и запросов.',52,195)
    note('Медиана 3 запусков после прогрева. Кэш ОС не очищался. Память tracemalloc не включает все нативные выделения.');end()
    start('Основные результаты')
    text('Создан полный цикл анализа и база со связями.<br/>10 SQL-запросов и фильтры помогают исследовать выборку.<br/>Пропуски зарплат и сбора ограничивают обобщение.',52,420)
    text(f"Сопоставимая зарплата: {num(summary['salary_coverage_pct'],1)}% вакансий.<br/>Медиана: {num(summary['salary_median_usd_year'])} USD в год.<br/>На тестовой неделе Naive точнее скользящего среднего.",52,270)
    note('Дальнейшая работа: ручная проверка извлечения навыков и более длинный непрерывный ряд.');end()
    start('Участники и вклад в проект')
    participant_style=ParagraphStyle('participant',parent=body,fontSize=18,leading=25)
    y=420
    for person in metadata.get('participants',[]):
        y=text('<b>'+escape(person['name'])+'</b><br/>'+escape(person['contribution']),52,y,850,participant_style)-28
    note('Совместная работа: интеграция модулей и проверка результатов.');end()
    c.save()

def create_documents():
    register_fonts()
    summary=load_json(OUTPUT/'summary.json')
    audit=load_json(OUTPUT/'audit.json')
    metadata=load_json(ROOT/'project_metadata.json')
    metrics=pd.read_csv(OUTPUT/'tables/forecast_metrics.csv')
    storage=pd.read_csv(OUTPUT/'tables/storage_benchmark.csv')
    make_er_diagram()
    create_report(summary,audit,metadata,metrics,storage)
    create_slides(summary,audit,metadata,metrics,storage)
    print('Created deliverables/report_ru.pdf and presentation_ru.pdf')
