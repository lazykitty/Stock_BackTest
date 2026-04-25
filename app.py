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


# 設定網頁標題
st.set_page_config(page_title="股票回測工具", layout="wide")
st.title("📈 股票報酬率回測")

# 1. USER 輸入股票代號
raw_input = st.text_input("請輸入股票代號 (例如: AAPL, 2330.TW)", "NVDA").strip()

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
            
            # 如果 全期間最大價差 > 150%, 則用 20%, 否則 10%
            step = 0.2 if ret_range > 1.5 else 0.1
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
            # 修改為僅顯示整數百分比
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

            fig1.update_layout(
                yaxis_tickformat='.0%',
                xaxis_title="年份",
                yaxis_title="報酬率",
                template="plotly_white",
                height=500
            )
            fig1.add_hline(y=0, line_width=1, line_color="black")
            st.plotly_chart(fig1, width='stretch')

            # 4-2. 文字方塊
            st.markdown(
                        f"""
                        <div style="background-color:#f0f2f6; padding:20px; border-radius:10px; border-left: 5px solid #4585f4;">
                            <p style="font-size:24px; font-weight:bold; margin:0; color:#31333F;">
                                共 {total_years} 年, 年化平均報酬率 = {cagr:.1%}
                            </p>
                        </div>
                        """, 
                        unsafe_allow_html=True
                        )

            # --- 3. 報酬率分佈柱狀圖 (含邊界合併邏輯) ---
            st.subheader("報酬率分佈")
            def categorize_bin(x, step):
                # 邊界合併邏輯
                if x <= -1.0:
                    return -999, "<-100%"
                elif x >= 1.0:
                    return 999, ">100%"
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

            fig2 = px.bar(
            dist_df, 
            x='Bin_Label', 
            y='Counts', 
            text='Counts',
            labels={'Bin_Label': '報酬率區間', 'Counts': '出現次數 (年)'},
            category_orders={"Bin_Label": dist_df['Bin_Label'].tolist()} # 強制依照排序後的標籤顯示
            )

            fig2.update_traces(marker_color='#4A90E2', textposition='outside')
            fig2.update_layout(
                template="plotly_white", 
                height=450,
                xaxis={'type': 'category'} # 確保 X 軸視為類別型資料而非數值軸
            )
            st.plotly_chart(fig2, use_container_width=True)

