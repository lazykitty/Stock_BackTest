import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import math

# 設定網頁標題
st.set_page_config(page_title="股票回測工具", layout="wide")
st.title("📈 股票報酬率回測")

# 1. USER 輸入股票代號
ticker_symbol = st.text_input("請輸入股票代號 (例如: AAPL, 2330.TW)", "AAPL").strip()

if ticker_symbol:
    try:
        # 2. 由 YF 取得全部周K，使用還原值 (auto_adjust=True)
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period="max", interval="1wk")

        if df.empty:
            st.error("找不到該股票資料，請檢查代號是否正確。")
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
            
            # 計算總年數與年化平均報酬率 (CAGR)
            total_years = len(res_df)
            initial_price = df['Close'].iloc[0]
            final_price = df['Close'].iloc[-1]
            cagr = (final_price / initial_price) ** (1 / total_years) - 1 if total_years > 0 else 0

            # 4. 輸出結果
            
            # 4-1. 每年報酬率柱狀圖
            st.subheader("每年報酬率柱狀圖")
            
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
            st.code(f"共 {total_years} 年, 年化平均報酬率 = {cagr:.1%}")

            # 4-3. 報酬率分佈柱狀圖
            st.subheader("報酬率分佈")
            
            # 每 10% 為一個區間
            res_df['Bin_Start'] = res_df['Return'].apply(lambda x: math.floor(x * 10) / 10)
            dist_df = res_df.groupby('Bin_Start').size().reset_index(name='Counts')
            dist_df['Bin_Label'] = dist_df['Bin_Start'].apply(lambda x: f"{x:.0%} ~ {x+0.1:.0%}")
            dist_df = dist_df.sort_values('Bin_Start')

            fig2 = px.bar(
                dist_df, 
                x='Bin_Label', 
                y='Counts',
                text='Counts',
                labels={'Bin_Label': '報酬率區間', 'Counts': '出現次數 (年)'}
            )
            fig2.update_traces(marker_color='#4A90E2', textposition='outside')
            fig2.update_layout(template="plotly_white", height=400)
            
            st.plotly_chart(fig2, use_container_width=True)

    except Exception as e:
        st.error(f"發生錯誤: {e}")