"""
Skills normalization.

Maintains a canonical alias dictionary mapping common abbreviations and
alternate spellings to their canonical names.

Supports fuzzy matching via rapidfuzz for near-misses.
"""
from typing import Optional
from rapidfuzz import fuzz, process

# ─── Canonical Skill Alias Dictionary ─────────────────────────────────────────
# Maps all known aliases/abbreviations -> canonical name
# Keys must be lowercase. Values are the display-canonical form.

SKILL_TAXONOMY: dict[str, str] = {
    # JavaScript ecosystem
    "javascript": "JavaScript",
    "js": "JavaScript",
    "ecmascript": "JavaScript",
    "es6": "JavaScript",
    "es2015": "JavaScript",
    "vanilla js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "express": "Express.js",
    "express.js": "Express.js",
    "expressjs": "Express.js",
    "react": "React",
    "react.js": "React",
    "reactjs": "React",
    "react native": "React Native",
    "rn": "React Native",
    "vue": "Vue.js",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "angular": "Angular",
    "angularjs": "Angular",
    "next": "Next.js",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "nuxt": "Nuxt.js",
    "nuxt.js": "Nuxt.js",

    # Python ecosystem
    "python": "Python",
    "py": "Python",
    "python3": "Python",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scipy": "SciPy",
    "sklearn": "scikit-learn",
    "scikit-learn": "scikit-learn",
    "scikit learn": "scikit-learn",

    # Go
    "go": "Go",
    "golang": "Go",

    # Java / JVM
    "java": "Java",
    "kotlin": "Kotlin",
    "scala": "Scala",
    "spring": "Spring Boot",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",

    # C family
    "c": "C",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "csharp": "C#",
    "dotnet": ".NET",
    ".net": ".NET",
    "asp.net": "ASP.NET",
    "aspnet": "ASP.NET",

    # Ruby
    "ruby": "Ruby",
    "rails": "Ruby on Rails",
    "ruby on rails": "Ruby on Rails",
    "ror": "Ruby on Rails",

    # PHP
    "php": "PHP",
    "laravel": "Laravel",
    "symfony": "Symfony",

    # Rust / Swift / Dart
    "rust": "Rust",
    "swift": "Swift",
    "dart": "Dart",
    "flutter": "Flutter",

    # Cloud
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "Google Cloud",
    "google cloud": "Google Cloud",
    "google cloud platform": "Google Cloud",
    "azure": "Azure",
    "microsoft azure": "Azure",

    # DevOps / Infrastructure
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "helm": "Helm",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "jenkins": "Jenkins",
    "github actions": "GitHub Actions",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",

    # Databases
    "sql": "SQL",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "elastic": "Elasticsearch",
    "cassandra": "Cassandra",
    "dynamodb": "DynamoDB",
    "firebase": "Firebase",

    # ML / AI
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "deep learning": "Deep Learning",
    "dl": "Deep Learning",
    "nlp": "NLP",
    "natural language processing": "NLP",
    "computer vision": "Computer Vision",
    "cv": "Computer Vision",
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "keras": "Keras",
    "llm": "LLMs",
    "large language models": "LLMs",
    "genai": "Generative AI",
    "generative ai": "Generative AI",
    "rag": "RAG",
    "retrieval augmented generation": "RAG",

    # Data Engineering
    "spark": "Apache Spark",
    "apache spark": "Apache Spark",
    "kafka": "Apache Kafka",
    "apache kafka": "Apache Kafka",
    "airflow": "Apache Airflow",
    "apache airflow": "Apache Airflow",
    "dbt": "dbt",
    "data build tool": "dbt",

    # Systems & Networks
    "linux": "Linux",
    "unix": "Unix",
    "bash": "Bash",
    "shell": "Shell Scripting",
    "shell scripting": "Shell Scripting",
    "git": "Git",
    "graphql": "GraphQL",
    "rest": "REST APIs",
    "rest api": "REST APIs",
    "restful": "REST APIs",
    "grpc": "gRPC",
    "microservices": "Microservices",
    "kafka streams": "Kafka Streams",

    # Testing
    "jest": "Jest",
    "pytest": "pytest",
    "junit": "JUnit",
    "selenium": "Selenium",
    "cypress": "Cypress",

    # CS Fundamentals (common in fresher resumes)
    "dbms": "DBMS",
    "database management": "DBMS",
    "database management system": "DBMS",
    "rdbms": "RDBMS",
    "oop": "OOP",
    "object oriented programming": "OOP",
    "object-oriented programming": "OOP",
    "oops": "OOP",
    "dsa": "Data Structures & Algorithms",
    "data structures": "Data Structures & Algorithms",
    "data structures and algorithms": "Data Structures & Algorithms",
    "algorithms": "Data Structures & Algorithms",
    "os": "Operating Systems",
    "operating system": "Operating Systems",
    "cn": "Computer Networks",
    "computer network": "Computer Networks",
    "computer networking": "Computer Networks",
    "networking": "Computer Networks",
    "se": "Software Engineering",
    "software engineering": "Software Engineering",

    # Web basics
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    "sass": "Sass",
    "scss": "Sass",
    "bootstrap": "Bootstrap",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",

    # Mobile
    "android": "Android",
    "ios": "iOS",
    "react native": "React Native",
    "flutter": "Flutter",
    "swift": "Swift",
    "kotlin": "Kotlin",

    # Data / BI
    "pandas": "Pandas",
    "numpy": "NumPy",
    "matplotlib": "Matplotlib",
    "seaborn": "Seaborn",
    "scipy": "SciPy",
    "power bi": "Power BI",
    "powerbi": "Power BI",
    "tableau": "Tableau",
    "excel": "Microsoft Excel",
    "ms excel": "Microsoft Excel",
    "looker": "Looker",
    "metabase": "Metabase",
    "snowflake": "Snowflake",
    "databricks": "Databricks",
    "hadoop": "Hadoop",
    "hive": "Hive",
    "spark sql": "Spark SQL",
    "pyspark": "PySpark",

    # Other
    "agile": "Agile",
    "scrum": "Scrum",
    "jira": "Jira",
    "figma": "Figma",
    "postman": "Postman",
    "swagger": "Swagger",
    "openapi": "OpenAPI",
    "rabbitmq": "RabbitMQ",
    "nginx": "Nginx",
    "apache": "Apache HTTP Server",
    "celery": "Celery",
    "redis celery": "Celery",
    "jwt": "JWT",
    "oauth": "OAuth",
    "oauth2": "OAuth 2.0",
    "openid": "OpenID Connect",
    "websocket": "WebSockets",
    "websockets": "WebSockets",
    "grpc": "gRPC",
    "microservices": "Microservices",
    "kafka streams": "Kafka Streams",
    "solidity": "Solidity",
    "web3": "Web3",
    "blockchain": "Blockchain",
    "elixir": "Elixir",
    "phoenix": "Phoenix",
    "r": "R",
    "matlab": "MATLAB",
    "svelte": "Svelte",
    "remix": "Remix",
    "trpc": "tRPC",
    "vercel": "Vercel",
    "netlify": "Netlify",
    "heroku": "Heroku",
    "digitalocean": "DigitalOcean",
}

