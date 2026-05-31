# 0008. Транспорт (polling/webhook) и graceful shutdown

Статус: Accepted

## Контекст

Бот на aiogram 3.x должен получать апдейты Telegram и корректно останавливаться при рестарте/деплое
(бриф §3/§7). Два транспорта: long-polling (просто, без публичного адреса) и webhook (нужен HTTPS-эндпоинт,
сервер). Деплой — Docker, реакция на `SIGTERM` обязательна. Фоновый refresh-task должен гаситься без
зависаний, а конфиг-ошибка (битый секрет, 401/403/404) — приводить к видимому падению, а не вечному
ретраю.

## Решение

- **Polling по умолчанию**, webhook — под флагом `USE_WEBHOOK`. `choose_transport()` возвращает
  `"polling"`/`"webhook"`. В этом плане webhook — тонкий каркас (`NotImplementedError`); полная
  реализация (aiohttp, `set_webhook`, healthcheck = liveness процесса) — в плане infra.
- **Polling — строго одна реплика** (иначе Telegram 409). Документируется для деплоя.
- **Graceful shutdown:** `loop.add_signal_handler(SIGTERM/SIGINT)` ставит `asyncio.Event`; `run()` ждёт
  первым из {polling, refresh_task, stop}. По сигналу → отмена polling → `shutdown()`:
  `refresh_task.cancel()` + await (suppress `CancelledError`) → `bot.close()`. Общий лимит —
  `SHUTDOWN_TIMEOUT_S` через `asyncio.wait_for`. На Windows `add_signal_handler` отсутствует —
  `NotImplementedError` подавляется.
- **Non-transient `FetchError`** (битый creds, 401/403/404), всплывший из refresh-task, → `error` +
  `SystemExit(1)`: контейнер падает, оператор видит причину (а не молчаливый вечный backoff).

## Последствия

- Старт «из коробки» без инфраструктуры (polling); webhook включается флагом без правки кода вызова.
- Останов детерминирован: нет подвисших задач/сессий при деплое.
- Логика проводки (`run()`) тонкая и опирается на отдельно покрытые тестами `build_*`/`shutdown`/
  `choose_transport`; сам `asyncio.run`-glue юнит-тестами не покрывается (composition root).

## Альтернативы (отвергнуты)

- **Webhook-первым**: лишняя инфраструктура (домен/HTTPS/сервер) на старте, не нужная для запуска.
- **`dp.run_polling()` со встроенной обработкой сигналов**: меньше контроля над одновременной отменой
  refresh-task и порядком закрытия; выбран ручной `start_polling(handle_signals=False)` + свой shutdown.
- **Вечный backoff на любой ошибке**: маскирует конфиг-ошибки; различаем по `FetchError.transient`.
