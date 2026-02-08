## Why

目前關鍵字設定採用文字指令模式（`+關鍵字`、`-關鍵字`、`done`），使用者需要記住特殊前綴語法，每次操作只有文字回覆而看不到全貌，操作步驟多且容易誤操作。應改為與區域設定一致的 inline keyboard 互動模式，讓關鍵字管理更直覺流暢。

## What Changes

- **關鍵字設定改為 inline keyboard 互動**：進入關鍵字設定後，顯示目前所有包含/排除關鍵字為按鈕，點擊可刪除；底部提供「新增包含」「新增排除」按鈕觸發文字輸入；每次操作後即時更新整個 keyboard 顯示最新狀態
- **移除文字指令模式**：不再需要 `+`/`-`/`clear`/`done` 等文字指令
- **新增操作按鈕**：清除全部、完成（返回 settings）

## Capabilities

### New Capabilities

### Modified Capabilities
- `telegram-bot-handler`: 關鍵字設定從文字指令模式改為 inline keyboard 互動模式

## Impact

- 修改 `src/tw_homedog/bot.py`：重寫 `settings_keywords_handler` 和相關 callback
- 修改 `tests/test_bot.py`：更新關鍵字設定相關測試
- 不影響 DB schema、pipeline、其他設定流程
