# small helper for testing plans until payments are set up
#
# usage (from the backend folder):
#   python admin.py pro <username>     give someone Pro
#   python admin.py free <username>    put them back on Free
#   python admin.py admin <username>   make someone an admin (they get the Admin page)
#   python admin.py list               show all users and their plans

import sys

from dotenv import load_dotenv

load_dotenv("../.env")

import db  # noqa: E402

db.setup()

if len(sys.argv) >= 2 and sys.argv[1] == "list":
    conn = db.connect()
    for row in conn.execute("SELECT username, plan, free_category, is_admin, created_at FROM users ORDER BY id"):
        admin = "admin" if row["is_admin"] else ""
        print(f"{row['username']:<20} {row['plan']:<5} {row['free_category'] or '':<15} {admin:<6} {row['created_at']}")
    conn.close()
elif len(sys.argv) == 3 and sys.argv[1] == "admin":
    user = db.find_user(sys.argv[2])
    if not user:
        print("No user named", sys.argv[2])
    else:
        db.set_admin(user["id"], True)
        print(user["username"], "is now an admin")
elif len(sys.argv) == 3 and sys.argv[1] in ("pro", "free"):
    user = db.find_user(sys.argv[2])
    if not user:
        print("No user named", sys.argv[2])
    else:
        db.set_plan(user["id"], sys.argv[1])
        print(user["username"], "is now on", sys.argv[1])
else:
    print("usage: python admin.py pro <username> | free <username> | admin <username> | list")
