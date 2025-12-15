import sqlite3
import random
from datetime import datetime, timedelta

DB_FILE = "portfolio.db"

def seed_history():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Optional: Clear existing logs to start fresh
    # c.execute("DELETE FROM logs")
    
    print("🌱 Seeding 60 days of history...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    current_date = start_date
    
    while current_date < end_date:
        # 1. Determine "Day Type" probability
        # 80% chance of working, 20% chance of "Truancy" (Grey Square)
        if random.random() > 0.15: 
            
            # How many tasks did we do today? (1 to 4)
            num_tasks = random.randint(1, 4)
            
            for _ in range(num_tasks):
                # Pick a random task profile
                # Format: (Name, Duration, Points, Note)
                task_options = [
                    ("News App", 25, 15, "Fixed bug in scraper"),
                    ("Trading Algos", 45, 15, "Optimized backtest loop"),
                    ("Agentic AI", 120, 30, "Implemented memory module"), # Deep Work
                    ("Adversarial DL", 95, 30, "Read research paper"), # Deep Work
                    ("Academics", 60, 10, "Finance chapter review"),
                    ("Volleyball", 120, 25, "Practice match"),
                    ("Social Life", 180, 30, "Dinner with team"),
                ]
                
                # Weighted choice: More likely to do Core/Rent than Deep Work every single time
                choice = random.choice(task_options)
                
                name, duration, points, note = choice
                
                # Add some randomness to duration
                actual_duration = duration + random.randint(-5, 15)
                
                # Construct timestamp (random time during the day)
                hour = random.randint(9, 22)
                minute = random.randint(0, 59)
                timestamp = current_date.replace(hour=hour, minute=minute).isoformat()
                
                c.execute("INSERT INTO logs (timestamp, project, duration, points, notes) VALUES (?, ?, ?, ?, ?)", 
                          (timestamp, name, actual_duration, points, f"[AUTO-SEED] {note}"))
        
        # Move to next day
        current_date += timedelta(days=1)

    conn.commit()
    conn.close()
    print("✅ Database seeded! Refresh your app to see the Heatmap.")

if __name__ == "__main__":
    seed_history()