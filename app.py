# 股票報酬率回測

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import math
import json
from datetime import timedelta
from pathlib import Path

# set_page_config 必須是第一個 Streamlit 指令
st.set_page_config(page_title="股票回測工具", layout="wide")

MAX_HISTORY = 15
YEAR_OPTIONS = {"5 年": 5, "10 年": 10, "15 年": 15, "20 年": 20, "全部": None}


@st.cache_data(ttl=18640)
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    # 抓取歷史週K
    df = stock.history(period="max", interval="1wk", auto_adjust=True)

    # 抓取股名
    try:
        s_info = stock.info
        name = s_info.get('longName') or s_info.get('shortName') or ticker
        industry = s_info.get('industry') or ""
    except Exception:
        name = ticker
        industry = ""

    return df, name, industry


def apply_mobile_layout(fig):
    fig.update_layout(
        # 鎖定 X 軸與 Y 軸，防止任何形式的縮放或位移
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True),
        dragmode=False,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
    )
    return fig


# --- 歷史查詢的持久化儲存 ---
# 雲端：Google Sheet (st.secrets 有設定時)；本機：history.json 備援
LOCAL_FILE = Path(__file__).with_name("history.json")
SHEET_NAME = "stock_history"
QUERY_SHEET_NAME = "query"     # 每個代號一列的回測結果
QUERY_HEADER = ["代號", "股名", "類別", "產業別", "總年數", "CAGR", "近10年CAGR"]


@st.cache_resource
def _get_spreadsheet(sheet_id):
    import gspread
    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    return gc.open_by_key(sheet_id)


def _get_tab(sh, name, cols=10):
    import gspread
    try:
        return sh.worksheet(name)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(name, rows=1000, cols=cols)


def _get_worksheet():
    return _get_tab(_get_spreadsheet(st.secrets["history_sheet_id"]), SHEET_NAME, 1)


def _use_sheet():
    try:
        return "gcp_service_account" in st.secrets and "history_sheet_id" in st.secrets
    except Exception:
        return False


def load_history():
    try:
        if _use_sheet():
            vals = _get_worksheet().col_values(1)
            return [v.strip() for v in vals if v.strip()][:MAX_HISTORY]
        if LOCAL_FILE.exists():
            return json.loads(LOCAL_FILE.read_text(encoding="utf-8"))[:MAX_HISTORY]
    except Exception as e:
        st.session_state["history_err"] = f"讀取歷史失敗: {e}"
    return []


def save_history(hist):
    try:
        if _use_sheet():
            ws = _get_worksheet()
            ws.clear()
            ws.update(values=[[t] for t in hist], range_name="A1")
        else:
            LOCAL_FILE.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        st.session_state["history_err"] = f"儲存歷史失敗: {e}"


# --- quarry 分頁：每個代號一列 (格式同 backtest.py 的輸出) ---
def calc_full_cagr(df):
    """全部歷史的 CAGR (依日期天數 / 365.25)，同 backtest.py"""
    if df is None or len(df) < 2:
        return None, None
    start_price, end_price = df['Close'].iloc[0], df['Close'].iloc[-1]
    n_years = (df.index[-1] - df.index[0]).days / 365.25
    if n_years <= 0 or start_price <= 0:
        return None, None
    return (end_price / start_price) ** (1 / n_years) - 1, n_years


def calc_10y_cagr(df):
    """近 10 年 CAGR；資料不足 10 年時由呼叫端改用全部 CAGR"""
    if df is None or len(df) < 2:
        return None
    cutoff = df.index[-1] - timedelta(days=3652)
    d = df[df.index >= cutoff]
    if len(d) < 2:
        return None
    start_price, end_price = d['Close'].iloc[0], d['Close'].iloc[-1]
    n_years = (d.index[-1] - d.index[0]).days / 365.25
    if n_years <= 0 or start_price <= 0:
        return None
    return (end_price / start_price) ** (1 / n_years) - 1


def guess_category(ticker):
    if ticker.endswith(".TWO"):
        return "tpex"
    if "." not in ticker:
        return "us"
    return "twse"


def upsert_quarry(ws, ticker, name, category, industry, years, cagr, cagr10):
    """代號已存在 → 只更新 總年數/CAGR/近10年CAGR (E:G)；不存在 → 新增一列"""
    if not ws.get_all_values():
        ws.append_row(QUERY_HEADER)
    values = [round(float(years), 2) if years else "N/A",
              round(float(cagr), 4) if cagr is not None else "N/A",
              round(float(cagr10), 4) if cagr10 is not None else "N/A"]
    codes = ws.col_values(1)
    if ticker in codes:
        r = codes.index(ticker) + 1
        ws.update(values=[values], range_name=f"E{r}:G{r}")
        return "updated"
    ws.append_row([ticker, name, category, industry] + values)
    return "added"


