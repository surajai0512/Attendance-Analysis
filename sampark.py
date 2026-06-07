import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime

# ReportLab imports for professional PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# 1. PAGE SETUP
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Community Attendance Dashboard", layout="wide")
st.title("🎯 Weekly Gathering Attendance Analysis")

# -----------------------------------------------------------------------------
# 2. UNIVERSAL DATA PROCESSING ENGINE (DYNAMIC COLUMN MAPPING ENGINE)
# -----------------------------------------------------------------------------
st.sidebar.header("📁 Data Source")
uploaded_file = st.sidebar.file_uploader("Upload Community File (.csv or .xlsx)", type=["csv", "xlsx"])

@st.cache_data
def process_data(file_source):
    if file_source.name.endswith('.xlsx'):
        df = pd.read_excel(file_source)
    else:
        df = pd.read_csv(file_source, errors='coerce')
        
    # Standardize column headers: strip whitespace
    df.columns = [str(c).strip() for c in df.columns]
    
    # DYNAMIC MAPPING DICTIONARY (Handles variations between old and new sample files)
    column_mappings = {
        'Follow-up': ['Follow-up', 'Followup', 'Follow up', 'Coordinator'],
        'Joining Date': ['Joining Date', 'JoiningDate', 'Date of Joining', 'DOJ'],
        'Living Date': ['Living Date', 'LivingDate', 'Date of Leaving', 'DOL'],
        'Last Attended Sabha': ['Last Attended Sabha', 'LastAttendedSabha', 'Last Attended'],
        'Total Sabha': ['Total Attended Sabha', 'Total Sabha', 'TotalSabha', 'Total Attended'],
        'User Status': ['User Status', 'UserStatus', 'Status']
    }
    
    # Automatically remap matching variants to standard internal names
    for internal_name, variants in column_mappings.items():
        for variant in variants:
            if variant in df.columns and internal_name != variant:
                df[internal_name] = df[variant]
                break

    # Verify minimum required analytical pillars
    required = ['First Name', 'Last Name', 'Category', 'Follow-up', 'Living Date', 'W4', 'W12', 'Joining Date']
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"❌ Missing mandatory analytical columns in file: {', '.join(missing)}")
        st.markdown("**Available Columns Detected in Your File:**")
        st.write(list(df.columns))
        st.stop()

    # Apply internal structural fallback defaults if missing from schema
    if 'Middle Name' not in df.columns:
        df['Middle Name'] = ""
    if 'Last Attended Sabha' not in df.columns:
        df['Last Attended Sabha'] = "N/A"
    if 'Mandal' not in df.columns:
        df['Mandal'] = "Unassigned"
    if 'Total Sabha' not in df.columns:
        df['Total Sabha'] = 0
    if 'User Status' not in df.columns:
        df['User Status'] = 1  # Default fallback if column is entirely missing

    # Clean text values up smoothly
    for col in ['First Name', 'Middle Name', 'Last Name', 'Category', 'Follow-up', 'Living Date', 'Joining Date', 'Mandal']:
        df[col] = df[col].fillna("Unassigned").astype(str).str.strip()
        df[col] = df[col].replace(['', 'nan', 'None', 'nan nan'], 'Unassigned')
            
    def build_clean_name(row):
        parts = [row['First Name'], row['Middle Name'], row['Last Name']]
        filtered_parts = [p for p in parts if p != "" and p != "Unassigned"]
        return " ".join(filtered_parts) if filtered_parts else "Unknown Member"
        
    df['Full Name'] = df.apply(build_clean_name, axis=1)
    
    # Standard numerical parsings
    df['W4'] = pd.to_numeric(df['W4'], errors='coerce').fillna(0).astype(int)
    df['W12'] = pd.to_numeric(df['W12'], errors='coerce').fillna(0).astype(int)
    
    # Compute active risk tier parameters
    def assign_tier(row):
        w4 = row['W4']
        w12 = row['W12']
        if w4 >= 3: return 'Active & Consistent'
        elif 1 <= w4 <= 2: return 'Slowing Down / At Risk'
        elif w4 == 0 and w12 > 0: return 'Recent Dropout'
        elif w12 == 0: return 'Chronic / Long-term Drop'
        return 'Unclassified'
        
    df['Risk Tier'] = df.apply(assign_tier, axis=1)
    
    def is_new_joinee(date_str):
        if not date_str or date_str == 'Unassigned' or date_str == '':
            return False
        for fmt in ('%d-%m-%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%m/%d/%Y'):
            try:
                j_date = pd.to_datetime(date_str, format=fmt, errors='coerce')
                if not pd.isna(j_date):
                    delta_months = (datetime.now().year - j_date.year) * 12 + datetime.now().month - j_date.month
                    return delta_months <= 6
            except:
                continue
        try:
            j_date = pd.to_datetime(date_str, errors='coerce')
            if pd.isna(j_date): return False
            delta_months = (datetime.now().year - j_date.year) * 12 + datetime.now().month - j_date.month
            return delta_months <= 6
        except:
            return False
        return False
            
    df['Is New Joinee'] = df['Joining Date'].apply(is_new_joinee)
    return df

