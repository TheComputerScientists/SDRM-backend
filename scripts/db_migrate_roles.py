#!/usr/bin/env python3

""" db_migrate_roles.py
Upgrades an existing database for SDRM volunteer roles (issue #2) WITHOUT dropping any data.
Unlike db_init.py, nothing is deleted: this only adds columns and updates roles.

1. Backs up the database (SQLite file copy, or mysqldump in production)
2. Adds the users._guardian_name / users._guardian_email columns if they are missing
3. Keeps Admin and Coordinator roles; every other role (User, Teacher, ...) becomes Volunteer
4. Prints how many users have each role

main.py runs step 2-3 at startup as well, so this script is mainly for taking the backup
first and seeing the result. It is safe to run more than once.

Usage, from the root of the project:
> python scripts/db_migrate_roles.py
"""
import os
import shutil
import sys
from datetime import datetime

# Add the directory containing main.py to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Importing main also runs migrate_user_roles() at startup, so take the backup from the
# file path before that import touches the database.
from __init__ import app, db

BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'instance', 'backups'))


def backup_database():
    """Copy the SQLite file (or mysqldump MySQL) into instance/backups. Returns the backup path or None."""
    with app.app_context():
        url = db.engine.url
    if url.drivername.startswith('sqlite'):
        db_path = url.database
        if not db_path or not os.path.exists(db_path):
            print("No SQLite database yet, nothing to back up.")
            return 'none-needed'
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f"{os.path.splitext(os.path.basename(db_path))[0]}_{timestamp}.db")
        shutil.copyfile(db_path, backup_path)
        print(f"Database backed up to {backup_path}")
        return backup_path

    from db_init import backup_mysql_database
    return backup_mysql_database()


def main():
    if backup_database() is None and os.getenv('ALLOW_NO_BACKUP') != 'true':
        print("Refusing to migrate without a backup. Fix the backup above, or set ALLOW_NO_BACKUP=true.")
        sys.exit(1)

    from model.user import migrate_user_roles
    counts = migrate_user_roles()
    print("Users per role:", counts or "(no users table yet)")
    print("Role migration done.")


if __name__ == "__main__":
    main()
