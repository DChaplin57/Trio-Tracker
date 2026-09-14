import streamlit as st
import pandas as pd
from datetime import datetime, date
from supabase import create_client, Client

# --- PAGE CONFIG & CUSTOM STYLING (Vibrant Colors & Clean Spacing) ---
st.set_page_config(page_title="Trio Weight Tracker", page_icon="🥗", layout="centered")

st.markdown("""
    <style>
    /* Main Background Accent */
    .stApp {
        background-color: #F8F9FA;
    }
    
    /* Header Styling */
    h1 {
        color: #1E3A8A;
        font-weight: 800;
        text-align: center;
        padding-bottom: 10px;
    }
    
    /* Vibrant Metric Boxes */
    div[data-testid="stMetricValue"] {
        font-size: 2rem !important;
        color: #0D9488 !important;
        font-weight: 700;
    }
    
    /* Highlight Cards */
    .highlight-card {
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
        color: white;
        padding: 18px;
        border-radius: 12px;
        margin-bottom: 15px;
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
