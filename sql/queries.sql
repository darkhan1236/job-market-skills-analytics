-- name: 01_top_dictionary_skills
SELECT s.name, COUNT(*) AS jobs,
       ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM jobs),2) AS pct_all_jobs
FROM job_skills js JOIN skills s USING(skill_id)
WHERE s.source='dictionary'
GROUP BY s.skill_id ORDER BY jobs DESC;

-- name: 02_top_platform_functions
SELECT s.name, COUNT(*) AS jobs
FROM job_skills js JOIN skills s USING(skill_id)
WHERE s.source='platform'
GROUP BY s.skill_id ORDER BY jobs DESC;

-- name: 03_salary_by_region
SELECT region, COUNT(*) AS salary_n, AVG(annual_salary) AS mean_usd_year
FROM jobs WHERE annual_salary IS NOT NULL
GROUP BY region HAVING COUNT(*) >= 100 ORDER BY salary_n DESC;

-- name: 04_top_employers
SELECT c.company_id, c.name, COUNT(*) AS jobs
FROM companies c JOIN jobs j USING(company_id)
GROUP BY c.company_id ORDER BY jobs DESC LIMIT 20;

-- name: 05_daily_counts
SELECT posted_date, COUNT(*) AS jobs FROM jobs
WHERE posted_date IS NOT NULL GROUP BY posted_date ORDER BY posted_date;

-- name: 06_top_titles_within_region
WITH counts AS (
 SELECT region, title, COUNT(*) AS jobs FROM jobs GROUP BY region,title
), ranked AS (
 SELECT *, ROW_NUMBER() OVER (PARTITION BY region ORDER BY jobs DESC,title) AS rank
 FROM counts
)
SELECT * FROM ranked WHERE rank <= 3 ORDER BY region,rank;

-- name: 07_salary_above_category_average
WITH category_means AS (
 SELECT category, AVG(annual_salary) AS category_mean FROM jobs GROUP BY category
)
SELECT j.category, COUNT(*) AS jobs_above_category_mean
FROM jobs j JOIN category_means c ON c.category=j.category
WHERE j.annual_salary > c.category_mean
GROUP BY j.category;

-- name: 08_monthly_change
WITH monthly AS (
 SELECT substr(posted_date,1,7) AS month, COUNT(*) AS jobs FROM jobs
 WHERE posted_date IS NOT NULL GROUP BY month
)
SELECT month,jobs, LAG(jobs) OVER(ORDER BY month) AS previous_observed_month_jobs
FROM monthly ORDER BY month;

-- name: 09_skill_salary
SELECT s.name, COUNT(*) AS salary_n, AVG(j.annual_salary) AS mean_usd_year
FROM skills s JOIN job_skills js USING(skill_id) JOIN jobs j USING(job_id)
WHERE s.source='dictionary' AND j.annual_salary IS NOT NULL
GROUP BY s.skill_id HAVING COUNT(*) >= 50 ORDER BY salary_n DESC;

-- name: 10_experience_coverage
SELECT experience, COUNT(*) AS jobs, COUNT(annual_salary) AS salary_n,
       ROUND(100.0*COUNT(annual_salary)/COUNT(*),2) AS salary_coverage_pct
FROM jobs GROUP BY experience ORDER BY jobs DESC;
