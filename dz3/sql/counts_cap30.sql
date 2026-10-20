WITH limited AS (SELECT vacancy_id, list_slice(skills,1,30) AS sk FROM vacancies),
    singles AS (SELECT vacancy_id, unnest(sk) AS a FROM limited),
    pairs AS (SELECT x.vacancy_id,x.a,y.a AS b FROM singles x JOIN singles y
              ON x.vacancy_id=y.vacancy_id AND x.a<y.a),
    triples AS (SELECT p.vacancy_id,p.a,p.b,z.a AS c FROM pairs p JOIN singles z
                ON p.vacancy_id=z.vacancy_id AND p.b<z.a)
    SELECT 1 AS k,[a] AS skills,count(*) AS frequency FROM singles GROUP BY a
    UNION ALL SELECT 2,[a,b],count(*) FROM pairs GROUP BY a,b
    UNION ALL SELECT 3,[a,b,c],count(*) FROM triples GROUP BY a,b,c;