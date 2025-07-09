import sqlite3

with open('database.sql', 'r') as f:
    sql_script = f.read()

conn = sqlite3.connect('test_db.sqlite')
conn.executescript(sql_script)
conn.commit()
conn.close()
print("Schema loaded successfully.")
