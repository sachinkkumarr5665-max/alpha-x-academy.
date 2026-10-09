"""Create (or reset) the administrator account. Run:  python create_admin.py"""
import getpass, re, sqlite3, sys
import database as db


def main():
    db.init_db()
    user = input("Admin username (3-40 letters/numbers/_): ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,40}", user):
        sys.exit("Invalid username.")
    pw = getpass.getpass("Password (min 12 characters): ")
    if len(pw) < 12:
        sys.exit("Password must be at least 12 characters.")
    if pw != getpass.getpass("Confirm password: "):
        sys.exit("Passwords do not match.")
    try:
        db.create_admin(user, pw)
        print("Admin created. Start the server with: python server.py")
    except sqlite3.IntegrityError:
        if input("That username exists. Reset its password? (y/N): ").lower() == "y":
            db.set_admin_password(user, pw)
            print("Password updated; existing sessions were signed out.")


if __name__ == "__main__":
    main()
