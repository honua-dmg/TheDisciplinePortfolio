import streamlit as st
import pandas as pd
import psycopg2
import dotenv
import os
import shutil
from datetime import datetime, date, timedelta

dotenv.load_dotenv()

def get_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in environment")
    return psycopg2.connect(db_url, sslmode="require")

# --- CONFIGURATION ---
WEEKLY_TOKEN_CAP = 6
BASE_RENT = 30
SOCIAL_EMA_TARGET = 8.0

# --- DATABASE ENGINE ---
@st.cache_resource
def init_db():
    conn = get_conn()
    c = conn.cursor()

    # --- TABLES ---
    c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        timestamp TIMESTAMP,
        project TEXT,
        duration INTEGER,
        points INTEGER,
        notes TEXT
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        name TEXT UNIQUE,
        tier TEXT,
        active BOOLEAN DEFAULT TRUE
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS bounties (
        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        name TEXT UNIQUE,
        value INTEGER,
        status TEXT DEFAULT 'Open',
        end_goal TEXT
    )
    """)

    conn.commit()

    # --- SEED DEFAULT TASKS ---
    c.execute("SELECT COUNT(*) FROM tasks")
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
        for name, tier in defaults:
            c.execute("INSERT INTO tasks (name, tier, active) VALUES (%s, %s, TRUE) ON CONFLICT (name) DO NOTHING", (name, tier))
        conn.commit()

    c.close()
    conn.close()


def get_active_tasks():
    conn = get_conn()
    df = pd.read_sql("SELECT name, tier FROM tasks WHERE active=TRUE", conn)
    conn.close()
    return df

def manage_task(action, name=None, tier=None):
    conn = get_conn()
    c = conn.cursor()
    if action == "add":
        try:
            c.execute("INSERT INTO tasks (name, tier, active) VALUES (%s, %s, TRUE) ON CONFLICT (name) DO NOTHING", (name, tier))
            st.toast(f"Asset '{name}' IPO'd successfully!", icon="🔔")
        except Exception as e:
            st.error(f"Error adding asset: {e}")
    elif action == "delete":
        c.execute("DELETE FROM tasks WHERE name=%s", (name,))
        st.toast(f"Asset '{name}' Delisted.", icon="🗑️")
    conn.commit()
    c.close()
    conn.close()

# --- BOUNTY SYSTEM ---
def manage_bounty(action, name=None, value=0, end_goal=None):
    conn = get_conn()
    c = conn.cursor()
    if action == "add":
        try:
            c.execute("INSERT INTO bounties (name, value, end_goal) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING",
                      (name, value, end_goal))
            st.toast(f"Bounty '{name}' Posted: {value} PTS", icon="💎")
        except Exception as e:
            st.error(f"Bounty add error: {e}")
    elif action == "claim":
        c.execute("UPDATE bounties SET status='Claimed' WHERE name=%s", (name,))
        c.execute("SELECT value FROM bounties WHERE name=%s", (name,))
        val = c.fetchone()[0]
        timestamp_str = datetime.now().isoformat()
        c.execute("INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (%s, %s, %s, %s, %s)",
                  (timestamp_str, "Bounty Hunt", 0, val, f"CLAIMED: {name}"))
        st.balloons()
        st.success(f"💰 BOUNTY CLAIMED: +{val} PTS")
    elif action == "delete":
        c.execute("DELETE FROM bounties WHERE name=%s", (name,))
    conn.commit()
    c.close()
    conn.close()

def get_open_bounties():
    conn = get_conn()
    df = pd.read_sql("SELECT name, value, end_goal FROM bounties WHERE status='Open'", conn)
    conn.close()
    return df


# --- NEEDLE MOVER LOGIC ---
def check_needle_status(target_date=None):
    if target_date is None: target_date = date.today()
    conn = get_conn()
    try:
        df = pd.read_sql(
            "SELECT * FROM logs WHERE project='System' AND notes='Needle Moved'", conn
        )
    except:
        conn.close()
        return False
    conn.close()
    
    if df.empty: return False
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    log = df[df['timestamp'].dt.date == target_date]
    return not log.empty


def set_needle_status(state):
    if state:
        timestamp_str = datetime.now().isoformat()
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (%s, %s, %s, %s, %s)",
            (timestamp_str, "System", 0, 0, "Needle Moved")
        )
        conn.commit()
        c.close()
        conn.close()
        st.balloons()
        st.toast("🚀 BOOM! NEEDLE MOVED!", icon="🔥")


# --- BOSS BATTLE LOGIC ---

def check_exam_mode():
    conn = get_conn()
    try:
        df = pd.read_sql(
            "SELECT * FROM logs WHERE project='System' AND notes='Exam Mode Activated'", conn
        )
    except:
        conn.close()
        return False, None
    conn.close()
    
    if df.empty: return False, None
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    last_activation = df['timestamp'].max()
    if datetime.now() < (last_activation + timedelta(hours=72)):
        return True, last_activation + timedelta(hours=72)
    return False, None


def activate_exam_mode():
    timestamp_str = datetime.now().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (%s, %s, %s, %s, %s)",
        (timestamp_str, "System", 0, -50, "Exam Mode Activated")
    )
    conn.commit()
    c.close()
    conn.close()


def undo_last_log():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT project, points, id FROM logs ORDER BY id DESC LIMIT 1")
    last_row = c.fetchone()
    if last_row:
        last_id = last_row[2]
        c.execute("DELETE FROM logs WHERE id=%s", (last_id,))
        conn.commit()
        st.toast(f"Reverted: {last_row[0]} ({last_row[1]} pts)", icon="↩️")
    else:
        st.error("Ledger is empty.")
    c.close()
    conn.close()


# --- ANALYTICS ENGINE ---
def get_analytics():
    conn = get_conn()
    try:
        df = pd.read_sql("SELECT * FROM logs", conn)
    except:
        df = pd.DataFrame(columns=['timestamp', 'project', 'duration', 'points', 'notes'])
    conn.close()

    if df.empty: return 0, 0, BASE_RENT, df

    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
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
    if not social_logs.empty:
        daily_social = social_logs.groupby(social_logs['timestamp'].dt.date)['points'].sum().reindex(
            pd.date_range(start=df['timestamp'].min().date(), end=today), fill_value=0
        )
        daily_social = daily_social.to_frame('points')
        daily_social['EMA'] = daily_social['points'].ewm(span=7).mean()
        current_social_ema = daily_social['EMA'].iloc[-1]
    else:
        current_social_ema = 0

    current_rent = BASE_RENT
    if current_social_ema < (SOCIAL_EMA_TARGET / 2): current_rent = int(BASE_RENT * 1.5)
    elif current_social_ema < SOCIAL_EMA_TARGET: current_rent = int(BASE_RENT * 1.2)

    return tokens, current_social_ema, current_rent, df


# --- LOG WORK ---
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
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (%s, %s, %s, %s, %s)",
            (timestamp_str, project, duration, 0, f"{notes} (VAMPIRE PENALTY)")
        )
        conn.commit()
        c.close()
        conn.close()
        return 0

    # Fetch today's logs
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM logs WHERE project=%s", conn, params=(project,))
    conn.close()

    today_logs = df[df['timestamp'].dt.date == date.today()] if not df.empty else pd.DataFrame()
    
    if tier == "Core":
        already_collected_base = not today_logs[(today_logs['points'] >= 10)].empty
        if duration >= 20 and not already_collected_base:
            points += 10
            if current_hour < 17: points += 5
        current_total = today_logs['duration'].sum() + duration if not today_logs.empty else duration
        prev_total = today_logs['duration'].sum() if not today_logs.empty else 0
        if current_total >= 90 and prev_total < 90: points += 15
    elif tier == "Deep Work":
        points = 30 if duration >= 90 else 5
    elif tier == "Rent":
        if today_logs.empty:
            points = 25 if project == "Volleyball" else (20 if is_exam_mode and project=="Academics" else 10)
    elif tier == "Social":
        base_social_pts = {"Deep Convo / New People":30, "Hangout / Activity":15, "Casual Check-up":5}.get(social_subtype,0)
        today_social = today_logs['points'].sum() if not today_logs.empty else 0
        points = base_social_pts if today_social < 40 else 0; notes += " (Social Cap Hit)" if today_social >= 40 else ""

    final_points = int(points * multiplier)
    timestamp_str = datetime.now().isoformat()

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (%s, %s, %s, %s, %s)",
        (timestamp_str, project, duration, final_points, notes)
    )
    conn.commit()
    c.close()
    conn.close()

    return final_points
# --- UI LAYOUT ---
st.set_page_config(page_title="Discipline Portfolio", page_icon="📈", layout="wide")
init_db()

# --- THE SHAME PROTOCOL ---
yesterday_status = check_needle_status(date.today() - timedelta(days=1))
needle_today = check_needle_status(date.today())

if not yesterday_status:
    st.markdown("""
        <style>
        [data-testid="stSidebar"] {
            background-color: #3b0e0e; 
        }
        .stApp {
            background-color: #1a0505; 
        }
        </style>
        """, unsafe_allow_html=True)
    st.error("⚠️ **FAILURE DETECTED:** YOU DID NOT MOVE THE NEEDLE YESTERDAY. THE SYSTEM IS IN RED ALERT.")

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

with st.sidebar.expander("🏆 Bounty Board"):
    b_tab1, b_tab2 = st.tabs(["Post", "Claim"])
    with b_tab1: 
        b_name = st.text_input("Bounty Name")
        b_goal = st.text_area("Definition of Done", placeholder="e.g. Code passes all unit tests, deployed to prod.")
        b_hours = st.number_input("Est. Hours", 1, 100, 5)
        col_b1, col_b2 = st.columns(2)
        b_fear = col_b1.checkbox("High Fear?", help="+25%")
        b_lev = col_b2.checkbox("Resume?", help="+50%")
        final_val = int((b_hours * 20) * (1.0 + (0.25 if b_fear else 0) + (0.50 if b_lev else 0)))
        st.metric("Fair Value", f"{final_val} PTS")
        if st.button("Post Bounty"):
            if b_name: manage_bounty("add", b_name, final_val, b_goal); st.rerun()
    with b_tab2: 
        open_bounties = get_open_bounties()
        if not open_bounties.empty:
            # Dropdown with name + points
            b_claim_idx = st.selectbox("Select Bounty", range(len(open_bounties)), format_func=lambda x: f"{open_bounties.iloc[x]['name']} ({open_bounties.iloc[x]['value']} pts)")
            
            # Show the selected bounty's details
            selected_row = open_bounties.iloc[b_claim_idx]
            real_name = selected_row['name']
            condition = selected_row['end_goal'] if selected_row['end_goal'] else "No condition specified."
            
            # THE NEW BOX
            st.warning(f"**🎯 Condition:** {condition}")
            
            if st.button("💰 CLAIM"): manage_bounty("claim", real_name); st.rerun()
        else: st.info("No active bounties.")

exam_active, exam_end = check_exam_mode()
st.sidebar.divider()
if exam_active:
    st.sidebar.error(f"🔥 EXAM MODE ACTIVE")
else:
    if st.sidebar.button("💀 Activate Exam Mode (-50 Pts)"):
        activate_exam_mode(); st.rerun()

# 2. THE GIANT NEEDLE TOGGLE
st.sidebar.header("🚀 THE NEEDLE")
st.sidebar.caption("Did you materially advance your life today?")

if "needle_flipped" not in st.session_state: st.session_state.needle_flipped = False

with st.sidebar.container(border=True):
    if needle_today:
        st.markdown("### ✅ MOVED")
    else:
        st.markdown("### ❌ STAGNANT")
        
    needle_input = st.toggle("Confirm Movement", value=needle_today, disabled=needle_today)

    if needle_input and not needle_today:
        set_needle_status(True)
        st.rerun()

st.sidebar.divider()
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
    else: st.sidebar.caption(f"Class: {project_tier}")
else: project_name = None; project_tier = None

duration = st.sidebar.number_input("Duration (Mins)", min_value=0, step=10, value=20)
notes = st.sidebar.text_input("Trade Notes", placeholder="Details?")

if st.sidebar.button("Log Session"):
    if project_name:
        earned = log_work(project_name, duration, notes, project_tier, sleep_val, social_subtype)
        if earned > 0: st.sidebar.success(f"✅ +{earned} PTS")
        elif 0 <= datetime.now().hour < 6 and not exam_active: st.sidebar.error("🧛 VAMPIRE RULE")
        else: st.sidebar.warning("⚠️ No Points")
    else: st.sidebar.error("Create an asset first!")
    
if st.sidebar.button("↩️ Undo Last Trade"): undo_last_log(); st.rerun()

# --- DASHBOARD ---
st.title("📈 The Discipline Portfolio")
tokens_used, social_ema, current_rent, df = get_analytics()

if needle_today:
    st.success("##### 🚀 MISSION ACCOMPLISHED: THE NEEDLE WAS MOVED TODAY")
elif not yesterday_status:
    st.error("##### 🛑 CRITICAL FAILURE: YOU STAGNATED YESTERDAY. FIX IT.")

col1, col2, col3, col4 = st.columns(4)

if not df.empty:
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', errors='coerce')
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
        chart_tasks = get_active_tasks()
        chart_core = chart_tasks[chart_tasks['tier'] == 'Core']['name'].tolist()

        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', errors='coerce')
        daily_groups = df.groupby(df['timestamp'].dt.date)
        daily_revenue = {}
        
        for day, group in daily_groups:
            day_core_met = not group[
                (group['project'].isin(chart_core)) & 
                (group['duration'] >= 20)
            ].empty
            total_pts = group['points'].sum()
            if day_core_met: daily_revenue[day] = total_pts
            else: daily_revenue[day] = 0 

        start_date = df['timestamp'].min().date()
        end_date = date.today()
        
        if pd.isna(start_date): start_date = end_date
        all_days = pd.date_range(start_date, end_date).date 
        
        chart_rows = []
        cumulative_equity = 0
        
        for d in all_days:
            rev = daily_revenue.get(d, 0)
            net = rev - BASE_RENT
            cumulative_equity += net
            chart_rows.append({'Date': d, 'Equity': cumulative_equity})
            
        chart_df = pd.DataFrame(chart_rows)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df['Date'], y=chart_df['Equity'], 
            mode='lines+markers', fill='tozeroy', 
            line=dict(color='#00CC96', width=3), name="Net Worth"
        ))
        fig.add_hline(y=0, line_dash="dot", line_color="red")
        st.plotly_chart(fig, use_container_width=True)
            
with tab2:
    if not df.empty:
        try:
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', errors='coerce')
            daily_intensity = df.groupby(df['timestamp'].dt.date)['duration'].sum().reset_index()
            daily_intensity.columns = ['date', 'duration']
            
            start_date = df['timestamp'].min().date()
            if pd.isna(start_date): start_date = date.today()
            start_date = start_date - timedelta(days=start_date.weekday())
            end_date = date.today()
            
            full_range = pd.date_range(start_date, end_date).date
            grid_df = pd.DataFrame({'date': full_range})
            hm_df = pd.merge(grid_df, daily_intensity, on='date', how='left').fillna(0)
            
            hm_df['dt'] = pd.to_datetime(hm_df['date'])
            hm_df['week_start'] = hm_df['dt'] - pd.to_timedelta(hm_df['dt'].dt.dayofweek, unit='D')
            hm_df['day_num'] = hm_df['dt'].dt.dayofweek
            
            fig_hm = go.Figure(data=go.Heatmap(
                x=hm_df['week_start'], y=hm_df['day_num'], z=hm_df['duration'],
                colorscale=[[0, '#ebedf0'], [0.001, '#9be9a8'], [1.0, '#216e39']], 
                showscale=False, xgap=3, ygap=3, 
                hoverongaps=False, hovertemplate='%{x}<br>%{z} mins<extra></extra>'
            ))
            fig_hm.update_layout(
                height=200, margin=dict(l=20, r=20, t=20, b=20),
                xaxis=dict(showgrid=False, zeroline=False, tickformat='%b %d'),
                yaxis=dict(tickmode='array', tickvals=[0,1,2,3,4,5,6], ticktext=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'], 
                           showgrid=False, zeroline=False, autorange="reversed"),
                plot_bgcolor='rgba(0,0,0,0)', yaxis_scaleanchor="x"
            )
            st.plotly_chart(fig_hm, use_container_width=True)
        except Exception as e: st.error(f"Heatmap Error: {e}")
    else: st.info("Log data to see heatmap.")

st.divider()
st.subheader("Transaction Ledger")
if not df.empty: st.dataframe(df.sort_values(by='timestamp', ascending=False).head(5), use_container_width=True)