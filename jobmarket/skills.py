"""Transparent dictionary extraction. Mentions are not verified required skills."""
import re

PATTERNS = {
    'Python': r'\bpython\b', 'SQL': r'\b(?:sql|postgresql|mysql|sqlite|t-sql)\b',
    'Excel': r'\b(?:excel|spreadsheets?)\b', 'Tableau': r'\btableau\b',
    'Power BI': r'\bpower\s*bi\b', 'R': r'(?<![\w&])R(?![\w&])',
    'Java': r'\bjava\b', 'JavaScript': r'\b(?:javascript|typescript)\b',
    'C++': r'(?<!\w)c\+\+(?!\w)', 'C#': r'(?<!\w)c#(?!\w)',
    'AWS': r'\b(?:aws|amazon web services)\b', 'Azure': r'\bazure\b',
    'Google Cloud': r'\b(?:gcp|google cloud)\b', 'Docker': r'\bdocker\b',
    'Kubernetes': r'\b(?:kubernetes|k8s)\b', 'Git': r'\b(?:git|github|gitlab)\b',
    'Spark': r'\b(?:apache spark|pyspark|spark)\b', 'Hadoop': r'\bhadoop\b',
    'Machine Learning': r'\bmachine learning\b', 'Deep Learning': r'\bdeep learning\b',
    'NLP': r'\b(?:nlp|natural language processing)\b',
    'TensorFlow': r'\btensorflow\b', 'PyTorch': r'\bpytorch\b',
    'Pandas': r'\bpandas\b', 'NumPy': r'\bnumpy\b', 'Scikit-learn': r'\bscikit[- ]learn\b',
    'Statistics': r'\b(?:statistics|statistical)\b', 'Linux': r'\blinux\b',
    'Communication': r'\bcommunication\b', 'Leadership': r'\bleadership\b',
    'Project Management': r'\bproject management\b', 'Salesforce': r'\bsalesforce\b',
}
COMPILED = {name: re.compile(pattern, 0 if name == 'R' else re.IGNORECASE)
            for name, pattern in PATTERNS.items()}

def extract_skills(text):
    text = '' if text is None else str(text)
    return [name for name, pattern in COMPILED.items() if pattern.search(text)]

def role_category(title):
    title = str(title).lower()
    if re.search(r'data scien|machine learning|\bai\b|\bml\b', title):
        return 'Data Science / AI'
    elif re.search(r'data engineer|analytics engineer|database', title):
        return 'Data Engineering'
    elif re.search(r'analyst|analytics|business intelligence', title):
        return 'Analytics'
    elif re.search(r'software|developer|devops|programmer', title):
        return 'Software'
    return 'Other'
