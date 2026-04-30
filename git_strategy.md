# Git стратегия — VolunteersOS

## 5.1.1 Стратегия веток

```
main          ← production (Render деплоит отсюда)
  └── develop ← интеграция всех фич
       ├── feature/cqrs-bff        ← задание 4.1 + 4.2
       ├── feature/domain-events   ← задание 4.3
       ├── feature/hotspot-metrics ← задание 5.2
       ├── feature/security        ← задание 6
       └── feature/teams           ← команды куратора
```

**Правила:**
- `main` — только через Pull Request из `develop`
- `develop` — только через Pull Request из `feature/*`
- Прямые коммиты в `main` запрещены
- Каждая фича = отдельная ветка

---

## 5.1.2 Feature workflow

```bash
# 1. Создать ветку от develop
git checkout develop
git pull origin develop
git checkout -b feature/teams

# 2. Разработка и коммиты
git add app/routers/teams_router.py
git commit -m "feat(teams): add team CRUD endpoints"

git add app/main.py
git commit -m "feat(teams): register teams router in main.py"

# 3. Push и Pull Request
git push origin feature/teams
# → GitHub: создать PR из feature/teams → develop

# 4. После merge в develop → PR в main
git checkout develop
git pull origin develop
git checkout -b release/v2.0
git push origin release/v2.0
# → GitHub: PR из release/v2.0 → main
```

---

## 5.1.3 Pull Request — шаблон описания

### PR: feat(cqrs-bff) — CQRS + BFF + Domain Events

**Что реализовано:**
- ✅ 4.1 CQRS — разделение Command/Query (`cqrs_commands.py`, `cqrs_queries.py`)
- ✅ 4.2 BFF — отдельные эндпоинты под Mobile/Web/Desktop
- ✅ 4.3 Domain Events — Redis Pub/Sub + Worker обновляет Read Model
- ✅ 5.2 Тепловая карта — горячие точки, метрики, кэш с инвалидацией
- ✅ 6. Безопасность — Rate Limiting, CORS, XSS, Mass Assignment

**Как проверить:**

1. Деплой на Render после merge
2. Открыть Swagger: `https://volunteer-api-5oq5.onrender.com/docs`
3. Проверить эндпоинты:
   ```
   GET  /query/volunteer/dashboard  → 200 (CQRS Query)
   POST /cmd/tasks/{id}/apply       → 200 (CQRS Command + cache invalidation)
   GET  /bff/mobile/dashboard       → 200 (BFF)
   GET  /metrics/hotspots           → 200 (тепловая карта)
   ```
4. Проверить кэш: дважды GET /query/volunteer/dashboard
   - 1й запрос: `"_from_cache": false`
   - 2й запрос: `"_from_cache": true`
5. После POST /cmd — снова GET, должно быть `false` (кэш сброшен)

**Связанные файлы:**
```
app/cqrs_commands.py   app/cqrs_queries.py
app/bff_mobile.py      app/bff_web.py      app/bff_desktop.py
app/domain_events.py   app/hotspot_metrics.py
app/security.py        app/middleware.py
app/routers/teams_router.py
```

---

## 5.1.4 Стандарт коммитов (Conventional Commits)

```
<type>(<scope>): <description>

feat     — новая функциональность
fix      — исправление бага
refactor — рефакторинг без изменения поведения
docs     — документация
test     — тесты
chore    — конфигурация, зависимости
```

**Примеры:**
```bash
git commit -m "feat(cqrs): add Command/Query split with cache invalidation"
git commit -m "feat(bff): add mobile dashboard aggregation endpoint"
git commit -m "feat(events): add Domain Event subscriber with Redis Pub/Sub"
git commit -m "feat(security): add rate limiting and XSS protection"
git commit -m "fix(bff-mobile): handle missing task_reports table gracefully"
git commit -m "fix(cors): add null origin support for file:// protocol"
git commit -m "feat(teams): add team enrollment for volunteers"
git commit -m "chore(deps): add slowapi==0.1.9 for rate limiting"
```

**Что НЕ делать:**
```bash
# ❌ Плохо
git commit -m "fix"
git commit -m "updated files"
git commit -m "changes"

# ✅ Хорошо
git commit -m "fix(auth): handle empty password in login endpoint"
```
