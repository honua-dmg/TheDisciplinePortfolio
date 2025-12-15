import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import shutil
import os

# --- CONFIGURATION ---
DB_FILE = "portfolio.db"
WEEKLY_TOKEN_CAP = 6  
BASE_RENT = 30 
SOCIAL_EMA_TARGET = 8.0 

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
    
    # NEW: Bounties Table
    c.execute('''CREATE TABLE IF NOT EXISTS bounties 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE, 
                  value INTEGER, 
                  status TEXT)''') # status: 'Open', 'Claimed'
    
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

def undo_last_log():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Get the last log to show user what they are deleting
    c.execute("SELECT project, points FROM logs ORDER BY id DESC LIMIT 1")
    last_row = c.fetchone()

    if last_row:
        c.execute("DELETE FROM logs WHERE id = (SELECT MAX(id) FROM logs)")
        conn.commit()
        st.toast(f"Reverted: {last_row[0]} ({last_row[1]} pts)", icon="↩️")
    else:
        st.error("Ledger is empty.")
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

# --- BOUNTY SYSTEM ---
def manage_bounty(action, name=None, value=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if action == "add":
        try:
            c.execute("INSERT INTO bounties (name, value, status) VALUES (?, ?, 'Open')", (name, value))
            st.toast(f"Bounty '{name}' Posted: {value} PTS", icon="💎")
        except sqlite3.IntegrityError:
            st.error("Bounty name already exists!")
    elif action == "claim":
        # 1. Mark as claimed
        c.execute("UPDATE bounties SET status='Claimed' WHERE name=?", (name,))
        # 2. Get value
        c.execute("SELECT value FROM bounties WHERE name=?", (name,))
        val = c.fetchone()[0]
        # 3. Log the "Trade"
        timestamp_str = datetime.now().isoformat()
        c.execute("INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (?, ?, ?, ?, ?)", 
                  (timestamp_str, "Bounty Hunt", 0, val, f"CLAIMED: {name}"))
        st.balloons()
        st.success(f"💰 BOUNTY CLAIMED: +{val} PTS")
    elif action == "delete":
        c.execute("DELETE FROM bounties WHERE name=?", (name,))
    conn.commit()
    conn.close()

def get_open_bounties():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT name, value FROM bounties WHERE status='Open'", conn)
    conn.close()
    return df

# --- BOSS BATTLE LOGIC ---
def check_exam_mode():
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql("SELECT * FROM logs WHERE project='System' AND notes='Exam Mode Activated'", conn)
    except: return False, None
    conn.close()
    if df.empty: return False, None
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    last_activation = df['timestamp'].max()
    if datetime.now() < (last_activation + timedelta(hours=72)):
        return True, last_activation + timedelta(hours=72)
    return False, None

def activate_exam_mode():
    timestamp_str = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (?, ?, ?, ?, ?)", 
              (timestamp_str, "System", 0, -50, "Exam Mode Activated"))
    conn.commit()
    conn.close()

# --- ANALYTICS ENGINE ---
def get_analytics():
    conn = sqlite3.connect(DB_FILE)
    try: df = pd.read_sql("SELECT * FROM logs", conn)
    except: df = pd.DataFrame(columns=['timestamp', 'project', 'duration', 'points', 'notes'])
    conn.close()

    if df.empty: return 0, 0, BASE_RENT, df

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    tasks_df = get_active_tasks()
    deep_work_projects = tasks_df[tasks_df['tier'] == 'Deep Work']['name'].tolist()
    social_projects = tasks_df[tasks_df['tier'] == 'Social']['name'].tolist()
    
    today = date.today()
    start_of_week = pd.to_datetime(today - timedelta(days=today.weekday()))
    this_week = df[df['timestamp'] >= start_of_week]
    
    tokens = this_week[
        (this_week['project'].isin(deep_work_projects)) & 
        (this_week['duration'] >= 90)
    ].shape[0]

    social_logs = df[df['project'].isin(social_projects)].copy()
    daily_social = social_logs.groupby(social_logs['timestamp'].dt.date)['points'].sum().reset_index()
    all_dates = pd.date_range(start=df['timestamp'].min().date(), end=today)
    daily_social.set_index('timestamp', inplace=True)
    daily_social = daily_social.reindex(all_dates, fill_value=0)
    daily_social['EMA'] = daily_social['points'].ewm(span=7).mean()
    current_social_ema = daily_social['EMA'].iloc[-1] if not daily_social.empty else 0
    
    current_rent = BASE_RENT
    if current_social_ema < (SOCIAL_EMA_TARGET / 2): current_rent = int(BASE_RENT * 1.5)
    elif current_social_ema < SOCIAL_EMA_TARGET: current_rent = int(BASE_RENT * 1.2)
        
    return tokens, current_social_ema, current_rent, df

