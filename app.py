import streamlit as st
import pandas as pd
from datetime import datetime, date
from st_supabase_connection import SupabaseConnection

# --- PAGE CONFIG & STYLING ---
st.set_page_config(page_title="Trio Weight Tracker", page_icon="🥗", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #F8F9FA; }
    h1 { color: #1E3A8A; font-weight: 800; text-align: center; }
    div[data-testid="stMetricValue"] { font-size: 2rem !important; color: #0D9488 !important; font-weight: 700; }
    .highlight-card {
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
        color: white; padding: 18px; border-radius: 12px; margin-bottom: 15px;
    }
    .stButton>button { border-radius: 8px; background-color: #2563EB; color: white; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# --- SUPABASE CONNECTION ---
st_supabase = st.connection("supabase", type=SupabaseConnection)

# --- WEIGHT CONVERSION HELPERS ---
def st_lbs_to_kg(st_val, lbs_val):
    return (float(st_val) * 6.35029318) + (float(lbs_val) * 0.45359237)

def kg_to_st_lbs(kg_val):
    total_lbs = float(kg_val) * 2.20462262
    stones = int(total_lbs // 14)
    pounds = round(total_lbs % 14, 1)
    return stones, pounds

# --- CALORIE ENGINE ---
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

# --- APP INTERFACE ---
st.title("🥗 Trio Weight Tracker")

# Dynamic Profile Selection
existing_profiles = st_supabase.query("profiles", ttl=0).execute()
profile_names = [p['user_name'] for p in existing_profiles.data] if existing_profiles.data else ["User 1"]
profile_options = profile_names + ["+ Create New Profile"]

selected_option = st.sidebar.selectbox("👤 Select Active Profile", profile_options)

if selected_option == "+ Create New Profile":
    current_user = st.sidebar.text_input("Enter New Profile Name", value="New User")
else:
    current_user = selected_option

tabs = st.tabs(["📊 Daily Log", "📈 Progress & Graphs", "📖 Shared Food Library", "🍳 Recipe Builder", "⚙️ Profile Settings"])

# --- TAB 1: DAILY LOG ---
with tabs[0]:
    selected_date = st.date_input("Select Date", date.today())
    date_str = selected_date.strftime("%Y-%m-%d")
    
    daily_target = 2000.0
    profile_res = st_supabase.query("profiles", ttl=0).eq("user_name", current_user).execute()
    if profile_res.data:
        p = profile_res.data[0]
        daily_target = calculate_daily_target(
            p['gender'], p['age'], p['height_cm'], p['start_weight_kg'], 
            p['target_weight_kg'], p['start_date'], p['target_date'], p['activity_multiplier']
        )

    logs_res = st_supabase.query("daily_logs", ttl=0).eq("log_date", date_str).eq("user_name", current_user).execute()
    consumed_cals = 0.0
    logs_df = pd.DataFrame()
    if logs_res.data:
        logs_df = pd.DataFrame(logs_res.data)
        consumed_cals = logs_df['calories'].sum()

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
    
    # Quick Unassigned Calories
    with st.expander("⚡ Add Quick / Unassigned Calories (e.g. Snack, Chocolate)"):
        c_desc, c_kcal, c_meal = st.columns([2, 1, 1])
        q_desc = c_desc.text_input("Description", value="Quick Calorie Item")
        q_cal = c_kcal.number_input("Calories (kcal)", min_value=1, value=200)
        q_type = c_meal.selectbox("Meal Category", ["Snacks", "Breakfast", "Lunch", "Dinner"], key="q_meal")
        if st.button("Add Quick Entry"):
            st_supabase.table("daily_logs").insert({
                "log_date": date_str, "user_name": current_user, 
                "food_name": q_desc, "portion_g": 0, "calories": q_cal, "meal_type": q_type
            }).execute()
            st.success(f"Added {q_cal} kcal to {q_type}")
            st.rerun()

    # Standard Item Logging
    st.subheader("➕ Log Food Entry")
    foods_res = st_supabase.query("food_library", ttl=60).execute()
    if foods_res.data:
        foods_df = pd.DataFrame(foods_res.data)
        
        col_f, col_m = st.columns([2, 1])
        selected_food = col_f.selectbox("Food Item", foods_df['food_name'].tolist())
        meal_cat = col_m.selectbox("Category", ["Breakfast", "Lunch", "Dinner", "Snacks"])
        
        food_row = foods_df[foods_df['food_name'] == selected_food].iloc[0]
        log_mode = st.radio("Log By", ["Portion/Serving", "Exact Weight (grams)"], horizontal=True)
        
        if log_mode == "Portion/Serving":
            p_name = food_row.get('default_portion_name', 'serving')
            p_qty = st.number_input(f"Number of Portions ({p_name})", min_value=0.25, value=1.0, step=0.25)
            logged_cal = (food_row['calories_per_100g'] / 100.0) * (food_row.get('portion_grams', 100.0) * p_qty)
            portion_desc = f"{p_qty} {p_name}"
        else:
            grams = st.number_input("Weight (g)", min_value=1.0, value=100.0)
            logged_cal = (food_row['calories_per_100g'] / 100.0) * grams
            portion_desc = f"{grams}g"

        if st.button("Add to Daily Log"):
            st_supabase.table("daily_logs").insert({
                "log_date": date_str, "user_name": current_user, 
                "food_name": f"{selected_food} ({portion_desc})", "portion_g": 0, "calories": logged_cal, "meal_type": meal_cat
            }).execute()
            st.success(f"Added {selected_food} ({int(logged_cal)} kcal)")
            st.rerun()

    if not logs_df.empty:
        st.markdown("---")
        st.subheader("Today's Summary")
        for category in ["Breakfast", "Lunch", "Dinner", "Snacks"]:
            cat_df = logs_df[logs_df['meal_type'] == category]
            if not cat_df.empty:
                st.markdown(f"**{category}** — *{int(cat_df['calories'].sum())} kcal*")
                st.dataframe(cat_df[['food_name', 'calories']], use_container_width=True)

# --- TAB 2: PROGRESS & GRAPHS WITH BMI & TARGET GOAL ---
with tabs[1]:
    st.subheader(f"📈 Progress Tracking: {current_user}")
    
    st.markdown("### 📝 Record Today's Weight")
    w_unit = st.radio("Input Unit", ["kg", "stone & lbs"], horizontal=True, key="w_log_unit")
    
    with st.form("log_weight"):
        w_date = st.date_input("Date", date.today())
        
        if w_unit == "kg":
            w_val = st.number_input("Recorded Weight (kg)", min_value=30.0, max_value=250.0, value=85.0, step=0.1)
            final_kg = w_val
        else:
            col_st, col_lbs = st.columns(2)
            st_val = col_st.number_input("Stone", min_value=4, max_value=40, value=13)
            lbs_val = col_lbs.number_input("Pounds", min_value=0.0, max_value=13.9, value=5.0, step=0.5)
            final_kg = st_lbs_to_kg(st_val, lbs_val)
            
        if st.form_submit_button("Log Weight Entry"):
            st_supabase.table("weight_logs").insert({
                "log_date": w_date.strftime("%Y-%m-%d"),
                "user_name": current_user,
                "weight_kg": final_kg
            }).execute()
            st.success(f"Weight logged successfully ({round(final_kg, 1)} kg / {kg_to_st_lbs(final_kg)[0]}st {kg_to_st_lbs(final_kg)[1]}lbs)!")
            st.rerun()

    st.markdown("---")
    
    w_res = st_supabase.query("weight_logs", ttl=0).eq("user_name", current_user).execute()
    prof_res = st_supabase.query("profiles", ttl=0).eq("user_name", current_user).execute()
    
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
        if bmi_val:
            col_m3.metric("Current BMI", f"{bmi_val}", delta=bmi_status, delta_color="normal")
        else:
            col_m3.metric("Current BMI", "N/A", help="Set height in Profile Settings to calculate BMI")

        st.markdown("---")

        col_g1, col_g2 = st.columns([2, 1])
        col_g1.markdown("### Weight Trend vs Target")
        graph_unit = col_g2.selectbox("Graph Y-Axis Unit", ["Kilograms (kg)", "Total Stones (st)", "Total Pounds (lbs)"])
        
        if graph_unit == "Kilograms (kg)":
            w_df["Actual Weight"] = w_df["weight_kg"]
            if target_kg:
                w_df["Target Goal"] = target_kg
        elif graph_unit == "Total Stones (st)":
            w_df["Actual Weight"] = w_df["weight_kg"] * 0.157473
            if target_kg:
                w_df["Target Goal"] = target_kg * 0.157473
        else:
            w_df["Actual Weight"] = w_df["weight_kg"] * 2.20462
            if target_kg:
                w_df["Target Goal"] = target_kg * 2.20462
            
        chart_cols = ["Actual Weight", "Target Goal"] if target_kg else ["Actual Weight"]
        st.line_chart(w_df.set_index("log_date")[chart_cols])
    else:
        st.info("No weight entries recorded yet. Log your current weight above to generate your trend graph.")

# --- TAB 3: SHARED FOOD LIBRARY ---
with tabs[2]:
    st.subheader("📖 Shared Household Food Library")
    with st.form("add_food"):
        fname = st.text_input("Food Item Name")
        fcal = st.number_input("Calories per 100g", min_value=0.0)
        pname = st.text_input("Portion Description (e.g. 1 slice, 1 bar)", value="serving")
        pgrams = st.number_input("Portion Weight in Grams", min_value=1.0, value=100.0)
        
        if st.form_submit_button("Save to Master Library") and fname:
            st_supabase.table("food_library").upsert({
                "food_name": fname, "calories_per_100g": fcal,
                "default_portion_name": pname, "portion_grams": pgrams
            }, on_conflict="food_name").execute()
            st.success(f"Saved '{fname}'!")
            st.rerun()

    master_res = st_supabase.query("food_library", ttl=0).execute()
    if master_res.data:
        st.dataframe(pd.DataFrame(master_res.data)[['food_name', 'calories_per_100g', 'default_portion_name', 'portion_grams']], use_container_width=True)

# --- TAB 4: RECIPE BUILDER ---
with tabs[3]:
    st.subheader("🍳 Recipe Builder")
    recipe_name = st.text_input("Recipe Name")
    servings = st.number_input("Servings", min_value=1.0, value=4.0)
    
    foods_res = st_supabase.query("food_library", ttl=60).execute()
    if foods_res.data:
        available_foods = pd.DataFrame(foods_res.data)
        if 'recipe_items' not in st.session_state:
            st.session_state.recipe_items = []

        c_ing, c_qty, c_btn = st.columns([2, 1, 1])
        ing = c_ing.selectbox("Select Ingredient", available_foods['food_name'].tolist())
        qty = c_qty.number_input("Weight (g)", min_value=1.0, value=100.0)
        if c_btn.button("Add"):
            c100 = available_foods[available_foods['food_name'] == ing]['calories_per_100g'].values[0]
            st.session_state.recipe_items.append({'item': ing, 'grams': qty, 'cals': (c100 / 100.0) * qty})

        if st.session_state.recipe_items:
            recipe_df = pd.DataFrame(st.session_state.recipe_items)
            st.table(recipe_df)
            tot_cals = recipe_df['cals'].sum()
            per_portion = tot_cals / servings
            st.info(f"**Energy per Portion:** {int(per_portion)} kcal")
            
            if st.button("Save Recipe to Library") and recipe_name:
                st_supabase.table("food_library").upsert({
                    "food_name": recipe_name, "calories_per_100g": per_portion,
                    "default_portion_name": "1 portion", "portion_grams": 100.0
                }, on_conflict="food_name").execute()
                st.session_state.recipe_items = []
                st.success("Recipe saved!")
                st.rerun()

# --- TAB 5: PROFILE SETTINGS & EXPORT ---
with tabs[4]:
    st.subheader(f"⚙️ Profile Settings: {current_user}")
    
    prof_data = st_supabase.query("profiles", ttl=0).eq("user_name", current_user).execute().data
    p_curr = prof_data[0] if prof_data else {}

    with st.form("profile_form"):
        new_name = st.text_input("Profile Display Name", value=current_user)
        
        u_gender = st.selectbox("Biological Sex", ["Female", "Male"], 
                                index=0 if p_curr.get("gender") == "Female" else 1)
        u_age = st.number_input("Age", min_value=10, max_value=120, value=int(p_curr.get("age", 40)))
        u_height = st.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=float(p_curr.get("height_cm", 175.0)))
        
        p_unit = st.radio("Preferred Weight Unit", ["kg", "stone & lbs"], horizontal=True, key="prof_unit")
        
        start_kg_curr = float(p_curr.get("start_weight_kg", 85.0))
        target_kg_curr = float(p_curr.get("target_weight_kg", 75.0))
        
        if p_unit == "kg":
            u_start_wt = st.number_input("Starting Weight (kg)", min_value=30.0, max_value=300.0, value=start_kg_curr, step=0.5)
            u_target_wt = st.number_input("Target Weight (kg)", min_value=30.0, max_value=300.0, value=target_kg_curr, step=0.5)
        else:
            s_st, s_lbs = kg_to_st_lbs(start_kg_curr)
            t_st, t_lbs = kg_to_st_lbs(target_kg_curr)
            
            st.markdown("**Starting Weight**")
            col_s1, col_s2 = st.columns(2)
            u_s_st = col_s1.number_input("Start Stone", min_value=4, max_value=40, value=s_st)
            u_s_lbs = col_s2.number_input("Start Pounds", min_value=0.0, max_value=13.9, value=s_lbs, step=0.5)
            u_start_wt = st_lbs_to_kg(u_s_st, u_s_lbs)
            
            st.markdown("**Target Weight**")
            col_t1, col_t2 = st.columns(2)
            u_t_st = col_t1.number_input("Target Stone", min_value=4, max_value=40, value=t_st)
            u_t_lbs = col_t2.number_input("Target Pounds", min_value=0.0, max_value=13.9, value=t_lbs, step=0.5)
            u_target_wt = st_lbs_to_kg(u_t_st, u_t_lbs)

        u_start_dt = st.date_input("Start Date", value=datetime.strptime(p_curr.get("start_date", str(date.today())), "%Y-%m-%d").date())
        u_target_dt = st.date_input("Target End Date", value=datetime.strptime(p_curr.get("target_date", str(date.today())), "%Y-%m-%d").date())
        
        act_opts = {
            "Sedentary": 1.2, "Lightly Active": 1.375,
            "Moderately Active": 1.55, "Very Active": 1.725
        }
        u_act = st.selectbox("Activity Level", list(act_opts.keys()))
        
        if st.form_submit_button("Save Parameters"):
            st_supabase.table("profiles").upsert({
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
            
            st.success(f"Parameters saved for {new_name}!")
            st.rerun()

    st.markdown("---")
    st.subheader("📥 Data Backup & Export")
    col_exp1, col_exp2 = st.columns(2)

    export_logs = st_supabase.query("daily_logs", ttl=0).eq("user_name", current_user).execute()
    if export_logs.data:
        df_logs_export = pd.DataFrame(export_logs.data)
        csv_logs = df_logs_export.to_csv(index=False).encode('utf-8')
        col_exp1.download_button(
            label="📄 Export Meal Logs (CSV)",
            data=csv_logs,
            file_name=f"{current_user.lower().replace(' ', '_')}_meal_logs.csv",
            mime="text/csv"
        )
    else:
        col_exp1.info("No meal logs to export.")

    export_weight = st_supabase.query("weight_logs", ttl=0).eq("user_name", current_user).execute()
    if export_weight.data:
        df_weight_export = pd.DataFrame(export_weight.data)
        csv_weight = df_weight_export.to_csv(index=False).encode('utf-8')
        col_exp2.download_button(
            label="📈 Export Weight Logs (CSV)",
            data=csv_weight,
            file_name=f"{current_user.lower().replace(' ', '_')}_weight_logs.csv",
            mime="text/csv"
        )
    else:
        col_exp2.info("No weight logs to export.")        margin-bottom: 15px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    /* Buttons */
    .stButton>button {
        border-radius: 8px;
        background-color: #2563EB;
        color: white;
        font-weight: 600;
        border: none;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #1D4ED8;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# --- SUPABASE INITIALIZATION ---
# Connect using secrets configured on Streamlit Cloud or local environment
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://your-supabase-url.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "your-anon-key")

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase = init_supabase()
except Exception:
    supabase = None

# --- CALORIE ENGINE (Mifflin-St Jeor) ---
def calculate_daily_target(gender, age, height_cm, start_weight_kg, target_weight_kg, start_date_str, target_date_str, activity_mult):
    if gender == "Male":
        bmr = (10 * start_weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:
        bmr = (10 * start_weight_kg) + (6.25 * height_cm) - (5 * age) - 161
    
    tdee = bmr * activity_mult
    
    d1 = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    d2 = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    total_days = max((d2 - d1).days, 1)
    
    weight_diff_kg = start_weight_kg - target_weight_kg
    total_deficit_needed = weight_diff_kg * 7700
    daily_deficit = total_deficit_needed / total_days
    
    return max(tdee - daily_deficit, 1200.0)

# --- HEADER & PROFILE SELECTION ---
st.title("🥗 Trio Weight Tracker")

users = ["User 1", "User 2", "User 3"]
current_user = st.sidebar.selectbox("👤 Active Profile", users)

tabs = st.tabs(["📊 Daily Log", "📖 Shared Food Library", "🍳 Recipe Builder", "⚙️ Profile Settings"])

# --- TAB 1: DAILY LOG ---
with tabs[0]:
    selected_date = st.date_input("Select Date", date.today())
    date_str = selected_date.strftime("%Y-%m-%d")
    
    # Fetch profile from Supabase
    daily_target = 2000.0
    if supabase:
        res = supabase.table("profiles").select("*").eq("user_name", current_user).execute()
        if res.data:
            p = res.data[0]
            daily_target = calculate_daily_target(
                p['gender'], p['age'], p['height_cm'], p['start_weight_kg'], 
                p['target_weight_kg'], p['start_date'], p['target_date'], p['activity_multiplier']
            )

    # Vibrant Visual Status Card
    st.markdown(f"""
        <div class="highlight-card">
            <h4 style="margin:0; font-size: 1.1rem; opacity: 0.9;">Target Target for {current_user}</h4>
            <h2 style="margin:5px 0 0 0; font-size: 2.2rem; font-weight:800;">{int(daily_target)} kcal / day</h2>
        </div>
    """, unsafe_allow_html=True)

    # Fetch daily entries
    consumed_cals = 0.0
    logs_df = pd.DataFrame()
    if supabase:
        logs_res = supabase.table("daily_logs").select("*").eq("log_date", date_str).eq("user_name", current_user).execute()
        if logs_res.data:
            logs_df = pd.DataFrame(logs_res.data)
            consumed_cals = logs_df['calories'].sum()

    # Progress bar with dynamic coloring
    pct = min(consumed_cals / daily_target, 1.0) if daily_target > 0 else 0
    st.caption(f"**Energy Allowance Progress:** {int(consumed_cals)} / {int(daily_target)} kcal")
    st.progress(pct)

    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Consumed", f"{int(consumed_cals)} kcal")
    col_m2.metric("Remaining", f"{int(daily_target - consumed_cals)} kcal", 
                  delta=f"{int(daily_target - consumed_cals)} kcal", delta_color="normal")

    st.markdown("---")
    st.subheader("➕ Log Food Entry")
    
    if supabase:
        foods_res = supabase.table("food_library").select("food_name, calories_per_100g").execute()
        foods_df = pd.DataFrame(foods_res.data) if foods_res.data else pd.DataFrame()
        
        if not foods_df.empty:
            col1, col2 = st.columns([2, 1])
            selected_food = col1.selectbox("Food Item", foods_df['food_name'].tolist())
            portion = col2.number_input("Portion (g)", min_value=1.0, value=100.0)
            
            if st.button("Add Item to Daily Log"):
                c_100 = foods_df[foods_df['food_name'] == selected_food]['calories_per_100g'].values[0]
                logged_cal = (c_100 / 100.0) * portion
                
                supabase.table("daily_logs").insert({
                    "log_date": date_str,
                    "user_name": current_user,
                    "food_name": selected_food,
                    "portion_g": portion,
                    "calories": logged_cal
                }).execute()
                st.success(f"Added {selected_food} ({int(logged_cal)} kcal)")
                st.rerun()

    if not logs_df.empty:
        st.subheader("Today's Logged Items")
        st.dataframe(logs_df[['food_name', 'portion_g', 'calories']], use_container_width=True)

# --- TAB 2: SHARED FOOD LIBRARY ---
with tabs[1]:
    st.subheader("📖 Shared Household Food Library")
    st.info("Items added or edited here instantly sync across all 3 users.")
    
    with st.form("add_food_form"):
        fname = st.text_input("Food Item Name")
        fcal = st.number_input("Calories per 100g", min_value=0.0)
        fprot = st.number_input("Protein per 100g (g)", min_value=0.0)
        fcarb = st.number_input("Carbs per 100g (g)", min_value=0.0)
        ffat = st.number_input("Fat per 100g (g)", min_value=0.0)
        submit = st.form_submit_button("Save Entry to Master Library")
        
        if submit and fname and supabase:
            supabase.table("food_library").upsert({
                "food_name": fname,
                "calories_per_100g": fcal,
                "protein_g": fprot,
                "carbs_g": fcarb,
                "fat_g": ffat
            }, on_conflict="food_name").execute()
            st.success(f"Updated '{fname}' in master cloud database!")
            st.rerun()

    if supabase:
        master_res = supabase.table("food_library").select("*").execute()
        if master_res.data:
            st.dataframe(pd.DataFrame(master_res.data)[['food_name', 'calories_per_100g', 'protein_g', 'carbs_g', 'fat_g']], use_container_width=True)

# --- TAB 3: RECIPE BUILDER ---
with tabs[2]:
    st.subheader("🍳 Custom Recipe & Batch Calculator")
    st.caption("Construct multi-ingredient recipes and save portion macros directly to the shared library.")
    
    recipe_name = st.text_input("Recipe Name (e.g., Sunday Roast Veg)")
    servings = st.number_input("Total Recipe Servings", min_value=1.0, value=4.0)
    
    if supabase:
        foods_res = supabase.table("food_library").select("food_name, calories_per_100g").execute()
        available_foods = pd.DataFrame(foods_res.data) if foods_res.data else pd.DataFrame()
        
        if 'recipe_items' not in st.session_state:
            st.session_state.recipe_items = []

        if not available_foods.empty:
            c_ing, c_qty, c_btn = st.columns([2, 1, 1])
            ing = c_ing.selectbox("Select Ingredient", available_foods['food_name'].tolist())
            qty = c_qty.number_input("Weight (g)", min_value=1.0, value=100.0)
            
            if c_btn.button("Add"):
                c100 = available_foods[available_foods['food_name'] == ing]['calories_per_100g'].values[0]
                st.session_state.recipe_items.append({'item': ing, 'grams': qty, 'cals': (c100 / 100.0) * qty})

        if st.session_state.recipe_items:
            recipe_df = pd.DataFrame(st.session_state.recipe_items)
            st.table(recipe_df)
            tot_cals = recipe_df['cals'].sum()
            per_portion = tot_cals / servings
            st.warning(f"**Total Energy:** {int(tot_cals)} kcal | **Energy per Serving:** {int(per_portion)} kcal")
            
            if st.button("Save Recipe to Food Library"):
                supabase.table("food_library").upsert({
                    "food_name": recipe_name,
                    "calories_per_100g": per_portion,
                    "protein_g": 0, "carbs_g": 0, "fat_g": 0
                }, on_conflict="food_name").execute()
                st.session_state.recipe_items = []
                st.success(f"Recipe '{recipe_name}' stored in Master Library!")
                st.rerun()

# --- TAB 4: PROFILE SETTINGS ---
with tabs[3]:
    st.subheader(f"⚙️ Core Parameters: {current_user}")
    
    with st.form("profile_form"):
        u_gender = st.selectbox("Biological Sex", ["Female", "Male"])
        u_age = st.number_input("Age", min_value=10, max_value=120, value=40)
        u_height = st.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=175.0)
        u_start_wt = st.number_input("Starting Weight (kg)", min_value=30.0, max_value=300.0, value=85.0)
        u_target_wt = st.number_input("Target Weight (kg)", min_value=30.0, max_value=300.0, value=75.0)
        u_start_dt = st.date_input("Start Date", date.today())
        u_target_dt = st.date_input("Target End Date", date.today())
        
        act_opts = {
            "Sedentary (Little/no exercise)": 1.2,
            "Lightly Active (1-3 days/week)": 1.375,
            "Moderately Active (3-5 days/week)": 1.55,
            "Very Active (6-7 days/week)": 1.725
        }
        u_act = st.selectbox("Activity Level", list(act_opts.keys()))
        
        if st.form_submit_button("Save Profile Parameters") and supabase:
            supabase.table("profiles").upsert({
                "user_name": current_user,
                "gender": u_gender,
                "age": u_age,
                "height_cm": u_height,
                "start_weight_kg": u_start_wt,
                "target_weight_kg": u_target_wt,
                "start_date": u_start_dt.strftime("%Y-%m-%d"),
                "target_date": u_target_dt.strftime("%Y-%m-%d"),
                "activity_multiplier": act_opts[u_act]
            }, on_conflict="user_name").execute()
            st.success("Profile updated successfully!")
