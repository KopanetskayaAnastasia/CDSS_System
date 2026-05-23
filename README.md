# CDSS - Clinical Decision Support System

Система поддержки принятия врачебных решений на основе RAG-архитектуры (Retrieval-Augmented Generation).

## 📋 Описание

СППВР предназначена для автоматизации информационной поддержки врачей при работе с клиническими рекомендациями Минздрава РФ. Система обеспечивает:

- 🔍 Семантический поиск в клинических рекомендациях
- 🤖 Генерацию ответов с атрибуцией источников
- 📚 Долговременную память (медицинские факты о пациентах)
- 📊 Журнал аудита всех действий
- 🐳 Полную контейнеризацию через Docker

## 🛠 Технологический стек

| Компонент | Технология |
|-----------|------------|
| Backend API | FastAPI |
| База данных | PostgreSQL 15 |
| Векторная БД | ChromaDB |
| Кэш/сессии | Redis 7 |
| LLM | GigaChat API |
| Векторизация | multilingual-E5-large |
| UI | Streamlit |
| Контейнеризация | Docker + Docker Compose |

## 🚀 Быстрый старт

### Требования

- Docker Desktop (Windows/Mac) или Docker Engine (Linux)
- Git
- Ключ API GigaChat (получить на [developers.sber.ru](https://developers.sber.ru/))

### Установка и запуск

```bash
# 1. Клонирование репозитория
git clone https://github.com/KopanetskayaAnastasia/CDSS.git
cd CDSS

# 2. Создание файла с секретами
cp .env.example .env
# Отредактируйте .env - укажите свои ключи

# 3. Создание volume для PostgreSQL
docker volume create cdss_postgres_data

# 4. Запуск всех сервисов
docker compose up --build

# 5. В другом терминале создайте администратора
docker exec -it cdss_api python create_superuser.py