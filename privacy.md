# 隱私權政策 — Obsidian Automator

最後更新：2026-11-03

Obsidian Automator 是作者個人使用的自動化工具，用來把自己的 Gmail、Google 日曆與天氣資訊整理成本機 Obsidian 筆記。它只在作者自己的電腦上執行，只由作者本人授權自己的 Google 帳號使用，不對外提供服務，也不開放其他使用者授權。

## 取得哪些 Google 資料

透過 Google OAuth 取得以下權限：

- Gmail 讀取、標籤、修改、篩選器設定（`gmail.readonly`、`gmail.labels`、`gmail.modify`、`gmail.settings.basic`）
- Google 日曆唯讀（`calendar.readonly`）

每日執行時讀取：

- 前 24 小時的未讀信件（最多 50 封）：寄件人、收件人、主旨、日期、片段與前 500 字內文、既有標籤；首次執行為過去 14 天最多 500 封，只讀片段
- 使用者自己建立的 Gmail 標籤名稱
- 當天所有行事曆的事件：標題、時間、地點、會議連結、前 200 字說明

## 如何處理

- 抓到的資料存在作者本機 Docker 容器的暫存目錄，每天被下一次執行覆蓋。
- 信件與行程的摘要片段會送到 Anthropic 的 Claude 模型（透過 Claude Code CLI）產生中文摘要與分類，處理方式依 Anthropic 的服務條款。除此之外不會傳送給任何第三方。
- 產生的摘要寫入作者本機的 Obsidian 筆記。
- 對 Gmail 的寫入動作只有兩種：加上標籤、把促銷與通知類信件移出收件匣（封存）。不會刪除信件、不會寄信、不會改動行事曆。

## 不做的事

- 不販售、不分享、不公開任何信件或行程內容。
- 不用於廣告或分析。
- 不保存原始信件內容超過一天。

## 憑證

OAuth token 存在本機的 `credentials/` 目錄，不進版本控制。可隨時在 [Google 帳戶的第三方存取設定](https://myaccount.google.com/permissions) 撤銷授權，撤銷後本工具即無法再讀取任何資料。

## 聯絡

有疑問請在本專案的 GitHub Issues 提出。
