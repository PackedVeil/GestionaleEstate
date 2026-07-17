import sqlite3
import os

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'centro_estivo.db')
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Inizializza il database caricando lo schema SQL."""
    if not os.path.exists(SCHEMA_PATH):
        raise FileNotFoundError(f"Schema file not found at: {SCHEMA_PATH}")
        
    conn = get_db_connection()
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

# --- Funzioni Utenti ---
def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user

def create_user(username, password_hash, role='admin'):
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                     (username, password_hash, role))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

# --- Funzioni Catalogo Attività ---
def get_catalog_activities():
    conn = get_db_connection()
    activities = conn.execute('SELECT * FROM activity_catalog ORDER BY name ASC').fetchall()
    conn.close()
    return activities

def get_catalog_activity_by_id(catalog_id):
    conn = get_db_connection()
    activity = conn.execute('SELECT * FROM activity_catalog WHERE id = ?', (catalog_id,)).fetchone()
    conn.close()
    return activity

def add_catalog_activity(name, description):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO activity_catalog (name, description) VALUES (?, ?)', (name, description))
        conn.commit()
        activity_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        row = conn.execute('SELECT id FROM activity_catalog WHERE name = ?', (name,)).fetchone()
        activity_id = row['id'] if row else None
    finally:
        conn.close()
    return activity_id

# --- Funzioni Attività Schedulate ---
def schedule_activity(catalog_id, title, description, day_of_week, start_time, end_time, week_start,
                      category, optional_activity=None, field=None, referees_needed=0, activity_type='torneo',
                      team1=None, team2=None, team3=None, team4=None, matchups_json=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scheduled_activities (
            catalog_id, title, description, day_of_week, start_time, end_time, week_start,
            category, optional_activity, field, referees_needed, activity_type,
            team1, team2, team3, team4, winner, second_place, third_place, fourth_place,
            matchups_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?)
    ''', (catalog_id, title, description, day_of_week, start_time, end_time, week_start,
          category, optional_activity, field, referees_needed, activity_type,
          team1, team2, team3, team4, matchups_json))
    conn.commit()
    inserted_id = cursor.lastrowid
    conn.close()
    return inserted_id

def update_scheduled_activity(activity_id, title, description, day_of_week, start_time, end_time, week_start,
                              category, optional_activity=None, field=None, referees_needed=0, activity_type='torneo',
                              team1=None, team2=None, team3=None, team4=None, winner=None,
                              second_place=None, third_place=None, fourth_place=None, matchups_json=None):
    conn = get_db_connection()
    conn.execute('''
        UPDATE scheduled_activities
        SET title = ?, description = ?, day_of_week = ?, start_time = ?, end_time = ?, week_start = ?,
            category = ?, optional_activity = ?, field = ?, referees_needed = ?, activity_type = ?,
            team1 = ?, team2 = ?, team3 = ?, team4 = ?, winner = ?,
            second_place = ?, third_place = ?, fourth_place = ?,
            matchups_json = ?
        WHERE id = ?
    ''', (title, description, day_of_week, start_time, end_time, week_start,
          category, optional_activity, field, referees_needed, activity_type,
          team1, team2, team3, team4, winner,
          second_place, third_place, fourth_place, matchups_json, activity_id))
    conn.commit()
    conn.close()

def get_scheduled_activities(week_start=None, day_of_week=None):
    conn = get_db_connection()
    query = '''
        SELECT sa.id, sa.catalog_id, sa.title, 
               COALESCE(sa.description, ac.description) as description, 
               sa.day_of_week, sa.start_time, sa.end_time, sa.week_start,
               sa.category, sa.optional_activity, sa.field,
               sa.referees_needed, sa.activity_type,
               sa.team1, sa.team2, sa.team3, sa.team4, sa.winner,
               sa.second_place, sa.third_place, sa.fourth_place,
               sa.matchups_json
        FROM scheduled_activities sa
        LEFT JOIN activity_catalog ac ON sa.catalog_id = ac.id
    '''
    params = []
    conditions = []
    if week_start:
        conditions.append('sa.week_start = ?')
        params.append(week_start)
    if day_of_week:
        conditions.append('sa.day_of_week = ?')
        params.append(day_of_week)
        
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
        
    query += '''
        ORDER BY 
            CASE sa.day_of_week
                WHEN 'Lunedì' THEN 1
                WHEN 'Martedì' THEN 2
                WHEN 'Mercoledì' THEN 3
                WHEN 'Giovedì' THEN 4
                WHEN 'Venerdì' THEN 5
                ELSE 6
            END ASC,
            sa.start_time ASC
    '''
    rows = conn.execute(query, params).fetchall()
    
    activities = []
    for row in rows:
        act = dict(row)
        ref_rows = conn.execute('SELECT referee_name FROM activity_referees WHERE scheduled_activity_id = ?', (act['id'],)).fetchall()
        act['referees'] = [r['referee_name'] for r in ref_rows]
        activities.append(act)
        
    conn.close()
    return activities

def get_scheduled_activity_by_id(activity_id):
    conn = get_db_connection()
    query = '''
        SELECT sa.id, sa.catalog_id, sa.title, 
               COALESCE(sa.description, ac.description) as description, 
               sa.day_of_week, sa.start_time, sa.end_time, sa.week_start,
               sa.category, sa.optional_activity, sa.field,
               sa.referees_needed, sa.activity_type,
               sa.team1, sa.team2, sa.team3, sa.team4, sa.winner,
               sa.second_place, sa.third_place, sa.fourth_place,
               sa.matchups_json
        FROM scheduled_activities sa
        LEFT JOIN activity_catalog ac ON sa.catalog_id = ac.id
        WHERE sa.id = ?
    '''
    row = conn.execute(query, (activity_id,)).fetchone()
    if not row:
        conn.close()
        return None
        
    activity = dict(row)
    ref_rows = conn.execute('SELECT referee_name FROM activity_referees WHERE scheduled_activity_id = ?', (activity_id,)).fetchall()
    activity['referees'] = [r['referee_name'] for r in ref_rows]
    conn.close()
    return activity

def add_activity_referee(activity_id, referee_name):
    conn = get_db_connection()
    success = False
    try:
        act = conn.execute('SELECT referees_needed FROM scheduled_activities WHERE id = ?', (activity_id,)).fetchone()
        if act:
            current_count = conn.execute('SELECT COUNT(*) as cnt FROM activity_referees WHERE scheduled_activity_id = ?', (activity_id,)).fetchone()['cnt']
            if current_count < act['referees_needed']:
                conn.execute('INSERT INTO activity_referees (scheduled_activity_id, referee_name) VALUES (?, ?)',
                             (activity_id, referee_name.strip()))
                conn.commit()
                success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    return success

def remove_activity_referee(activity_id, referee_name):
    conn = get_db_connection()
    conn.execute('DELETE FROM activity_referees WHERE scheduled_activity_id = ? AND referee_name = ?',
                 (activity_id, referee_name.strip()))
    conn.commit()
    conn.close()

def delete_scheduled_activity(activity_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM scheduled_activities WHERE id = ?', (activity_id,))
    conn.commit()
    conn.close()
