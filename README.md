# Obsidian Automator

個人用的每日筆記自動化：每天早上 05:00（Asia/Taipei）抓天氣、Google 日曆行程、Gmail 未讀信與 AI 建造者動態，交給 Claude Code CLI 寫成 Obsidian 的 Daily note 與 AI Digest，並依分類幫信件加標籤、把促銷與通知信移出收件匣。

只供作者本人使用，Google OAuth 授權也只綁作者自己的帳號。資料處理方式見 [隱私權政策](privacy.md)。

## 流程

```
cron 05:00 ─▶ gmail_fetcher.py ─▶ /tmp/emails.json、/tmp/gmail-labels.json
           ─▶ calendar_fetcher.py ─▶ /tmp/calendar.json
           ─▶ weather.sh ─▶ /tmp/weather.json
           ─▶ claude --print（prompts/daily.md）─▶ /vault/Daily/{date}.md
                                                 /vault/AI-Digest/{date}.md
                                                 /tmp/email-labels.json
           ─▶ gmail_labeler.py ─▶ Gmail 加標籤／封存
```

Daily note 以 `<!-- AUTO-END: -->` 標記分成自動區與手寫區，每日更新只改自動區。

## 安裝

1. 在 Google Cloud 建一個專案，啟用 Gmail API 與 Google Calendar API，建立「電腦版應用程式」類型的 OAuth 用戶端，下載成 `credentials/credentials.json`。
2. OAuth 同意畫面要發布成「正式版」。停在「測試中」的話 refresh token 7 天就過期，之後每天 `invalid_grant`。
3. 複製 `.env.example` 為 `.env`，填 `PERSONAL_GMAIL`。
4. 首次授權（在 WSL 跑，印出的網址用 Windows 瀏覽器開；8080 常被別的服務占用，這裡用 8765）：

   ```bash
   docker compose run --rm -p 8765:8765 -e OAUTH_PORT=8765 -e OAUTH_BIND=0.0.0.0 -e OAUTH_OPEN_BROWSER=0 automator python3 /app/scripts/google_auth.py --auth personal
   ```

5. 啟動：`docker compose build && docker compose up -d`。第一次執行會做 14 天的補抓，之後每天只整理前 24 小時的未讀信。

Claude Code CLI 的登入狀態直接掛主機的 `~/.claude`（唯讀）。

## 授權失效時

fetcher 以結束碼 3 回報，容器 log（`/tmp/automator-<日期>.log`）會印 ✗ 與重新授權指令，當天的 Daily note 也會出現「授權失效」警告框，不會再默默寫成「（無）」。重新授權就是再跑一次上面第 4 步。

## 目錄

| 路徑 | 用途 |
|------|------|
| `scripts/google_auth.py` | OAuth 授權與 token 更新 |
| `scripts/gmail_fetcher.py` | 抓未讀信與使用者既有標籤 |
| `scripts/calendar_fetcher.py` | 抓當日行程 |
| `scripts/weather.sh` | Open-Meteo 天氣 |
| `scripts/prompts/daily.md` | 給 Claude 的生成指令 |
| `scripts/gmail_labeler.py` | 套用 Claude 決定的標籤與封存 |
| `scripts/entrypoint.sh` | 每日流程 |
| `credentials/` | OAuth 憑證與 token，不進版本控制 |
