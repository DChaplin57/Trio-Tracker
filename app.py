import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
from st_supabase_connection import SupabaseConnection

# --- PAGE CONFIG & STYLING ---
st.set_page_config(page_title="Trio Weight Tracker", page_icon="🥗", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #F8F9FA; }
    h1 { color: #1E3A8A; font-weight: 800; text-align: center; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #0D9488 !important; font-weight: 700; }
    .highlight-card {
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
        color: white; padding: 18px; border-radius: 12px; margin-bottom: 15px;
    }
    .stButton>button { border-radius: 8px; background-color: #2563EB; color: white; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# --- SUPABASE CONNECTION ---
st_supabase = st.connection("supabase", type=SupabaseConnection)

# --- HELPER FUNCTIONS ---
def st_lbs_to_kg(st_val, lbs_val):
    return (float(st_val) * 6.35029318) + (float(lbs_val) * 0.45359237)

def kg_to_st_lbs(kg_val):
    total_lbs = float(kg_val) * 2.20462262
    stones = int(total_lbs // 14)
    pounds = round(total_lbs % 14, 1)
    return stones, pounds

def calculate_daily_target(gender, age, height_cm, start_weight_kg, target_weight_kg, start_date_str, target_date_str, activity_mult):
    if gender == "Male":
        bmr = (10 * start_weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:
        bmr = (10 * start_weight_kg) + (6.25 * height_cm) - (5 * age) - 161
    
    tdee = bmr * activity_mult
    d1 = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    d2 = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    total_days = max((d2 - d1).days, 1)
    
    total_deficit = (start_weight_kg - target_weight_kg) * 7700
    daily_deficit = total_deficit / total_days
    return max(tdee - daily_deficit, 1200.0)

# --- HEADER & SIDEBAR PROFILE SELECTION ---
st.title("🥗 Trio Weight Tracker")

try:
    existing_profiles = st_supabase.client.from_("profiles").select("user_name").execute()
    profile_names = [p['user_name'] for p in existing_profiles.data] if existing_profiles.data else ["User 1"]
except Exception:
    profile_names = ["User 1"]

profile_options = profile_names + ["+ Create New Profile"]
selected_option = st.sidebar.selectbox("👤 Select Active Profile", profile_options, key="active_profile_select")

if selected_option == "+ Create New Profile":
    current_user = st.sidebar.text_input("Enter New Profile Name", value="New User", key="new_profile_name_input")
else:
    current_user = selected_option

# --- TAB SETUP ---
tabs = st.tabs([
    "📊 Daily Log", 
    "📈 Progress & Graphs", 
    "📖 Shared Food Library", 
    "🍳 Recipe Builder", 
    "⚙️ Profile Settings"
])

# ==========================================
# TAB 0: DAILY LOG
# ==========================================
with tabs[0]:
    selected_date = st.date_input("Select Date", date.today(), key="log_date_picker")
    date_str = selected_date.strftime("%Y-%m-%d")
    
    daily_target = 2000.0
    try:
        profile_res = st_supabase.client.from_("profiles").select("*").eq("user_name", current_user).execute()
        if profile_res.data:
            p = profile_res.data[0]
            daily_target = calculate_daily_target(
                p['gender'], p['age'], p['height_cm'], p['start_weight_kg'], 
                p['target_weight_kg'], p['start_date'], p['target_date'], p['activity_multiplier']
            )
    except Exception:
        pass

    logs_df = pd.DataFrame()
    consumed_cals = 0.0
    try:
        logs_res = st_supabase.client.from_("daily_logs").select("*").eq("log_date", date_str).eq("user_name", current_user).execute()
        if logs_res.data:
            logs_df = pd.DataFrame(logs_res.data)
            consumed_cals = logs_df['calories'].sum()
    except Exception as e:
        st.error(f"Error loading daily entries: {e}")

    st.markdown(f"""
        <div class="highlight-card">
            <h4 style="margin:0; opacity:0.9;">Target for {current_user}</h4>
            <h2 style="margin:5px 0 0 0; font-weight:800;">{int(daily_target)} kcal / day</h2>
        </div>
    """, unsafe_allow_html=True)

    st.progress(min(consumed_cals / daily_target, 1.0) if daily_target > 0 else 0)
    col1, col2 = st.columns(2)
    col1.metric("Consumed", f"{int(consumed_cals)} kcal")
    col2.metric("Remaining", f"{int(daily_target - consumed_cals)} kcal")

    st.markdown("---")
    
    st.subheader("📊 Category Running Totals")
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    categories = ["Breakfast", "Lunch", "Dinner", "Snacks"]
    
    cat_totals = {cat: 0.0 for cat in categories}
    if not logs_df.empty and 'meal_type' in logs_df.columns:
        for cat in categories:
            cat_totals[cat] = logs_df[logs_df['meal_type'] == cat]['calories'].sum()

    m_col1.metric("🍳 Breakfast", f"{int(cat_totals['Breakfast'])} kcal")
    m_col2.metric("🥗 Lunch", f"{int(cat_totals['Lunch'])} kcal")
    m_col3.metric("🍽️ Dinner", f"{int(cat_totals['Dinner'])} kcal")
    m_col4.metric("🥨 Snacks", f"{int(cat_totals['Snacks'])} kcal")

    st.markdown("---")

    with st.expander("⚡ Add Quick / Unassigned Calories"):
        c_desc, c_kcal, c_meal = st.columns([2, 1, 1])
        q_desc = c_desc.text_input("Description", value="Quick Calorie Item", key="q_desc_input")
        q_cal = c_kcal.number_input("Calories (kcal)", min_value=1, value=200, key="q_cal_input")
        q_type = c_meal.selectbox("Meal Category", categories, key="q_meal_select")
        if st.button("Add Quick Entry", key="q_add_btn"):
            try:
                st_supabase.client.from_("daily_logs").insert({
                    "log_date": date_str, "user_name": current_user, 
                    "food_name": q_desc, "portion_g": 0.0, "calories": float(q_cal), "meal_type": q_type
                }).execute()
                st.success(f"Added {q_cal} kcal to {q_type}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to log item: {e}")

    st.subheader("➕ Log Food Entry")
    try:
        foods_res = st_supabase.client.from_("food_library").select("*").execute()
        if foods_res.data:
            foods_df = pd.DataFrame(foods_res.data)
            
            col_f, col_m = st.columns([2, 1])
            selected_food = col_f.selectbox("Food Item", foods_df['food_name'].tolist(), key="log_food_select")
            meal_cat = col_m.selectbox("Category", categories, key="log_category_select")
            
            food_row = foods_df[foods_df['food_name'] == selected_food].iloc[0]
            log_mode = st.radio("Log By", ["Portion/Serving", "Exact Weight (grams)"], horizontal=True, key="log_mode_radio")
            
            if log_mode == "Portion/Serving":
                p_name = food_row.get('default_portion_name', 'serving')
                p_qty = st.number_input(f"Number of Portions ({p_name})", min_value=0.25, value=1.0, step=0.25, key="p_qty_input")
                logged_cal = (float(food_row['calories_per_100g']) / 100.0) * (float(food_row.get('portion_grams', 100.0)) * p_qty)
                portion_desc = f"{p_qty} {p_name}"
            else:
                grams = st.number_input("Weight (g)", min_value=1.0, value=100.0, key="grams_qty_input")
                logged_cal = (float(food_row['calories_per_100g']) / 100.0) * grams
                portion_desc = f"{grams}g"

            if st.button("Add to Daily Log", key="add_daily_log_btn"):
                st_supabase.client.from_("daily_logs").insert({
                    "log_date": date_str, 
                    "user_name": current_user, 
                    "food_name": f"{selected_food} ({portion_desc})", 
                    "portion_g": 0.0, 
                    "calories": float(logged_cal), 
                    "meal_type": meal_cat
                }).execute()
                st.success(f"Added {selected_food} ({int(logged_cal)} kcal)")
                st.rerun()
        else:
            st.info("Your food library is empty. Add or search items in the 'Shared Food Library' tab.")
    except Exception as e:
        st.error(f"Error accessing library: {e}")

    if not logs_df.empty:
        st.markdown("---")
        st.subheader("Today's Breakdown")
        for category in categories:
            cat_df = logs_df[logs_df['meal_type'] == category] if 'meal_type' in logs_df.columns else pd.DataFrame()
            if not cat_df.empty:
                st.markdown(f"**{category}** — *{int(cat_df['calories'].sum())} kcal*")
                st.dataframe(cat_df[['food_name', 'calories']], use_container_width=True)

# ==========================================
# TAB 1: PROGRESS & GRAPHS
# ==========================================
with tabs[1]:
    st.subheader(f"📈 Progress Tracking: {current_user}")
    st.markdown("### 📝 Record Weight Entry")
    w_unit = st.radio("Input Unit", ["kg", "stone & lbs"], horizontal=True, key="w_log_unit_radio")
    
    with st.form("log_weight_form", clear_on_submit=True):
        w_date = st.date_input("Date", date.today(), key="w_date_input")
        
        if w_unit == "kg":
            w_val = st.number_input("Recorded Weight (kg)", min_value=30.0, max_value=250.0, value=85.0, step=0.1, key="w_kg_input")
            final_kg = w_val
        else:
            col_st, col_lbs = st.columns(2)
            st_val = col_st.number_input("Stone", min_value=4, max_value=40, value=13, key="w_st_input")
            lbs_val = col_lbs.number_input("Pounds", min_value=0.0, max_value=13.9, value=5.0, step=0.5, key="w_lbs_input")
            final_kg = st_lbs_to_kg(st_val, lbs_val)
            
        if st.form_submit_button("Log Weight Entry"):
            try:
                st_supabase.client.from_("weight_logs").insert({
                    "log_date": w_date.strftime("%Y-%m-%d"),
                    "user_name": current_user,
                    "weight_kg": final_kg
                }).execute()
                st.success(f"Weight logged ({round(final_kg, 1)} kg)!")
                st.rerun()
            except Exception as e:
                st.error(f"Error logging weight: {e}")

    st.markdown("---")
    
    try:
        w_res = st_supabase.client.from_("weight_logs").select("*").eq("user_name", current_user).execute()
        prof_res = st_supabase.client.from_("profiles").select("*").eq("user_name", current_user).execute()
        
        if w_res.data:
            w_df = pd.DataFrame(w_res.data).sort_values("log_date")
            latest_kg = w_df.iloc[-1]["weight_kg"]
            l_st, l_lbs = kg_to_st_lbs(latest_kg)
            
            target_kg = None
            bmi_val = None
            bmi_status = ""
            
            if prof_res.data:
                p_data = prof_res.data[0]
                target_kg = float(p_data.get("target_weight_kg", 0.0)) if p_data.get("target_weight_kg") else None
                
                if "height_cm" in p_data and float(p_data["height_cm"]) > 0:
                    height_m = float(p_data["height_cm"]) / 100.0
                    bmi_val = round(latest_kg / (height_m ** 2), 1)
                    if bmi_val < 18.5:
                        bmi_status = "Underweight"
                    elif 18.5 <= bmi_val < 25.0:
                        bmi_status = "Normal weight"
                    elif 25.0 <= bmi_val < 30.0:
                        bmi_status = "Overweight"
                    else:
                        bmi_status = "Obese"

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Latest Weight", f"{round(latest_kg, 1)} kg")
            col_m2.metric("Latest Weight (st/lbs)", f"{l_st}st {l_lbs}lbs")
            col_m3.metric("Current BMI", f"{bmi_val}" if bmi_val else "N/A", delta=bmi_status if bmi_status else None)

            st.markdown("---")

            col_g1, col_g2 = st.columns([2, 1])
            col_g1.markdown("### Weight Trend vs Target")
            graph_unit = col_g2.selectbox("Graph Y-Axis Unit", ["Kilograms (kg)", "Total Stones (st)", "Total Pounds (lbs)"], key="graph_unit_select")
            
            if graph_unit == "Kilograms (kg)":
                w_df["Actual Weight"] = w_df["weight_kg"]
                if target_kg: w_df["Target Goal"] = target_kg
            elif graph_unit == "Total Stones (st)":
                w_df["Actual Weight"] = w_df["weight_kg"] * 0.157473
                if target_kg: w_df["Target Goal"] = target_kg * 0.157473
            else:
                w_df["Actual Weight"] = w_df["weight_kg"] * 2.20462
                if target_kg: w_df["Target Goal"] = target_kg * 2.20462
                
            chart_cols = ["Actual Weight", "Target Goal"] if target_kg else ["Actual Weight"]
            st.line_chart(w_df.set_index("log_date")[chart_cols])
        else:
            st.info("No weight entries recorded yet.")
    except Exception as e:
        st.error(f"Error generating progress graphs: {e}")

# ==========================================
# TAB 2: SHARED FOOD LIBRARY
# ==========================================
with tabs[2]:
    st.subheader("📖 Shared Household Food Library")
    
    lib_tab1, lib_tab2 = st.tabs(["🔍 Search UK Supermarket Database", "➕ Add Custom Item Manually"])
    
    with lib_tab1:
        st.markdown("##### Search over 300,000+ UK products (Tesco, Sainsbury's, Asda, etc.)")
        search_query = st.text_input("Product or Brand Name (e.g. Warburtons Toastie, Heinz Beans)", key="off_search_input")
        
        if search_query:
            with st.spinner("Searching UK database..."):
                url = f"https://uk.openfoodfacts.org/cgi/search.pl?search_terms={search_query}&search_simple=1&action=process&json=1&page_size=10"
                try:
                    res = requests.get(url, headers={"User-Agent": "TrioTracker - Streamlit - Version 1.0"}).json()
                    products = res.get("products", [])
                    
                    if products:
                        for prod in products:
                            p_name = prod.get("product_name", "Unknown Item")
                            p_brand = prod.get("brands", "")
                            nutriments = prod.get("nutriments", {})
                            cals_100g = nutriments.get("energy-kcal_100g", 0)
                            
                            if cals_100g and p_name != "Unknown Item":
                                display_title = f"{p_brand} - {p_name}" if p_brand else p_name
                                c1, c2, c3 = st.columns([3, 2, 1])
                                c1.write(f"**{display_title}**")
                                c2.write(f"{int(cals_100g)} kcal / 100g")
                                
                                if c3.button("Import", key=f"import_off_{prod.get('_id', p_name)}"):
                                    st_supabase.client.from_("food_library").upsert({
                                        "food_name": display_title[:100],
                                        "calories_per_100g": float(cals_100g),
                                        "default_portion_name": "serving",
                                        "portion_grams": 100.0
                                    }, on_conflict="food_name").execute()
                                    st.success(f"Added '{display_title}' to Master Library!")
                                    st.rerun()
                    else:
                        st.info("No matching products found. Try a broader search term.")
                except Exception as e:
                    st.error(f"Search service error: {e}")

    with lib_tab2:
        with st.form("add_custom_food_form", clear_on_submit=True):
            fname = st.text_input("Food Item Name", key="custom_fname_input")
            fcal = st.number_input("Calories per 100g", min_value=0.0, key="custom_fcal_input")
            pname = st.text_input("Portion Description (e.g. 1 slice, 1 bar)", value="serving", key="custom_pname_input")
            pgrams = st.number_input("Portion Weight in Grams", min_value=1.0, value=100.0, key="custom_pgrams_input")
            
            if st.form_submit_button("Save Custom Item") and fname:
                try:
                    st_supabase.client.from_("food_library").upsert({
                        "food_name": fname, 
                        "calories_per_100g": fcal,
                        "default_portion_name": pname, 
                        "portion_grams": pgrams
                    }, on_conflict="food_name").execute()
                    st.success(f"Saved '{fname}'!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving item: {e}")

    st.markdown("---")
    st.subheader("📚 Saved Household Food Library")
    try:
        master_res = st_supabase.client.from_("food_library").select("*").execute()
        if master_res.data:
            df_master = pd.DataFrame(master_res.data)
            st.dataframe(df_master, use_container_width=True)
        else:
            st.info("No items in the food library yet. Import or add items above.")
    except Exception as e:
        st.error(f"Error loading food library: {e}")

# ==========================================
# TAB 3: RECIPE BUILDER
# ==========================================
with tabs[3]:
    st.subheader("🍳 Recipe Builder")
    recipe_name = st.text_input("Recipe Name", key="recipe_name_input")
    servings = st.number_input("Servings", min_value=1.0, value=4.0, key="recipe_servings_input")
    
    try:
        foods_res = st_supabase.client.from_("food_library").select("*").execute()
        if foods_res.data:
            available_foods = pd.DataFrame(foods_res.data)
            if 'recipe_items' not in st.session_state:
                st.session_state.recipe_items = []

            c_ing, c_qty, c_btn = st.columns([2, 1, 1])
            ing = c_ing.selectbox("Select Ingredient", available_foods['food_name'].tolist(), key="recipe_ing_select")
            qty = c_qty.number_input("Weight (g)", min_value=1.0, value=100.0, key="recipe_qty_input")
            
            if c_btn.button("Add Ingredient", key="add_ing_to_recipe_btn"):
                c100 = available_foods[available_foods['food_name'] == ing]['calories_per_100g'].values[0]
                st.session_state.recipe_items.append({'item': ing, 'grams': qty, 'cals': (float(c100) / 100.0) * qty})

            if st.session_state.recipe_items:
                recipe_df = pd.DataFrame(st.session_state.recipe_items)
                st.table(recipe_df)
                tot_cals = recipe_df['cals'].sum()
                per_portion = tot_cals / servings
                st.info(f"**Total Energy:** {int(tot_cals)} kcal | **Energy per Serving:** {int(per_portion)} kcal")
                
                if st.button("Save Recipe to Food Library", key="save_recipe_to_lib_btn") and recipe_name:
                    st_supabase.client.from_("food_library").upsert({
                        "food_name": recipe_name, 
                        "calories_per_100g": per_portion,
                        "default_portion_name": "1 portion", 
                        "portion_grams": 100.0
                    }, on_conflict="food_name").execute()
                    st.session_state.recipe_items = []
                    st.success(f"Recipe '{recipe_name}' stored in Master Library!")
                    st.rerun()
        else:
            st.info("Populate your food library first to build composite recipes.")
    except Exception as e:
        st.error(f"Error in Recipe Builder: {e}")

# ==========================================
# TAB 4: PROFILE SETTINGS & EXPORT
# ==========================================
with tabs[4]:
    st.subheader(f"⚙️ Profile Settings: {current_user}")
    
    p_curr = {}
    try:
        prof_data = st_supabase.client.from_("profiles").select("*").eq("user_name", current_user).execute().data
        if prof_data: p_curr = prof_data[0]
    except Exception:
        pass

    with st.form("profile_settings_form"):
        new_name = st.text_input("Profile Display Name", value=current_user, key="p_name_input")
        u_gender = st.selectbox("Biological Sex", ["Female", "Male"], index=0 if p_curr.get("gender") == "Female" else 1, key="p_gender_select")
        u_age = st.number_input("Age", min_value=10, max_value=120, value=int(p_curr.get("age", 40)), key="p_age_input")
        u_height = st.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=float(p_curr.get("height_cm", 175.0)), key="p_height_input")
        
        p_unit = st.radio("Preferred Weight Unit", ["kg", "stone & lbs"], horizontal=True, key="p_unit_radio")
        
        start_kg_curr = float(p_curr.get("start_weight_kg", 85.0))
        target_kg_curr = float(p_curr.get("target_weight_kg", 75.0))
        
        if p_unit == "kg":
            u_start_wt = st.number_input("Starting Weight (kg)", min_value=30.0, max_value=300.0, value=start_kg_curr, step=0.5, key="p_start_kg_input")
            u_target_wt = st.number_input("Target Weight (kg)", min_value=30.0, max_value=300.0, value=target_kg_curr, step=0.5, key="p_target_kg_input")
        else:
            s_st, s_lbs = kg_to_st_lbs(start_kg_curr)
            t_st, t_lbs = kg_to_st_lbs(target_kg_curr)
            
            st.markdown("**Starting Weight**")
            col_s1, col_s2 = st.columns(2)
            u_s_st = col_s1.number_input("Start Stone", min_value=4, max_value=40, value=s_st, key="p_s_st_input")
            u_s_lbs = col_s2.number_input("Start Pounds", min_value=0.0, max_value=13.9, value=s_lbs, step=0.5, key="p_s_lbs_input")
            u_start_wt = st_lbs_to_kg(u_s_st, u_s_lbs)
            
            st.markdown("**Target Weight**")
            col_t1, col_t2 = st.columns(2)
            u_t_st = col_t1.number_input("Target Stone", min_value=4, max_value=40, value=t_st, key="p_t_st_input")
            u_t_lbs = col_t2.number_input("Target Pounds", min_value=0.0, max_value=13.9, value=t_lbs, step=0.5, key="p_t_lbs_input")
            u_target_wt = st_lbs_to_kg(u_t_st, u_t_lbs)

        u_start_dt = st.date_input("Start Date", value=datetime.strptime(p_curr.get("start_date", str(date.today())), "%Y-%m-%d").date(), key="p_start_dt_input")
        u_target_dt = st.date_input("Target End Date", value=datetime.strptime(p_curr.get("target_date", str(date.today())), "%Y-%m-%d").date(), key="p_target_dt_input")
        
        act_opts = {
            "Sedentary (Little/no exercise)": 1.2,
            "Lightly Active (1-3 days/week)": 1.375,
            "Moderately Active (3-5 days/week)": 1.55,
            "Very Active (6-7 days/week)": 1.725
        }
        u_act = st.selectbox("Activity Level", list(act_opts.keys()), key="p_act_select")
        
        if st.form_submit_button("Save Parameters"):
            try:
                st_supabase.client.from_("profiles").upsert({
                    "user_name": new_name, 
                    "gender": u_gender, 
                    "age": u_age,
                    "height_cm": u_height, 
                    "start_weight_kg": u_start_wt, 
                    "target_weight_kg": u_target_wt,
                    "start_date": u_start_dt.strftime("%Y-%m-%d"), 
                    "target_date": u_target_dt.strftime("%Y-%m-%d"),
                    "activity_multiplier": act_opts[u_act]
                }, on_conflict="user_name").execute()
                
                st.success(f"Profile parameters updated for {new_name}!")
                st.rerun()
            except Exception as e:
                st.error(f"Error saving profile: {e}")

    st.markdown("---")
    st.subheader("📥 Data Backup & Export")
    col_exp1, col_exp2 = st.columns(2)

    try:
        export_logs = st_supabase.client.from_("daily_logs").select("*").eq("user_name", current_user).execute()
        if export_logs.data:
            df_logs_export = pd.DataFrame(export_logs.data)
            csv_logs = df_logs_export.to_csv(index=False).encode('utf-8')
            col_exp1.download_button("📄 Export Meal Logs (CSV)", data=csv_logs, file_name=f"{current_user.lower().replace(' ', '_')}_meal_logs.csv", mime="text/csv", key="export_logs_btn")
        else:
            col_exp1.info("No meal logs to export.")

        export_weight = st_supabase.client.from_("weight_logs").select("*").eq("user_name", current_user).execute()
        if export_weight.data:
            df_weight_export = pd.DataFrame(export_weight.data)
            csv_weight = df_weight_export.to_csv(index=False).encode('utf-8')
            col_exp2.download_button("📈 Export Weight Logs (CSV)", data=csv_weight, file_name=f"{current_user.lower().replace(' ', '_')}_weight_logs.csv", mime="text/csv", key="export_weight_btn")
        else:
            col_exp2.info("No weight logs to export.")
    except Exception as e:
        st.error(f"Export error: {e}")