if uploaded_file is None:
    st.info("👋 Welcome! Please upload your community data file (.csv or .xlsx) in the sidebar to begin.")
    st.stop()
else:
    raw_data = process_data(uploaded_file)

# -----------------------------------------------------------------------------
# SIDEBAR FILTERS SECTION
# -----------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.header("🎯 Filters")

# 1. User Status Selection Dropdown
try:
    raw_status_options = sorted(list(raw_data['User Status'].unique()))
    status_display_map = {str(opt): f"Status {opt}" for opt in raw_status_options}
except:
    raw_status_options = [0, 1]
    status_display_map = {"0": "Status 0", "1": "Status 1"}

status_selection = st.sidebar.selectbox(
    "Select User Status:",
    options=["All Statuses"] + [str(opt) for opt in raw_status_options],
    format_func=lambda x: "All Members" if x == "All Statuses" else status_display_map.get(x, x)
)

# 2. Dynamic Multi-Select Category Filter (Pulls Yuvak, Ambrish, Karyakarta, Relocated, etc.)
try:
    raw_category_options = sorted(list(raw_data['Category'].unique()))
except:
    raw_category_options = ['Yuvak', 'Ambrish', 'Karyakarta', 'Relocated']

selected_categories = st.sidebar.multiselect(
    "Select Categories:",
    options=raw_category_options,
    default=raw_category_options
)

# Apply Data Filtering Pipeline Sequence
data = raw_data.copy()

# Filter Parameter A: User Status
if status_selection != "All Statuses":
    try:
        target_status_val = int(status_selection)
        data = data[data['User Status'].astype(float).astype(int) == target_status_val]
    except:
        data = data[data['User Status'].astype(str) == str(status_selection)]

# Filter Parameter B: Multi-Select Category Match
if selected_categories:
    data = data[data['Category'].isin(selected_categories)]
else:
    data = pd.DataFrame(columns=raw_data.columns)

color_map = {
    'Active & Consistent': '#10B981',
    'Slowing Down / At Risk': '#F59E0B',
    'Recent Dropout': '#EF4444',
    'Chronic / Long-term Drop': '#7F1D1D'
}

# -----------------------------------------------------------------------------
# 3. SIDEBAR CUSTOM COLUMN PICKER
# -----------------------------------------------------------------------------
standard_cols = ['Full Name', 'Category', 'Follow-up', 'Last Attended Sabha', 'W4', 'W12']
all_csv_cols = data.columns.tolist()
internal_flags = ['First Name', 'Middle Name', 'Last Name', 'Risk Tier', 'Living Date', 'Is New Joinee', 'Full Name', 'Total Sabha', 'User Status']

raw_extra_cols = [c for c in all_csv_cols if c not in standard_cols + internal_flags]
extra_cols = raw_extra_cols if raw_extra_cols is not None else []