def sync_quarry(df, ticker, name, industry):
    if not _use_sheet():
        return
    cagr, years = calc_full_cagr(df)
    cagr10 = calc_10y_cagr(df)
    if cagr10 is None:
        cagr10 = cagr
    sid = st.secrets.get("QUERY_sheet_id", st.secrets["history_sheet_id"])
    ws = _get_tab(_get_spreadsheet(sid), QUERY_SHEET_NAME, len(QUERY_HEADER))
    upsert_quarry(ws, ticker, name, guess_category(ticker), industry, years, cagr, cagr10)


# --- session_state 初始化 (每個連線載入一次) ---
if "history" not in st.session_state:
    st.session_state.history = load_history()   # 最新在前，最多 15 筆

# 注入 CSS：美化輸入框與強制文字不換行
st.markdown("""
    <style>
    div[data-baseweb="input"], div[data-baseweb="select"] > div {
        border: 2px solid #ff4b4b !important;
        border-radius: 10px !important;
    }
    .mobile-font-fix {
        white-space: nowrap !important;
        overflow: hidden;
        text-overflow: clip;
        font-size: clamp(16px, 4.5vw, 32px) !important;
        font-weight: 800;
    }
    </style>
""", unsafe_allow_html=True)

plotly_config = {
    'scrollZoom': False,
    'displayModeBar': False,
    'showAxisDragHandles': False,
    'staticPlot': False,
    'doubleClick': False,
}

st.title("📈 股票報酬率回測")

# --- 輸入區域 ---
st.markdown("### 🔍 股票代號查詢")
col_input, col_years = st.columns([3, 1])

def _pick_history():
    # 舊版 Streamlit 的備援：選歷史代號後填入文字框
    pick = st.session_state.get("hist_pick")
    if pick:
        st.session_state["stock_input_txt"] = pick


with col_input:
    try:
        # 新版：selectbox + accept_new_options，點擊顯示歷史清單，也可直接打字輸入新代號
        raw_value = st.selectbox(
            "股票代號",
            options=st.session_state.history,
            index=None,
            placeholder="輸入代號 (如 NVDA, 2330.TW) 或點擊選擇歷史查詢",
            accept_new_options=True,
            label_visibility="collapsed",
            key="stock_input",
        )
    except TypeError:
        # 舊版 Streamlit (不支援 accept_new_value)：文字框 + 歷史查詢下拉
        raw_value = st.text_input(
            "股票代號",
            placeholder="輸入代號 (如 NVDA, 2330.TW)",
            label_visibility="collapsed",
            key="stock_input_txt",
        )
        st.selectbox(
            "歷史查詢",
            options=st.session_state.history,
            index=None,
            placeholder="歷史查詢 (點選自動填入)",
            label_visibility="collapsed",
            key="hist_pick",
            on_change=_pick_history,
        )

with col_years:
    # 用 key 綁定 session_state，選過之後後續查詢都沿用
    years_label = st.selectbox(
        "查詢年數",
        options=list(YEAR_OPTIONS.keys()),
        index=list(YEAR_OPTIONS.keys()).index("全部"),
        key="years_option",
    )
years_limit = YEAR_OPTIONS[years_label]
if st.session_state.get("history_err"):
    st.caption(f"⚠️ {st.session_state['history_err']}")

raw_input = (raw_value or "").strip()

# 如果輸入全是數字 (例如 2542)，自動補上 .TW
if raw_input.isdigit():
    ticker_symbol = f"{raw_input}.TW"
else:
    ticker_symbol = raw_input.upper()