# --- LOGGING LOGIC ---
def log_work(project, duration, notes, tier, sleep_hours, social_subtype=None):
    points = 0
    current_hour = datetime.now().hour
    is_exam_mode, _ = check_exam_mode()
    
    multiplier = 1.0
    if sleep_hours < 5: multiplier = 0.5; notes += " (ZOMBIE TAX -50%)"
    elif sleep_hours < 6.5: multiplier = 0.8; notes += " (TIRED TAX -20%)"
    
    is_vampire_time = (0 <= current_hour < 6)
    is_exempt_activity = (tier == 'Social') or (project == 'Volleyball')
    if is_exam_mode: is_vampire_time = False

    if is_vampire_time and not is_exempt_activity:
        timestamp_str = datetime.now().isoformat()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (?, ?, ?, ?, ?)", 
                  (timestamp_str, project, duration, 0, f"{notes} (VAMPIRE PENALTY)"))
        conn.commit()
        conn.close()
        return 0 

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
            else: 
                if is_exam_mode and project == "Academics": points = 20; notes += " (EXAM SURGE)"
                else: points = 10
            
    elif tier == "Social":
        base_social_pts = 0
        if social_subtype == "Deep Convo / New People": base_social_pts = 30
        elif social_subtype == "Hangout / Activity": base_social_pts = 15
        elif social_subtype == "Casual Check-up": base_social_pts = 5
        
        today_social = today_logs[today_logs['project'] == project]['points'].sum()
        if today_social < 40: points = base_social_pts
        else: points = 0; notes += " (Social Cap Hit)"

    final_points = int(points * multiplier)
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

# 1. SIDEBAR
with st.sidebar.expander("⚙️ Asset Manager"):
    tab1, tab2 = st.tabs(["Add", "Delist"])
    with tab1:
        new_task = st.text_input("New Asset Name")
        new_tier = st.selectbox("Asset Class", ["Core", "Deep Work", "Rent", "Social"])
        if st.button("IPO Asset"):
            if new_task: manage_task("add", new_task, new_tier); st.rerun()
    with tab2:
        tasks_df = get_active_tasks()
        del_task = st.selectbox("Select Asset to Delist", tasks_df['name'].tolist() if not tasks_df.empty else [])
        if st.button("Delist Asset"): manage_task("delete", del_task); st.rerun()