st.sidebar.markdown("---")
st.sidebar.header("➕ Custom Columns")
selected_extras = st.sidebar.multiselect("Select additional columns to show:", extra_cols) or []
active_display_columns = standard_cols + selected_extras

def convert_df_to_csv(df):
    if df is None or df.empty:
        return "".encode('utf-8')
    return df.to_csv(index=False).encode('utf-8')

# -----------------------------------------------------------------------------
# 4. ADMIN SUMMARY GENERATOR WITH OPERATIONAL TARGET ACTIONS & TOTALS
# -----------------------------------------------------------------------------
def build_administrative_summary(source_df, group_col):
    metrics = [
        ('Active & Consistent', 'Maintain Engagement'),
        ('Slowing Down / At Risk', 'Priority - Engagement Required'),
        ('Recent Dropout', 'High Priority - Engagement Required'),
        ('Chronic / Long-term Drop', 'High Priority - Follow Up Required')
    ]
    
    summary_rows = []
    
    if source_df.empty:
        return pd.DataFrame()
        
    unique_groups = sorted(source_df[group_col].unique())
    
    for g in unique_groups:
        g_df = source_df[source_df[group_col] == g]
        j_df = g_df[g_df['Is New Joinee'] == True]
        
        total_overall = len(g_df)
        total_joinees = len(j_df)
        
        for idx, (tier, action) in enumerate(metrics):
            g_tier_count = len(g_df[g_df['Risk Tier'] == tier])
            j_tier_count = len(j_df[j_df['Risk Tier'] == tier])
            
            g_pct = (g_tier_count / total_overall * 100) if total_overall > 0 else 0.0
            j_pct = (j_tier_count / total_joinees * 100) if total_joinees > 0 else 0.0
            
            row = {
                "Group / Allocation": g,  
                "Status Type": tier,
                "Operational Action": action,
                "Overall (Count)": g_tier_count,
                "Overall (%)": f"{g_pct:.1f}%",
                "New Members (Count)": j_tier_count,
                "New Members (%)": f"{j_pct:.1f}%",
                "_raw_overall_count": g_tier_count,
                "_raw_new_count": j_tier_count
            }
            summary_rows.append(row)
            
    summary_df = pd.DataFrame(summary_rows)
    
    # Calculate and Append Total Row
    if not summary_df.empty:
        total_overall_sum = summary_df["_raw_overall_count"].sum()
        total_new_sum = summary_df["_raw_new_count"].sum()
        
        pct_overall = 100.0 if total_overall_sum > 0 else 0.0
        pct_new = 100.0 if total_new_sum > 0 else 0.0
        
        total_row = {
            "Group / Allocation": "TOTAL",
            "Status Type": "All Tiers Combined",
            "Operational Action": "Summary Total Metrics",
            "Overall (Count)": total_overall_sum,
            "Overall (%)": f"{pct_overall:.1f}%",
            "New Members (Count)": total_new_sum,
            "New Members (%)": f"{pct_new:.1f}%",
            "_raw_overall_count": total_overall_sum,
            "_raw_new_count": total_new_sum
        }
        summary_df = pd.concat([summary_df, pd.DataFrame([total_row])], ignore_index=True)
        
    return summary_df

def get_coordinator_performance_df(source_df):
    if source_df.empty:
        empty_cols = ['Follow-up Coordinator', 'Total Assigned Members', 'Performance Alert Status'] + [f'{k} (Count)' for k in color_map.keys()] + [f'{k} (%)' for k in color_map.keys()]
        return pd.DataFrame(columns=empty_cols)
        
    ctab_counts = pd.crosstab(source_df['Follow-up'], source_df['Risk Tier'])
    ctab_pct = pd.crosstab(source_df['Follow-up'], source_df['Risk Tier'], normalize='index') * 100
    
    for status in color_map.keys():
        if status not in ctab_counts.columns: ctab_counts[status] = 0
        if status not in ctab_pct.columns: ctab_pct[status] = 0.0
        
    perf_df = pd.DataFrame()
    perf_df['Follow-up Coordinator'] = ctab_counts.index
    perf_df['Total Members'] = source_df['Follow-up'].value_counts().loc[ctab_counts.index].values
    
    alert_statuses = []
    for idx in ctab_pct.index:
        drop_rate = float(ctab_pct.loc[idx, 'Recent Dropout']) + float(ctab_pct.loc[idx, 'Chronic / Long-term Drop'])
        if drop_rate >= 25.0:
            alert_statuses.append('⚠️ High Risk Leakage')
        else:
            alert_statuses.append('✅ Stable Base')
            
    for status in color_map.keys():
        perf_df[f'{status} (Count)'] = ctab_counts[status].values
        perf_df[f'{status} (%)'] = [f"{val:.1f}%" for val in ctab_pct[status].values]
        
    perf_df['Performance Alert Status'] = alert_statuses
    return perf_df

