## Context

目前 `/settings` → 關鍵字使用 ConversationHandler 文字輸入模式：使用者需輸入 `+車位`、`-機械車位`、`clear`、`done` 等文字指令。這與其他設定項（模式用 InlineKeyboard 切換、區域用 toggle + 確認）的互動模式不一致，且操作不直覺。

現有流程：
1. 點選「關鍵字」→ 顯示目前關鍵字 + 文字格式說明
2. 使用者輸入 `+xxx` 或 `-xxx` → 系統回覆確認
3. 重複步驟 2 直到輸入 `done`

## Goals / Non-Goals

**Goals:**
- 關鍵字設定改為全 inline keyboard 互動，與區域設定體驗一致
- 每次操作後即時更新 keyboard 顯示完整狀態
- 支援新增、刪除個別關鍵字、清除全部

**Non-Goals:**
- 不改變關鍵字在 DB 中的儲存結構（`search.keywords_include`、`search.keywords_exclude` 維持 list）
- 不改變 matcher.py 的關鍵字匹配邏輯

## Decisions

### 1. 互動模式：Inline Keyboard 狀態面板 + 文字輸入混合

**選擇**：顯示 keyword 狀態面板（所有現有關鍵字為按鈕），底部操作列提供「➕ 包含」「➖ 排除」「🗑 清除」「✅ 完成」。點擊現有關鍵字按鈕可刪除該關鍵字。點擊「➕ 包含」或「➖ 排除」後進入文字輸入模式等待使用者輸入關鍵字，輸入後立即更新面板。

**替代方案**：預設關鍵字列表讓使用者 toggle（類似區域選擇）
**理由**：關鍵字是自由輸入的，無法預設列表。混合模式在需要新增時才進入文字輸入，其餘操作全在 keyboard 上完成。

### 2. 刪除確認：點擊即刪除，無二次確認

**選擇**：點擊關鍵字按鈕直接從列表移除並刷新 keyboard
**理由**：關鍵字可以立即重新新增，誤刪成本低。二次確認會讓操作更繁瑣。

### 3. ConversationHandler 狀態設計

**選擇**：新增 `SETTINGS_KW_ADD_INCLUDE` 和 `SETTINGS_KW_ADD_EXCLUDE` 兩個狀態，分別處理包含/排除關鍵字的文字輸入。原 `SETTINGS_KW_INPUT` 狀態移除。

**理由**：需要區分使用者正在新增的是包含還是排除關鍵字，以便將輸入的文字存入正確的列表。

## Risks / Trade-offs

- **Keyboard 按鈕數量限制** → Telegram InlineKeyboard 每行最多 8 個按鈕，每則訊息最多 100 個按鈕。關鍵字通常不超過 10 個，不會觸及限制。
- **callback_data 長度限制** → Telegram callback_data 最長 64 bytes。使用 `kw_del_i:{keyword}` 和 `kw_del_e:{keyword}` 格式，關鍵字本身不應超過 50 字元，足夠使用。
