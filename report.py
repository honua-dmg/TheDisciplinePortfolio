import sqlite3
import pandas as pd
from datetime import datetime, timedelta

DB_FILE = "portfolio.db"

def generate_llm_prompt():
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql("SELECT * FROM logs", conn)
    except:
        print("No database found.")
        return
    conn.close()

    if df.empty:
        print("No logs found.")
        return

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Filter for last 30 days
    last_30 = df[df['timestamp'] > (datetime.now() - timedelta(days=30))]
    
    if last_30.empty:
        print("No data in last 30 days.")
        return

    # Calculate Stats
    total_points = last_30['points'].sum()
    top_project = last_30.groupby('project')['duration'].sum().idxmax()
    avg_sleep = 7.0 # Placeholder if you tracked sleep in notes, but we didn't save raw sleep val to DB (Optimization for V3)
    
    # Aggregate Notes
    notes_text = ""
    for _, row in last_30.iterrows():
        if row['notes']:
            date_str = row['timestamp'].strftime("%Y-%m-%d")
            notes_text += f"- [{date_str}] {row['project']} ({row['duration']}m): {row['notes']}\n"

    # Construct the Prompt
    prompt = f"""
    ACT AS: A ruthlessly efficient Hedge Fund Manager reviewing a Portfolio Manager's performance.
    
    CONTEXT:
    I am a student/engineer managing my life like a portfolio. 
    - 'Core' assets are daily habits (News App, Trading Algos).
    - 'Deep Work' assets are high-value projects (Agentic AI).
    - 'Social' is liquidity.
    
    DATA (LAST 30 DAYS):
    - Total Alpha Generated: {total_points}
    - Primary Asset Focus: {top_project}
    
    LOGS & NOTES:
    {notes_text}
    
    TASK:
    Write a "Monthly Shareholder Letter" to me.
    1. Analyze my asset allocation. Did I over-index on low-value tasks?
    2. Roast me for any inconsistencies found in the logs.
    3. Highlight the specific wins based on the notes.
    4. Give a "Buy/Sell/Hold" rating on my current trajectory.
    """
    
    print("-" * 50)
    print("COPY THE TEXT BELOW AND PASTE INTO CHATGPT/CLAUDE")
    print("-" * 50)
    print(prompt)
    print("-" * 50)

if __name__ == "__main__":
    generate_llm_prompt()