import streamlit as st
import pandas as pd
import numpy as np
import re
import io

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Inventory Allocation App", layout="wide")
st.title("🧡 CFBNJ Monthly Allocation MyPlate Inventory Preparation Site")

# ==========================================
# HELPER FUNCTIONS (SCRIPT 2)
# ==========================================
def clean_name(desc):
    if pd.isna(desc): return ""
    text = str(desc).lower()
    text = re.sub(r'\bcoop\b|\busda\b|gv\d+|\(.*?\)|\b(and|with|of|the|in|cereal|soup)\b', '', text)
    text = re.sub(r'[^a-z\s]', ' ', text)
    return " ".join(text.split())

def remove_duplicates(df, fbc_col, desc_col, qty_col):
    df = df.copy()
    df['clean_desc'] = df[desc_col].apply(clean_name)
    idx = df.groupby([fbc_col, 'clean_desc'])[qty_col].idxmax()
    return df.loc[idx].drop(columns='clean_desc')

# ==========================================
# STEP 1: INVENTORY CLEANING
# ==========================================
st.header("Step 1: Upload Allocation plan excel extract file from CERES, and please remove headers and footers from the excel")
raw_file = st.file_uploader("Before uploading the Excel please remove the top 2 rows and bottom 2 rows, as they are not part of the requested data. Then upload the Excel file below.", type=["xlsx", "xls"], key="raw_upload")

