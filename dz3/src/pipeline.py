"""Variant 11: independent S3 MapReduce / DuckDB, reproducible CPU benchmarks."""
from __future__ import annotations
import argparse, collections, concurrent.futures, csv, hashlib, io, itertools, json
import math, os, pathlib, platform, re, statistics, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
PATTERN = r'(^|[^a-zа-яё0-9])(dev[ -]*ops|дев[ -]*опс)([^a-zа-яё0-9]|$)'
CAPS = (5, 10, 30)
EXPECTED_SHA = '303db922b541e4440906f5a7e8be32fb55e8808f950ffddb8c272f1548212a65'
REGIONS = ('Москва', 'Санкт-Петербург', 'Екатеринбург')

def dump(path, obj):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))

def config():
    return load(ROOT / 'private_config.json')

def s3_client():
    import boto3
    from botocore.config import Config
    c = config()
    return boto3.client('s3', endpoint_url=c['endpoint'], aws_access_key_id=c['access_key'],
                        aws_secret_access_key=c['secret_key'], region_name='us-east-1',
                        config=Config(signature_version='s3v4', s3={'addressing_style':'path'},
                                      retries={'max_attempts':3}))

def selected(row):
    return row.get('role', '').strip() == 'DevOps-инженер' or bool(re.search(PATTERN, row.get('name','').lower()))

def skills(value):
    # Deliberately no synonym merging; one vacancy contributes once per unordered key.
    return sorted({s.strip(' \t\r\n').lower() for s in (value or '').split(';') if s.strip(' \t\r\n')})

def csv_rows():
    c=config(); body=s3_client().get_object(Bucket=c['bucket'],Key=c['key'])['Body']
    with io.TextIOWrapper(body,encoding='utf-8-sig',newline='') as stream:
        yield from csv.DictReader(stream)

def write_csv(path, rows, fields=None):
    rows=list(rows); path=pathlib.Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fields=fields or (list(rows[0]) if rows else [])
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def upload():
    """Local file is only the upload source; both calculations subsequently use S3."""
    import gzip, shutil
    source=ROOT.parent/'it_vacancies_2024.csv'
    if not source.exists():
        with gzip.open(ROOT.parent/'it_vacancies_2024.csv.gz','rb') as f, source.open('wb') as out:
            shutil.copyfileobj(f,out)
    h=hashlib.sha256()
    with source.open('rb') as f:
        while b:=f.read(8*1024*1024):h.update(b)
    assert h.hexdigest()==EXPECTED_SHA, 'Source SHA256 differs from HW2'
    s=s3_client();c=config()
    if c['bucket'] not in [b['Name'] for b in s.list_buckets()['Buckets']]:s.create_bucket(Bucket=c['bucket'])
    s.upload_file(str(source),c['bucket'],c['key'])
    body=s.get_object(Bucket=c['bucket'],Key=c['key'])['Body']; rh=hashlib.sha256();n=0
    for b in body.iter_chunks(8*1024*1024):rh.update(b);n+=len(b)
    body.close();assert rh.hexdigest()==h.hexdigest()
    evidence={'source':'s3://'+c['bucket']+'/'+c['key'],'bytes':n,'sha256':rh.hexdigest(),
              'roundtrip_match':True,'head_bytes':s.head_object(Bucket=c['bucket'],Key=c['key'])['ContentLength']}
    dump(RESULTS/'storage.json',evidence);print(json.dumps(evidence,indent=2))