# --- NEW: BOUNTY BOARD TAB ---
with st.sidebar.expander("🏆 Bounty Board"):
    b_tab1, b_tab2 = st.tabs(["Post", "Claim"])
    
    with b_tab1: # CALCULATOR
        st.caption("Valuation Model")
        b_name = st.text_input("Bounty Name", placeholder="e.g. Ship News App")
        b_hours = st.number_input("Est. Hours", 1, 100, 5)
        
        col_b1, col_b2 = st.columns(2)
        b_fear = col_b1.checkbox("High Fear?", help="+25% Value")
        b_lev = col_b2.checkbox("Resume Item?", help="+50% Value")
        
        # VALUATION FORMULA
        base_val = b_hours * 20
        multiplier = 1.0
        if b_fear: multiplier += 0.25
        if b_lev: multiplier += 0.50
        
        final_val = int(base_val * multiplier)
        st.metric("Fair Value", f"{final_val} PTS")
        
        if st.button("Post Bounty"):
            if b_name: manage_bounty("add", b_name, final_val); st.rerun()
            
    with b_tab2: # CLAIM
        open_bounties = get_open_bounties()
        if not open_bounties.empty:
            b_claim = st.selectbox("Select Bounty", open_bounties['name'] + " (" + open_bounties['value'].astype(str) + " pts)")
            # Extract name back from string
            real_name = b_claim.split(" (")[0]
            if st.button("💰 CLAIM REWARD"):
                manage_bounty("claim", real_name)
                st.rerun()
        else:
            st.info("No active bounties.")

# EXAM MODE
exam_active, exam_end = check_exam_mode()
st.sidebar.divider()
if exam_active:
    st.sidebar.error(f"🔥 EXAM MODE ACTIVE")
    st.sidebar.caption(f"Ends: {exam_end.strftime('%b %d %H:%M')}")
else:
    if st.sidebar.button("💀 Activate Exam Mode (-50 Pts)"):
        activate_exam_mode()
        st.rerun()

# 2. ORDER EXECUTION
st.sidebar.header("📝 Execute Order")
sleep_val = st.sidebar.slider("Sleep Last Night (Hrs)", 0.0, 12.0, 7.0, 0.5)

tasks_df = get_active_tasks()
if not tasks_df.empty:
    tier_order = {"Core": 0, "Deep Work": 1, "Social": 2, "Rent": 3}
    tasks_df['sort_key'] = tasks_df['tier'].map(tier_order)
    tasks_df = tasks_df.sort_values(by=['sort_key', 'name'])

    def get_tier_icon(name):
        row = tasks_df[tasks_df['name'] == name]
        if not row.empty:
            tier = row.iloc[0]['tier']
            mapping = {"Core": "🔴", "Deep Work": "🟣", "Social": "🟢", "Rent": "🔵"}
            return mapping.get(tier, "⚪")
        return "⚪"

    project_name = st.sidebar.selectbox("Asset", tasks_df['name'], format_func=lambda x: f"{get_tier_icon(x)} {x}")
    project_tier = tasks_df[tasks_df['name'] == project_name]['tier'].values[0]
    
    social_subtype = None
    if project_tier == "Social":
        social_subtype = st.sidebar.radio("Type", ["Deep Convo / New People", "Hangout / Activity", "Casual Check-up"])
        st.sidebar.info(f"Yield: {30 if 'Deep' in social_subtype else 15 if 'Hangout' in social_subtype else 5} pts")
    else:
        st.sidebar.caption(f"Class: {project_tier}")
else:
    project_name = None; project_tier = None

duration = st.sidebar.number_input("Duration (Mins)", min_value=0, step=10, value=20)
notes = st.sidebar.text_input("Trade Notes", placeholder="Details?")

if st.sidebar.button("Log Session"):
    if project_name:
        earned = log_work(project_name, duration, notes, project_tier, sleep_val, social_subtype)
        if earned > 0: st.sidebar.success(f"✅ +{earned} PTS")
        elif 0 <= datetime.now().hour < 6 and not exam_active: st.sidebar.error("🧛 VAMPIRE RULE")
        else: st.sidebar.warning("⚠️ No Points")
    else: st.sidebar.error("Create an asset first!")


if st.sidebar.button("↩️ Undo Last Trade"):
    undo_last_log()
    st.rerun()

# --- DASHBOARD ---
st.title("📈 The Discipline Portfolio")
tokens_used, social_ema, current_rent, df = get_analytics()

col1, col2, col3, col4 = st.columns(4)

