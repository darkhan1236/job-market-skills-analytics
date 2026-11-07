"""Streamlit mini-dashboard. Run: python -m streamlit run app.py"""
import json
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
from jobmarket.config import DB, OUTPUT

st.set_page_config(page_title='Job Market Skills Analytics',page_icon='📊',layout='wide')
st.title('Job Market Skills Analytics')
st.caption('LinkedIn snapshots 2023–2024 · исторические данные · USD base salary')
if not DB.exists():
    st.info('Сначала выполните: python main.py all')
    st.stop()

@st.cache_data
def query(sql, params, db_stamp):
    with sqlite3.connect(DB) as connection:
        return pd.read_sql_query(sql,connection,params=params)

stamp = DB.stat().st_mtime_ns
def read(sql, params=()):
    return query(sql,tuple(params),stamp)

options = read('SELECT DISTINCT substr(posted_date,1,4) AS year,region,category,experience FROM jobs')
st.sidebar.header('Фильтры')
years = st.sidebar.multiselect('Год', sorted(options['year'].dropna().unique()))
regions = st.sidebar.multiselect('Регион', sorted(options['region'].unique()))
categories = st.sidebar.multiselect('Категория должности', sorted(options['category'].unique()))
experience = st.sidebar.multiselect('Уровень опыта', sorted(options['experience'].unique()))
remote = st.sidebar.checkbox('Только явно разрешённая удалённая работа')
source = st.sidebar.selectbox('Источник навыков',['dictionary','platform'],format_func=lambda x: 'Упоминания в тексте' if x=='dictionary' else 'Категории LinkedIn')
skill_options = read('SELECT skill_id,name FROM skills WHERE source=? ORDER BY name',(source,))
skill = st.sidebar.selectbox('Навык для фильтрации вакансий',['Все']+skill_options['name'].tolist())
conditions, params = ['1=1'], []
for column, values in [('substr(j.posted_date,1,4)',years),('j.region',regions),('j.category',categories),('j.experience',experience)]:
    if values:
        conditions.append(f"{column} IN ({','.join('?' for _ in values)})")
        params.extend(values)
if remote:
    conditions.append('j.remote_allowed=1')
if skill != 'Все':
    conditions.append('EXISTS(SELECT 1 FROM job_skills js JOIN skills s USING(skill_id) WHERE js.job_id=j.job_id AND s.source=? AND s.name=?)')
    params.extend([source,skill])
where = ' AND '.join(conditions)
data = read('SELECT j.* FROM jobs j WHERE '+where,params)
if data.empty:
    st.warning('Нет вакансий для выбранных фильтров. Измените выбор.')
    st.stop()
salary = data['annual_salary'].dropna()
cols = st.columns(3)
cols[0].metric('Вакансий',f'{len(data):,}')
cols[1].metric('Сопоставимая зарплата',f'{len(salary)/len(data):.1%}')
cols[2].metric('Медиана USD в год',f'${salary.median():,.0f}' if len(salary) else 'Нет данных')
tabs = st.tabs(['Навыки и роли','Зарплаты','Время и прогноз','Данные и метод'])
with tabs[0]:
    skills = read('SELECT s.name,COUNT(*) AS jobs FROM jobs j JOIN job_skills js USING(job_id) JOIN skills s USING(skill_id) WHERE '+where+' AND s.source=? GROUP BY s.skill_id ORDER BY jobs DESC',params+[source])
    skills['share_pct'] = skills['jobs']/len(data)*100
    st.plotly_chart(px.bar(skills.head(20),x='jobs',y='name',orientation='h',hover_data=['share_pct'],title='Число вакансий с навыком в выбранной группе').update_layout(yaxis={'categoryorder':'total ascending'}),width='stretch')
    st.caption('Одна вакансия может содержать несколько навыков. Знаменатель долей: все вакансии после фильтров. Упоминание не подтверждает обязательность навыка.')
    role_counts=data['category'].value_counts().rename_axis('category').reset_index(name='jobs')
    st.plotly_chart(px.bar(role_counts,x='category',y='jobs',title='Группы должностей по правилам названий'),width='stretch')
with tabs[1]:
    st.caption('Только USD и BASE_SALARY. Медиана источника либо середина корректного диапазона. Почасовая ставка × 2080, месячная × 12, недельная × 52. Пропуски не заполняются.')
    if salary.empty:
        st.info('Сопоставимых зарплат нет.')
    else:
        trimmed=st.checkbox('Ограничить графики интервалом IQR',value=True)
        plot=data.dropna(subset=['annual_salary']).copy()
        if trimmed:
            q1,q3=salary.quantile([.25,.75]); spread=q3-q1
            plot=plot.loc[plot['annual_salary'].between(max(0,q1-1.5*spread),q3+1.5*spread)]
        st.caption(f'На графиках {len(plot):,} из {len(salary):,} зарплат. Исходные значения сохранены в базе.')
        st.plotly_chart(px.histogram(plot,x='annual_salary',nbins=50,labels={'annual_salary':'USD в год'}),width='stretch')
        top=plot['region'].value_counts().head(10).index
        st.plotly_chart(px.box(plot.loc[plot['region'].isin(top)],x='region',y='annual_salary',points=False),width='stretch')
        st.dataframe(data.groupby('region')['annual_salary'].agg(['count','median']).sort_values('count',ascending=False))
with tabs[2]:
    daily = data.assign(date=pd.to_datetime(data['posted_date'])).groupby('date').size().rename('jobs').asfreq('D').reset_index()
    timeline = px.line(daily,x='date',y='jobs',title='Наблюдаемые даты публикаций в выбранной группе')
    timeline.update_traces(connectgaps=False)
    st.plotly_chart(timeline,width='stretch')
    st.warning('Пропущенные дни означают неизвестное покрытие сбора. Изменения числа объявлений нельзя напрямую трактовать как изменение всего рынка.')
    if (OUTPUT/'tables/forecast_metrics.csv').exists():
        st.subheader('Проверка прогноза для полного набора данных')
        st.caption('Эти результаты относятся ко всему набору и не пересчитываются боковыми фильтрами. Прогноз на 1 день с обновлением истории после наблюдения факта.')
        st.dataframe(pd.read_csv(OUTPUT/'tables/forecast_metrics.csv'))
        protocol=json.loads((OUTPUT/'forecast_protocol.json').read_text())
        st.write(f"Выбор по validation: {protocol['selected_on_validation']}. Test начинается {protocol['test_start']}.")
with tabs[3]:
    st.write('Категории должностей определяются правилами. Регион - двухбуквенный суффикс location, без геокодирования. Отсутствие флага remote означает неизвестность.')
    st.write('Сезонная декомпозиция STL использует период 7 дней. Она описывает наблюдаемый сегмент и не участвует в признаках прогноза.')
    st.dataframe(data.head(100))
    st.download_button('Скачать отфильтрованные данные CSV',data.to_csv(index=False).encode('utf-8-sig'),file_name='filtered_jobs.csv',mime='text/csv')
