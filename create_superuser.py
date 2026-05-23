#!/usr/bin/env python3
"""
Скрипт для создания суперпользователя (администратора)
Запуск: docker exec -it cdss_api python create_superuser.py
"""

import os
import sys
import bcrypt
import psycopg2
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()


def create_superuser():
    """Создание администратора в БД, если его нет"""

    print("🔐 Создание суперпользователя CDSS...")

    # Подключение к БД
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.getenv("POSTGRES_DB", "cdss_db"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres")
        )
        cur = conn.cursor()
        print("✅ Подключение к PostgreSQL успешно")
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        sys.exit(1)

    # Проверка существования таблицы doctors
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'doctors'
        );
    """)
    table_exists = cur.fetchone()[0]

    if not table_exists:
        print("⚠️ Таблица doctors не существует. Запустите сначала приложение для создания таблиц.")
        print("   docker compose up --build")
        cur.close()
        conn.close()
        sys.exit(1)

    # Проверка существования таблицы roles
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'roles'
        );
    """)
    roles_exists = cur.fetchone()[0]

    if not roles_exists:
        print("⚠️ Таблица roles не существует. Запустите приложение для инициализации.")
        cur.close()
        conn.close()
        sys.exit(1)

    # Данные суперпользователя из .env
    admin_login = os.getenv("ADMIN_LOGIN", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    admin_full_name = os.getenv("ADMIN_FULL_NAME", "System Administrator")
    admin_specialty = os.getenv("ADMIN_SPECIALTY", "Administrator")

    # Хэширование пароля
    password_hash = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Проверка, существует ли роль Admin
    cur.execute("SELECT id FROM roles WHERE role_name = 'Admin'")
    role_result = cur.fetchone()

    if not role_result:
        print("⚠️ Роль 'Admin' не найдена. Создаю...")
        cur.execute("INSERT INTO roles (role_name, description) VALUES (%s, %s) RETURNING id",
                    ("Admin", "Администратор - загрузка PDF КР, управление версиями, просмотр логов"))
        role_id = cur.fetchone()[0]
        conn.commit()
        print(f"✅ Создана роль Admin с id={role_id}")
    else:
        role_id = role_result[0]

    # Проверка, существует ли уже такой пользователь
    cur.execute("SELECT id FROM doctors WHERE login = %s", (admin_login,))
    existing = cur.fetchone()

    if existing:
        print(f"⚠️ Пользователь {admin_login} уже существует. Обновляю пароль...")
        cur.execute(
            """UPDATE doctors 
               SET password_hash = %s, full_name = %s, specialty = %s, role_id = %s, is_active = TRUE 
               WHERE login = %s""",
            (password_hash, admin_full_name, admin_specialty, role_id, admin_login)
        )
        print(f"✅ Пароль пользователя {admin_login} обновлен")
    else:
        # Создание пользователя
        cur.execute("""
            INSERT INTO doctors (login, password_hash, full_name, specialty, role_id, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
        """, (admin_login, password_hash, admin_full_name, admin_specialty, role_id))
        print(f"✅ Создан новый пользователь: {admin_login}")

    conn.commit()
    cur.close()
    conn.close()

    print("\n" + "=" * 50)
    print("🎉 ГОТОВО! Суперпользователь создан/обновлен")
    print(f"   Логин: {admin_login}")
    print(f"   Пароль: {admin_password}")
    print("=" * 50)


if __name__ == "__main__":
    create_superuser()