def profile_data():
    total=0; ids=collections.Counter(); roles=collections.Counter(); areas=collections.Counter()
    stack=collections.Counter();curr=collections.Counter();gross=collections.Counter();names=collections.Counter()
    empty=0;examples=[];excluded=[];sum_combos={k:0 for k in (1,2,3)}; salary_rows=0
    for r in csv_rows():
        total+=1
        if not selected(r):
            if len(excluded)<20 and any(s in r['name'].lower() for s in ('sre','системный администратор','docker')):
                excluded.append({k:r[k] for k in ('vacancy_id','name','role')})
            continue
        ids[r['vacancy_id']]+=1;roles[r['role']]+=1;areas[r['area']]+=1;names[r['name']]+=1
        sk=skills(r['key_skills']);stack[len(sk)]+=1;curr[r['currency']]+=1;gross[r['gross']]+=1
        salary_rows+=bool(r['salary_from'] or r['salary_to']);empty+=not sk
        for k in (1,2,3):sum_combos[k]+=math.comb(len(sk),k)
        if len(examples)<25:examples.append({k:r[k] for k in ('vacancy_id','name','role','area')})
    duplicates=sum(x-1 for x in ids.values());assert duplicates==0,'Define duplicate policy before running'
    out={'total_rows':total,'selected_rows':sum(ids.values()),'unique_vacancy_ids':len(ids),'duplicate_selected_ids':duplicates,
         'empty_skills':empty,'with_salary_any_currency':salary_rows,'roles':dict(roles),'areas':dict(areas.most_common()),
         'currency':dict(curr),'gross':dict(gross),'stack_distribution':dict(sorted(stack.items())),
         'expected_emissions_all_skills':sum_combos,'filter':PATTERN,'role_or_name':True,
         'stack_caps':CAPS,'regions':REGIONS,'names_top':names.most_common(30)}
    dump(RESULTS/'data_quality.json',out);write_csv(RESULTS/'filter_included.csv',examples)
    write_csv(RESULTS/'filter_excluded_examples.csv',excluded)
    print(json.dumps(out,ensure_ascii=False,indent=2))

def map_chunk(task):
    chunk_id, rows, cap, optimize, fail_once = task
    if fail_once:
        # A real mapper process exits; coordinator replaces the broken pool and resubmits pending tasks.
        os._exit(23)
    if optimize:
        counters=[collections.Counter() for _ in range(3)]
        for sk in rows:
            sk=sk[:cap]
            for k in (1,2,3):counters[k-1].update(itertools.combinations(sk,k))
        return chunk_id,counters
    mapped=[[] for _ in range(3)]
    for sk in rows:
        sk=sk[:cap]
        for k in (1,2,3):mapped[k-1].extend(itertools.combinations(sk,k))
    return chunk_id,[collections.Counter(x) for x in mapped]

def mapreduce(cap, chunk_size=1000, workers=2, optimize=False, inject_failure=False):
    counters=[collections.Counter() for _ in range(3)]; seen=set(); attempts=0;failed=False
    pool=concurrent.futures.ProcessPoolExecutor(max_workers=workers)
    pending=[]; current=[];chunk_id=0;vacancies=0
    def consume(batch):
        nonlocal pool,attempts,failed
        try: results=[f.result() for _,f in batch]
        except concurrent.futures.process.BrokenProcessPool:
            failed=True; attempts+=1;pool.shutdown(wait=True,cancel_futures=True)
            pool=concurrent.futures.ProcessPoolExecutor(max_workers=workers)
            # None of this batch is committed until ALL futures succeeded.
            results=[pool.submit(map_chunk,task[:-1]+(False,)).result() for task,_ in batch]
        for cid,partial in results:
            if cid in seen:continue
            for target,source in zip(counters,partial):target.update(source)
            seen.add(cid)
    try:
        for r in csv_rows():
            if not selected(r):continue
            vacancies+=1;current.append(skills(r['key_skills']))
            if len(current)>=chunk_size:
                task=(chunk_id,current,cap,optimize,False)
                pending.append((task,pool.submit(map_chunk,task)));current=[];chunk_id+=1
                if len(pending)>=workers:consume(pending);pending=[]
        if current:
            task=(chunk_id,current,cap,optimize,inject_failure);pending.append((task,pool.submit(map_chunk,task)))
        if pending:consume(pending)
    finally:pool.shutdown(wait=True,cancel_futures=True)
    return counters,{'vacancies':vacancies,'chunks_committed':len(seen),'mapper_failure_observed':failed,
                     'recovered_batches':attempts,'workers':workers,'chunk_rows':chunk_size}

def save_counts(path, counters):
    write_csv(path,({'k':k,'skills':json.dumps(key,ensure_ascii=False),'frequency':freq}
                   for k,c in enumerate(counters,1) for key,freq in sorted(c.items())),['k','skills','frequency'])

