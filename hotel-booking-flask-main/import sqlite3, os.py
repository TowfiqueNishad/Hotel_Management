import sqlite3, os
from werkzeug.security import generate_password_hash

DB = os.path.join(os.path.dirname(__file__), 'hotel.db')
new_pw = 'YourNewPassword'   # <-- set your desired password here

conn = sqlite3.connect(DB)
conn.execute(
    'UPDATE users SET password = ? WHERE username = ?',
    (generate_password_hash(new_pw), 'admin')
)
conn.commit()
conn.close()
print('Admin password updated.')