# -----------------------------------------------------------------------------
# 4b. RETENTION ENGAGEMENT ATTENDANCE MATRIX CALCULATION (W4 VS LIFETIME)
# -----------------------------------------------------------------------------
def build_attendance_matrix_table(source_df):
    df_working = source_df.copy()
    df_working['Total_Sabha_Numeric'] = pd.to_numeric(df_working['Total Sabha'], errors='coerce').fillna(0).astype(int)
    
    def assign_lifetime_tier(val):
        if val == 0: return '0 Lifetime' 
        elif 1 <= val <= 50: return '1-50'
        elif 51 <= val <= 100: return '51-100'
        elif 101 <= val <= 150: return '101-150'
        elif 151 <= val <= 200: return '151-200'
        elif 201 <= val <= 250: return '201-250'
        else: return '>250'
        
    df_working['Historical Bracket'] = df_working['Total_Sabha_Numeric'].apply(assign_lifetime_tier)
    
    brackets = ['0 Lifetime', '1-50', '51-100', '101-150', '151-200', '201-250', '>250']
    w4_options = [0, 1, 2, 3, 4]
    
    matrix_rows = []
    for w in w4_options:
        sub_w = df_working[df_working['W4'] == w]
        row_dict = {"Past 4 Sabha": str(w), "Count": len(sub_w)}
        
        for b in brackets:
            row_dict[b] = len(sub_w[sub_w['Historical Bracket'] == b])
        matrix_rows.append(row_dict)
        
    matrix_df = pd.DataFrame(matrix_rows)
    
    grand_total_row = {"Past 4 Sabha": "Grand Total", "Count": matrix_df["Count"].sum()}
    for b in brackets:
        grand_total_row[b] = matrix_df[b].sum()
        
    matrix_df = pd.concat([matrix_df, pd.DataFrame([grand_total_row])], ignore_index=True)
    return matrix_df

# -----------------------------------------------------------------------------
# 5. ADMINISTRATIVE EXECUTIVE OVERVIEW MODULE (TOP-LEVEL CHANNELS)
# -----------------------------------------------------------------------------
st.subheader("📋 Administrative Attendance Strategy Dashboard")
admin_tab1, admin_tab2 = st.tabs(["🏛️ Sliced by Mandal Network", "👥 Sliced by Age Category Group"])

with admin_tab1:
    st.markdown("**Core Mandal Engagement Allocation (Overall vs New Arrivals)**")
    mandal_summary_data = build_administrative_summary(data, 'Mandal')
    
    if not mandal_summary_data.empty:
        cols_to_render = [c for c in mandal_summary_data.columns if c not in ['Mandal', '_raw_overall_count', '_raw_new_count']]
        st.dataframe(mandal_summary_data[cols_to_render], use_container_width=True, hide_index=True)
    else:
        st.info("No rows returned matching criteria setup for current state filters.")

with admin_tab2:
    st.markdown("**Core Category Engagement Allocation (Overall vs New Arrivals)**")
    category_summary_data = build_administrative_summary(data, 'Category')
    
    if not category_summary_data.empty:
        cols_to_render_cat = [c for c in category_summary_data.columns if c not in ['Category', '_raw_overall_count', '_raw_new_count']]
        st.dataframe(category_summary_data[cols_to_render_cat], use_container_width=True, hide_index=True)
    else:
        st.info("No rows returned matching criteria setup for current state filters.")

