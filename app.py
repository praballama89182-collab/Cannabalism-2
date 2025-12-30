import streamlit as st
import pandas as pd
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Prabal Ecommerce Analyzer",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    h1, h2, h3 { color: #232f3e; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
    </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def normalize_match_type(val):
    if pd.isna(val): return 'UNKNOWN'
    val = str(val).upper()
    if 'EXACT' in val: return 'EXACT'
    if 'PHRASE' in val: return 'PHRASE'
    if 'BROAD' in val: return 'BROAD'
    return 'AUTO/OTHER'

def determine_winner(group, improvement_thresh, min_orders):
    max_sales_idx = group['sales_val'].idxmax()
    sales_leader = group.loc[max_sales_idx]
    
    max_roas_idx = group['calculated_roas'].idxmax()
    roas_leader = group.loc[max_roas_idx]
    
    if max_sales_idx == max_roas_idx:
        return max_sales_idx, "Best Sales & ROAS"
    
    roas_sales = sales_leader['calculated_roas']
    roas_challenger = roas_leader['calculated_roas']
    
    improvement = (roas_challenger - roas_sales) / roas_sales if roas_sales > 0 else 999
    
    if (improvement >= (improvement_thresh / 100.0)) and (roas_leader['orders_val'] >= min_orders):
        return max_roas_idx, f"Efficient (ROAS +{improvement:.0%})"
    else:
        return max_sales_idx, "Volume Leader"

def generate_ngrams(text, n):
    words = str(text).lower().split()
    if len(words) < n:
        return []
    return [' '.join(words[i:i+n]) for i in range(len(words)-n+1)]

def process_ngrams(df, n_value):
    ngram_data = []
    for _, row in df.iterrows():
        term = row['Search Term']
        grams = generate_ngrams(term, n_value)
        for gram in grams:
            ngram_data.append({
                'N-Gram': gram,
                'Spend': row['Spend'],
                'Sales': row['Sales'],
                'Orders': row['Orders'],
                'Clicks': row['Clicks']
            })
            
    if not ngram_data:
        return pd.DataFrame()
        
    ng_df = pd.DataFrame(ngram_data)
    ng_agg = ng_df.groupby('N-Gram', as_index=False).sum()
    
    # Calculate Metrics
    ng_agg['ROAS'] = ng_agg.apply(lambda x: x['Sales']/x['Spend'] if x['Spend'] > 0 else 0, axis=1)
    ng_agg['CPC'] = ng_agg.apply(lambda x: x['Spend']/x['Clicks'] if x['Clicks'] > 0 else 0, axis=1)
    ng_agg['ACOS'] = ng_agg.apply(lambda x: (x['Spend']/x['Sales'])*100 if x['Sales'] > 0 else 0, axis=1)
    ng_agg['Count'] = ng_df.groupby('N-Gram').size().values 
    
    return ng_agg.sort_values(by='Spend', ascending=False)

def to_excel(dfs):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in dfs.items():
            if not df.empty:
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False) 
    return output.getvalue()

# --- MAIN APP ---

