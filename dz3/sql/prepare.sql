CREATE TABLE vacancies AS
    SELECT *, list_sort(list_distinct(list_filter(
        list_transform(string_split(coalesce(key_skills,''), ';'), s -> lower(trim(s, ' 	
'))),
        s -> s <> ''))) AS skills
    FROM read_csv('s3://hh-lake/raw/it_vacancies_2024.csv', header=true, all_varchar=true, delim=',', quote='"', escape='"',
                  nullstr='', max_line_size=16777216)
    WHERE trim(coalesce(role,'')) = 'DevOps-инженер'
       OR regexp_matches(lower(coalesce(name,'')), '(^|[^a-zа-яё0-9])(dev[ -]*ops|дев[ -]*опс)([^a-zа-яё0-9]|$)');