if ticker_symbol:
    with st.spinner(f"正在從 Yahoo Finance 載入 {ticker_symbol} 市場資料..."):
        df, display_name, industry_name = get_stock_data(ticker_symbol)

    if df.empty:
        st.error("找不到資料")   # 錯誤代號不寫入歷史
    else:
        # 正確代號 → 移到歷史最前面 (去重、最多 15 筆)，有變動就重跑一次讓下拉清單立即更新
        hist = st.session_state.history
        if not hist or hist[0] != ticker_symbol:
            # 先讀最新的儲存內容再合併，避免手機與電腦同時使用時互相覆蓋
            base = load_history() or hist
            new_hist = ([ticker_symbol] + [t for t in base if t != ticker_symbol])[:MAX_HISTORY]
            save_history(new_hist)
            st.session_state.history = new_hist
            st.rerun()

        df.index = pd.to_datetime(df.index)

        # 寫入 quarry 分頁 (同一連線內每個代號只同步一次，避免切換年數時重複寫入)
        synced = st.session_state.setdefault("QUERY_synced", set())
        if ticker_symbol not in synced:
            try:
                sync_quarry(df[['Close']].dropna(), ticker_symbol, display_name, industry_name)
                synced.add(ticker_symbol)
            except Exception as e:
                st.caption(f"⚠️ 寫入 {QUERY_SHEET_NAME} 失敗: {e}")

        # 計算每一年的報酬率 (跨年定義)
        annual_df = df['Close'].resample('YE').last().to_frame()
        annual_df['Return'] = annual_df['Close'].pct_change()
        res_full = annual_df.dropna()   # 第一年沒有「去年」可比，已排除

        # 依查詢年數取最近 N 年
        if years_limit is None:
            res_df = res_full.copy()
        else:
            res_df = res_full.tail(years_limit).copy()
            if len(res_full) < years_limit:
                st.caption(f"ℹ️ {ticker_symbol} 只有 {len(res_full)} 年資料，不足 {years_limit} 年，已顯示全部。")

        first_idx = res_df.index[0]
        res_df = res_df.reset_index()
        res_df.columns = ['Date', 'Close', 'Return']
        res_df['Year'] = res_df['Date'].dt.year

        step = 0.1
        total_years = len(res_df)

        # 年化報酬率 (CAGR)，區間與所選年數一致
        clean_close = df['Close'].dropna()
        if years_limit is None:
            initial_price = clean_close.iloc[0]
            period_close = clean_close
        else:
            # 起點 = 第一個所選年度的「前一年年底」收盤價
            pos = annual_df.index.get_loc(first_idx)
            base_label = annual_df.index[pos - 1]
            initial_price = annual_df['Close'].iloc[pos - 1]
            period_close = clean_close[clean_close.index > base_label]
        final_price = clean_close.iloc[-1]
        n_years = len(period_close) / 52
        cagr = (final_price / initial_price) ** (1 / n_years) - 1 if n_years > 0 else 0

        # ------------------------------
        # 輸出結果
        # ------------------------------
        st.markdown(
            f"""
            <div style="background-color:#ffffff; padding:20px; border-radius:12px; border: 1px solid #e0e0e0; border-left: 8px solid #ff4b4b;">
                <div style="font-size:14px; color:#444444; margin-bottom:5px; font-weight:500;">{display_name}</div>
                <div class="mobile-font-fix" style="color:#1a1a1a;">
                    共 {total_years} 年, 年化報酬率 <span style="color:#d93025; font-weight:bold;">{cagr:.1%}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # 每年報酬率柱狀圖
        st.subheader(f"每年報酬率柱狀圖 - {display_name}")
        res_df['Color'] = res_df['Return'].apply(lambda x: 'red' if x > 0 else 'green')
        res_df['Text_Int'] = res_df['Return'].apply(lambda x: f"{int(round(x * 100, 0))}%")

        fig1 = go.Figure(data=[
            go.Bar(
                x=res_df['Year'],
                y=res_df['Return'],
                marker_color=res_df['Color'],
                text=res_df['Text_Int'],
                textposition='auto',
                hovertemplate="年份: %{x}<br>報酬率: %{y:.2%}<extra></extra>"
            )
        ])
        fig1.update_layout(
            font=dict(size=10),
            yaxis=dict(tickformat='.0%', fixedrange=True),
            xaxis=dict(fixedrange=True),
            template="plotly_white",
            margin=dict(l=10, r=10, t=30, b=10)
        )
        fig1.add_hline(y=0, line_width=1, line_color="black")
        fig1 = apply_mobile_layout(fig1)
        st.plotly_chart(fig1, width='stretch', config=plotly_config)

        # 報酬率分佈柱狀圖 (含邊界合併邏輯)
        st.subheader(f"報酬率分佈 {ticker_symbol}")

        def categorize_bin(x, step):
            if x <= -0.8:
                return -999, "<-80%"
            elif x >= 0.8:
                return 999, ">80%"
            else:
                bin_start = math.floor(round(x, 4) / step) * step
                return bin_start, f"{bin_start:.0%} ~ {bin_start + step:.0%}"

        res_df[['bin_sort', 'Bin_Label']] = res_df['Return'].apply(
            lambda x: pd.Series(categorize_bin(x, step))
        )
        dist_df = res_df.groupby(['bin_sort', 'Bin_Label']).size().reset_index(name='Counts')
        dist_df = dist_df.sort_values('bin_sort')
        dist_df['Color'] = dist_df['bin_sort'].apply(lambda x: '#ff4b4b' if x >= 0 else '#00873c')

        fig2 = go.Figure(data=[
            go.Bar(
                x=dist_df['Bin_Label'],
                y=dist_df['Counts'],
                text=dist_df['Counts'],
                textposition='outside',
                marker_color=dist_df['Color']
            )
        ])
        fig2.update_layout(
            xaxis_title='報酬率區間',
            yaxis_title='出現次數 (年)',
            xaxis={'type': 'category', 'categoryorder': 'array', 'categoryarray': dist_df['Bin_Label'].tolist()},
            template="plotly_white"
        )
        fig2 = apply_mobile_layout(fig2)
        st.plotly_chart(fig2, width='stretch', config=plotly_config)