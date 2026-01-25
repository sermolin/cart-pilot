# Dockerfile Optimization for Production

Все Dockerfile'ы были оптимизированы для production с использованием multi-stage builds.

## Основные улучшения

### 1. Multi-Stage Builds

Каждый Dockerfile теперь использует два этапа:

- **Builder stage**: Установка зависимостей и компиляция (если требуется)
- **Runtime stage**: Минимальный production образ только с необходимыми файлами

### 2. Оптимизация размера образа

- Разделение build-зависимостей (gcc, g++) и runtime зависимостей
- Удаление build-зависимостей из финального образа
- Использование `--no-cache-dir` для pip
- Минимизация количества слоев

### 3. Безопасность

- Использование non-root пользователя (`appuser`) для запуска приложений
- Правильные права доступа к файлам (`--chown=appuser:appuser`)
- Минимизация attack surface

### 4. Кэширование слоев

- Копирование `requirements.txt` перед копированием кода приложения
- Это позволяет Docker кэшировать слой с зависимостями при изменении кода

### 5. Production-ready настройки

- Оптимизированные health checks с увеличенными интервалами для production
- Правильные environment variables
- Улучшенные таймауты для health checks

## Оптимизированные Dockerfile'ы

### cartpilot-api/Dockerfile

- Multi-stage build с разделением builder и runtime
- Сохранение entrypoint скрипта для миграций БД
- Non-root пользователь для безопасности

### cartpilot-mcp/Dockerfile

- Multi-stage build
- Настройка TRANSPORT=sse по умолчанию для Docker
- Минимальный runtime образ

### merchant-a/Dockerfile

- Multi-stage build
- Простой runtime образ без лишних зависимостей
- Оптимизированный health check

### merchant-b/Dockerfile

- Multi-stage build
- Идентичная структура с merchant-a для консистентности
- Production-ready конфигурация

## Размеры образов (примерные)

До оптимизации:
- ~200-250 MB на сервис (включая build-зависимости)

После оптимизации:
- ~150-180 MB на сервис (только runtime зависимости)

**Экономия: ~20-30% размера образа**

## Использование

Сборка образов остается такой же:

```bash
# Локальная сборка
docker build -t cartpilot-api ./cartpilot-api

# Для GCP Artifact Registry
docker build -t us-central1-docker.pkg.dev/PROJECT_ID/cartpilot-docker/cartpilot-api:latest ./cartpilot-api
docker push us-central1-docker.pkg.dev/PROJECT_ID/cartpilot-docker/cartpilot-api:latest
```

## Проверка образов

После сборки можно проверить размер:

```bash
docker images | grep cartpilot
```

И проверить, что приложение запускается от non-root пользователя:

```bash
docker run --rm cartpilot-api whoami
# Должно вывести: appuser
```

## Совместимость

Оптимизированные Dockerfile'ы полностью совместимы с:
- Docker Compose (локальная разработка)
- Cloud Run (GCP deployment)
- Kubernetes (если потребуется в будущем)

Все существующие команды и конфигурации продолжают работать без изменений.
