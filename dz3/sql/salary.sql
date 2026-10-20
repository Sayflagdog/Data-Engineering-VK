CREATE TABLE pay AS SELECT *,
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
             JOIN skill_rows z ON x.vacancy_id=z.vacancy_id AND y.skill<z.skill;