def read_counts(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        return {(int(r['k']),tuple(json.loads(r['skills']))):int(r['frequency']) for r in csv.DictReader(f)}

def sql_connection():
    import duckdb
    c=config();conn=duckdb.connect();conn.execute('SET threads=2')
    extension_dir=ROOT/'.duckdb_extensions';extension_dir.mkdir(exist_ok=True)
    conn.execute("SET extension_directory = '"+str(extension_dir).replace("'","''")+"'")
    conn.execute('INSTALL httpfs');conn.execute('LOAD httpfs')
    q=lambda s:"'"+s.replace("'","''")+"'"
    conn.execute(f"CREATE SECRET lab (TYPE s3, KEY_ID {q(c['access_key'])}, SECRET {q(c['secret_key'])}, REGION 'us-east-1', ENDPOINT {q(c['endpoint'].split('://')[1])}, URL_STYLE 'path', USE_SSL false)")
    return conn

def base_sql():
    c=config();uri='s3://'+c['bucket']+'/'+c['key']
    return f"""CREATE TABLE vacancies AS
    SELECT *, list_sort(list_distinct(list_filter(
        list_transform(string_split(coalesce(key_skills,''), ';'), s -> lower(trim(s, ' \t\r\n'))),
        s -> s <> ''))) AS skills
    FROM read_csv('{uri}', header=true, all_varchar=true, delim=',', quote='"', escape='"',
                  nullstr='', max_line_size=16777216)
    WHERE trim(coalesce(role,'')) = 'DevOps-инженер'
       OR regexp_matches(lower(coalesce(name,'')), '{PATTERN}');"""

def count_sql(cap):
    return f"""WITH limited AS (SELECT vacancy_id, list_slice(skills,1,{cap}) AS sk FROM vacancies),
    singles AS (SELECT vacancy_id, unnest(sk) AS a FROM limited),
    pairs AS (SELECT x.vacancy_id,x.a,y.a AS b FROM singles x JOIN singles y
              ON x.vacancy_id=y.vacancy_id AND x.a<y.a),
    triples AS (SELECT p.vacancy_id,p.a,p.b,z.a AS c FROM pairs p JOIN singles z
                ON p.vacancy_id=z.vacancy_id AND p.b<z.a)
    SELECT 1 AS k,[a] AS skills,count(*) AS frequency FROM singles GROUP BY a
    UNION ALL SELECT 2,[a,b],count(*) FROM pairs GROUP BY a,b
    UNION ALL SELECT 3,[a,b,c],count(*) FROM triples GROUP BY a,b,c;"""

def duck_counts(cap):
    conn=sql_connection();conn.execute(base_sql())
    rows=conn.execute(count_sql(cap)).fetchall();n=conn.execute('SELECT count(*) FROM vacancies').fetchone()[0]
    counters=[collections.Counter() for _ in range(3)]
    for k,sk,nf in rows:counters[k-1][tuple(sk)]=nf
    conn.close();return counters,{'vacancies':n,'threads':2}

def worker(args):
    start=time.perf_counter()
    if args.method=='duckdb':counts,meta=duck_counts(args.cap)
    else:counts,meta=mapreduce(args.cap,optimize=args.method=='mapreduce_optimized',inject_failure=args.failure)
    elapsed=time.perf_counter()-start
    path=RESULTS/args.output;save_counts(path,counts)
    meta.update(compute_seconds=elapsed,unique_keys=[len(c) for c in counts],emissions=[sum(c.values()) for c in counts])
    dump(path.with_suffix('.meta.json'),meta)
    print(json.dumps(meta,ensure_ascii=False))

def measured_run(method,cap,repeat,*,failure=False):
    import psutil
    filename=f'{method}_cap{cap}_run{repeat}'+('_failure' if failure else '')+'.csv'
    cmd=[sys.executable,str(pathlib.Path(__file__)), 'worker','--method',method,'--cap',str(cap),'--output',filename]
    if failure:cmd.append('--failure')
    t=time.perf_counter();peak=0
    logpath=RESULTS/'logs'/filename.replace('.csv','.log');logpath.parent.mkdir(parents=True,exist_ok=True)
    with logpath.open('w') as log:
        p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy());proc=psutil.Process(p.pid)
        while p.poll() is None:
            try:
                procs=[proc]+proc.children(recursive=True)
                # Sample sum of RSS of coordinator + its mapper processes, excludes RustFS.
                mem=sum(x.memory_info().rss for x in procs if x.is_running());peak=max(peak,mem)
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            time.sleep(.02)
        if p.returncode:raise RuntimeError(logpath.read_text())
    meta=load(RESULTS/filename.replace('.csv','.meta.json'))
    return {'method':method,'cap':cap,'repeat':repeat,'wall_seconds':time.perf_counter()-t,
            'peak_rss_mib':peak/1024**2,'compute_seconds':meta['compute_seconds'],'file':filename,**meta}