def main():
    with st.sidebar:
        st.title("🛒 Prabal Ecommerce Analyzer")
        st.markdown("---")
        
        # 1. File Upload
        st.subheader("1. Data Source")
        uploaded_file = st.file_uploader("Upload Search Term Report", type=["csv", "xlsx"])
        
        df = None
        
        # 2. Portfolio Filter
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_raw = pd.read_csv(uploaded_file)
                else:
                    df_raw = pd.read_excel(uploaded_file)
                
                df_raw.columns = df_raw.columns.str.strip()
                
                port_col = next((c for c in df_raw.columns if 'Portfolio' in c), None)
                
                if port_col:
                    st.subheader("2. Filter Data")
                    all_portfolios = df_raw[port_col].dropna().unique().tolist()
                    selected_ports = st.multiselect("Select Portfolios", options=all_portfolios, default=all_portfolios)
                    
                    if selected_ports:
                        df = df_raw[df_raw[port_col].isin(selected_ports)].copy()
                    else:
                        df = df_raw.copy()
                else:
                    df = df_raw.copy()
                    st.info("No 'Portfolio' column found. Showing all data.")

            except Exception as e:
                st.error(f"Error reading file: {e}")
        
        # 3. Settings
        if df is not None:
            st.markdown("---")
            st.subheader("3. Analysis Thresholds")
            
            with st.expander("⚔️ Cannibalization Rules", expanded=False):
                roas_threshold = st.slider("Better ROAS Threshold (%)", 30, 200, 100, 10)
                min_orders_cannibal = st.number_input("Min Orders to Win", 1, 10, 2)
                
            with st.expander("🌾 Harvesting Rules", expanded=True):
                min_orders_harvest = st.number_input("Min Orders", 1, 10, 2, help="Strictly > 1 means set this to 2")
                min_roas_harvest = st.number_input("Min ROAS", 0.1, 10.0, 1.0, 0.1)
                
            with st.expander("💰 CPC Analyzer", expanded=False):
                top_n_terms = st.slider("Analyze Top N Terms", 10, 100, 50)
                bad_roas_limit = st.number_input("Low ROAS Flag (<)", 0.1, 5.0, 1.0, 0.1)

    # --- MAIN CONTENT ---
    if df is not None:
        try:
            # Column Mapping
            col_map = {
                'date': next((c for c in df.columns if 'Date' in c), None),
                'term': next((c for c in df.columns if 'Matched product' in c or 'Customer Search Term' in c), None),
                'camp': next((c for c in df.columns if 'Campaign Name' in c), None),
                'adg': next((c for c in df.columns if 'Ad Group Name' in c), None),
                'match': next((c for c in df.columns if 'Match Type' in c), None),
                'orders': next((c for c in df.columns if 'Orders' in c or 'Units' in c), None),
                'sales': next((c for c in df.columns if 'Sales' in c), None),
                'spend': next((c for c in df.columns if 'Spend' in c), None),
                'clicks': next((c for c in df.columns if 'Clicks' in c), None),
                'impressions': next((c for c in df.columns if 'Impressions' in c), None)
            }

            if any(v is None for v in ['term', 'camp', 'adg', 'spend', 'sales']):
                st.error(f"Missing essential columns. Please check your file headers. Found: {col_map}")
            else:
                # Cleanup Numeric
                num_cols = ['orders', 'sales', 'spend', 'clicks', 'impressions']
                for c in num_cols:
                    if col_map[c]:
                        df[col_map[c]] = pd.to_numeric(df[col_map[c]], errors='coerce').fillna(0)
                
                df['norm_match'] = df[col_map['match']].apply(normalize_match_type)
                if col_map['date']:
                    df['Date'] = pd.to_datetime(df[col_map['date']], errors='coerce')
                    df['DayOfWeek'] = df['Date'].dt.day_name()

                # --- AGGREGATION ---
                agg_cols = [col_map['term'], col_map['camp'], col_map['adg'], 'norm_match']
                df_agg = df.groupby(agg_cols, as_index=False).agg({
                    col_map['spend']: 'sum',
                    col_map['sales']: 'sum',
                    col_map['orders']: 'sum',
                    col_map['clicks']: 'sum',
                    col_map['impressions']: 'sum'
                })
                
                df_agg.rename(columns={
                    col_map['term']: 'Search Term',
                    col_map['camp']: 'Campaign',
                    col_map['adg']: 'Ad Group',
                    col_map['orders']: 'Orders',
                    col_map['sales']: 'Sales',
                    col_map['spend']: 'Spend',
                    col_map['clicks']: 'Clicks',
                    col_map['impressions']: 'Impressions'
                }, inplace=True)
                
                df_agg['ROAS'] = df_agg.apply(lambda x: x['Sales']/x['Spend'] if x['Spend'] > 0 else 0, axis=1)
                df_agg['CPC'] = df_agg.apply(lambda x: x['Spend']/x['Clicks'] if x['Clicks'] > 0 else 0, axis=1)
                df_agg['ACOS'] = df_agg.apply(lambda x: (x['Spend']/x['Sales'])*100 if x['Sales'] > 0 else 0, axis=1)

                # Rounding 1 Decimal
                for col in ['Spend', 'Sales', 'ROAS', 'CPC', 'ACOS']:
                    df_agg[col] = df_agg[col].round(1)

                existing_exact = set(df_agg[df_agg['norm_match'] == 'EXACT']['Search Term'].str.lower().unique())

                # --- HEADER ---
                st.title("Prabal Ecommerce Analyzer")
                st.markdown(f"**Analyzing File:** `{uploaded_file.name}`")
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Spend", f"₹{df_agg['Spend'].sum():,.1f}")
                c2.metric("Total Sales", f"₹{df_agg['Sales'].sum():,.1f}")
                
                total_spend = df_agg['Spend'].sum()
                total_sales = df_agg['Sales'].sum()
                account_roas = total_sales / total_spend if total_spend > 0 else 0
                c3.metric("Account ROAS", f"{account_roas:.1f}")
                c4.metric("Unique Search Terms", f"{df_agg['Search Term'].nunique():,}")

                # --- TABS ---
                tabs = st.tabs(["⚔️ Cannibalization", "🌾 Harvesting", "💰 CPC Analyzer", "📅 Best Days", "💸 Wasted Spend", "🔠 N-Gram Analysis"])

                # TAB 1: CANNIBALIZATION
                with tabs[0]:
                    st.subheader("Detect & Fix Self-Competition")
                    sales_df = df_agg[df_agg['Orders'] > 0].copy()
                    dupe_counts = sales_df.groupby('Search Term').size()
                    cannibal_list = dupe_counts[dupe_counts > 1].index.tolist()
                    
                    st.info(f"**Common Search Terms Found:** {len(cannibal_list)} (Terms appearing in >1 Ad Group with Sales)")

                    cannibal_results = []
                    if cannibal_list:
                        for term in cannibal_list:
                            subset = sales_df[sales_df['Search Term'] == term].rename(columns={'Sales': 'sales_val', 'Spend': 'spend_val', 'ROAS': 'calculated_roas', 'Orders': 'orders_val'}).copy()
                            win_idx, _ = determine_winner(subset, roas_threshold, min_orders_cannibal) 
                            for idx, row in subset.iterrows():
                                is_winner = (idx == win_idx)
                                cannibal_results.append({
                                    'Search Term': term, 'Campaign': row['Campaign'], 'Ad Group': row['Ad Group'],
                                    'CPC': row['CPC'], 'Spend': row['spend_val'], 'Sales': row['sales_val'], 
                                    'Orders': row['orders_val'], 'ROAS': row['calculated_roas'], 
                                    'Action': "✅ KEEP" if is_winner else "⛔ NEGATE"
                                })
                        
                        df_cannibal = pd.DataFrame(cannibal_results)
                        for c in ['Spend', 'Sales', 'ROAS', 'CPC']: df_cannibal[c] = df_cannibal[c].round(1)
                        st.dataframe(df_cannibal.style.apply(lambda x: ['background-color: #ffebee' if 'NEGATE' in str(v) else '' for v in x], axis=1), use_container_width=True)
                    else:
                        st.success("No cannibalization found.")
                        df_cannibal = pd.DataFrame()

                # TAB 2: HARVESTING
                with tabs[1]:
                    st.subheader("Strict Growth Opportunities")
                    st.caption(f"Criteria: Orders >= {min_orders_harvest} AND ROAS >= {min_roas_harvest}")
                    candidates = df_agg[(df_agg['norm_match'] != 'EXACT') & (df_agg['Orders'] >= min_orders_harvest) & (df_agg['ROAS'] >= min_roas_harvest)].copy()
                    
                    harvest_results = []
                    for idx, row in candidates.iterrows():
                        if row['Search Term'].lower() not in existing_exact:
                            harvest_results.append({
                                'Search Term': row['Search Term'], 'Rec Type': '🚀 NEW EXACT', 
                                'Source Campaign': row['Campaign'], 'Source Ad Group': row['Ad Group'],
                                'Orders': row['Orders'], 'Sales': row['Sales'], 'ROAS': row['ROAS'], 'CPC': row['CPC']
                            })
                    
                    df_harvest = pd.DataFrame(harvest_results)
                    if not df_harvest.empty:
                        for c in ['Sales', 'ROAS', 'CPC']: df_harvest[c] = df_harvest[c].round(1)
                        st.dataframe(df_harvest.sort_values(by='Sales', ascending=False), use_container_width=True)
                    else:
                        st.info("No terms met criteria.")
                        df_harvest = pd.DataFrame()

                # TAB 3: CPC ANALYZER
                with tabs[2]:
                    st.subheader(f"Top {top_n_terms} Terms: CPC & Performance")
                    top_terms = df_agg.groupby('Search Term')['Spend'].sum().nlargest(top_n_terms).index.tolist()
                    df_top = df_agg[df_agg['Search Term'].isin(top_terms)].copy()
                    
                    cpc_results = []
                    for term in top_terms:
                        subset = df_top[df_top['Search Term'] == term]
                        avg_cpc = subset['CPC'].mean()
                        for idx, row in subset.iterrows():
                            rec = "✅ Healthy"
                            if row['ROAS'] < bad_roas_limit: rec = "⚠️ Low ROAS"
                            elif row['CPC'] > (avg_cpc * 1.3): rec = "⚠️ High CPC"
                            cpc_results.append({
                                'Search Term': term, 'Campaign': row['Campaign'], 'Match': row['norm_match'],
                                'Spend': row['Spend'], 'Sales': row['Sales'], 'CPC': row['CPC'], 'ROAS': row['ROAS'], 'Rec': rec
                            })
                    
                    df_cpc = pd.DataFrame(cpc_results)
                    for c in ['Spend', 'Sales', 'CPC', 'ROAS']: df_cpc[c] = df_cpc[c].round(1)
                    
                    def highlight_high_cpc(row):
                        if 'High CPC' in row['Rec'] or 'Low ROAS' in row['Rec']: return ['color: #d32f2f; font-weight: bold'] * len(row)
                        return [''] * len(row)
                    st.dataframe(df_cpc.style.apply(highlight_high_cpc, axis=1).format({'CPC': '{:.1f}', 'ROAS': '{:.1f}', 'Spend': '{:.1f}', 'Sales': '{:.1f}'}), use_container_width=True)

                # TAB 4: BEST DAYS
                with tabs[3]:
                    st.subheader("📅 Day Parting Performance")
                    if col_map['date']:
                        day_agg = df.groupby(df['Date'].dt.day_name()).agg({col_map['spend']: 'sum', col_map['sales']: 'sum', col_map['orders']: 'sum'}).reindex(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])
                        day_agg['ROAS'] = day_agg.apply(lambda x: x[col_map['sales']]/x[col_map['spend']] if x[col_map['spend']]>0 else 0, axis=1)
                        day_agg['ACOS'] = day_agg.apply(lambda x: (x[col_map['spend']]/x[col_map['sales']])*100 if x[col_map['sales']]>0 else 0, axis=1)
                        
                        day_display = day_agg.rename(columns={col_map['spend']: 'Spend', col_map['sales']: 'Sales', col_map['orders']: 'Orders'})
                        for c in ['Spend', 'Sales', 'ROAS', 'ACOS']: day_display[c] = day_display[c].round(1)

                        c1, c2 = st.columns(2)
                        with c1: st.markdown("##### 📉 Spend Trend"); st.bar_chart(day_display['Spend'], color="#ff4b4b")
                        with c2: st.markdown("##### 📦 Order Volume"); st.bar_chart(day_display['Orders'], color="#00C0F2")
                        st.markdown("##### Daily Breakdown"); st.dataframe(day_display[['Spend', 'Sales', 'Orders', 'ROAS', 'ACOS']].style.format("{:.1f}"), use_container_width=True)
                    else:
                        st.warning("No 'Date' column found.")
                        day_display = pd.DataFrame()

                # TAB 5: WASTED SPEND
                with tabs[4]:
                    st.subheader("💸 Wasted Spend (Zero Orders)")
                    waste_threshold = st.slider("Min Spend Threshold", 50, 1000, 200)
                    df_waste = df_agg[(df_agg['Orders'] == 0) & (df_agg['Spend'] >= waste_threshold)].sort_values(by='Spend', ascending=False)
                    for c in ['Spend', 'CPC', 'ACOS']: df_waste[c] = df_waste[c].round(1)
                    st.dataframe(df_waste[['Search Term', 'Campaign', 'Ad Group', 'Spend', 'Orders', 'ACOS', 'Clicks', 'CPC']].style.format({'Spend': '{:.1f}', 'CPC': '{:.1f}', 'ACOS': '{:.1f}'}), use_container_width=True)

                # TAB 6: N-GRAMS
                with tabs[5]:
                    st.subheader("🔠 N-Gram Analyzer")
                    col_control1, col_control2 = st.columns([1, 3])
                    with col_control1: n_select = st.radio("Select Phrase Size (N)", [1, 2, 3, 4], horizontal=True, index=0)
                    with col_control2: search_gram = st.text_input("🔍 Filter by word (e.g., 'leather')", "")
                    
                    df_ngram = process_ngrams(df_agg, n_select)
                    if not df_ngram.empty:
                        for c in ['Spend', 'Sales', 'ROAS', 'CPC', 'ACOS']: df_ngram[c] = df_ngram[c].round(1)
                        if search_gram: df_ngram = df_ngram[df_ngram['N-Gram'].str.contains(search_gram.lower())]
                        
                        st.markdown(f"##### Top {n_select}-Word Phrases by Spend")
                        st.bar_chart(df_ngram.head(20).set_index('N-Gram')['Spend'], color="#ff4b4b")
                        st.markdown("##### Detailed N-Gram Report")
                        st.dataframe(
                            df_ngram[['N-Gram', 'Count', 'Spend', 'Sales', 'Orders', 'ACOS', 'ROAS']].style.format({
                                'Spend': '{:.1f}', 'Sales': '{:.1f}', 'ACOS': '{:.1f}%', 'ROAS': '{:.1f}'
                            }), 
                            use_container_width=True
                        )
                    else:
                        st.warning("No data found.")

                # EXPORT
                st.markdown("---")
                st.markdown("### 📥 Download Everything")
                export_data = {
                    'Cannibalization': df_cannibal if 'df_cannibal' in locals() else pd.DataFrame(),
                    'Harvesting': df_harvest if 'df_harvest' in locals() else pd.DataFrame(),
                    'CPC_Analysis': df_cpc if 'df_cpc' in locals() else pd.DataFrame(),
                    'Wasted_Spend': df_waste if 'df_waste' in locals() else pd.DataFrame(),
                    'Day_Performance': day_display if 'day_display' in locals() else pd.DataFrame(),
                    'N-Gram_Analysis': df_ngram if 'df_ngram' in locals() else pd.DataFrame()
                }
                excel_file = to_excel(export_data)
                st.download_button(label="📥 Download Master Report", data=excel_file, file_name="Prabal_Ecommerce_Master_Report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                
        except Exception as e:
            st.error(f"Error processing analysis: {e}")
    else:
        st.info("👋 Welcome! Please upload your Search Term Report to begin.")

if __name__ == "__main__":
    main()
