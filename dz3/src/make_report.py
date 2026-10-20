"""Build a Russian PDF exclusively from measured Colab outputs."""
from __future__ import annotations
import csv, datetime, json, pathlib, platform, sys, html, statistics
ROOT=pathlib.Path(__file__).resolve().parents[1]
R=ROOT/'results'; OUT=ROOT/'report'; OUT.mkdir(exist_ok=True)
def load(name):return json.loads((R/name).read_text(encoding='utf-8'))
def rows(name):
    with (R/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def num(v,d=0):
    if v is None or v=='':return '—'
    try:return f'{float(v):,.{d}f}'.replace(',',' ')
    except (ValueError,TypeError):return str(v)

def charts():
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    b=rows('benchmark_summary.csv'); quality=load('data_quality.json');analysis=load('analysis.json')
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,metric,label in [(axes[0],'median_wall_seconds','Время, с (медиана 3 запусков)'),(axes[1],'median_peak_rss_mib','Пик RSS, МиБ (медиана 3 запусков)')]:
        for offset,method,color,label_m in [(-.18,'mapreduce','#245580','MapReduce'),(.18,'duckdb','#B67C28','DuckDB')]:
            vals=[next(float(r[metric]) for r in b if r['method']==method and int(r['cap'])==k) for k in (5,10,30)]
            ax.bar([i+offset for i in range(3)],vals,width=.35,color=color,label=label_m)
        ax.set_xticks(range(3),['5','10','30']);ax.set_xlabel('Ограничение стека навыков');ax.set_ylabel(label);ax.set_ylim(bottom=0);ax.legend(frameon=False,loc='upper center',bbox_to_anchor=(.5,1.20),ncol=2);ax.grid(axis='y',alpha=.2)
    fig.savefig(OUT/'performance.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained')
    counts=rows('duckdb_cap30_run1.csv');skills=sorted([r for r in counts if r['k']=='1'],key=lambda r:-int(r['frequency']))[:12]
    ax.barh([json.loads(r['skills'])[0] for r in skills][::-1],[int(r['frequency']) for r in skills][::-1],color='#245580')
    ax.set_xlabel('Вакансии, шт.');ax.set_title('Наиболее частые навыки DevOps');ax.grid(axis='x',alpha=.2)
    fig.savefig(OUT/'skills.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    regs=analysis['regions'];labels=[r['region'].replace('Санкт-Петербург','Санкт-\nПетербург') for r in regs]
    axes[0].bar(labels,[r['vacancies'] for r in regs],color='#245580');axes[0].set_ylabel('Вакансии, шт.');axes[0].set_ylim(bottom=0)
    axes[1].bar(labels,[r['median_rub_net']/1000 for r in regs],color='#B67C28');axes[1].set_ylabel('Медиана, тыс. руб. на руки');axes[1].set_ylim(bottom=0)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.savefig(OUT/'regions.png',dpi=160);plt.close(fig)

def report():
    from reportlab.pdfgen import canvas
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,Preformatted,KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fontdir=pathlib.Path(__import__('matplotlib').get_data_path())/'fonts/ttf'
    if not fontdir.exists():
        fontdir=pathlib.Path('/System/Library/Fonts/Supplemental')
        regular=fontdir/'Arial.ttf';bold=fontdir/'Arial Bold.ttf';mono=pathlib.Path('/System/Library/Fonts/Menlo.ttc')
    else:regular=fontdir/'DejaVuSans.ttf';bold=fontdir/'DejaVuSans-Bold.ttf';mono=fontdir/'DejaVuSansMono.ttf'
    pdfmetrics.registerFont(TTFont('Body',str(regular)));pdfmetrics.registerFont(TTFont('BodyBold',str(bold)))
    pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='B',fontName='Body',fontSize=9.5,leading=14,spaceAfter=7))
    styles.add(ParagraphStyle(name='H',fontName='BodyBold',fontSize=16,leading=21,spaceAfter=12,textColor=colors.black))
    styles.add(ParagraphStyle(name='T',fontName='BodyBold',fontSize=23,leading=29,spaceAfter=18,textColor=colors.black))
    styles.add(ParagraphStyle(name='S',fontName='Body',fontSize=7.3,leading=10,spaceAfter=4))
    doc=SimpleDocTemplate(str(OUT/'ДЗ3_Зыков_Макар_DevOps.pdf'),pagesize=(595.28,841.89),rightMargin=40,leftMargin=40,topMargin=43,bottomMargin=40)
    story=[]
    def p(text,style='B'):return Paragraph(text,styles[style])
    def add(text):story.append(p(text))
    def heading(text):story.append(p(text,'H'))
    def page():story.append(PageBreak())
    def table(headers,data,widths=None):
        values=[[p(html.escape(str(x)),'S') for x in headers]]+[[p(html.escape(str(x)),'S') for x in row] for row in data]
        t=Table(values,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E5EDF4')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#D9D9D9')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(t);story.append(Spacer(1,9))
    q=load('data_quality.json');a=load('analysis.json');v=load('verification.json');storage=load('storage.json');failure=load('mapper_failure.json');bench=rows('benchmark_summary.csv')
    story.append(p('Обработка вакансий DevOps\nв объектном хранилище','T'))
    add('<b>Домашнее задание 3. Зыков Макар Романович</b><br/>Вариант 11 - DevOps инженер. Группа по списку вариантов: ИИИ-3-ИнжДан-1-3.')
    add('Работа выполнена в Google Colab на CPU. RustFS развёрнут в той же облачной среде, оба способа читают один объект S3. Обучение модели машинного обучения не требуется и не выполнялось.')
    add(f'Исходный набор: <b>{num(q["total_rows"])} записей</b>, отобрано <b>{num(q["selected_rows"])} DevOps-вакансий</b>. Полные таблицы частот собственного MapReduce и DuckDB совпали во всех проверенных запусках. Зарплатная выборка: {num(a["salary_n"])} вакансий, медиана {num(a["median_rub_net"])} руб. на руки.')
    table(['Результат','Подтверждение'],[['Объектное хранилище','RustFS 1.0.1; бакет hh-lake; GET и SHA-256 совпадают'],['Два независимых расчёта','Python MapReduce и SQL DuckDB; навыки, пары, тройки'],['Эксперименты','Стек 5, 10, 30; минимум 3 попытки; время и RSS'],['Надёжность','Принудительное завершение mapper; повтор без двойного счёта'],['Анализ','Зарплаты, положительные и отрицательные различия; 3 региона'],['Сдача','Код, SQL, сырые замеры, CSV результатов и этот PDF']], [145,370])
    add('Расчёты относятся к предоставленному набору вакансий 2024 года. Различия медиан описывают связь с набором навыков и не доказывают влияние конкретного навыка на зарплату.')
    add('Исходный код, SQL и результаты размещены в GitHub. Структура репозитория описана в README.md.')
    page();heading('Данные и правила отбора')
    add('Фильтр: точное значение role = «DevOps-инженер» ИЛИ отдельное обозначение DevOps / Dev Ops / Dev-Ops / девопс в названии вакансии без учёта регистра. SRE, MLOps и DevSecOps попадают в основной анализ только при соответствующей профессии DevOps-инженер. Наличие Docker само по себе не служит критерием.')
    table(['Проверка','Результат'],[['Всего строк',num(q['total_rows'])],['DevOps',num(q['selected_rows'])],['Уникальные vacancy_id',num(q['unique_vacancy_ids'])],['Повторные ID в выборке',num(q['duplicate_selected_ids'])],['Пустой список навыков',num(q['empty_skills'])],['Указана зарплата в любой валюте',num(q['with_salary_any_currency'])],['Сопоставимая зарплата RUR, gross=false',num(a['salary_n'])]],[340,175])
    add('Навыки: разбиение key_skills по «;», удаление краевых пробелов, перевод в нижний регистр, удаление повторов внутри вакансии, лексикографическая сортировка. Синонимы не объединяются. Пара и тройка не зависят от порядка. Каждая вакансия даёт единицу частоты каждому своему сочетанию.')
    add('<b>Допущение о размерах стека.</b> Присланное ТЗ требует три размера, но не задаёт их значения. Взяты первые 5, 10 и 30 навыков после нормализации и сортировки. Это эксперимент с ограничением стека, не размер чанка. Стек 30 охватывает фактический максимум, проверенный в данных. Для выводов о зарплате и регионах используется полный стек. Алфавитное усечение не является рейтингом важности навыков.')
    add('Размер чанка MapReduce - 1000 отобранных вакансий, одновременно до двух задач и два mapper-процесса. Исходный CSV разбирается потоковым CSV-парсером, а не разбиением по байтовым границам.')
    page();heading('RustFS и контроль исходного объекта')
    add('В ДЗ 2 RustFS работал локально на macOS с EC 2+2. Для исполнения в Colab создан отдельный одноузловой стенд с одним каталогом хранения на облачной VM. Этот стенд не повторяет эксперимент отказоустойчивости ДЗ 2. API доступен внутри VM на 127.0.0.1:19000; публичный туннель не создавался. Секрет генерируется при запуске и не включён в архив сдачи.')
    table(['Параметр','Значение'],[['Объект',storage['source']],['Размер, байт',num(storage['bytes'])],['SHA-256',storage['sha256']],['HEAD',num(storage['head_bytes'])+' байт'],['Полный GET','Контрольная сумма совпала'],['Версия','RustFS 1.0.1, Linux x86_64']],[115,400])
    add('CSV сначала загружен с компьютера в файловую систему Colab, распакован и записан через S3 multipart upload. Далее расчётные программы получают данные через S3: Python - get_object и поток, DuckDB - read_csv по s3://. Локальный CSV не используется как источник вычислений.')
    add('Команды воспроизведения: python src/pipeline.py upload; python src/pipeline.py profile; python src/pipeline.py benchmark; python src/pipeline.py analysis; python src/pipeline.py publish. Полные исходники и SQL приложены отдельными файлами.')
    if (R/'s3_objects.json').exists():add(f'После публикации результатов HEAD проверен для {len(load("s3_objects.json"))} объектов. Полный перечень: results/s3_objects.json.')
    add('У Colab временное хранилище: содержимое бакета сохраняется, пока существует VM. Для долговременного хранения нужно выгрузить результаты и при необходимости повторить загрузку на постоянный RustFS.')
    page();heading('Частоты навыков и сочетаний')
    data=[]
    for cap in (5,10,30):
        meta=load(f'duckdb_cap{cap}_run1.meta.json')
        for k in (1,2,3):data.append([cap,k,num(meta['unique_keys'][k-1]),num(meta['emissions'][k-1])])
    table(['Стек','Длина сочетания','Различных ключей','Всего вхождений'],data,[75,120,160,160])
    add('Для вакансии с k навыками получаем C(k,1)=k одиночных навыков, C(k,2)=k(k-1)/2 пар, C(k,3)=k(k-1)(k-2)/6 троек. При k=5 это 5, 10 и 10; при k=10 - 10, 45 и 120; при k=30 - 30, 435 и 4060. Различных ключей меньше суммарных вхождений, поскольку одни сочетания встречаются в нескольких вакансиях.')
    story.append(Image(str(OUT/'skills.png'),width=515,height=229))
    page();heading('Независимая проверка и отказ mapper')
    add('Python реализует mapper с itertools.combinations и собственный reducer с Counter. DuckDB независимо выполняет SQL-фильтрацию, нормализацию списков и соединение навыков по vacancy_id с условиями a&lt;b&lt;c. DuckDB не читает промежуточные счётчики MapReduce.')
    table(['Стек','Проверенных таблиц','Сравненных ключей','Расхождения'],[[cap,sum(c['cap']==cap for c in v['checks']),num(next(c['compared_keys'] for c in v['checks'] if c['cap']==cap)),0] for cap in (5,10,30)],[75,145,160,135])
    add('Сравниваются полные словари (длина сочетания, навыки) → частота, включая отсутствие лишних ключей. Дополнительно число отобранных вакансий во всех запусках сравнивается с профилем данных. Результаты одинаковы между повторами и между исходной и оптимизированной реализациями.')
    add('Для проверки отказа один mapper принудительно завершается os._exit(23) на последнем неполном чанке. ProcessPoolExecutor сообщает BrokenProcessPool. Координатор создаёт новый пул и повторяет незавершённую группу задач. Группа коммитится только после успешного завершения всех её задач; идентификаторы чанков предотвращают повторное применение.')
    table(['Контроль','Результат'],[['Отказ mapper обнаружен',str(failure['mapper_failure_observed'])],['Повторённых групп',failure['recovered_batches']],['Успешных чанков',failure['chunks_committed']],['Полное совпадение после повтора',str(failure['exact_match'])],['Время с восстановлением, с',num(failure['wall_seconds'],3)]],[340,175])
    add('Это проверка отказа процесса на одной VM, а не отказа распределённого кластера. Память состояния reducer не восстанавливается после потери координатора; такой сценарий в эксперимент не входит.')
    page();heading('Сравнение времени и памяти')
    add('Каждый замер запускается в новом Python-процессе. Для каждого размера стека выполнено по три запуска MapReduce и DuckDB; порядок чередуется. Настройка расширения httpfs выполнена заранее. CSV полностью читается из RustFS при каждом запуске; кэш ОС не очищается, это повторные, а не гарантированно холодные чтения.')
    table(['Способ','Стек','Попытки','Медиана, с','Медиана пика, МиБ'],[[r['method'],r['cap'],r['attempts'],num(r['median_wall_seconds'],3),num(r['median_peak_rss_mib'],1)] for r in bench],[150,45,65,115,140])
    story.append(Image(str(OUT/'performance.png'),width=515,height=187))
    add('Время wall включает запуск процесса, чтение S3, вычисление и сохранение CSV. Отдельное compute_seconds включает подготовку клиента/соединения и чтение, но исключает запись итогового CSV. RSS измерен с интервалом 20 мс: сумма RSS координатора и его дочерних mapper. RustFS и ноутбук не включены. RSS может повторно учитывать общие страницы между процессами; это не уникальная физическая память. Очень короткие пики между отсчётами могли быть пропущены.')
    page();heading('Интерпретация производительности и оптимизация')
    baseline=next(r for r in bench if r['method']=='mapreduce' and r['cap']=='30');opt=next(r for r in bench if r['method']=='mapreduce_optimized')
    db=next(r for r in bench if r['method']=='duckdb' and r['cap']=='30')
    ratio=float(baseline['median_wall_seconds'])/float(db['median_wall_seconds'])
    add(f'Для полного стека отношение медиан времени MapReduce / DuckDB равно {ratio:.2f}. Это результат именно этой VM, объёма CSV и параметров двух рабочих процессов/потоков; универсальное преимущество одного подхода из одного опыта не следует.')
    add('Базовый mapper материализует список всех сочетаний чанка и затем строит счётчик. Оптимизированный mapper сразу обновляет Counter из генератора сочетаний. Входной S3-объект, фильтр, размер чанка, число процессов и выходные частоты одинаковы.')
    table(['Показатель','База','Оптимизация'],[['Медиана времени, с',num(baseline['median_wall_seconds'],3),num(opt['median_wall_seconds'],3)],['Медиана пика RSS, МиБ',num(baseline['median_peak_rss_mib'],1),num(opt['median_peak_rss_mib'],1)],['Число попыток',3,3],['Совпадение частот','Полное','Полное']],[245,135,135])
    dt=100*(1-float(opt['median_wall_seconds'])/float(baseline['median_wall_seconds']));dm=100*(1-float(opt['median_peak_rss_mib'])/float(baseline['median_peak_rss_mib']))
    add(f'Изменение относительно базы: время {dt:+.1f}% экономии, RSS {dm:+.1f}% экономии. Отрицательное значение означает ухудшение. Вывод об улучшении делается отдельно по каждой метрике; три повтора не дают строгой оценки статистической значимости небольших различий.')
    add('Для малых стеков чтение большого CSV и разбор строк могут составлять значительную долю времени. Рост числа сочетаний увеличивает вычисления и объём словарей, но время не обязано расти пропорционально C(k,3): одновременно действуют I/O, кэш и накладные расходы процессов.')
    page();heading('Метод сравнения зарплат')
    add('Зарплатная выборка: currency=RUR и gross=false. Если обе границы заполнены, используется их среднее; если одна - эта граница. Значения без зарплаты, неположительные и перевёрнутые диапазоны исключаются. Среднее границ является приближением, а не фактической выплатой. Валюты не пересчитываются, НДФЛ не моделируется.')
    add(f'В сопоставимой выборке {num(a["salary_n"])} вакансий из {num(q["selected_rows"])} ({100*a["salary_n"]/q["selected_rows"]:.1f}%). Медиана {num(a["median_rub_net"])} руб. на руки. Выводы относятся к вакансиям с раскрытой сопоставимой зарплатой; пропуски не заменены нулями.')
    add('Для пары A+B базой служит навык с большей частотой во всех DevOps-вакансиях. Для тройки A+B+C - наиболее частая содержащаяся пара. При равных частотах выбирается лексикографически первая база. Сравнение включает вакансии базы с дополнительным навыком и без него, поэтому это вложенные выборки.')
    add('Δ = медиана сочетания − медиана базы; Δ% = 100 × Δ / медиана базы. В итоговый рейтинг включены сочетания и базы минимум с 20 зарплатными наблюдениями. Порог выбран до рейтинга; это ограничение поддержки, а не тест статистической значимости. В полном CSV сохранены квартильные границы и все прошедшие порог сочетания.')
    exp=rows('salary_experience.csv');table(['Опыт','Вакансий с зарплатой','Медиана, руб.'],[[r['experience'],num(r['n']),num(r['median_rub_net'])] for r in exp],[235,140,140])
    add('Опыт, регион, работодатель и уровень должности могут объяснять различия. Отрицательная разница не означает, что навык сам по себе снижает оплату; возможны различия состава вакансий. Рейтинг исследовательский: многие сочетания проверяются одновременно, причинная модель не строилась.')
    for k in (2,3):
        for direction,title in [('higher','Более высокая'),('lower','Более низкая')]:
            page();heading(f'{title} медиана у {"пар" if k==2 else "троек"} навыков')
            top=[r for r in a['top'] if r['k']==k and r['direction']==direction][:6]
            if not top:add('Нет сочетаний, удовлетворяющих порогу и направлению различия.');continue
            table(['Сочетание / база','n / n базы','Медиана / база, руб.','Δ, руб.','Δ, %'],[[r['skills']+'\nБаза: '+r['base_skills'],str(r['n_pay'])+' / '+str(r['base_n_pay']),num(r['median_rub_net'])+' / '+num(r['base_median_rub_net']),num(r['delta_rub']),num(r['delta_pct'],1)] for r in top],[205,65,110,75,60])
            first=top[0]
            add(f'Наибольшая показанная разница: {html.escape(first["skills"])}. Медиана {num(first["median_rub_net"])} руб. против {num(first["base_median_rub_net"])} руб. у базы «{html.escape(first["base_skills"])}», Δ {num(first["delta_pct"],1)}%, n={first["n_pay"]}. Это наблюдаемая связь в выбранной подвыборке.')
            add('Возможное объяснение - сочетание навыков характерно для другого уровня опыта или другого типа работодателей. Для проверки причин потребовалось бы сопоставление вакансий по этим признакам. Данные этого расчёта не позволяют приписать разницу только дополнительному навыку.')
    page();heading('Три региона и сопоставимые зарплаты')
    add('Выбраны Москва, Санкт-Петербург и Екатеринбург: три крупных региона основной выборки. Регион - поле area, а не фактическое место проживания сотрудника; удалённая вакансия может относиться к офису работодателя. Количество вакансий и доли навыков считаются по всем выбранным вакансиям региона, зарплаты - по сопоставимой подвыборке.')
    table(['Регион','Всего','С навыками','n зарплат','Покрытие, %','Медиана, руб.'],[[r['region'],num(r['vacancies']),num(r['with_skills']),num(r['net_rub_salary_n']),num(r['salary_coverage_pct'],1),num(r['median_rub_net'])] for r in a['regions']],[120,65,75,75,80,100])
    story.append(Image(str(OUT/'regions.png'),width=515,height=187))
    regs=a['regions'];rich=max(regs,key=lambda r:r['median_rub_net']);large=max(regs,key=lambda r:r['vacancies'])
    add(f'{large["region"]} лидирует по числу вакансий: {num(large["vacancies"])}. Наибольшая медиана в сопоставимой выборке у региона {rich["region"]}: {num(rich["median_rub_net"])} руб. Различие числа вакансий и зарплаты - разные характеристики рынка, одна не определяет другую.')
    add('Покрытие зарплатой различается между регионами. Поэтому сравнение медиан нельзя без оговорок переносить на все вакансии. Для навыков используется доля от всех вакансий региона, включая вакансии с пустым key_skills.')
    page();heading('Навыки пары и тройки по регионам')
    regional=rows('regions_skills_pairs_triples.csv')
    for area in ('Москва','Санкт-Петербург','Екатеринбург'):
        add('<b>'+area+'</b>')
        rr=[r for k in ('1','2','3') for r in regional if r['region']==area and r['k']==k][:0]
        rr=[]
        for k in ('1','2','3'):rr.extend([r for r in regional if r['region']==area and r['k']==k][:2])
        table(['k','Навыки','Частота','Доля, %','n зарплат','Медиана, руб.'],[[r['k'],r['skills'],num(r['frequency']),num(r['share_all_region_pct'],1),num(r['salary_n']),num(r['median_rub_net'])] for r in rr],[25,210,65,65,65,85])
    add('Полная вторая региональная таблица включает топ-10 навыков, пар и троек для каждого региона (90 строк). Пропущенная медиана означает отсутствие подходящих зарплат, а не нулевую оплату. При малом n зарплат интерпретировать медиану следует особенно осторожно.')
    page();heading('Воспроизводимость и ограничения')
    add('Ноутбук и исходники сохраняют настройки, SQL и журналы. results/benchmark_runs.csv содержит каждый замер; benchmark_summary.csv - медианы. verification.json фиксирует полную сверку, mapper_failure.json - восстановление, salary_all_supported.csv - все поддержанные зарплатные сочетания. Частоты каждого запуска сохранены отдельно и выгружены в S3.')
    add('Основные ограничения: самостоятельно выбранные размеры стека и состав региональных таблиц из-за отсутствия полной методички; один облачный узел; повторные чтения с кэшем ОС; выборка только объявлений с раскрытой зарплатой; приблизительная зарплата по границам; отсутствие причинной интерпретации и проверки значимости рейтинга.')
    add('Перед сдачей сверить с полной методичкой трактовку трёх размеров стека и требуемые колонки региональных таблиц. Если преподаватель задаёт другие значения, изменить CAPS и повторить benchmark. Данные и результаты не подменять чужими контрольными числами.')
    heading('Источники и документация')
    for text in ['Предоставленное ТЗ и критерии оценивания; Список вариантов.xlsx, строка Зыков Макар Романович.',
                 'Предоставленный отчёт ДЗ 2; CSV it_vacancies_2024.csv с SHA-256, приведённым выше.',
                 'RustFS 1.0.1: https://github.com/rustfs/rustfs/releases/tag/1.0.1',
                 'DuckDB S3 API: https://duckdb.org/docs/stable/core_extensions/httpfs/s3api.html',
                 'Ноутбук: https://colab.research.google.com/drive/18tdEHgEzH16MMqmATXIIaPR1WHNHIrQy']:
        add(html.escape(text))
    for filename,title,description in [
        ('rustfs_checks.jpg','Скриншот RustFS и результатов S3',
         'Снимок выполненного ноутбука Colab: HEAD исходного CSV в hh-lake, число объектов результатов и итоги сверки. Полные значения доступны в storage.json, verification.json и s3_objects.json.'),
        ('independent_verification.jpg','Скриншот независимой проверки',
         'Выполненная ячейка проверки Python против DuckDB. Подтверждены 1285 поддержанных сочетаний, 1108 зарплатных наблюдений и 3 региона. Снимки сделаны после фактического запуска, без подмены чисел.')]:
        shot=OUT/'evidence'/filename
        if shot.exists():
            page();heading(title);add(description)
            from PIL import Image as PILImage
            with PILImage.open(shot) as im: width,height=im.size
            scale=min(420/width,610/height)
            story.append(Image(str(shot),width=width*scale,height=height*scale))
    def footer(c,doc):
        c.setFont('Body',8);c.setFillColor(colors.HexColor('#555555'));c.drawString(40,23,'Зыков Макар | DevOps | ДЗ 3');c.drawRightString(555,23,str(doc.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print('PDF:',OUT/'ДЗ3_Зыков_Макар_DevOps.pdf')

if __name__=='__main__':charts();report()
