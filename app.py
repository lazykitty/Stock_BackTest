import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import math

@st.cache_data(ttl=18640)
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    # 抓取歷史週K
    df = stock.history(period="max", interval="1wk", auto_adjust=True)
    
    # 抓取股名
    try:
        s_info = stock.info
        name = s_info.get('longName') or s_info.get('shortName') or ticker
    except:
        name = ticker
        
    return df, name

# --- 2. 在 update_layout 中鎖定座標軸 ---
def apply_mobile_layout(fig):
    fig.update_layout(
        # 鎖定 X 軸與 Y 軸，防止任何形式的縮放或位移
        xaxis=dict(fixedrange=True), 
        yaxis=dict(fixedrange=True),
        # 禁用點擊選擇與框選
        dragmode=False,
        # 手機端邊距優化
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified", # 讓手指比較好點到資料點
    )
    return fig

# 1. 注入 CSS：美化輸入框與強制文字不換行
st.markdown("""
    <style>
    /* 輸入框美化 */
    div[data-baseweb="input"] {
        border: 2px solid #ff4b4b !important;
        border-radius: 10px !important;
    }
    
    /* 強制標題與大文字方塊不換行，並根據寬度縮小字體 */
    .mobile-font-fix {
        white-space: nowrap !important;
        overflow: hidden;
        text-overflow: clip;
        font-size: clamp(16px, 4.5vw, 32px) !important;
        font-weight: 800;
    }
    .mobile-box {
    background-color: #ffffff !important; /* 改為純白底色 */
    padding: 20px !important;
    margin: 10px 0 !important;
    border: 1px solid #e0e0e0 !important; /* 加上淡灰色邊框增加層次感 */
    border-left: 8px solid #ff4b4b !important; /* 保留你喜歡的紅色粗邊 */
    box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important; /* 加上微弱陰影，讓它跳脫背景 */
    }
    </style>
""", unsafe_allow_html=True)

# 2. 設定 Plotly 禁用縮放配置
plotly_config = {
    'scrollZoom': False,          # 禁用滾動縮放
    'displayModeBar': False,      # 隱藏工具列
    'showAxisDragHandles': False, # 隱藏座標軸拖拽手把
    'staticPlot': False,          # 若設為 True 會連 Hover 都沒了，所以維持 False
    'doubleClick': False,         # 【修正】完全禁用連擊重設功能
}


# 設定網頁標題
st.set_page_config(page_title="股票回測工具", layout="wide")
st.title("📈 股票報酬率回測")

# 3. 輸入區域
st.markdown("### 🔍 股票代號查詢")
raw_input = st.text_input(
    label="股票代號", 
    label_visibility="collapsed", 
    placeholder="輸入代號 (如 NVDA, 2330.TW)", 
    key="stock_input"
).strip()

# --- 優化輸入邏輯 ---
# 如果輸入全是數字 (例如 2542)，自動補上 .TW
if raw_input.isdigit():
    ticker_symbol = f"{raw_input}.TW"
    #print(f"偵測到純數字輸入，自動修正為: {ticker_symbol}")
else:
    ticker_symbol = raw_input.upper() # 確保代號是大寫 (如 aapl -> AAPL)