# The set of canonical display names (for fuzzy matching targets)
CANONICAL_SKILLS: list[str] = sorted(set(SKILL_TAXONOMY.values()))


def normalize_skill(skill_name: str, fuzzy_threshold: float = 80.0) -> str:
    """
    Normalize a skill name to its canonical form.

    Resolution order:
    1. Exact match in alias dictionary (case-insensitive)
    2. Exact match against canonical names (case-insensitive)
    3. Fuzzy match against canonical names (rapidfuzz ratio)
    4. Fallback: title-case the original string

    Returns the canonical name string.
    """
    if not skill_name or not skill_name.strip():
        return ""

    clean = skill_name.strip().lower()

    # 1. Exact alias lookup
    if clean in SKILL_TAXONOMY:
        return SKILL_TAXONOMY[clean]

    # 2. Case-insensitive match against canonical values
    for canonical in CANONICAL_SKILLS:
        if clean == canonical.lower():
            return canonical

    # 3. Fuzzy match against canonicals
    result = process.extractOne(clean, CANONICAL_SKILLS, scorer=fuzz.ratio)
    if result:
        match, score, _ = result
        if score >= fuzzy_threshold:
            return match

    # 4. Fallback: title-case original
    return skill_name.strip().title()


def get_alias_reason(skill_name: str) -> str:
    """Return a human-readable reason for skill normalization."""
    clean = skill_name.strip().lower()
    if clean in SKILL_TAXONOMY:
        canonical = SKILL_TAXONOMY[clean]
        if canonical.lower() != clean:
            return f"Matched alias '{skill_name}' → '{canonical}' via alias dictionary"
        return f"Exact match in canonical dictionary"
    result = process.extractOne(clean, CANONICAL_SKILLS, scorer=fuzz.ratio)
    if result:
        match, score, _ = result
        if score >= 80.0:
            return f"Fuzzy matched '{skill_name}' → '{match}' (score={score:.0f})"
    return f"Title-cased fallback for '{skill_name}'"