def benchmark():
    # Pre-install extension once, outside timed runs; fresh process/connection for every measurement.
    conn=sql_connection();conn.close()
    (ROOT/'sql').mkdir(exist_ok=True)
    (ROOT/'sql'/'prepare.sql').write_text(base_sql(),encoding='utf-8')
    for cap in CAPS:(ROOT/'sql'/f'counts_cap{cap}.sql').write_text(count_sql(cap),encoding='utf-8')
    runs=[]
    for cap in CAPS:
        for repeat in (1,2,3):
            # Alternate order to reduce an always-first cache advantage.
            methods=('mapreduce','duckdb') if repeat%2 else ('duckdb','mapreduce')
            for method in methods:
                row=measured_run(method,cap,repeat);runs.append(row);dump(RESULTS/'benchmark_raw.json',runs)
                print(method,'cap',cap,'run',repeat,'seconds',round(row['wall_seconds'],3),'RSS MiB',round(row['peak_rss_mib'],1),flush=True)
    for repeat in (1,2,3):
        row=measured_run('mapreduce_optimized',30,repeat);runs.append(row);dump(RESULTS/'benchmark_raw.json',runs)
        print('optimized',repeat,round(row['wall_seconds'],3),round(row['peak_rss_mib'],1),flush=True)
    summary=[]
    for method,cap in sorted({(r['method'],r['cap']) for r in runs}):
        group=[r for r in runs if r['method']==method and r['cap']==cap]
        summary.append({'method':method,'cap':cap,'attempts':len(group),
                        'median_wall_seconds':statistics.median(r['wall_seconds'] for r in group),
                        'median_compute_seconds':statistics.median(r['compute_seconds'] for r in group),
                        'median_peak_rss_mib':statistics.median(r['peak_rss_mib'] for r in group),
                        'max_peak_rss_mib':max(r['peak_rss_mib'] for r in group)})
    write_csv(RESULTS/'benchmark_summary.csv',summary);write_csv(RESULTS/'benchmark_runs.csv',
         [{k:r[k] for k in ('method','cap','repeat','wall_seconds','compute_seconds','peak_rss_mib','file')} for r in runs])
    checks=[]
    for cap in CAPS:
        baseline=read_counts(RESULTS/f'mapreduce_cap{cap}_run1.csv')
        for r in [r for r in runs if r['cap']==cap]:
            assert r['vacancies']==load(RESULTS/'data_quality.json')['selected_rows']
            other=read_counts(RESULTS/r['file']);keys=set(baseline)|set(other)
            mismatches=sum(baseline.get(k)!=other.get(k) for k in keys)
            checks.append({'cap':cap,'file':r['file'],'compared_keys':len(keys),'mismatches':mismatches})
            assert mismatches==0,(cap,r['file'],mismatches)
    failure=measured_run('mapreduce',30,99,failure=True)
    baseline=read_counts(RESULTS/'mapreduce_cap30_run1.csv');recovered=read_counts(RESULTS/failure['file'])
    assert baseline==recovered;assert failure['mapper_failure_observed']
    failure['exact_match']=True;dump(RESULTS/'mapper_failure.json',failure)
    dump(RESULTS/'verification.json',{'all_exact':True,'checks':checks,'failure_exact':True})
    print('ALL FULL FREQUENCY TABLES MATCH; MAPPER FAILURE RECOVERED',flush=True)

