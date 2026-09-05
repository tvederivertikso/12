# VPN subscription checker

Источники включают два списка `Hidashimora/free-vpn-anti-rkn` и список `VansFenix/vpnparser`.

Скрипт каждый час скачивает источники, проверяет прокси через Xray-core из GitHub Actions и публикует список отвечающих узлов в формате URI, который понимает v2rayN.

> Используй только узлы и сервисы, которыми разрешено пользоваться в твоей юрисдикции. Публичные бесплатные узлы нестабильны и могут быть небезопасны.

## 1. Создание репозитория

1. Создай **публичный** репозиторий на GitHub, например `vpn-sub-checker`.
2. В локальной папке проекта выполни:

```bat
git init
git add .
git commit -m "initial vpn checker"
git branch -M main
git remote add origin https://github.com/ТВОЙ_ЛОГИН/vpn-sub-checker.git
git push -u origin main
```

Публичный репозиторий нужен, чтобы GitHub Actions не упирался в небольшой лимит минут приватного аккаунта. Не добавляй в него личные ключи, токены или приватные подписки.

## 2. Запуск

Открой GitHub → вкладка **Actions** → workflow **Check VPN subscription** → **Run workflow**. В дальнейшем cron запускает его примерно раз в час (GitHub может задерживать cron на несколько минут).

В workflow используется официальный Xray-core, а проверка выполняется реальным HTTPS-запросом к `https://www.avito.ru/` через локальный SOCKS5-вход каждого узла. Узел считается рабочим только при ответе `HTTP 200` и загрузке тела страницы не менее 1000 байт. Проверка выполняется из IP-адресов GitHub Actions, а не из твоей домашней сети.

## 3. Подписка в v2rayN

После первого успешного запуска итоговая ссылка будет:

```text
https://raw.githubusercontent.com/ТВОЙ_ЛОГИН/vpn-sub-checker/main/output/sub.txt
```

В v2rayN:

1. Открой **Подписки** → **Настройки подписки**.
2. Добавь URL выше и задай любое имя.
3. Нажми **Обновить подписки**.
4. В настройках подписки включи автоматическое обновление, если доступная версия v2rayN это поддерживает.

Важно: Xray проверяет только поддержанные схемы `vmess://`, `vless://`, `trojan://` и `ss://`. Неподдержанные форматы будут пропущены.

## Локальный запуск

Нужны Python 3.10+, Xray-core и `curl` в `PATH`:

```bat
python scripts\check.py --xray C:\путь\к\xray.exe --limit 20 --workers 4 --timeout 10
```

В Windows-папке v2rayN обычно уже есть `xray.exe`; укажи полный путь к нему. Локальный запуск проверяет узлы из твоей сети и пишет результаты в `output\sub.txt` и `output\report.md`.

## Защита от пустого результата

Если в очередном запуске не найден ни один рабочий узел, существующий непустой `output/sub.txt` сохраняется, чтобы подписка не исчезла из v2rayN. Причина записывается в отчёт.

## Файлы

- [`sources.txt`](sources.txt) — исходные URL подписок.
- [`scripts/parsers.py`](scripts/parsers.py) — извлечение URI и создание Xray outbound-конфигураций.
- [`scripts/check.py`](scripts/check.py) — проверка узлов и публикация результатов.
- [`.github/workflows/check.yml`](.github/workflows/check.yml) — ежечасный запуск.
- [`output/sub.txt`](output/sub.txt) — итоговая подписка.
- [`output/report.md`](output/report.md) — отчёт проверки.
