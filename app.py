import streamlit as st
import pandas as pd
import io
import plotly.express as px

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Amazon PPC Command Center",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    h1, h2, h3 { color: #232f3e; }
    .highlight { background-color: #e8f5e9; padding: 10px; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.title("🚀 PPC Command Center")
    st.markdown("---")
    
    # File Upload
    st.subheader("1. Data Source")
    uploaded_file = st.file_uploader("Upload Search Term Report", type=["csv", "xlsx"])
    
    # Settings
    if uploaded_file:
        st.markdown("---")
        st.subheader("2. Analysis Thresholds")
        
        with st.expander("⚔️ Cannibalization Rules", expanded=False):
            roas_threshold = st.slider("Better ROAS Threshold (%)", 30, 200, 100, 10)
            min_orders_cannibal = st.number_input("Min Orders to Win", 1, 10, 2)
            
        with st.expander("🌾 Harvesting Rules", expanded=True):
            min_orders_harvest = st.number_input("Min Orders", 1, 10, 2, help="Strictly > 1 means set this to 2")
            min_roas_harvest = st.number_input("Min ROAS", 0.1, 10.0, 1.0, 0.1)
            
        with st.expander("💰 CPC Analyzer", expanded=False):
            top_n_terms = st.slider("Analyze Top N Terms", 10, 100, 50)
            bad_roas_limit = st.number_input("Low ROAS Flag (<)", 0.1, 5.0, 1.0, 0.1)

# --- HELPER FUNCTIONS ---

def normalize_match_type(val):
    if pd.isna(val): return 'UNKNOWN'
    val = str(val).upper()
    if 'EXACT' in val: return 'EXACT'
    if 'PHRASE' in val: return 'PHRASE'
    if 'BROAD' in val: return 'BROAD'
    return 'AUTO/OTHER'

def determine_winner(group, improvement_thresh, min_orders):
    # Logic to find the best performing ad group for a search term
    max_sales_idx = group['sales_val'].idxmax()
    sales_leader = group.loc[max_sales_idx]
    
    max_roas_idx = group['calculated_roas'].idxmax()
    roas_leader = group.loc[max_roas_idx]
    
    if max_sales_idx == max_roas_idx:
        return max_sales_idx, "🏆 Best Sales & ROAS"
    
    roas_sales = sales_leader['calculated_roas']
    roas_challenger = roas_leader['calculated_roas']
    
    improvement = (roas_challenger - roas_sales) / roas_sales if roas_sales > 0 else 999
    
    if (improvement >= (improvement_thresh / 100.0)) and (roas_leader['orders_val'] >= min_orders):
        return max_roas_idx, f"💎 Efficient Choice (ROAS +{improvement:.0%})"
    else:
        return max_sales_idx, "📦 Volume Leader"

def to_excel(dfs):
    # Helper to create a multi-sheet Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()

# --- MAIN LOGIC ---

if uploaded_file:
    try:
        # 1. READ DATA
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        df.columns = df.columns.str.strip()
        
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
            # Cleanup
            num_cols = ['orders', 'sales', 'spend', 'clicks', 'impressions']
            for c in num_cols:
                if col_map[c]:
                    df[col_map[c]] = pd.to_numeric(df[col_map[c]], errors='coerce').fillna(0)
            
            df['norm_match'] = df[col_map['match']].apply(normalize_match_type)
            if col_map['date']:
                df['Date'] = pd.to_datetime(df[col_map['date']], errors='coerce')
                df['DayOfWeek'] = df['Date'].dt.day_name()

            # AGGREGATION (Group Daily Data)
            agg_cols = [col_map['term'], col_map['camp'], col_map['adg'], 'norm_match']
            df_agg = df.groupby(agg_cols, as_index=False).agg({
                col_map['spend']: 'sum',
                col_map['sales']: 'sum',
                col_map['orders']: 'sum',
                col_map['clicks']: 'sum',
                col_map['impressions']: 'sum'
            })
            
            # Standardize
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

            # --- BUILD KNOWLEDGE BASE (Existing Targets) ---
            existing_exact = set(df_agg[df_agg['norm_match'] == 'EXACT']['Search Term'].str.lower().unique())

            # --- HEADER METRICS ---
            st.markdown(f"### 📊 Analysis Report: {uploaded_file.name}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Spend", f"₹{df_agg['Spend'].sum():,.0f}")
            c2.metric("Total Sales", f"₹{df_agg['Sales'].sum():,.0f}")
            total_roas = df_agg['Sales'].sum() / df_agg['Spend'].sum() if df_agg['Spend'].sum() > 0 else 0
            c3.metric("Account ROAS", f"{total_roas:.2f}")
            c4.metric("Unique Search Terms", f"{df_agg['Search Term'].nunique():,}")

            # --- TABS ---
            tabs = st.tabs(["⚔️ Cannibalization", "🌾 Harvesting", "💰 CPC Analyzer", "📅 Best Days", "💸 Wasted Spend"])

            # ---------------------------
            # TAB 1: CANNIBALIZATION
            # ---------------------------
            with tabs[0]:
                st.subheader("Detect & Fix Self-Competition")
                # Filter Terms with Sales > 0
                sales_df = df_agg[df_agg['Orders'] > 0].copy()
                dupe_counts = sales_df.groupby('Search Term').size()
                cannibal_list = dupe_counts[dupe_counts > 1].index.tolist()
                
                cannibal_results = []
                if cannibal_list:
                    for term in cannibal_list:
                        subset = sales_df[sales_df['Search Term'] == term].rename(columns={'Sales': 'sales_val', 'Spend': 'spend_val', 'ROAS': 'calculated_roas', 'Orders': 'orders_val'}).copy()
                        win_idx, reason = determine_winner(subset, roas_threshold, min_orders_cannibal)
                        
                        for idx, row in subset.iterrows():
                            is_winner = (idx == win_idx)
                            cannibal_results.append({
                                'Search Term': term, 'Campaign': row['Campaign'], 'Ad Group': row['Ad Group'],
                                'Match': row['norm_match'], 'Spend': row['spend_val'], 'Sales': row['sales_val'], 
                                'ROAS': row['calculated_roas'], 'Action': "✅ KEEP" if is_winner else "⛔ NEGATE",
                                'Reason': reason if is_winner else "Lower Efficiency/Vol"
                            })
                    
                    df_cannibal = pd.DataFrame(cannibal_results)
                    st.dataframe(df_cannibal.style.apply(lambda x: ['background-color: #ffebee' if 'NEGATE' in v else '' for v in x], subset=['Action']), use_container_width=True)
                else:
                    st.success("No cannibalization found.")
                    df_cannibal = pd.DataFrame()

            # ---------------------------
            # TAB 2: HARVESTING (Strict)
            # ---------------------------
            with tabs[1]:
                st.subheader("Strict Growth Opportunities")
                st.caption(f"Criteria: Orders >= {min_orders_harvest} AND ROAS >= {min_roas_harvest}")
                
                candidates = df_agg[
                    (df_agg['norm_match'] != 'EXACT') & 
                    (df_agg['Orders'] >= min_orders_harvest) & 
                    (df_agg['ROAS'] >= min_roas_harvest)
                ].copy()
                
                harvest_results = []
                for idx, row in candidates.iterrows():
                    term = row['Search Term']
                    if term.lower() not in existing_exact:
                        harvest_results.append({
                            'Search Term': term, 'Rec Type': '🚀 NEW EXACT', 
                            'Source Campaign': row['Campaign'], 'Source Ad Group': row['Ad Group'],
                            'Orders': row['Orders'], 'Sales': row['Sales'], 'ROAS': row['ROAS'], 'CPC': row['CPC']
                        })
                
                df_harvest = pd.DataFrame(harvest_results)
                if not df_harvest.empty:
                    st.dataframe(df_harvest.sort_values(by='Sales', ascending=False), use_container_width=True)
                else:
                    st.info("No terms met the strict harvesting criteria.")

            # ---------------------------
            # TAB 3: CPC ANALYZER (Top 50)
            # ---------------------------
            with tabs[2]:
                st.subheader(f"Top {top_n_terms} Search Terms: CPC & Performance Variance")
                st.markdown("Spot where you pay too much for the same keyword across different campaigns.")
                
                # Get Top Terms by Spend
                top_terms = df_agg.groupby('Search Term')['Spend'].sum().nlargest(top_n_terms).index.tolist()
                df_top = df_agg[df_agg['Search Term'].isin(top_terms)].copy()
                
                cpc_results = []
                for term in top_terms:
                    subset = df_top[df_top['Search Term'] == term]
                    avg_cpc = subset['CPC'].mean()
                    
                    for idx, row in subset.iterrows():
                        rec = "✅ Healthy"
                        if row['ROAS'] < bad_roas_limit:
                            rec = "⚠️ Lower Bid / Negate (Low ROAS)"
                        elif row['CPC'] > (avg_cpc * 1.3):
                            rec = "⚠️ Lower Bid (High CPC)"
                            
                        cpc_results.append({
                            'Search Term': term, 'Campaign': row['Campaign'], 'Match': row['norm_match'],
                            'Spend': row['Spend'], 'Sales': row['Sales'], 'CPC': row['CPC'], 'ROAS': row['ROAS'],
                            'Rec': rec
                        })
                
                df_cpc = pd.DataFrame(cpc_results)
                
                # Visual Heatmap
                st.dataframe(df_cpc.style.background_gradient(subset=['CPC'], cmap='Reds').format({'CPC': '{:.2f}', 'ROAS': '{:.2f}'}), use_container_width=True)

            # ---------------------------
            # TAB 4: BEST DAYS (Day Parting)
            # ---------------------------
            with tabs[3]:
                st.subheader("📅 Day of Week Performance")
                if col_map['date']:
                    day_agg = df.groupby(df['Date'].dt.day_name()).agg({
                        col_map['spend']: 'sum', col_map['sales']: 'sum', col_map['orders']: 'sum'
                    }).reindex(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])
                    
                    day_agg['ROAS'] = day_agg[col_map['sales']] / day_agg[col_map['spend']]
                    day_agg['ACOS'] = day_agg[col_map['spend']] / day_agg[col_map['sales']]
                    
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.dataframe(day_agg[['ROAS', 'ACOS']].style.highlight_max(subset=['ROAS'], color='#d4edda').highlight_min(subset=['ACOS'], color='#d4edda'), use_container_width=True)
                    with c2:
                        fig = px.bar(day_agg, x=day_agg.index, y='ROAS', title="ROAS by Day", color='ROAS', color_continuous_scale='Greens')
                        st.plotly_chart(fig, use_container_width=True)
                        
                    st.caption("Tip: If ROAS is consistently low on weekends, consider using Day Parting software or automated rules to lower bids on Sat/Sun.")
                else:
                    st.warning("No 'Date' column found in the report to analyze Day Parting.")
                    day_agg = pd.DataFrame()

            # ---------------------------
            # TAB 5: WASTED SPEND
            # ---------------------------
            with tabs[4]:
                st.subheader("High Spend, Zero Sales")
                waste_threshold = st.slider("Min Spend Threshold", 50, 1000, 200)
                
                df_waste = df_agg[(df_agg['Orders'] == 0) & (df_agg['Spend'] >= waste_threshold)].sort_values(by='Spend', ascending=False)
                st.dataframe(df_waste[['Search Term', 'Campaign', 'Ad Group', 'Spend', 'Clicks', 'CPC']], use_container_width=True)

            # ---------------------------
            # MASTER EXPORT BUTTON
            # ---------------------------
            st.markdown("---")
            st.markdown("### 📥 Download Everything")
            
            # Prepare Dictionary for Excel Writer
            export_data = {
                'Cannibalization': df_cannibal if 'df_cannibal' in locals() else pd.DataFrame(),
                'Harvesting': df_harvest if 'df_harvest' in locals() else pd.DataFrame(),
                'CPC_Analysis': df_cpc if 'df_cpc' in locals() else pd.DataFrame(),
                'Wasted_Spend': df_waste if 'df_waste' in locals() else pd.DataFrame(),
                'Day_Performance': day_agg if 'day_agg' in locals() else pd.DataFrame()
            }
            
            excel_file = to_excel(export_data)
            
            st.download_button(
                label="📥 Download Master Report (All Analyses)",
                data=excel_file,
                file_name="Amazon_PPC_Master_Analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"Error processing file: {e}")
