import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# --- CONFIGURATION ---
DB_FILE = "portfolio.db"
WEEKLY_TOKEN_CAP = 6  
BASE_RENT = 30 
SOCIAL_EMA_TARGET = 8.0 # Points per day needed to keep Rent low

# --- DATABASE ENGINE ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT, 
                  project TEXT, 
                  duration INTEGER, 
                  points INTEGER,
                  notes TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS tasks 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE, 
                  tier TEXT, 
                  active BOOLEAN)''')
    
    # SEED DEFAULTS
    c.execute("SELECT count(*) FROM tasks")
    if c.fetchone()[0] == 0:
        defaults = [
            ("News App", "Core"),
            ("Trading Algos", "Core"),
            ("Agentic AI", "Deep Work"),
            ("Adversarial DL", "Deep Work"),
            ("Academics", "Rent"),
            ("Volleyball", "Rent"),
            ("Social Life", "Social") 
        ]
        c.executemany("INSERT INTO tasks (name, tier, active) VALUES (?, ?, 1)", defaults)
        conn.commit()
    conn.commit()
    conn.close()

def get_active_tasks():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT name, tier FROM tasks WHERE active=1", conn)
    conn.close()
    return df

def manage_task(action, name=None, tier=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if action == "add":
        try:
            c.execute("INSERT INTO tasks (name, tier, active) VALUES (?, ?, 1)", (name, tier))
            st.toast(f"Asset '{name}' IPO'd successfully!", icon="🔔")
        except sqlite3.IntegrityError:
            st.error("Asset already exists!")
    elif action == "delete":
        c.execute("DELETE FROM tasks WHERE name=?", (name,))
        st.toast(f"Asset '{name}' Delisted.", icon="🗑️")
    conn.commit()
    conn.close()

# --- ANALYTICS ENGINE (CALCULATES RENT) ---
def get_analytics():
    conn = sqlite3.connect(DB_FILE)
    try: df = pd.read_sql("SELECT * FROM logs", conn)
    except: df = pd.DataFrame(columns=['timestamp', 'project', 'duration', 'points', 'notes'])
    conn.close()

    if df.empty: return 0, 0, BASE_RENT, df

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 1. GET TASKS INFO
    tasks_df = get_active_tasks()
    deep_work_projects = tasks_df[tasks_df['tier'] == 'Deep Work']['name'].tolist()
    social_projects = tasks_df[tasks_df['tier'] == 'Social']['name'].tolist()
    
    # 2. WEEKLY TOKENS
    today = date.today()
    start_of_week = pd.to_datetime(today - timedelta(days=today.weekday()))
    this_week = df[df['timestamp'] >= start_of_week]
    
    tokens = this_week[
        (this_week['project'].isin(deep_work_projects)) & 
        (this_week['duration'] >= 90)
    ].shape[0]

    # 3. SOCIAL EMA & DYNAMIC RENT
    # Filter only social logs
    social_logs = df[df['project'].isin(social_projects)].copy()
    
    # Group by day to get daily social points
    daily_social = social_logs.groupby(social_logs['timestamp'].dt.date)['points'].sum().reset_index()
    
    # To calculate a true EMA, we need to fill missing days with 0
    all_dates = pd.date_range(start=df['timestamp'].min().date(), end=today)
    daily_social.set_index('timestamp', inplace=True)
    daily_social = daily_social.reindex(all_dates, fill_value=0)
    
    # Calculate 7-Day EMA
    daily_social['EMA'] = daily_social['points'].ewm(span=7).mean()
    
    # Get Today's Social EMA Value
    current_social_ema = daily_social['EMA'].iloc[-1] if not daily_social.empty else 0
    
    # DETERMINE RENT BASED ON SOCIAL EMA
    current_rent = BASE_RENT
    if current_social_ema < (SOCIAL_EMA_TARGET / 2): # Critical Isolation (< 4.0)
        current_rent = int(BASE_RENT * 1.5) # 45 Pts
    elif current_social_ema < SOCIAL_EMA_TARGET: # Isolation (< 8.0)
        current_rent = int(BASE_RENT * 1.2) # 36 Pts
        
    return tokens, current_social_ema, current_rent, df

# --- LOGGING LOGIC ---
def log_work(project, duration, notes, tier, sleep_hours, social_subtype=None):
    points = 0
    current_hour = datetime.now().hour
    
    # 1. SLEEP MULTIPLIER (Calculate first, apply at end)
    multiplier = 1.0
    if sleep_hours < 5:
        multiplier = 0.5; notes += " (ZOMBIE TAX -50%)"
    elif sleep_hours < 6.5:
        multiplier = 0.8; notes += " (TIRED TAX -20%)"
    
    # --- 2. THE VAMPIRE RULE (SMART VERSION) ---
    # Only penalize Work/Study. Allow Social/Sport to thrive at night.
    is_vampire_time = (0 <= current_hour < 6)
    is_exempt_activity = (tier == 'Social') or (project == 'Volleyball')
    
    if is_vampire_time and not is_exempt_activity:
        # PENALTY APPLIED
        timestamp_str = datetime.now().isoformat()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (?, ?, ?, ?, ?)", 
                  (timestamp_str, project, duration, 0, f"{notes} (VAMPIRE PENALTY)"))
        conn.commit()
        conn.close()
        return 0 

    # --- 3. STANDARD LOGGING ---
    conn = sqlite3.connect(DB_FILE)
    try: df = pd.read_sql("SELECT * FROM logs", conn)
    except: df = pd.DataFrame()
    conn.close()
    
    expected_columns = ['timestamp', 'project', 'duration', 'points', 'notes']
    if df.empty: project_logs = pd.DataFrame(columns=expected_columns)
    else:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        today_logs = df[df['timestamp'].dt.date == date.today()]
        project_logs = today_logs[today_logs['project'] == project]

    # --- SCORING ---
    if tier == "Core":
        already_collected_base = not project_logs[(project_logs['points'] >= 10)].empty
        if duration >= 20 and not already_collected_base:
            points += 10
            if current_hour < 17: points += 5 
        current_total = project_logs['duration'].sum() + duration
        prev_total = project_logs['duration'].sum()
        if current_total >= 90 and prev_total < 90: points += 15 

    elif tier == "Deep Work":
        if duration >= 90: points = 30
        else: points = 5

    elif tier == "Rent":
        if project_logs.empty: 
            if project == "Volleyball": points = 25 
            else: points = 10
            
    elif tier == "Social":
        # WEIGHTED SOCIAL SCORING
        base_social_pts = 0
        if social_subtype == "Deep Convo / New People": base_social_pts = 30
        elif social_subtype == "Hangout / Activity": base_social_pts = 15
        elif social_subtype == "Casual Check-up": base_social_pts = 5
        
        # Cap daily social points at 40
        today_social = today_logs[today_logs['project'] == project]['points'].sum()
        if today_social < 40:
            points = base_social_pts
        else:
            points = 0
            notes += " (Social Cap Hit)"

    # APPLY MULTIPLIER
    final_points = int(points * multiplier)

    # SAVE
    timestamp_str = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (?, ?, ?, ?, ?)", 
              (timestamp_str, project, duration, final_points, notes))
    conn.commit()
    conn.close()
    return final_points
    
# --- UI LAYOUT ---
st.set_page_config(page_title="Discipline Portfolio", page_icon="📈", layout="wide")
init_db()

# 1. TASK MANAGER
with st.sidebar.expander("⚙️ Asset Manager"):
    tab1, tab2 = st.tabs(["Add", "Delist"])
    with tab1:
        new_task = st.text_input("New Asset Name")
        new_tier = st.selectbox("Asset Class", ["Core", "Deep Work", "Rent", "Social"])
        if st.button("IPO Asset"):
            if new_task: manage_task("add", new_task, new_tier)
            st.rerun()
    with tab2:
        tasks_df = get_active_tasks()
        del_task = st.selectbox("Select Asset to Delist", tasks_df['name'].tolist() if not tasks_df.empty else [])
        if st.button("Delist Asset"):
            manage_task("delete", del_task)
            st.rerun()

# 2. ORDER EXECUTION
st.sidebar.divider()
st.sidebar.header("📝 Execute Order")

sleep_val = st.sidebar.slider("Sleep Last Night (Hrs)", 0.0, 12.0, 7.0, 0.5)

# --- NEW SORTING LOGIC ---
tasks_df = get_active_tasks()

if not tasks_df.empty:
    # 1. Define the Hierarchy (Priority Order)
    tier_order = {"Core": 0, "Deep Work": 1, "Social": 2, "Rent": 3}
    
    # 2. Map the order to the dataframe
    tasks_df['sort_key'] = tasks_df['tier'].map(tier_order)
    
    # 3. Sort by Tier first, then by Name
    tasks_df = tasks_df.sort_values(by=['sort_key', 'name'])

    # --- ICON MAPPING ---
    def get_tier_icon(name):
        row = tasks_df[tasks_df['name'] == name]
        if not row.empty:
            tier = row.iloc[0]['tier']
            if tier == "Core": return "🔴"
            if tier == "Deep Work": return "🟣"
            if tier == "Social": return "🟢"
            if tier == "Rent": return "🔵"
        return "⚪"

    project_name = st.sidebar.selectbox(
        "Asset", 
        tasks_df['name'], 
        format_func=lambda x: f"{get_tier_icon(x)} {x}" # The visual tag
    )
    
    # Backend Logic
    project_tier = tasks_df[tasks_df['name'] == project_name]['tier'].values[0]
    
    if project_tier == "Social":
        social_subtype = st.sidebar.radio("Interaction Type", 
            ["Deep Convo / New People", "Hangout / Activity", "Casual Check-up"])
        st.sidebar.info(f"Yield: {30 if 'Deep' in social_subtype else 15 if 'Hangout' in social_subtype else 5} pts")
    else:
        # No social subtype needed
        social_subtype = None
        st.sidebar.caption(f"Class: {project_tier}")
else:
    project_name = None; project_tier = None

duration = st.sidebar.number_input("Duration (Mins)", min_value=0, step=10, value=20)
notes = st.sidebar.text_input("Trade Notes", placeholder="Details?")

if st.sidebar.button("Log Session"):
    if project_name:
        earned = log_work(project_name, duration, notes, project_tier, sleep_val, social_subtype)
        if earned > 0: st.sidebar.success(f"✅ +{earned} PTS")
        elif 0 <= datetime.now().hour < 6: st.sidebar.error("🧛 VAMPIRE RULE: 0 PTS")
        else: st.sidebar.warning("⚠️ No Points")
    else: st.sidebar.error("Create an asset first!")
# --- DASHBOARD LOGIC ---
st.title("📈 The Discipline Portfolio")

# FETCH DATA & ANALYTICS
tokens_used, social_ema, current_rent, df = get_analytics()

# --- TOP LEVEL METRICS ---
col1, col2, col3, col4 = st.columns(4)

# 1. ALPHA (Money)
if not df.empty:
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    today_df = df[df['timestamp'].dt.date == date.today()]
    
    # Gatekeeper Check
    core_projects = tasks_df[tasks_df['tier'] == 'Core']['name'].tolist()
    core_met = not today_df[(today_df['project'].isin(core_projects)) & (today_df['duration'] >= 20)].empty
    
    raw_points = today_df['points'].sum()
    final_points = raw_points if core_met else 0
    
    col1.metric("Today's Alpha", f"{final_points}", delta=f"Rent: {current_rent}", delta_color="inverse")
    if core_met: col2.success("✅ GATEKEEPER OPEN")
    else: col2.error("🔒 GATEKEEPER CLOSED")
else:
    col1.metric("Today's Alpha", "0", delta=f"Rent: {current_rent}")
    col2.error("🔒 GATEKEEPER CLOSED")

# 2. TOKENS (Work)
col3.metric("Deep Work Tokens", f"{tokens_used} / {WEEKLY_TOKEN_CAP}")

# 3. SOCIAL (EMA)
social_delta = round(social_ema - SOCIAL_EMA_TARGET, 1)
col4.metric("❤️ Social EMA", f"{round(social_ema, 1)} / {SOCIAL_EMA_TARGET}", delta=social_delta)

# WARNINGS FOR RENT HIKE
if current_rent > BASE_RENT:
    st.error(f"⚠️ **RENT PENALTY ACTIVE:** Daily Rent is {current_rent} (Target: {BASE_RENT}). Go socialize to lower it!")

st.divider()

# --- CHART LOGIC (WITH VARIABLE RENT TRUANCY) ---
if not df.empty:
    daily_groups = df.groupby(df['timestamp'].dt.date)
    daily_data = {}
    
    for day, group in daily_groups:
        day_core_met = not group[(group['project'].isin(core_projects)) & (group['duration'] >= 20)].empty
        raw_points = group['points'].sum()
        if day_core_met: daily_data[day] = raw_points
        else: daily_data[day] = 0 

    start_date = df['timestamp'].min().date()
    end_date = date.today()
    all_dates = pd.date_range(start_date, end_date)
    chart_rows = []
    cumulative_equity = 0
    
    # WE MUST RE-CALCULATE RENT FOR THE PAST TO DRAW CHART CORRECTLY?
    # Complexity trade-off: The chart will use TODAY's Rent Logic for simplicity, 
    # OR we assume Rent was 30 in the past. 
    # For a personal tool, applying CURRENT RENT to history is confusing. 
    # Let's apply BASE_RENT (30) for historical view, but penalize future/today.
    # OR: Just subtract the calculated current_rent from today's point.
    
    for single_date in all_dates:
        d = single_date.date()
        points_today = daily_data.get(d, 0)
        
        # Ideally we calculate historical rent, but that requires historical EMA.
        # For MVP, we stick to Base Rent for history, and show Penalty in "Today's Alpha" metric.
        # This keeps the chart stable.
        net_change = points_today - BASE_RENT 
        
        cumulative_equity += net_change
        chart_rows.append({'date': d, 'Equity': cumulative_equity})
        
    chart_df = pd.DataFrame(chart_rows)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=chart_df['date'], y=chart_df['Equity'], name='Net Worth', mode='lines+markers', fill='tozeroy', line=dict(color='#00CC96', width=3), marker=dict(size=6)))
    fig.add_hline(y=0, line_dash="dot", line_color="red", annotation_text="Bankruptcy")
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="Cumulative Alpha")
    st.plotly_chart(fig, use_container_width=True)

    # Ledger
    st.subheader("Transaction Ledger")
    st.dataframe(df.sort_values(by='timestamp', ascending=False).head(5), use_container_width=True)
else:
    st.info("👋 Welcome. Initialize assets in sidebar.")