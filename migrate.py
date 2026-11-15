import glob
import os
import sqlite3
import sys


def apply(db_path, folder='migrations'):
    con = sqlite3.connect(db_path)
    con.execute('CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
    done = {r[0] for r in con.execute('SELECT name FROM schema_migrations')}
    applied = []
    for path in sorted(glob.glob(os.path.join(folder, '*.sql'))):
        name = os.path.basename(path)
        if name in done:
            continue
        con.executescript(open(path).read())
        con.execute('INSERT INTO schema_migrations(name) VALUES(?)', (name,))
        con.commit()
        applied.append(name)
    con.close()
    return applied


if __name__ == '__main__':
    print(apply(sys.argv[1] if len(sys.argv) > 1 else 'data/app.db'))
