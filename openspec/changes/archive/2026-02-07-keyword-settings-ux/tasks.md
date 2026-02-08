## 1. ConversationHandler 狀態重構

- [x] 1.1 將 `SETTINGS_KW_INPUT` 狀態替換為 `SETTINGS_KW_ADD_INCLUDE` 和 `SETTINGS_KW_ADD_EXCLUDE` 兩個新狀態
- [x] 1.2 更新 `create_application()` 中 settings ConversationHandler 的 states 映射

## 2. Keyword Panel 建構

- [x] 2.1 實作 `_build_keyword_keyboard(kw_include, kw_exclude)` 函式：產生包含所有現有關鍵字按鈕 + 操作列（➕ 包含、➖ 排除、🗑 清除、✅ 完成）的 InlineKeyboardMarkup
- [x] 2.2 空關鍵字時顯示「尚無關鍵字」提示，隱藏清除按鈕

## 3. Callback Handlers

- [x] 3.1 重寫 `settings_callback` 中 `settings:keywords` 分支：改為顯示 keyword panel（呼叫 `_build_keyword_keyboard`）
- [x] 3.2 實作 `kw_del_i:{keyword}` callback：從 include list 刪除指定關鍵字並刷新 panel
- [x] 3.3 實作 `kw_del_e:{keyword}` callback：從 exclude list 刪除指定關鍵字並刷新 panel
- [x] 3.4 實作 `kw_add_include` callback：發送提示訊息，返回 `SETTINGS_KW_ADD_INCLUDE` 狀態
- [x] 3.5 實作 `kw_add_exclude` callback：發送提示訊息，返回 `SETTINGS_KW_ADD_EXCLUDE` 狀態
- [x] 3.6 實作 `kw_clear` callback：清除所有關鍵字並刷新 panel
- [x] 3.7 實作 `kw_done` callback：回覆確認訊息，返回 `ConversationHandler.END`

## 4. 文字輸入 Handlers

- [x] 4.1 實作 `settings_kw_add_include_handler`：接收文字輸入，新增至 include list，檢查重複，刷新 panel 並發送新訊息
- [x] 4.2 實作 `settings_kw_add_exclude_handler`：接收文字輸入，新增至 exclude list，檢查重複，刷新 panel 並發送新訊息

## 5. Handler 註冊

- [x] 5.1 在 settings ConversationHandler 中新增 `SETTINGS_KW_ADD_INCLUDE` 和 `SETTINGS_KW_ADD_EXCLUDE` 狀態的 MessageHandler
- [x] 5.2 在 application 中註冊 keyword 相關的 CallbackQueryHandler（`kw_del_i:`, `kw_del_e:`, `kw_add_include`, `kw_add_exclude`, `kw_clear`, `kw_done`）

## 6. 移除舊程式碼

- [x] 6.1 移除舊的 `settings_keywords_handler` 函式
- [x] 6.2 移除 `SETTINGS_KW_INPUT` 狀態常數，更新 range() 數量

## 7. 測試

- [x] 7.1 測試 `_build_keyword_keyboard`：空關鍵字、有 include/exclude、混合情境
- [x] 7.2 測試新增重複關鍵字不會重複加入
- [x] 7.3 更新或移除舊的關鍵字文字指令相關測試
