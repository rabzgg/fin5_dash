import streamlit as st
import pandas as pd
import plotly.express as px

# --- Setup Page ---
st.set_page_config(page_title="ESG Greenwashing Detector", layout="wide")
st.title("💸 The Greenwashing Detector")
st.subheader("Are German CEOs Paid for Real Impact or Just Good PR?")

# --- 1. Load Data ---
@st.cache_data
def load_data():
    # Load Excel files, skipping the first two rows (header=2) to get the actual column names
    df_2023 = pd.read_excel("Executive_Compensation_ESG_2023.xlsx", header=2)
    df_2024 = pd.read_excel("Executive_Compensation_ESG_2024.xlsx", header=2)
    
    # Combine 2023 and 2024 data
    df = pd.concat([df_2023, df_2024], ignore_index=True)
    
    # Clean up data types (convert to numeric for the columns we need)
    cols_to_numeric = ['STI_total_ESG_Share', 'STI_Zielerreichung', 'STI_count_of_total_ESG_KPI']
    for col in cols_to_numeric:
        if col in df.columns:
            # Convert to string to safely use regex, then extract numbers/decimals
            df[col] = df[col].astype(str).replace(r'[^0-9\.-]', '', regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # FIX FOR SCATTER PLOT: 
            # If achievement is measured in decimals (e.g., 1.5 instead of 150), multiply by 100
            if col == 'STI_Zielerreichung':
                # Only multiply if the max value in the column is suspiciously low (e.g., < 3)
                if df[col].max() <= 5: 
                    df[col] = df[col] * 100
        
    return df

df = load_data()

# --- 2. Sidebar Filters ---
st.sidebar.header("Filter Data")
selected_year = st.sidebar.multiselect("Select Year", df['year'].dropna().unique(), default=df['year'].dropna().unique())
selected_index = st.sidebar.multiselect("Select Index", df['cindex'].dropna().unique(), default=df['cindex'].dropna().unique())

# Apply filters
filtered_df = df[(df['year'].isin(selected_year)) & (df['cindex'].isin(selected_index))]

# --- 3. The Hook: Big Numbers ---
st.markdown("---")
col1, col2, col3 = st.columns(3)

# Filter out NaNs for accurate calculations
valid_esg_share = filtered_df['STI_total_ESG_Share'].dropna()
valid_achievement = filtered_df['STI_Zielerreichung'].dropna()

with col1:
    avg_esg_share = valid_esg_share.mean() if not valid_esg_share.empty else 0
    st.metric("Avg ESG Weight in Bonus", f"{avg_esg_share:.1f}%", help="Average percentage of short-term bonus (STI) tied to ESG metrics.")
with col2:
    overachievers = len(valid_achievement[valid_achievement >= 100])
    total_firms = len(valid_achievement)
    pct_overachieve = (overachievers / total_firms * 100) if total_firms > 0 else 0
    st.metric("ESG Target Hit Rate (≥100%)", f"{pct_overachieve:.1f}%", help="Percentage of companies that hit or exceeded their ESG targets.")
with col3:
    st.metric("Companies Analyzed", f"{len(filtered_df['cnameshort'].dropna().unique())}")

# --- 4. The Evidence: Bullshit Meter (Scatter Plot) ---
st.markdown("---")
st.markdown("### 🎯 The 'Bullshit Meter': Weight vs Achievement")
st.markdown("*If the ESG weight is high but targets are always maxed out, are the goals too easy?*")

# Prepare data for plotting
plot_df = filtered_df.dropna(subset=['STI_total_ESG_Share', 'STI_Zielerreichung'])

# Optional: Filter out ridiculous outliers (e.g., data entry typos > 500%)
plot_df = plot_df[(plot_df['STI_total_ESG_Share'] <= 100) & (plot_df['STI_Zielerreichung'] <= 300)]

if not plot_df.empty:
    fig = px.scatter(
        plot_df, 
        x='STI_total_ESG_Share', 
        y='STI_Zielerreichung',
        hover_name='cnameshort',
        hover_data=['year', 'cindex'],
        color='cindex',
        opacity=0.7, # <--- THIS makes overlapping zeros visible!
        labels={
            "STI_total_ESG_Share": "ESG Share in Bonus (%)",
            "STI_Zielerreichung": "Target Achievement (%)"
        },
        template="plotly_dark"
    )
    
    # Add a reference line for 100% achievement
    fig.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="100% Target Hit")
    
    # FORCING THE AXES TO REALISTIC RANGES
    fig.update_layout(
        xaxis=dict(range=[-5, 105], title="ESG Share in Bonus (%)"), # Max bonus weight is 100%
        yaxis=dict(range=[-10, 250], title="Target Achievement (%)"), # Max achievement is usually ~200%
        margin=dict(l=40, r=40, t=40, b=40)
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Not enough data to generate the scatter plot with the current filters.")

# --- 5. The Outliers: Data Table ---
st.markdown("---")
st.markdown("### 🔍 Deep Dive: The Data")
# Select key columns to keep the table clean
display_cols = ['cnameshort', 'year', 'cindex', 'STI_total_ESG_Share', 'STI_Zielerreichung', 'STI_count_of_total_ESG_KPI']

# Ensure the columns exist before displaying to prevent errors
existing_cols = [col for col in display_cols if col in filtered_df.columns]
clean_table_df = filtered_df[existing_cols].dropna(subset=['STI_Zielerreichung']).sort_values(by='STI_Zielerreichung', ascending=False)

st.dataframe(clean_table_df, use_container_width=True)