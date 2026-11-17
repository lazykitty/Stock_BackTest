# 專案說明
- 用途:股票報酬率回測

## 架構
- app.py：主程式（Streamlit UI）

## 功能
- 輸入股票代號 (純數字自動補 .TW，英文自動轉大寫)，從 Yahoo Finance 抓週K (還原值)
- 顯示年化報酬率 (CAGR)、每年報酬率柱狀圖、報酬率分佈柱狀圖
- 歷史查詢：
  - 輸入框為 `st.selectbox(accept_new_options=True)`，點擊出現歷史下拉清單，也可直接輸入新代號
  - 只記錄「查得到資料」的代號，錯誤代號不記錄
  - 最多保留 15 筆，最新在前，重複代號移到最前面
  - 持久化：雲端存 Google Sheet 工作表 `stock_history` (A 欄，gspread + 服務帳戶)，手機/不同電腦共用；
    st.secrets 未設定時退回本機 `history.json`
  - 每個連線啟動時載入一次，存入 `st.session_state.history`；更新時先讀最新內容再合併後寫回
  - 讀寫失敗不會中斷程式，畫面上方顯示警告
- 查詢年數：
  - 下拉選項 5 / 10 / 15 / 20 年 / 全部，預設「全部」
  - 綁定 `st.session_state["years_option"]`，選擇後後續查詢都沿用
  - 取最近 N 個年度報酬；年化報酬率以該區間起點 (所選第一年的前一年年底收盤) 計算
  - 資料年數不足時顯示提示並顯示全部

- quarry 分頁 (Google Sheet)：
  - 每次查詢成功的代號寫入一列，欄位: 代號, 股名, 類別, 產業別, 總年數, CAGR(全部), 近5年CAGR, 近10年CAGR, 近15年CAGR, 近20年CAGR
  - 近N年欄位由 `QUARRY_YEARS` 決定，與「查詢年數」下拉 (`YEAR_OPTIONS`) 同步
  - 代號已存在只更新 E 欄起的數值欄，不存在就新增；同一連線每個代號只同步一次
  - 舊格式表頭 (只有 CAGR、近10年CAGR) 會自動遷移：在 G 欄插入「近5年CAGR」並補 近15/20 年表頭，舊列的新欄位留空，重新查詢該代號後補上
  - 數值一律用全部歷史週K計算 (日期天數/365.25，近N年 = N*365.25 天)，不受「查詢年數」下拉影響；
    資料不足 N 年時同全部 CAGR；與畫面上以週數/52 算的年化報酬率可能略有差異
  - 類別依後綴判斷 (.TWO=tpex、無後綴=us、其他=twse)，產業別取自 yfinance；舊列的類別/產業別不會被覆蓋
  - 預設與歷史查詢同一個 Google Sheet；可用 secrets `quarry_sheet_id` 指定其他檔案

## 規則
- Streamlit Cloud 的本機檔案重啟/重新部署後會消失，雲端歷史一律存 Google Sheet
- 需要 secrets: `gcp_service_account` (服務帳戶 JSON)、`history_sheet_id`；Sheet 要共用給服務帳戶 email (編輯者)
- `st.set_page_config` 必須放在所有 Streamlit 指令之前
- `accept_new_options` 需較新版 Streamlit (`pip install -U streamlit`)；舊版會自動退回「文字框 + 歷史查詢下拉」

## 雲端原始檔
- GitHub
- 憑證只放 st.secrets (見 .streamlit/secrets.toml.example)，不可寫進程式碼或 commit

## 執行方式
streamlit run app.py