if ticker_symbol:
    with st.spinner(f"正在從 Yahoo Finance 載入 {ticker_symbol} 市場資料..."):
        df, display_name = get_stock_data(ticker_symbol) # 2. 由 YF 取得全部周K，使用還原值 (auto_adjust=True)
        
        if df.empty:
            st.error("找不到資料")
        else:
            df.index = pd.to_datetime(df.index)
            
            # 3. 計算每一年的報酬率
            years = df.groupby(df.index.year)
            yearly_data = []
            
            for year, data in years:
                if len(data) < 2: continue 
                
                # 定義：(年尾最後一周CLOSE - 年初第一周CLOSE) / 年初第一周CLOSE
                first_close = data['Close'].iloc[0]
                last_close = data['Close'].iloc[-1]
                return_rate = (last_close - first_close) / first_close
                yearly_data.append({'Year': year, 'Return': return_rate})
            
            res_df = pd.DataFrame(yearly_data)
            # --- 動態間距判斷 (修正需求) ---
            ret_min = res_df['Return'].min()
            ret_max = res_df['Return'].max()
            ret_range = ret_max - ret_min
            
            # 如果 全期間最大價差 > 100%, 則用 20%, 否則 10%
            step = 0.2 if ret_range > 1.0 else 0.1
            st.write(f"💡 偵測波動幅度：{ret_range:.1%}，自動採用 {step:.0%} 間距統計")

            
            # 計算總年數與年化平均報酬率 (CAGR)
            total_years = len(res_df)
            initial_price = df['Close'].iloc[0]
            final_price = df['Close'].iloc[-1]
            cagr = (final_price / initial_price) ** (1 / total_years) - 1 if total_years > 0 else 0

            # 4. 輸出結果
            
            # 4-1. 每年報酬率柱狀圖
            st.subheader(f"每年報酬率柱狀圖 - {display_name}")            
            res_df['Color'] = res_df['Return'].apply(lambda x: 'red' if x > 0 else 'green')
            res_df['Text_Int'] = res_df['Return'].apply(lambda x: f"{int(round(x * 100, 0))}%")

            fig1 = go.Figure(data=[
                go.Bar(
                    x=res_df['Year'],
                    y=res_df['Return'],
                    marker_color=res_df['Color'],
                    text=res_df['Text_Int'], # 使用整數標籤
                    textposition='auto',
                    hovertemplate="年份: %{x}<br>報酬率: %{y:.2%}<extra></extra>"
                )
            ])

            # 針對手機端微調字體大小
            fig1.update_layout(
                font=dict(size=10), # 全域字體縮小
                xaxis=dict(tickfont=dict(size=9)), 
                yaxis=dict(tickfont=dict(size=9)),
                margin=dict(l=10, r=10, t=30, b=10) # 緊湊邊距
            )
            fig1.add_hline(y=0, line_width=1, line_color="black")
            if 'fig1' in locals():
                fig1 = apply_mobile_layout(fig1)
                #st.plotly_chart(fig1, use_container_width=True, config=plotly_config)
            st.plotly_chart(fig1, width='stretch', config=plotly_config)
            
            # 4. 放大版文字方塊 (手機適配版)
            st.markdown(
                f"""
                <div style="background-color:#ffffff; padding:20px; border-radius:12px; border-left: 8px solid #ff4b4b; border: 1px solid #e0e0e0; border-left: 8px solid #ff4b4b;">
                    <div style="font-size:14px; color:#444444; margin-bottom:5px; font-weight:500;">{display_name}</div>
                    <div class="mobile-font-fix" style="color:#1a1a1a;">
                        共 {total_years} 年, 年化報酬率 <span style="color:#d93025; font-weight:bold;">{cagr:.1%}</span>
                    </div>
                </div>
                """, 
                unsafe_allow_html=True
            )

            # --- 3. 報酬率分佈柱狀圖 (含邊界合併邏輯) ---
            st.subheader("報酬率分佈")
            def categorize_bin(x, step):
                # 邊界合併邏輯
                if x <= -0.8:
                    return -999, "<-80%"
                elif x >= 0.8:
                    return 999, ">80%"
                else:
                    # 正常區間計算
                    bin_start = math.floor(round(x, 4) / step) * step
                    return bin_start, f"{bin_start:.0%} ~ {bin_start + step:.0%}"

            # 套用分類邏輯，產生排序值與標籤
            res_df[['bin_sort', 'Bin_Label']] = res_df['Return'].apply(
                lambda x: pd.Series(categorize_bin(x, step))
            ) 
            # 統計各區間次數
            dist_df = res_df.groupby(['bin_sort', 'Bin_Label']).size().reset_index(name='Counts')
            # 依照 bin_sort 排序，確保 <-100% 在最左，>100% 在最右
            dist_df = dist_df.sort_values('bin_sort')          
            # 根據區間起點判斷顏色：大於等於 0 為紅，小於 0 為綠
            dist_df['Color'] = dist_df['bin_sort'].apply(lambda x: '#ff4b4b' if x >= 0 else '#00873c')

            #st.write("檢查統計表：", dist_df[['Bin_Label', 'bin_sort', 'Color']])

            fig2 = go.Figure(data=[
                go.Bar(
                    x=dist_df['Bin_Label'],
                    y=dist_df['Counts'],
                    text=dist_df['Counts'],
                    textposition='outside',
                    marker_color=dist_df['Color'] # 直接將顏色陣列傳入
                )
            ])

            fig2.update_layout(
                xaxis_title='報酬率區間',
                yaxis_title='出現次數 (年)',
                xaxis={'type': 'category', 'categoryorder': 'array', 'categoryarray': dist_df['Bin_Label'].tolist()},
                template="plotly_white"
            )

            if 'fig2' in locals():
                fig2 = apply_mobile_layout(fig2)
            st.plotly_chart(fig2, width='stretch', config=plotly_config)

