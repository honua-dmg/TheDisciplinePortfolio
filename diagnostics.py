import sqlite3
import pandas as pd

DB_FILE = "portfolio.db"

def fix_schema():
    print("🔧 Restoring ID column...")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Rescue the existing data
    try:
        df = pd.read_sql("SELECT * FROM logs", conn)
        print(f"✅ Rescued {len(df)} logs.")
    except Exception as e:
        print(f"❌ Error reading db: {e}")
        return

    # 2. Drop the broken table (the one missing the 'id' column)
    c.execute("DROP TABLE IF EXISTS logs")
    
    # 3. Re-create the table WITH the ID column correctly defined
    c.execute('''CREATE TABLE logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT, 
                  project TEXT, 
                  duration INTEGER, 
                  points INTEGER,
                  notes TEXT)''')
    
    # 4. Put the data back
    # We strip any old columns and only insert the core data, 
    # letting SQLite generate fresh IDs (1, 2, 3...) automatically.
    cols_to_keep = ['timestamp', 'project', 'duration', 'points', 'notes']
    
    # Ensure dataframe has these columns (fill missing with defaults if needed)
    for col in cols_to_keep:
        if col not in df.columns:
            df[col] = "" if col == 'notes' else 0

    data = df[cols_to_keep].values.tolist()
    
    c.executemany('''INSERT INTO logs (timestamp, project, duration, points, notes) 
                     VALUES (?, ?, ?, ?, ?)''', data)
    
    conn.commit()
    conn.close()
    print("✅ Repair Complete. 'id' column restored.")

if __name__ == "__main__":
    fix_schema()