def analysis():
    conn=sql_connection();conn.execute(base_sql())
    # A comparable salary cohort, no invented FX rates or tax conversion.
    salary_sql="""CREATE TABLE pay AS SELECT *,
        CASE WHEN salary_from IS NOT NULL AND salary_to IS NOT NULL
          THEN (try_cast(salary_from AS DOUBLE)+try_cast(salary_to AS DOUBLE))/2
          ELSE coalesce(try_cast(salary_from AS DOUBLE),try_cast(salary_to AS DOUBLE)) END AS salary
        FROM vacancies WHERE currency='RUR' AND gross='false';
        DELETE FROM pay WHERE salary IS NULL OR salary<=0
          OR (try_cast(salary_from AS DOUBLE)>try_cast(salary_to AS DOUBLE));
        CREATE TABLE skill_rows AS SELECT vacancy_id,unnest(skills) AS skill FROM vacancies;
        CREATE TABLE pay_groups AS
          SELECT vacancy_id,[skill] AS combo FROM skill_rows
          UNION ALL SELECT x.vacancy_id,[x.skill,y.skill] FROM skill_rows x JOIN skill_rows y
             ON x.vacancy_id=y.vacancy_id AND x.skill<y.skill
          UNION ALL SELECT x.vacancy_id,[x.skill,y.skill,z.skill] FROM skill_rows x JOIN skill_rows y
             ON x.vacancy_id=y.vacancy_id AND x.skill<y.skill
             JOIN skill_rows z ON x.vacancy_id=z.vacancy_id AND y.skill<z.skill;"""
    conn.execute(salary_sql);(ROOT/'sql'/'salary.sql').write_text(salary_sql,encoding='utf-8')
    cursor=conn.execute("""SELECT g.combo,count(*) n,median(p.salary) median_salary,
        quantile_cont(p.salary,.25) q25,quantile_cont(p.salary,.75) q75
        FROM pay_groups g JOIN pay p USING(vacancy_id) GROUP BY g.combo""")
    allstats={tuple(r[0]):{'n':r[1],'median_salary':r[2],'q25':r[3],'q75':r[4]} for r in cursor.fetchall()}
    frequencies=read_counts(RESULTS/'duckdb_cap30_run1.csv')
    salary_results=[]
    for combo,st in allstats.items():
        k=len(combo)
        if k<2 or st['n']<20:continue
        bases=list(itertools.combinations(combo,k-1))
        base=min(bases,key=lambda b:(-frequencies.get((k-1,b),0),b))
        bst=allstats.get(base)
        if not bst or bst['n']<20:continue
        delta=st['median_salary']-bst['median_salary']
        salary_results.append({'k':k,'skills':' + '.join(combo),'n_pay':st['n'],
             'median_rub_net':st['median_salary'],'base_skills':' + '.join(base),'base_n_pay':bst['n'],
             'base_frequency_all':frequencies[(k-1,base)],'base_median_rub_net':bst['median_salary'],
             'delta_rub':delta,'delta_pct':100*delta/bst['median_salary'],'q25':st['q25'],'q75':st['q75']})
    salary_results.sort(key=lambda r:(r['k'],-r['delta_pct'],r['skills']))
    write_csv(RESULTS/'salary_all_supported.csv',salary_results)
    top=[]
    for k in (2,3):
        group=[r for r in salary_results if r['k']==k]
        for direction,subset in [('higher',sorted([r for r in group if r['delta_rub']>0],key=lambda r:-r['delta_pct'])[:8]),
                                 ('lower',sorted([r for r in group if r['delta_rub']<0],key=lambda r:r['delta_pct'])[:8])]:
            top.extend(dict(direction=direction,**r) for r in subset)
    write_csv(RESULTS/'salary_top.csv',top)
    regions=[];regional_top=[]
    for area in REGIONS:
        n=conn.execute('SELECT count(*) FROM vacancies WHERE area=?',[area]).fetchone()[0]
        nskills=conn.execute('SELECT count(*) FROM vacancies WHERE area=? AND len(skills)>0',[area]).fetchone()[0]
        row=conn.execute('SELECT count(*),median(salary),quantile_cont(salary,.25),quantile_cont(salary,.75) FROM pay WHERE area=?',[area]).fetchone()
        regions.append({'region':area,'vacancies':n,'with_skills':nskills,'net_rub_salary_n':row[0],
                        'salary_coverage_pct':100*row[0]/n,'median_rub_net':row[1],'q25':row[2],'q75':row[3]})
        for k in (1,2,3):
            rows=conn.execute('''SELECT g.combo,count(*) n, count(p.salary) n_pay, median(p.salary) median_pay
                FROM pay_groups g JOIN vacancies v USING(vacancy_id) LEFT JOIN pay p USING(vacancy_id)
                WHERE v.area=? AND len(g.combo)=? GROUP BY g.combo ORDER BY n DESC,g.combo LIMIT 10''',[area,k]).fetchall()
            for combo,nf,np,med in rows:regional_top.append({'region':area,'k':k,'skills':' + '.join(combo),
                'frequency':nf,'share_all_region_pct':100*nf/n,'salary_n':np,'median_rub_net':med})
    write_csv(RESULTS/'regions_summary.csv',regions);write_csv(RESULTS/'regions_skills_pairs_triples.csv',regional_top)
    # Experience composition documents one major confounder in salary association.
    rows=conn.execute('''SELECT experience,count(*) n,median(salary) median_pay FROM pay GROUP BY experience ORDER BY n DESC''').fetchall()
    write_csv(RESULTS/'salary_experience.csv',[{'experience':a,'n':n,'median_rub_net':m} for a,n,m in rows])
    summary={'salary_cohort':'RUR and gross=false; positive salary; midpoint or single supplied bound',
             'minimum_salary_support':20,'salary_n':conn.execute('SELECT count(*) FROM pay').fetchone()[0],
             'median_rub_net':conn.execute('SELECT median(salary) FROM pay').fetchone()[0],
             'eligible_pairs':sum(r['k']==2 for r in salary_results),'eligible_triples':sum(r['k']==3 for r in salary_results),
             'regions':regions,'top':top}
    dump(RESULTS/'analysis.json',summary);conn.close();print(json.dumps(summary,ensure_ascii=False,indent=2))