# RENDER CROSS-TAB ATTENDANCE RETENTION ANALYSIS MATRIX WITH CONDITIONAL RISK STYLING
st.markdown("<br>**📊 Historical Retention Matrix (Past 4 Weeks Attendance vs Lifetime Volume Run)**", unsafe_allow_html=True)
attendance_matrix_data = build_attendance_matrix_table(data)

if "Error" in attendance_matrix_data.columns:
    st.warning(f"⚠️ Could not generate the Historical Breakdown Table automatically: {attendance_matrix_data.iloc[0]['Error']}")
else:
    def style_risk_matrix(row):
        sabha_val = row['Past 4 Sabha']
        if sabha_val in ['0', '1']:
            return ['background-color: #FDE8E8; color: #9B1C1C; font-weight: 500;'] * len(row)
        elif sabha_val == '2':
            return ['background-color: #FEF08A; color: #713F12; font-weight: 500;'] * len(row)
        elif sabha_val in ['3', '4']:
            return ['background-color: #DCFCE7; color: #14532D; font-weight: 500;'] * len(row)
        elif sabha_val == 'Grand Total':
            return ['background-color: #E5E7EB; color: #1F2937; font-weight: bold; border-top: 2px solid #9CA3AF;'] * len(row)
        return [''] * len(row)

    st.dataframe(
        attendance_matrix_data.style.apply(style_risk_matrix, axis=1),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("""
    <div style="padding: 15px; border-radius: 8px; background-color: #1E1E24; margin-top: 10px; border: 1px solid #333;">
        <h4 style="margin-top: 0; color: #F3F4F6; font-size: 15px;">🔍 Retention Risk Matrix Interpretation Legend</h4>
        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 16px; height: 16px; background-color: #FDE8E8; border-radius: 4px; border: 1px solid #9B1C1C;"></div>
                <span style="color: #D1D5DB; font-size: 13px;"><strong>🚨 Row 0-1 (Crisis Zone):</strong> Active or severe dropouts. Veterans here (>100 lifetime) indicate massive data leakage. Urgent, immediate intervention required.</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 16px; height: 16px; background-color: #FEF08A; border-radius: 4px; border: 1px solid #713F12;"></div>
                <span style="color: #D1D5DB; font-size: 13px;"><strong>⚠️ Row 2 (Warning Zone):</strong> Critical fence-sitters. Tipping point stage where personal contact can reliably pull them back to consistency.</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 16px; height: 16px; background-color: #DCFCE7; border-radius: 4px; border: 1px solid #14532D;"></div>
                <span style="color: #D1D5DB; font-size: 13px;"><strong>✅ Row 3-4 (Stability Zone):</strong> Engaged, predictable engine. Transition long-term veterans (>150 lifetime) here into leadership/coordinating roles.</span>
            </div>
        </div>
        <p style="margin-bottom: 0; margin-top: 12px; font-size: 12.5px; color: #9CA3AF; font-style: italic;">
            💡 <strong>Strategic Goal:</strong> Nudge members gradually <strong>downwards</strong> across the rows (from Row 0/1 → Row 2 → Row 3/4) to stabilize community health.
        </p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br><hr>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. GLOBAL ROSTER SECTION
# -----------------------------------------------------------------------------
st.header("🌐 Global Roster Overview")

# SUMMARY METRICS CARDS
total_g = len(data)
g_counts = data['Risk Tier'].value_counts()
g_green = g_counts.get('Active & Consistent', 0)
g_yellow = g_counts.get('Slowing Down / At Risk', 0)
g_red = g_counts.get('Recent Dropout', 0)
g_crimson = g_counts.get('Chronic / Long-term Drop', 0)

g_col_m1, g_col_m2, g_col_m3, g_col_m4, g_col_m5 = st.columns(5)
g_col_m1.metric("Total Active Base", total_g)
g_col_m2.metric("Consistent (Green)", g_green, delta=f"{(g_green/total_g*100 if total_g else 0):.1f}%")
g_col_m3.metric("At Risk (Yellow)", g_yellow, delta=f"{(g_yellow/total_g*100 if total_g else 0):.1f}%", delta_color="inverse")
g_col_m4.metric("Recent Dropouts (Red)", g_red, delta="Action Needed", delta_color="inverse")
g_col_m5.metric("Long Term Drops", g_crimson, delta="Re-engage Plan", delta_color="inverse")

st.markdown("<br>", unsafe_allow_html=True)

g_col1, g_col2 = st.columns([4, 6])
with g_col1:
    st.markdown("**Overall Attendance Distribution Breakdown**")
    if not data.empty:
        g_pie_df = data['Risk Tier'].value_counts().reset_index()
        g_pie_df.columns = ['Risk Tier', 'Count']
        fig_g_pie = px.pie(g_pie_df, names='Risk Tier', values='Count', color='Risk Tier', color_discrete_map=color_map, hole=0.4)
        fig_g_pie.update_traces(texttemplate='%{percent:.1%}', hovertemplate='%{label}<br>%{value} Count<br>%{percent:.1%}')
        fig_g_pie.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.05))
        st.plotly_chart(fig_g_pie, use_container_width=True)
    else:
        st.info("No chart matrix to map out.")

with g_col2:
    st.markdown("**Follow-up Coordinator Performance Audit Matrix**")
    global_perf_table = get_coordinator_performance_df(data)
    if not global_perf_table.empty:
        st.dataframe(
            global_perf_table.style.map(
                lambda v: 'background-color: #FEE2E2; color: #991B1B; font-weight: bold;' if v == '⚠️ High Risk Leakage' else '',
                subset=['Performance Alert Status'] if 'Performance Alert Status' in global_perf_table.columns else []
            ),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No records available to evaluate coordinator metrics.")

with st.expander("👁️ View Complete Global Roster Database Table & Dynamic Category Search"):
    raw_g_selection = st.multiselect(
        "Select Category Statuses to Filter Matrix:", 
        options=list(color_map.keys()), 
        default=list(color_map.keys()),
        key='g_ms'
    )
    selected_g_statuses = raw_g_selection if raw_g_selection is not None else []
    
    g_search_query = st.text_input("🔍 Search Anyone by Name (Global):", placeholder="Type member name to trace instantly...", key='g_search')
    
    g_display_df = data.copy()
    
    if isinstance(selected_g_statuses, list) and len(selected_g_statuses) > 0:
        g_display_df = g_display_df[g_display_df['Risk Tier'].isin(selected_g_statuses)]
    else:
        g_display_df = pd.DataFrame(columns=data.columns)
        
    if g_search_query and not g_display_df.empty:
        g_display_df = g_display_df[g_display_df['Full Name'].str.contains(g_search_query, case=False)]
        
    if isinstance(g_display_df, pd.DataFrame) and not g_display_df.empty:
        cols_to_export = [c for c in active_display_columns if c in g_display_df.columns] + ['Risk Tier']
        st.download_button(
            label="📥 Download Selected Rows to CSV",
            data=convert_df_to_csv(g_display_df[cols_to_export]),
            file_name=f"Global_Filtered_Extract_{datetime.now().strftime('%Y%m%d')}.csv",
            mime='text/csv',
            key='g_dl_btn'
        )
        st.dataframe(g_display_df[cols_to_export], use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ No matching members found for the selected filter combinations.")

st.markdown("---")

# -----------------------------------------------------------------------------
# 7. RECENT JOINEE SECTION (100% VISUAL & STRUCTURAL SYMMETRY)
# -----------------------------------------------------------------------------
st.header("👶 Recent Joinee Stability Analysis (<6 Months)")
joinee_df = data[data['Is New Joinee'] == True].copy()

if len(joinee_df) > 0:
    total_j = len(joinee_df)
    j_counts = joinee_df['Risk Tier'].value_counts()
    j_green = j_counts.get('Active & Consistent', 0)
    j_yellow = j_counts.get('Slowing Down / At Risk', 0)
    j_red = j_counts.get('Recent Dropout', 0)
    j_crimson = j_counts.get('Chronic / Long-term Drop', 0)

    j_col_m1, j_col_m2, j_col_m3, j_col_m4, j_col_m5 = st.columns(5)
    j_col_m1.metric("Total Recent Joinees", total_j)
    j_col_m2.metric("Consistent (Green)", j_green, delta=f"{(j_green/total_j*100 if total_j else 0):.1f}%")
    j_col_m3.metric("At Risk (Yellow)", j_yellow, delta=f"{(j_yellow/total_j*100 if total_j else 0):.1f}%", delta_color="inverse")
    j_col_m4.metric("Recent Dropouts (Red)", j_red, delta="Action Needed", delta_color="inverse")
    j_col_m5.metric("Long Term Drops", j_crimson, delta="Re-engage Plan", delta_color="inverse")

    st.markdown("<br>", unsafe_allow_html=True)

    j_col1, j_col2 = st.columns([4, 6])
    with j_col1:
        st.markdown("**New Joinee Attendance Distribution Breakdown**")
        j_pie_df = joinee_df['Risk Tier'].value_counts().reset_index()
        j_pie_df.columns = ['Risk Tier', 'Count']
        fig_j_pie = px.pie(j_pie_df, names='Risk Tier', values='Count', color='Risk Tier', color_discrete_map=color_map, hole=0.4)
        fig_j_pie.update_traces(texttemplate='%{percent:.1%}', hovertemplate='%{label}<br>%{value} Count<br>%{percent:.1%}')
        fig_j_pie.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.05))
        st.plotly_chart(fig_j_pie, use_container_width=True)
        
    with j_col2:
        st.markdown("**Recent Joinee Coordinator Performance Audit Matrix**")
        joinee_perf_table = get_coordinator_performance_df(joinee_df)
        if not joinee_perf_table.empty:
            st.dataframe(
                joinee_perf_table.style.map(
                    lambda v: 'background-color: #FEE2E2; color: #991B1B; font-weight: bold;' if v == '⚠️ High Risk Leakage' else '',
                    subset=['Performance Alert Status'] if 'Performance Alert Status' in joinee_perf_table.columns else []
                ),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No records available to evaluate recent joinee coordinator assignments.")
        
    with st.expander("👁️ View Complete Recent Joinee Database Table & Dynamic Category Search"):
        raw_j_selection = st.multiselect(
            "Select Category Statuses to Filter Matrix (New Joinees):", 
            options=list(color_map.keys()), 
            default=list(color_map.keys()),
            key='j_ms'
        )
        selected_j_statuses = raw_j_selection if raw_j_selection is not None else []
        
        j_search_query = st.text_input("🔍 Search Anyone by Name (New Joinees):", placeholder="Type joinee name to trace instantly...", key='j_search')
        
        j_display_df = joinee_df.copy()
        
        if len(selected_j_statuses) > 0:
            j_display_df = j_display_df[j_display_df['Risk Tier'].isin(selected_j_statuses)]
        else:
            j_display_df = pd.DataFrame(columns=joinee_df.columns)
            
        if j_search_query and not j_display_df.empty:
            j_display_df = j_display_df[j_display_df['Full Name'].str.contains(j_search_query, case=False)]
            
        if isinstance(j_display_df, pd.DataFrame) and not j_display_df.empty:
            cols_to_export_j = [c for c in active_display_columns if c in j_display_df.columns] + ['Risk Tier']
            st.download_button(
                label="📥 Download Selected New Joinee Rows to CSV",
                data=convert_df_to_csv(j_display_df[cols_to_export_j]),
                file_name=f"Joinees_Filtered_Extract_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
                key='j_dl_btn'
            )
            st.dataframe(j_display_df[cols_to_export_j], use_container_width=True, hide_index=True)
        else:
            st.warning("⚠️ No matching new joinees found for the selected filter combinations.")
else:
    st.info("No active records found matching entry windows within the last 6 months.")