if raw_file:
    # Reset processing state if a brand new file is uploaded
    if "current_raw_file" not in st.session_state or st.session_state["current_raw_file"] != raw_file.name:
        st.session_state["current_raw_file"] = raw_file.name
        st.session_state['step1_processed'] = False
        st.session_state['buffer_main'] = None
        st.session_state['buffer_soup'] = None

    st.subheader("📁 Name Your Processed Excel Files below")
    col_name1, col_name2 = st.columns(2)
    
    with col_name1:
        custom_main_name = st.text_input(
            "Main Review Inventory Excel Filename:", 
            value="MAY_REVIEW_Inventory",
            help="Type your preferred name for the main review file (Extension will be added automatically)"
        )
    with col_name2:
        custom_soup_name = st.text_input(
            "Soup Kitchen Items Review Inventory Excel Filename:", 
            value="MAY_SoupKitchen_Inventory",
            help="Type your preferred name for the soup kitchen file (Extension will be added automatically)"
        )

    # Automatically clean and append .xlsx extension if missing
    if not custom_main_name.endswith(".xlsx"):
        custom_main_name += ".xlsx"
    if not custom_soup_name.endswith(".xlsx"):
        custom_soup_name += ".xlsx"

    # Action button to trigger processing explicitly
    if st.button("⚙️ Process Raw Inventory Data for Manual review.", type="primary", key="process_raw_btn"):
        with st.spinner("Processing initial inventory data splits..."):
            try:
                df = pd.read_excel(raw_file)
                
                # Exclude Categories
                exclude_categories = [
                    'Fresh Fruits/Vegetables',
                    'Mixed and Assorted Food',
                    'Paper Product -  Household: Plates, Napkins, Towels, Toilet Paper, Facial Tissue, Wipes',
                    'Pasta: Macaroni, Spaghetti, Noodles'
                ]
                if 'FBC Prod. Type Description' in df.columns:
                    df = df[~df['FBC Prod. Type Description'].isin(exclude_categories)]

                # Soup Kitchen Logic
                if 'Allocatable Qty' in df.columns and 'Pack Size' in df.columns:
                    cond_qty_range = df['Allocatable Qty'].between(300, 600)
                    cond_pack_size = df['Pack Size'].astype(str).str.contains(r'/\s*#10\s*cans', case=False, na=False)
                    
                    df_soup_kitchen = df[cond_qty_range | cond_pack_size]
                    df = df[~(cond_qty_range | cond_pack_size)]
                else:
                    df_soup_kitchen = pd.DataFrame()

                # Expiration Logic
                if 'Expires' in df.columns:
                    df['Expires'] = pd.to_datetime(df['Expires'], errors='coerce')
                    today = pd.Timestamp.today().normalize()
                    two_weeks_from_today = today + pd.Timedelta(days=90)
                    df['Expiration Status'] = ''
                    
                    expiring_soon_mask = (df['Expires'].notna() & (df['Expires'] <= two_weeks_from_today))
                    df.loc[expiring_soon_mask, 'Expiration Status'] = 'Expiring in next 90 Days'
                else:
                    df['Expiration Status'] = ''
                    expiring_soon_mask = pd.Series([False]*len(df), index=df.index)

                # Suggested Distribution
                if 'Qty Available' in df.columns:
                    df['Suggested Distribution'] = np.where(
                        expiring_soon_mask, 'Allocate',
                        np.where(df['Qty Available'] > 800, 'Allocate', 'Do Not Select')
                    )
                    df['MAX'] = np.where(df['Qty Available'] > 5000, 5000, df['Qty Available'])
                    df['Allocatable Qty'] = np.where(df['Suggested Distribution'] == 'Allocate', df['MAX'], 0)
                    
                    if 'Unit Wt' in df.columns:
                        df['Allocatable Wt'] = df['Allocatable Qty'] * df['Unit Wt']
                    
                    # Remove non-selected items
                    df = df[df['Allocatable Qty'] != 0]

                # Convert DataFrames to Excel in memory for downloading
                buffer_main = io.BytesIO()
                df.to_excel(buffer_main, index=False)
                buffer_main.seek(0)
                
                buffer_soup = io.BytesIO()
                df_soup_kitchen.to_excel(buffer_soup, index=False)
                buffer_soup.seek(0)
                
                # Cache results in session state so download clicks don't reset the view
                st.session_state['step1_processed'] = True
                st.session_state['buffer_main'] = buffer_main
                st.session_state['buffer_soup'] = buffer_soup
                st.session_state['saved_main_name'] = custom_main_name
                st.session_state['saved_soup_name'] = custom_soup_name

            except Exception as e:
                st.error(f"An error occurred: {e}")

    # Display results if processing cache is active
    if st.session_state.get('step1_processed', False):
        st.success("**Initial processing completed!** 💡Please download both Excel files and review the Product Type categories, the items under each category, and **any items tagged as expiring in 90 days**. Once your review is complete, move to **Step 2**. Keep the reviewed Excel file open side-by-side with this website to easily enter the variety limits and total allocation weight.")
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label=f"📥 Download: {st.session_state['saved_main_name']}", 
                data=st.session_state['buffer_main'], 
                file_name=st.session_state['saved_main_name'], 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col_dl2:
            st.download_button(
                label=f"📥 Download: {st.session_state['saved_soup_name']}", 
                data=st.session_state['buffer_soup'], 
                file_name=st.session_state['saved_soup_name'], 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

st.markdown("---")

# ==========================================
# STEP 2: CONFIGURATION & REVIEW UPLOAD
# ==========================================
st.header("Step 2: Configure Products Variety & Total Allocation (lbs) in the fields below, and then upload the manually reviewed Main Inventory Excel file from Step 1 at the bottom of the page.")
st.info("Review or adjust each Product type variety limits and total allocation lbs by simply entering **number greater then 0 in each box below** or use the + / - buttons. Best Practice is to **open excel side by side** to this website so you can see number of items in each product type")

st.subheader("A. Below you can set the number of item varieties for each Product Type")

# Define Default Parameters
default_limits = {
    "Bread/Bakery: Bread, Biscuits, Rolls, Batter, Tortillas, Pie Crusts": 1,
    "Cereal:  Hot and Cold": 4,
    "Complete Meal/Entree, Soup": 3,
    "Dairy: Yogurt, Cheese, Milk, Butter, Sour cream Ice Cream": 1,
    "Fruit:  Canned and Frozen": 5,
    "Juice: 100% Fruit or Vegetable": 1,
    "Meat/Fish/Poultry": 5,
    "Protein - Non-Meat: Peanut Butter, Beans, Eggs, Pork & Beans, Nuts": 4,
    "Vegetables - Canned & Frozen": 5,
    "Rice": 2, 
    "Spice/Condiment/Sauce: Herbs, Salt, Sugar, Mixes, Vinegar, Extracts, Mustard, Syrup, Gravy, Jelly, Sauces, Salad Oil" : 4
}

base_allocation_map = {
    "Bread/Bakery: Bread, Biscuits, Rolls, Batter, Tortillas, Pie Crusts": 0.05,
    "Cereal:  Hot and Cold": 0.10,
    "Complete Meal/Entree, Soup": 0.15,
    "Dairy: Yogurt, Cheese, Milk, Butter, Sour cream Ice Cream": 0.05,
    "Fruit:  Canned and Frozen": 0.10,
    "Juice: 100% Fruit or Vegetable": 0.05,
    "Meat/Fish/Poultry": 0.10,
    "Protein - Non-Meat: Peanut Butter, Beans, Eggs, Pork & Beans, Nuts": 0.13,
    "Rice": 0.05,
    "Spice/Condiment/Sauce: Herbs, Salt, Sugar, Mixes, Vinegar, Extracts, Mustard, Syrup, Gravy, Jelly, Sauces, Salad Oil": 0.07,
    "Vegetables - Canned & Frozen": 0.15
}

user_limits = {}

# Layout adjustment columns
col_limits, col_targets = st.columns([2, 1])

with col_limits:
    st.write("**💡 Important Note:** Items expiring within 90 days are automatically added to the variety count, enrty below represents the additional varieties to select, not the final total.")
    st.markdown(
        "Example: You have 6 Cereal items and 1 is tagged as expiring within 90 days in excel file. "
        "SO if you enter 4 variety for Cereal, the final allocation will include 5 Cereal items"
        " because **4 were selected based on entry + 1 automatically included expiring item from excel uploaded below.**"
    )
    for cat, default_val in default_limits.items():
        short_label = cat.split(':')[0].split('-')[0].strip()
        # All limits are now fully unlocked and editable
        user_limits[cat] = st.number_input(
            f"{short_label} Limit", 
            min_value=1, 
            max_value=20, 
            value=default_val, 
            disabled=False,
            help=cat,
            key=f"input_{short_label}"
        )

with col_targets:
    st.write("**CFBNJ MyPlate Target Distributions**")
    
    # Initialize editable targets framework inside session state for stability
    if 'target_df_init' not in st.session_state:
        init_data = []
        for full_cat, pct in base_allocation_map.items():
            short_label = full_cat.split(':')[0].split('-')[0].strip()
            init_data.append({
                "Full_Category": full_cat,
                "Category": short_label,
                "Target %": round(pct * 100, 2)  # Resolves float precision anomaly (e.g. 7.000000000000001%)
            })
        st.session_state['target_df_init'] = pd.DataFrame(init_data)
        
    # Render table as an editable data frame
    edited_target_df = st.data_editor(
        st.session_state['target_df_init'],
        column_config={
            "Full_Category": None,  # Keep full category text hidden from frontend view
            "Category": st.column_config.TextColumn("Category", disabled=True),
            "Target %": st.column_config.NumberColumn("Target %", min_value=0.0, max_value=100.0, step=0.5, format="%.2f%%")
        },
        hide_index=True,
        use_container_width=True,
        key="target_editor"
    )
    
    # Build dynamic allocation map mapped directly back to optimization engine formulas
    dynamic_allocation_map = {
        row['Full_Category']: row['Target %'] / 100.0 for _, row in edited_target_df.iterrows()
    }

st.markdown("---")
st.subheader("2. Set Total Lbs Targeted for Allocation & then please upload Excel File")

# Dynamic Target Weight Input Field
final_weight_target = st.number_input(
    "Set Total Target Weight Goal (Lbs)",
    min_value=10000,
    max_value=10000000,
    value=2700000,
    step=50000,
    format="%d",
    help="Adjust the total baseline volume of food to distribute. The engine uses this value to run the MyPlate percentage breakdown."
)

reviewed_file = st.file_uploader("Upload the Reviewed Main Inventory (Excel)", type=["xlsx", "xls"], key="reviewed_upload")

if reviewed_file:
    # Reset processing state if a brand new reviewed file is uploaded
    if "current_reviewed_file" not in st.session_state or st.session_state["current_reviewed_file"] != reviewed_file.name:
        st.session_state["current_reviewed_file"] = reviewed_file.name
        st.session_state['step2_processed'] = False
        st.session_state['buffer_final'] = None

    st.subheader("🌟 Name Your Final Item Prep Allocation File")
    custom_final_name = st.text_input(
        "Final MyPlate Allocation Filename:",
        value="May_OurPlate_SetUp",
        help="Type your preferred name for the balanced setup distribution export."
    )
    
    if not custom_final_name.endswith(".xlsx"):
        custom_final_name += ".xlsx"

    if st.button("🚀 Run MyPlate Inventory Process", type="primary"):
        with st.spinner("Processing optimization parameters..."):
            try:
                df_alloc = pd.read_excel(reviewed_file)
                df_alloc.columns = df_alloc.columns.str.strip()
                
                desc_col, fbc_col, qty_col = 'Description.', 'FBC Prod. Type Description', 'Allocatable Qty'
                avail_col, wt_col, unit_wt_col, exp_col = 'Qty Available', 'Allocatable Wt', 'Unit Wt', 'Expiration Status'

                for col in [qty_col, avail_col, wt_col, unit_wt_col]:
                    df_alloc[col] = pd.to_numeric(df_alloc[col], errors='coerce').fillna(0)

                MIN_ALLOC_QTY = 825
                MAX_ALLOC_QTY = 5000

                expiring_items = df_alloc[df_alloc[exp_col].astype(str).str.strip() == "Expiring in next 90 Days"].copy()
                normal_items = df_alloc[~df_alloc.index.isin(expiring_items.index)].copy()
                normal_items = remove_duplicates(normal_items, fbc_col, desc_col, qty_col)
                
                allocated_rows = []

                # PASS 1: TARGET ALIGNMENT (Now using dynamic_allocation_map inputs)
                for category, pct in dynamic_allocation_map.items():
                    cat_goal_wt = final_weight_target * pct
                    cat_exp = expiring_items[expiring_items[fbc_col] == category].copy()
                    cat_norm = normal_items[normal_items[fbc_col] == category].copy()
                    
                    limit = user_limits.get(category, 99)
                    cat_norm = cat_norm.sort_values(by=avail_col, ascending=False).head(limit)
                    
                    category_batch = []
                    for _, row in cat_exp.iterrows():
                        row['Can_Grow'] = False
                        row['Note'] = "Priority: Expiring"
                        category_batch.append(row)
                        
                    for _, row in cat_norm.iterrows():
                        row[qty_col] = min(MIN_ALLOC_QTY, row[avail_col])
                        row['Can_Grow'] = True
                        row['Note'] = "Standard MyPlate"
                        category_batch.append(row)
                        
                    if not category_batch: continue
                    cat_df = pd.DataFrame(category_batch)

                    for _ in range(10):
                        current_wt = (cat_df[qty_col] * cat_df[unit_wt_col]).sum()
                        gap = cat_goal_wt - current_wt
                        if gap <= 0: break 
                        
                        grow_mask = (cat_df['Can_Grow']) & (cat_df[qty_col] < cat_df[avail_col]) & (cat_df[qty_col] < MAX_ALLOC_QTY)
                        tunable_wt = (cat_df.loc[grow_mask, qty_col] * cat_df.loc[grow_mask, unit_wt_col]).sum()
                        if tunable_wt <= 0: break
                        
                        stretch = (tunable_wt + gap) / tunable_wt
                        cat_df.loc[grow_mask, qty_col] = (cat_df.loc[grow_mask, qty_col] * stretch).round()
                        cat_df.loc[grow_mask, qty_col] = np.minimum(cat_df.loc[grow_mask, qty_col], cat_df.loc[grow_mask, avail_col])
                        cat_df.loc[grow_mask, qty_col] = np.minimum(cat_df.loc[grow_mask, qty_col], MAX_ALLOC_QTY)

                    allocated_rows.extend(cat_df.to_dict('records'))

                res_df = pd.DataFrame(allocated_rows)

                # PASS 2: CORRECTION MATRIX
                for _ in range(15):
                    res_df[wt_col] = res_df[qty_col] * res_df[unit_wt_col]
                    total_gap = final_weight_target - res_df[wt_col].sum()
                    if total_gap <= 100: break 
                    
                    grow_mask = (res_df[qty_col] < res_df[avail_col]) & (res_df[qty_col] < MAX_ALLOC_QTY)
                    tunable_wt = (res_df.loc[grow_mask, qty_col] * res_df.loc[grow_mask, unit_wt_col]).sum()
                    if tunable_wt <= 0: break 
                    
                    stretch = (tunable_wt + total_gap) / tunable_wt
                    res_df.loc[grow_mask, qty_col] = (res_df.loc[grow_mask, qty_col] * stretch).round()
                    res_df.loc[grow_mask, qty_col] = np.minimum(res_df.loc[grow_mask, qty_col], res_df.loc[grow_mask, avail_col])
                    res_df.loc[grow_mask, qty_col] = np.minimum(res_df.loc[grow_mask, qty_col], MAX_ALLOC_QTY)
                    res_df.loc[grow_mask, 'Note'] = res_df.loc[grow_mask, 'Note'].astype(str) + " + Overflow"

                res_df[wt_col] = res_df[qty_col] * res_df[unit_wt_col]
                final_weight = res_df[wt_col].sum()

                # Packaging final output dataset
                buffer_final = io.BytesIO()
                res_df.to_excel(buffer_final, index=False)
                buffer_final.seek(0)
                
                # Cache results for Step 2
                st.session_state['step2_processed'] = True
                st.session_state['buffer_final'] = buffer_final
                st.session_state['saved_final_name'] = custom_final_name
                st.session_state['final_weight'] = final_weight

            except Exception as e:
                st.error(f"An error occurred during allocation processing: {e}")

    # Display results if processing cache is active for Step 2
    if st.session_state.get('step2_processed', False):
        st.success(f"Allocation Complete! Final Expected Weight: **{st.session_state['final_weight']:,.0f} lbs** (Target: {final_weight_target:,.0f} lbs) **The final allocation may be below the target based on available inventory and the selected variety numbers**")
        st.download_button(
            label=f"🌟 Download Final Myplate Inventory for Allocation: {st.session_state['saved_final_name']}", 
            data=st.session_state['buffer_final'], 
            file_name=st.session_state['saved_final_name'], 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
