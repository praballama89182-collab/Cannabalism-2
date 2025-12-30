import streamlit as st
import pandas as pd

# --- PAGE CONFIGURATION (Must be first) ---
st.set_page_config(
    page_title="Amazon PPC Optimizer",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS FOR PROFESSIONAL LOOK ---
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 5px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    h1, h2, h3 {
        color: #232f3e; /* Amazon Dark Blue */
    }
    div[data-testid="stExpander"] {
        border: 1px solid #e0e0e0;
        border-radius: 5px;
        background-color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR SETTINGS ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg", width=150)
    st.title("PPC Optimizer Tool")
    
    st.markdown("### 1. Upload Data")
    uploaded_file = st.file_uploader("Search Term Report (CSV/XLSX)", type=["csv", "xlsx"])
    
    st.markdown("### 2. Analysis Settings")
    with st.expander("⚙️ Decision Logic", expanded=True):
        roas_threshold = st.slider(
            "Better ROAS Threshold (%)", 
            min_value=30, 
            max_value=200, 
            value=100,
            step=10,
            help="A term must have a ROAS this much better than the 'Sales Leader' to be chosen."
        )
        min_orders_for_roas = st.number_input(
            "Min Orders for High ROAS Winner",
            min_value=1,
            value=2,
            help="A High-ROAS term must have at least this many orders to overthrow a High-Sales term."
        )

# --- LOGIC FUNCTIONS ---

def normalize_match_type(val):
    if pd.isna(val): return 'UNKNOWN'
    val = str(val).upper()
    if 'EXACT' in val: return 'EXACT'
    if 'PHRASE' in val: return 'PHRASE'
    if 'BROAD' in val: return 'BROAD'
    return 'AUTO/OTHER'

def determine_winner(group, improvement_thresh, min_orders):
    """
    Decides which row to KEEP based on Sales vs ROAS trade-off.
    Logic:
    1. Default Winner = Highest Sales Volume.
    2. Challenger = Highest ROAS.
    3. Challenger wins ONLY IF:
       - Its ROAS is X% better than Default (User defined, e.g., 100%).
       - AND it has > Y orders (User defined, e.g., >1).
    """
    # 1. Identify Sales Leader
    max_sales_idx = group['sales_val'].idxmax()
    sales_leader = group.loc[max_sales_idx]
    
    # 2. Identify ROAS Leader
    max_roas_idx = group['calculated_roas'].idxmax()
    roas_leader = group.loc[max_roas_idx]
    
    # If they are the same row, simple win
    if max_sales_idx == max_roas_idx:
        return max_sales_idx, "🏆 Best Sales & ROAS"
    
    # Compare
    roas_sales = sales_leader['calculated_roas']
    roas_challenger = roas_leader['calculated_roas']
    
    # Calculate % improvement
    if roas_sales == 0:
        improvement = 999 # Infinite improvement
    else:
        improvement = (roas_challenger - roas_sales) / roas_sales
    
    # THRESHOLD CHECK (The "100% Better" Logic)
    threshold_decimal = improvement_thresh / 100.0
    
    # Condition: Better ROAS AND Sufficient Data (Orders)
    if (improvement >= threshold_decimal) and (roas_leader['orders_val'] >= min_orders):
        return max_roas_idx, f"💎 Efficient Choice (ROAS +{improvement:.0%})"
    else:
        if improvement >= threshold_decimal:
            return max_sales_idx, f"📦 Vol Leader (Challenger had only {roas_leader['orders_val']} order)"
        else:
            return max_sales_idx, "📦 Volume Leader"

# --- MAIN APP LOGIC ---

if uploaded_file:
    try:
        # Load Data
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        df.columns = df.columns.str.strip()
        
        # Smart Column Mapping
        col_map = {
            'term': next((c for c in df.columns if 'Matched product' in c or 'Customer Search Term' in c), None),
            'camp': next((c for c in df.columns if 'Campaign Name' in c), None),
            'adg': next((c for c in df.columns if 'Ad Group Name' in c), None),
            'match': next((c for c in df.columns if 'Match Type' in c), None),
            'orders': next((c for c in df.columns if 'Orders' in c or 'Units' in c), None),
            'sales': next((c for c in df.columns if 'Sales' in c), None),
            'spend': next((c for c in df.columns if 'Spend' in c), None),
        }

        if any(v is None for v in col_map.values()):
            st.error(f"Missing columns! Found: {col_map}")
        else:
            # Clean Numbers
            for c in ['orders', 'sales', 'spend']:
                df[col_map[c]] = pd.to_numeric(df[col_map[c]], errors='coerce').fillna(0)
            
            df['norm_match'] = df[col_map['match']].apply(normalize_match_type)

            # AGGREGATE (Handle daily rows)
            df_agg = df.groupby(
                [col_map['term'], col_map['camp'], col_map['adg'], 'norm_match'], 
                as_index=False
            ).agg({
                col_map['orders']: 'sum',
                col_map['sales']: 'sum',
                col_map['spend']: 'sum'
            })
            
            # Standardize Names for Processing
            df_agg.rename(columns={
                col_map['term']: 'search_term',
                col_map['camp']: 'campaign',
                col_map['adg']: 'ad_group',
                col_map['orders']: 'orders_val',
                col_map['sales']: 'sales_val',
                col_map['spend']: 'spend_val'
            }, inplace=True)
            
            # Metric Calculation
            df_agg['calculated_roas'] = df_agg.apply(lambda x: x['sales_val']/x['spend_val'] if x['spend_val'] > 0 else 0, axis=1)

            # --- HEADER ---
            st.title("📊 Search Term Analysis Report")
            
            # --- TABS FOR DIFFERENT TOOLS ---
            tab1, tab2 = st.tabs(["⚔️ Cannibalization Manager", "🌾 Keyword Harvester"])

            # ==========================
            # TAB 1: CANNIBALIZATION
            # ==========================
            with tab1:
                st.markdown("##### Detect & Fix Self-Competition")
                st.caption("Identifying search terms that trigger multiple ad groups and deciding the winner.")
                
                # Filter for Sales > 0
                sales_df = df_agg[df_agg['orders_val'] > 0].copy()
                
                # Find Duplicates
                dupe_check = sales_df.groupby('search_term').size()
                cannibal_terms = dupe_check[dupe_check > 1].index.tolist()
                
                if not cannibal_terms:
                    st.success("✅ No cannibalization found! Your account structure is clean.")
                else:
                    results = []
                    for term in cannibal_terms:
                        subset = sales_df[sales_df['search_term'] == term].copy()
                        
                        # Apply User Logic
                        win_idx, reason = determine_winner(subset, roas_threshold, min_orders_for_roas)
                        
                        for idx, row in subset.iterrows():
                            is_winner = (idx == win_idx)
                            action = "✅ KEEP" if is_winner else "⛔ NEGATE"
                            
                            results.append({
                                "Search Term": term,
                                "Campaign": row['campaign'],
                                "Ad Group": row['ad_group'],
                                "Spend": row['spend_val'],
                                "Sales": row['sales_val'],
                                "Orders": row['orders_val'],
                                "ROAS": row['calculated_roas'],
                                "Status": action,
                                "Reason": reason if is_winner else "Lower Efficiency/Vol"
                            })
                    
                    res_df = pd.DataFrame(results)
                    
                    # Top Level Metrics
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Cannibalized Keywords", len(cannibal_terms))
                    c2.metric("Wasted Spend (Negate Targets)", f"₹{res_df[res_df['Status']=='⛔ NEGATE']['Spend'].sum():,.2f}")
                    c3.metric("Conflicting Ad Groups", res_df['Ad Group'].nunique())
                    
                    # Styled Table
                    def highlight_rows(row):
                        if 'NEGATE' in row['Status']:
                            return ['background-color: #ffebee'] * len(row)
                        return ['background-color: #e8f5e9'] * len(row)

                    st.dataframe(
                        res_df.style.apply(highlight_rows, axis=1).format({
                            "Spend": "₹{:.2f}", 
                            "Sales": "₹{:.2f}", 
                            "ROAS": "{:.2f}"
                        }),
                        use_container_width=True
                    )
                    
                    # Download
                    csv = res_df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Action Plan (CSV)", csv, "cannibalization_fix.csv", "text/csv")

            # ==========================
            # TAB 2: HARVESTING
            # ==========================
            with tab2:
                st.markdown("##### Move Winners to Exact Match")
                st.caption(f"Finding terms in Auto/Broad/Phrase with Orders ≥ 1 (Configurable in Sidebar if needed) that are not yet Exact.")
                
                # 1. Knowledge Base
                exact_terms = set(df_agg[df_agg['norm_match'] == 'EXACT']['search_term'].str.lower().unique())
                
                # 2. Candidates (Non-Exact, High Sales)
                # You can add a slider for Min Orders for harvesting if you want
                candidates = df_agg[
                    (df_agg['norm_match'] != 'EXACT') & 
                    (df_agg['orders_val'] >= 1) # Default baseline
                ].copy()
                
                # 3. New Opportunities
                new_opps = candidates[~candidates['search_term'].str.lower().isin(exact_terms)].copy()
                
                if new_opps.empty:
                    st.info("No new harvesting opportunities found.")
                else:
                    disp_opps = new_opps[[
                        'search_term', 'campaign', 'ad_group', 'norm_match', 'orders_val', 'sales_val', 'spend_val', 'calculated_roas'
                    ]].sort_values(by='sales_val', ascending=False)
                    
                    c1, c2 = st.columns(2)
                    c1.metric("New Keywords Found", len(disp_opps))
                    c2.metric("Potential Revenue", f"₹{disp_opps['sales_val'].sum():,.2f}")
                    
                    st.dataframe(
                        disp_opps.style.format({
                            "sales_val": "₹{:.2f}",
                            "spend_val": "₹{:.2f}",
                            "calculated_roas": "{:.2f}"
                        }),
                        use_container_width=True
                    )
                    
                    csv_harvest = disp_opps.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Harvest List (CSV)", csv_harvest, "harvest_keywords.csv", "text/csv")

    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    # Empty State Design
    st.markdown("""
    <div style='text-align: center; padding: 50px; background-color: white; border-radius: 10px; border: 2px dashed #e0e0e0;'>
        <h2>👋 Welcome to PPC Optimizer</h2>
        <p>Upload your <b>Search Term Report</b> in the sidebar to begin.</p>
        <p style='color: #666;'>Supports CSV and Excel formats.</p>
    </div>
    """, unsafe_allow_html=True)