def publish_results():
    s=s3_client();c=config();objects=[]
    for p in sorted(RESULTS.rglob('*')):
        if p.is_file():
            key='results/devops/'+str(p.relative_to(RESULTS));s.upload_file(str(p),c['bucket'],key)
            head=s.head_object(Bucket=c['bucket'],Key=key);objects.append({'key':key,'bytes':head['ContentLength']})
    dump(RESULTS/'s3_objects.json',objects)
    print('S3 result objects:',len(objects));print(json.dumps(objects[:8],ensure_ascii=False,indent=2))

def verify_analysis():
    """Recompute reported medians in plain Python, independently of DuckDB aggregates."""
    salary_groups=collections.defaultdict(list); regional=collections.defaultdict(list)
    region_total=collections.Counter();n_salary=0;all_pay=[]
    for r in csv_rows():
        if not selected(r):continue
        region_total[r['area']]+=1
        if r['currency']!='RUR' or r['gross']!='false':continue
        bounds=[float(r[x]) if r[x] else None for x in ('salary_from','salary_to')]
        if all(x is not None for x in bounds) and bounds[0]>bounds[1]:continue
        supplied=[x for x in bounds if x is not None]
        if not supplied:continue
        pay=sum(supplied)/len(supplied)
        if pay<=0:continue
        all_pay.append(pay);regional[r['area']].append(pay);n_salary+=1
        sk=skills(r['key_skills'])
        for k in (1,2,3):
            for key in itertools.combinations(sk,k):salary_groups[key].append(pay)
    with (RESULTS/'salary_all_supported.csv').open(encoding='utf-8-sig',newline='') as f:
        supported=list(csv.DictReader(f))
    # Skill labels may themselves contain '+'; resolve labels through existing tuples, not by splitting.
    labels={' + '.join(k):k for k in salary_groups}
    assert len(labels)==len(salary_groups),'Ambiguous joined skill labels'
    for row in supported:
        values=salary_groups[labels[row['skills']]];base=salary_groups[labels[row['base_skills']]]
        assert len(values)==int(row['n_pay']) and len(base)==int(row['base_n_pay'])
        assert statistics.median(values)==float(row['median_rub_net'])
        assert statistics.median(base)==float(row['base_median_rub_net'])
    a=load(RESULTS/'analysis.json');assert a['salary_n']==n_salary
    assert statistics.median(all_pay)==a['median_rub_net']
    for row in a['regions']:
        assert region_total[row['region']]==row['vacancies']
        assert len(regional[row['region']])==row['net_rub_salary_n']
        assert statistics.median(regional[row['region']])==row['median_rub_net']
    evidence={'python_vs_duckdb_exact':True,'supported_combinations_checked':len(supported),
              'salary_rows':n_salary,'regions_checked':len(a['regions'])}
    dump(RESULTS/'analysis_verification.json',evidence);print(json.dumps(evidence,indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['upload','profile','benchmark','analysis','verify-analysis','publish','worker'])
    p.add_argument('--method',default='mapreduce');p.add_argument('--cap',type=int,default=30)
    p.add_argument('--output',default='counts.csv');p.add_argument('--failure',action='store_true');args=p.parse_args()
    RESULTS.mkdir(exist_ok=True)
    {'upload':upload,'profile':profile_data,'benchmark':benchmark,'analysis':analysis,'verify-analysis':verify_analysis,'publish':publish_results,
     'worker':lambda:worker(args)}[args.stage]()

if __name__=='__main__':main()