if not df.empty:
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    today_df = df[df['timestamp'].dt.date == date.today()]
    core_projects = tasks_df[tasks_df['tier'] == 'Core']['name'].tolist()
    core_met = not today_df[(today_df['project'].isin(core_projects)) & (today_df['duration'] >= 20)].empty
    final_points = today_df['points'].sum() if core_met else 0
    
    col1.metric("Today's Alpha", f"{final_points}", delta=f"Rent: {current_rent}", delta_color="inverse")
    if core_met: col2.success("✅ GATEKEEPER OPEN")
    else: col2.error("🔒 GATEKEEPER CLOSED")
else:
    col1.metric("Today's Alpha", "0", delta=f"Rent: {current_rent}")
    col2.error("🔒 GATEKEEPER CLOSED")

col3.metric("Deep Work Tokens", f"{tokens_used} / {WEEKLY_TOKEN_CAP}")
col4.metric("❤️ Social EMA", f"{round(social_ema, 1)} / {SOCIAL_EMA_TARGET}", delta=round(social_ema - SOCIAL_EMA_TARGET, 1))

if current_rent > BASE_RENT: st.error(f"⚠️ RENT PENALTY: {current_rent} pts (Social Isolation)")

# --- CHARTS ---
tab1, tab2 = st.tabs(["💰 Equity Curve", "🔥 Consistency Heatmap"])

with tab1:
    if not df.empty:
        daily_groups = df.groupby(df['timestamp'].dt.date)
        daily_data = {}
        for day, group in daily_groups:
            day_core_met = not group[(group['project'].isin(core_projects)) & (group['duration'] >= 20)].empty
            daily_data[day] = group['points'].sum() if day_core_met else 0

        start_date = df['timestamp'].min().date()
        end_date = date.today()
        chart_rows = []
        cumulative_equity = 0
        for single_date in pd.date_range(start_date, end_date):
            d = single_date.date()
            net = daily_data.get(d, 0) - BASE_RENT
            cumulative_equity += net
            chart_rows.append({'date': d, 'Equity': cumulative_equity})
            
        chart_df = pd.DataFrame(chart_rows)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_df['date'], y=chart_df['Equity'], mode='lines+markers', fill='tozeroy', line=dict(color='#00CC96', width=3)))
        fig.add_hline(y=0, line_dash="dot", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        start_date = df['timestamp'].min().date() - timedelta(days=df['timestamp'].min().date().weekday())
        end_date = date.today()
        all_dates = pd.date_range(start_date, end_date)
        
        daily_intensity = df.groupby(df['timestamp'].dt.date)['duration'].sum().reindex(all_dates, fill_value=0).reset_index()
        daily_intensity.columns = ['date', 'duration']
        daily_intensity['week_start'] = daily_intensity['date'] - pd.to_timedelta(daily_intensity['date'].dt.dayofweek, unit='D')
        daily_intensity['day_num'] = daily_intensity['date'].dt.dayofweek
        
        fig_hm = go.Figure(data=go.Heatmap(
            x=daily_intensity['week_start'], 
            y=daily_intensity['day_num'],
            z=daily_intensity['duration'],
            colorscale=[[0, '#ebedf0'], [0.01, '#9be9a8'], [1.0, '#216e39']],
            showscale=False, xgap=3, ygap=3, hoverongaps=False,
            hovertemplate='%{x}<br>%{z} mins<extra></extra>'
        ))
        fig_hm.update_layout(
            height=200, margin=dict(l=20, r=20, t=20, b=20),
            xaxis=dict(showgrid=False, zeroline=False, tickformat='%b %d'),
            yaxis=dict(tickmode='array', tickvals=[0,1,2,3,4,5,6], ticktext=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'], showgrid=False, zeroline=False, autorange="reversed"),
            plot_bgcolor='rgba(0,0,0,0)', yaxis_scaleanchor="x"
        )
        st.plotly_chart(fig_hm, use_container_width=True)
    else:
        st.info("Log data to see heatmap.")

st.divider()
st.subheader("Transaction Ledger")
if not df.empty:
    st.dataframe(df.sort_values(by='timestamp', ascending=False).head(5), use_container_width=True)