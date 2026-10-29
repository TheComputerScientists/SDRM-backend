#!/usr/bin/env python3

""" db_add_guardian_columns.py
Adds users._guardian_name and users._guardian_email (both nullable) to an existing
database WITHOUT dropping any data. Unlike db_init.py, nothing is deleted.

1. Backs up the database (SQLite file copy, or mysqldump in production)
2. Adds the two columns if they are missing (safe to run more than once)

Usage, from the root of the project:
> python scripts/db_add_guardian_columns.py
"""
import os
import sys

# Add the directory containing main.py to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from db_migrate_roles import backup_database


def main():
    if backup_database() is None and os.getenv('ALLOW_NO_BACKUP') != 'true':
        print("Refusing to migrate without a backup. Fix the backup above, or set ALLOW_NO_BACKUP=true.")
        sys.exit(1)

    from model.user import migrate_guardian_columns
    added = migrate_guardian_columns()
    if added:
        print("Added columns:", ", ".join(f"users.{name}" for name in added))
    else:
        print("Guardian columns are already there, nothing to change.")


if __name__ == "__main__":
    main()
