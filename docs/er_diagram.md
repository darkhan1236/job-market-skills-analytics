# Схема SQLite

```mermaid
erDiagram
    companies o|--o{ jobs : employs
    jobs ||--o{ job_skills : has
    skills ||--o{ job_skills : occurs_in
    companies {
        INTEGER company_id PK
        TEXT name
        TEXT country
        INTEGER company_size
    }
    jobs {
        INTEGER job_id PK
        INTEGER company_id FK "nullable"
        TEXT title
        TEXT location
        TEXT region
        TEXT category
        TEXT experience
        TEXT work_type
        TEXT posted_date
        TEXT currency
        TEXT pay_period
        REAL annual_salary
        INTEGER remote_allowed "1 or NULL"
        REAL views
        REAL applies
        INTEGER description_chars
    }
    skills {
        TEXT skill_id PK
        TEXT name
        TEXT source "platform or dictionary"
    }
    job_skills {
        INTEGER job_id PK,FK
        TEXT skill_id PK,FK
    }
```

`company_id` может быть NULL, поэтому у вакансии ноль или одна известная компания. Ключ `job_skills(job_id,skill_id)` составной. Справочник `skills` объединяет источники через уникальные префиксы ID. Повтор одного навыка на вакансию не создаёт повторных записей. Внешние ключи проверяются после ETL. Точная DDL находится в sql/schema.sql, графическая версия — outputs/figures/er_diagram.svg.
