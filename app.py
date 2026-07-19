import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import database
import json

#aggiunta commento per prova

def add_minutes_to_time(time_str, minutes):
    try:
        t = datetime.strptime(time_str, "%H:%M")
        t_new = t + timedelta(minutes=minutes)
        return t_new.strftime("%H:%M")
    except ValueError:
        return time_str

def process_activity_matchups(act):
    if act.get('matchups_json'):
        try:
            matchups = json.loads(act['matchups_json'])
            for idx, matchup in enumerate(matchups):
                matchup['start_time'] = add_minutes_to_time(act['start_time'], idx * 30)
                matchup['end_time'] = add_minutes_to_time(act['start_time'], (idx + 1) * 30)
            act['matchups'] = matchups
        except Exception:
            act['matchups'] = []
    else:
        if act.get('team1') or act.get('team2'):
            act['matchups'] = [{
                'team1': act.get('team1'),
                'team2': act.get('team2'),
                'team3': act.get('team3'),
                'team4': act.get('team4'),
                'winner': act.get('winner'),
                'second_place': act.get('second_place'),
                'third_place': act.get('third_place'),
                'fourth_place': act.get('fourth_place'),
                'start_time': act['start_time'],
                'end_time': act['end_time']
            }]
        else:
            act['matchups'] = []
    return act

app = Flask(__name__)
app.secret_key = 'centro_estivo_secret_key_super_secure'

# Codice di invito fisso per la registrazione di amministratori
REGISTRATION_INVITE_CODE = "ESTATE2026"

# Assicuriamoci che il database sia inizializzato all'avvio
with app.app_context():
    database.init_db()

# Nomi dei giorni in italiano (Solo feriali: da Lunedì a Venerdì)
DAY_NAMES = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì']

def get_teams_for_category(category):
    if not category:
        return []
    colors = ['Blu', 'Rossi', 'Verdi', 'Gialli']
    return [f"{category}{color}" for color in colors]

# Squadre predefinite (fallback per scopi globali)
PREDEFINED_TEAMS = [
    'macroRossi', 'macroVerdi', 'macroGialli', 'macroBlu',
    'MagnumRossi', 'MagnumVerdi', 'MagnumGialli', 'MagnumBlu'
]

def category_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'age_group' not in session:
            flash('Seleziona prima una categoria d\'età per procedere.', 'info')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Fasce orarie da 15 minuti (dalle 09:00 alle 17:00)
TIME_SLOTS = [
    ("09:00", "09:15"),
    ("09:15", "09:30"),
    ("09:30", "09:45"),
    ("09:45", "10:00"),
    ("10:00", "10:15"),
    ("10:15", "10:30"),
    ("10:30", "10:45"),
    ("10:45", "11:00"),
    ("11:00", "11:15"),
    ("11:15", "11:30"),
    ("11:30", "11:45"),
    ("11:45", "12:00"),
    ("12:00", "12:15"),
    ("12:15", "12:30"),
    ("12:30", "12:45"),
    ("12:45", "13:00"),
    ("13:00", "13:15"),
    ("13:15", "13:30"),
    ("13:30", "13:45"),
    ("13:45", "14:00"),
    ("14:00", "14:15"),
    ("14:15", "14:30"),
    ("14:30", "14:45"),
    ("14:45", "15:00"),
    ("15:00", "15:15"),
    ("15:15", "15:30"),
    ("15:30", "15:45"),
    ("15:45", "16:00"),
    ("16:00", "16:15"),
    ("16:15", "16:30"),
    ("16:30", "16:45"),
    ("16:45", "17:00")
]


def get_monday(date_obj):
    """Restituisce la data del Lunedì della settimana a cui appartiene la data fornita."""
    return date_obj - timedelta(days=date_obj.weekday())

def time_to_grid_row(time_str):
    """Calcola la riga iniziale della griglia CSS in base all'ora HH:MM (dalle 09:00 in poi, slot di 15m)"""
    try:
        hours, minutes = map(int, time_str.split(':'))
        # Calcola i minuti passati dalle 09:00
        elapsed_minutes = (hours - 9) * 60 + minutes
        # Ogni slot dura 15 minuti, restituiamo l'indice 1-based per CSS Grid con arrotondamento
        row_index = int(round(elapsed_minutes / 15.0)) + 1
        return row_index
    except Exception:
        return 1

def assign_grid_positions(activities):
    """Assegna le righe e le colonne di griglia a ciascuna attività per gestire le sovrapposizioni."""
    if not activities:
        return []
    
    # 1. Assegna righe iniziali e finali di griglia
    for act in activities:
        act['grid_row_start'] = time_to_grid_row(act['start_time'])
        act['grid_row_end'] = time_to_grid_row(act['end_time'])
        if act['grid_row_end'] <= act['grid_row_start']:
            act['grid_row_end'] = act['grid_row_start'] + 1
            
    # Ordina per ora d'inizio e poi per ora di fine (decrescente per coprire prima le attività più lunghe)
    sorted_acts = sorted(activities, key=lambda x: (x['start_time'], x['end_time']))
    
    # 2. Raggruppa in cluster di attività sovrapposte temporalmente
    clusters = []
    for act in sorted_acts:
        placed = False
        for cluster in clusters:
            if act['start_time'] < cluster['max_end']:
                cluster['activities'].append(act)
                if act['end_time'] > cluster['max_end']:
                    cluster['max_end'] = act['end_time']
                placed = True
                break
        if not placed:
            clusters.append({
                'activities': [act],
                'max_end': act['end_time']
            })
            
    # 3. Alloca colonne in ciascun cluster per evitare sovrapposizioni visive
    for cluster in clusters:
        columns = []  # Elenco di colonne, ciascuna contiene attività non sovrapposte tra loro
        for act in cluster['activities']:
            placed_in_col = False
            for col_idx, col in enumerate(columns):
                overlap = False
                for existing_act in col:
                    if act['start_time'] < existing_act['end_time'] and existing_act['start_time'] < act['end_time']:
                        overlap = True
                        break
                if not overlap:
                    col.append(act)
                    act['col_index'] = col_idx
                    placed_in_col = True
                    break
            if not placed_in_col:
                columns.append([act])
                act['col_index'] = len(columns) - 1
                
        num_cols = len(columns)
        for act in cluster['activities']:
            act['cluster_cols'] = num_cols
            col_idx = act['col_index']
            # Calcola le colonne della griglia CSS (su 12 colonne totali)
            start_col = int(col_idx * 12 / num_cols) + 1
            end_col = int((col_idx + 1) * 12 / num_cols) + 1
            if end_col > 13:
                end_col = 13
            act['grid_col_start'] = start_col
            act['grid_col_end'] = end_col
            
    return sorted_acts


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Devi accedere come amministratore per visualizzare questa pagina.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Context processor per rendere disponibili le variabili globali nei template Jinja2
@app.context_processor
def inject_globals():
    age_group = session.get('age_group')
    teams = get_teams_for_category(age_group) if age_group else []
    return dict(
        is_admin=('user_id' in session),
        PREDEFINED_TEAMS=teams,
        TIME_SLOTS=TIME_SLOTS,
        selected_age_group=age_group,
        CATEGORIES=['micro', 'mini', 'medi', 'maxi', 'mega', 'macro']
    )

@app.route('/')
def index():
    if 'age_group' not in session:
        return render_template('select_category.html')
        
    age_group = session['age_group']
    # Mostra per default le attività della settimana corrente
    today = datetime.now().date()
    current_monday = get_monday(today)
    current_monday_str = current_monday.strftime('%Y-%m-%d')
    current_friday = current_monday + timedelta(days=4)
    
    activities = database.get_scheduled_activities(week_start=current_monday_str, age_group=age_group)
    week_range_str = f"dal {current_monday.strftime('%d/%m/%Y')} al {current_friday.strftime('%d/%m/%Y')}"
    
    return render_template('index.html', activities=activities, week_range_str=week_range_str, current_week=current_monday_str)

@app.route('/set-category/<category_name>')
def set_category(category_name):
    valid_categories = ['micro', 'mini', 'medi', 'maxi', 'mega', 'macro']
    if category_name in valid_categories:
        session['age_group'] = category_name
        flash(f'Categoria {category_name.capitalize()} selezionata con successo.', 'success')
    return redirect(url_for('index'))

@app.route('/change-category')
def change_category():
    session.pop('age_group', None)
    return redirect(url_for('index'))

@app.route('/schedule')
@category_required
def schedule():
    week_param = request.args.get('week')
    day_param = request.args.get('day')
    
    today = datetime.now().date()
    current_monday = get_monday(today)
    
    selected_monday = current_monday
    if week_param:
        try:
            selected_monday = datetime.strptime(week_param, '%Y-%m-%d').date()
            selected_monday = get_monday(selected_monday)
        except ValueError:
            selected_monday = current_monday
            
    selected_monday_str = selected_monday.strftime('%Y-%m-%d')
    prev_week = (selected_monday - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (selected_monday + timedelta(days=7)).strftime('%Y-%m-%d')
    
    selected_day = day_param
    if not selected_day or selected_day not in DAY_NAMES:
        # Se oggi è sabato o domenica ( weekday >= 5 ), di default mostra lunedì
        if selected_monday == current_monday and today.weekday() < 5:
            selected_day = DAY_NAMES[today.weekday()]
        else:
            selected_day = 'Lunedì'
            
    day_dates = {}
    for i, name in enumerate(DAY_NAMES):
        date_for_day = selected_monday + timedelta(days=i)
        day_dates[name] = date_for_day.strftime('%d/%m')
        
    # Carica le attività della settimana e giorno
    activities = database.get_scheduled_activities(week_start=selected_monday_str, day_of_week=selected_day, age_group=session['age_group'])
    activities = [process_activity_matchups(act) for act in activities]
    
    # Calcola il posizionamento per la griglia CSS
    positioned_activities = assign_grid_positions(activities)
                
    week_end = selected_monday + timedelta(days=4)
    week_range_str = f"dal {selected_monday.strftime('%d/%m/%Y')} al {week_end.strftime('%d/%m/%Y')}"
    
    return render_template(
        'schedule.html',
        activities=positioned_activities,
        days=DAY_NAMES,
        selected_day=selected_day,
        selected_week=selected_monday_str,
        prev_week=prev_week,
        next_week=next_week,
        day_dates=day_dates,
        week_range_str=week_range_str
    )

@app.route('/book-referee/<int:activity_id>', methods=['POST'])
def book_referee(activity_id):
    referee_name = request.form.get('referee_name')
    if not referee_name or not referee_name.strip():
        flash('Inserisci un nome valido per prenotarti come arbitro.', 'error')
        return redirect(request.referrer or url_for('index'))
    
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
        
    if len(activity['referees']) >= activity['referees_needed']:
        flash('Tutti i posti per l\'arbitraggio sono già occupati.', 'error')
        return redirect(request.referrer or url_for('index'))
        
    if referee_name.strip() in activity['referees']:
        flash('Sei già prenotato come arbitro per questa attività.', 'error')
        return redirect(request.referrer or url_for('index'))
        
    success = database.add_activity_referee(activity_id, referee_name.strip())
    if success:
        flash(f'Ti sei prenotato con successo come arbitro per "{activity["title"]}"!', 'success')
    else:
        flash('Errore durante la registrazione della prenotazione. Riprova.', 'error')
    return redirect(request.referrer or url_for('index'))

@app.route('/cancel-referee/<int:activity_id>', methods=['POST'])
def cancel_referee(activity_id):
    referee_name = request.form.get('referee_name')
    if not referee_name or not referee_name.strip():
        flash('Nome dell\'arbitro non specificato.', 'error')
        return redirect(request.referrer or url_for('index'))
        
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
        
    database.remove_activity_referee(activity_id, referee_name.strip())
    flash(f'La prenotazione dell\'arbitro ({referee_name}) è stata annullata.', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/create', methods=['GET', 'POST'])
@login_required
@category_required
def create_activity():
    today = datetime.now().date()
    current_monday = get_monday(today)
    
    if request.method == 'POST':
        category = request.form.get('category', 'gioco')
        day_of_week = request.form.get('day_of_week')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        week_start = request.form.get('week_start')
        
        if not day_of_week or not start_time or not end_time or not week_start:
            flash('Tutti i parametri temporali sono obbligatori.', 'error')
            return redirect(url_for('create_activity'))
            
        if start_time >= end_time:
            flash('L\'ora di inizio deve essere precedente all\'ora di fine.', 'error')
            return redirect(url_for('create_activity'))
            
        # Inizializza variabili di default
        catalog_id = None
        title = ""
        description = ""
        optional_activity = None
        field = None
        referees_needed = 0
        activity_type = 'torneo'
        team1 = team2 = team3 = team4 = matchups_json = None
        
        CAT_TITLES = {
            'cerchio': 'Cerchio',
            'laboratorio_sportivo': 'Laboratorio Sportivo',
            'laboratorio_speciale': 'Laboratorio Speciale',
            'intervallo': 'Intervallo',
            'pranzo': 'Pranzo',
            'compiti': 'Compiti'
        }
        
        if category == 'gioco':
            catalog_selection = request.form.get('catalog_selection') # 'existing' o 'new'
            referees_needed = int(request.form.get('referees_needed', 1))
            activity_type = request.form.get('activity_type', 'torneo')
            field = request.form.get('field', '').strip()
            
            teams1 = request.form.getlist('team1')
            teams2 = request.form.getlist('team2')
            teams3 = request.form.getlist('team3') or []
            teams4 = request.form.getlist('team4') or []
            
            matchups = []
            length = max(len(teams1), len(teams2))
            if activity_type == 'grande_gioco':
                length = max(length, len(teams3), len(teams4))
                
            for idx in range(length):
                t1 = teams1[idx].strip() if idx < len(teams1) and teams1[idx] else ""
                t2 = teams2[idx].strip() if idx < len(teams2) and teams2[idx] else ""
                t3 = teams3[idx].strip() if (idx < len(teams3) and teams3[idx] and activity_type == 'grande_gioco') else ""
                t4 = teams4[idx].strip() if (idx < len(teams4) and teams4[idx] and activity_type == 'grande_gioco') else ""
                
                if t1 or t2:
                    matchups.append({
                        'team1': t1,
                        'team2': t2,
                        'team3': t3 or None,
                        'team4': t4 or None,
                        'winner': None,
                        'second_place': None,
                        'third_place': None,
                        'fourth_place': None
                    })
                    
            if not matchups:
                flash('Inserisci almeno un abbinamento di squadre.', 'error')
                return redirect(url_for('create_activity'))
                
            first_match = matchups[0]
            if not first_match['team1'] or not first_match['team2']:
                flash('Per il gioco inserisci almeno le prime due squadre per il primo abbinamento.', 'error')
                return redirect(url_for('create_activity'))
                
            if activity_type == 'grande_gioco' and (not first_match['team3'] or not first_match['team4']):
                flash('Per un Grande Gioco inserisci tutte e 4 le squadre per il primo abbinamento.', 'error')
                return redirect(url_for('create_activity'))
                
            team1 = first_match['team1']
            team2 = first_match['team2']
            team3 = first_match['team3']
            team4 = first_match['team4']
            matchups_json = json.dumps(matchups)
                
            if catalog_selection == 'existing':
                catalog_id = request.form.get('existing_activity_id')
                if not catalog_id:
                    flash('Seleziona un gioco dal catalogo.', 'error')
                    return redirect(url_for('create_activity'))
                
                catalog_act = database.get_catalog_activity_by_id(catalog_id)
                if not catalog_act:
                    flash('Gioco selezionato non valido.', 'error')
                    return redirect(url_for('create_activity'))
                    
                title = catalog_act['name']
                description = catalog_act['description']
                
            elif catalog_selection == 'new':
                new_name = request.form.get('new_activity_name')
                new_description = request.form.get('new_activity_description')
                
                if not new_name or not new_name.strip() or not new_description or not new_description.strip():
                    flash('Inserisci il nome e la descrizione per il nuovo gioco.', 'error')
                    return redirect(url_for('create_activity'))
                    
                catalog_id = database.add_catalog_activity(new_name.strip(), new_description.strip())
                title = new_name.strip()
                description = new_description.strip()
            else:
                flash('Selezione catalogo non valida.', 'error')
                return redirect(url_for('create_activity'))
                
        elif category == 'gioco_evento':
            title = request.form.get('title', '').strip()
            if not title:
                flash('Il titolo del gioco evento è obbligatorio.', 'error')
                return redirect(url_for('create_activity'))
            description = request.form.get('description', '').strip() or None
            
        elif category in CAT_TITLES:
            title = CAT_TITLES[category]
            description = ""
            if category == 'cerchio':
                optional_activity = request.form.get('optional_activity', '').strip() or None
        else:
            flash('Categoria non supportata.', 'error')
            return redirect(url_for('create_activity'))
            
        # Salva nel DB
        database.schedule_activity(
            catalog_id, title, description, day_of_week, start_time, end_time, week_start,
            category, optional_activity, field, referees_needed, activity_type,
            team1, team2, team3, team4, matchups_json, age_group=session['age_group']
        )
        flash(f'Attività "{title}" programmata con successo!', 'success')
        return redirect(url_for('schedule', week=week_start, day=day_of_week))
        
    catalog = database.get_catalog_activities()
    
    # Genera le opzioni per le settimane
    weeks_options = []
    for i in range(5):
        mon = current_monday + timedelta(weeks=i)
        sun = mon + timedelta(days=4)
        weeks_options.append({
            'value': mon.strftime('%Y-%m-%d'),
            'label': f"Settimana {mon.strftime('%d/%m/%Y')} - {sun.strftime('%d/%m/%Y')}"
        })
        
    return render_template('create.html', catalog=catalog, days=DAY_NAMES, weeks_options=weeks_options)

@app.route('/activity/<int:activity_id>/edit', methods=['GET', 'POST'])
@login_required
@category_required
def edit_activity(activity_id):
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
    activity = process_activity_matchups(activity)
        
    today = datetime.now().date()
    current_monday = get_monday(today)
    
    if request.method == 'POST':
        category = request.form.get('category', 'gioco')
        day_of_week = request.form.get('day_of_week')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        week_start = request.form.get('week_start')
        
        if not day_of_week or not start_time or not end_time or not week_start:
            flash('Tutti i campi temporali sono obbligatori.', 'error')
            return redirect(url_for('edit_activity', activity_id=activity_id))
            
        if start_time >= end_time:
            flash('L\'ora di inizio deve essere precedente all\'ora di fine.', 'error')
            return redirect(url_for('edit_activity', activity_id=activity_id))
            
        # Inizializza parametri condizionali
        title = ""
        description = ""
        optional_activity = None
        field = None
        referees_needed = 0
        activity_type = 'torneo'
        team1 = team2 = team3 = team4 = matchups_json = None
        winner = None
        second_place = None
        third_place = None
        fourth_place = None
        
        CAT_TITLES = {
            'cerchio': 'Cerchio',
            'laboratorio_sportivo': 'Laboratorio Sportivo',
            'laboratorio_speciale': 'Laboratorio Speciale',
            'intervallo': 'Intervallo',
            'pranzo': 'Pranzo',
            'compiti': 'Compiti'
        }
        
        if category == 'gioco':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            if not title:
                flash('Il titolo del gioco è obbligatorio.', 'error')
                return redirect(url_for('edit_activity', activity_id=activity_id))
                
            referees_needed = int(request.form.get('referees_needed', 1))
            activity_type = request.form.get('activity_type', 'torneo')
            field = request.form.get('field', '').strip()
            
            existing_matchups = []
            if activity.get('matchups_json'):
                try:
                    existing_matchups = json.loads(activity['matchups_json'])
                except Exception:
                    pass
                    
            teams1 = request.form.getlist('team1')
            teams2 = request.form.getlist('team2')
            teams3 = request.form.getlist('team3') or []
            teams4 = request.form.getlist('team4') or []
            
            matchups = []
            length = max(len(teams1), len(teams2))
            if activity_type == 'grande_gioco':
                length = max(length, len(teams3), len(teams4))
                
            for idx in range(length):
                t1 = teams1[idx].strip() if idx < len(teams1) and teams1[idx] else ""
                t2 = teams2[idx].strip() if idx < len(teams2) and teams2[idx] else ""
                t3 = teams3[idx].strip() if (idx < len(teams3) and teams3[idx] and activity_type == 'grande_gioco') else ""
                t4 = teams4[idx].strip() if (idx < len(teams4) and teams4[idx] and activity_type == 'grande_gioco') else ""
                
                if t1 or t2:
                    m_win = m_2nd = m_3rd = m_4th = None
                    if idx < len(existing_matchups):
                        old_m = existing_matchups[idx]
                        valid_t = [t1, t2]
                        if activity_type == 'grande_gioco':
                            valid_t.extend([t3, t4])
                        if old_m.get('winner') in valid_t or old_m.get('winner') == 'Pareggio':
                            m_win = old_m.get('winner')
                        if old_m.get('second_place') in valid_t:
                            m_2nd = old_m.get('second_place')
                        if old_m.get('third_place') in valid_t:
                            m_3rd = old_m.get('third_place')
                        if old_m.get('fourth_place') in valid_t:
                            m_4th = old_m.get('fourth_place')
                            
                    matchups.append({
                        'team1': t1,
                        'team2': t2,
                        'team3': t3 or None,
                        'team4': t4 or None,
                        'winner': m_win,
                        'second_place': m_2nd,
                        'third_place': m_3rd,
                        'fourth_place': m_4th
                    })
                    
            if not matchups:
                flash('Inserisci almeno un abbinamento di squadre.', 'error')
                return redirect(url_for('edit_activity', activity_id=activity_id))
                
            first_match = matchups[0]
            if not first_match['team1'] or not first_match['team2']:
                flash('Per il gioco inserisci almeno le prime due squadre per il primo abbinamento.', 'error')
                return redirect(url_for('edit_activity', activity_id=activity_id))
                
            if activity_type == 'grande_gioco' and (not first_match['team3'] or not first_match['team4']):
                flash('Per un Grande Gioco inserisci tutte e 4 le squadre per il primo abbinamento.', 'error')
                return redirect(url_for('edit_activity', activity_id=activity_id))
                
            team1 = first_match['team1']
            team2 = first_match['team2']
            team3 = first_match['team3']
            team4 = first_match['team4']
            winner = first_match['winner']
            second_place = first_match['second_place']
            third_place = first_match['third_place']
            fourth_place = first_match['fourth_place']
            matchups_json = json.dumps(matchups)
                
        elif category == 'gioco_evento':
            title = request.form.get('title', '').strip()
            if not title:
                flash('Il titolo del gioco evento è obbligatorio.', 'error')
                return redirect(url_for('edit_activity', activity_id=activity_id))
            description = request.form.get('description', '').strip() or None
            
        elif category in CAT_TITLES:
            title = CAT_TITLES[category]
            description = ""
            if category == 'cerchio':
                optional_activity = request.form.get('optional_activity', '').strip() or None
        else:
            flash('Categoria non supportata.', 'error')
            return redirect(url_for('edit_activity', activity_id=activity_id))
            
        database.update_scheduled_activity(
            activity_id, title, description, day_of_week, start_time, end_time, week_start,
            category, optional_activity, field, referees_needed, activity_type,
            team1, team2, team3, team4, winner,
            second_place, third_place, fourth_place, matchups_json, age_group=activity['age_group']
        )
        flash(f'Attività "{title}" aggiornata con successo!', 'success')
        return redirect(url_for('activity_detail', activity_id=activity_id, back_week=week_start, back_day=day_of_week))
        
    catalog = database.get_catalog_activities()
    
    # Genera le opzioni per le settimane
    weeks_options = []
    for i in range(5):
        mon = current_monday + timedelta(weeks=i)
        sun = mon + timedelta(days=4)
        weeks_options.append({
            'value': mon.strftime('%Y-%m-%d'),
            'label': f"Settimana {mon.strftime('%d/%m/%Y')} - {sun.strftime('%d/%m/%Y')}"
        })
        
    return render_template('edit.html', activity=activity, catalog=catalog, days=DAY_NAMES, weeks_options=weeks_options)

@app.route('/activity/<int:activity_id>')
def activity_detail(activity_id):
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
        
    if session.get('age_group') != activity.get('age_group'):
        session['age_group'] = activity.get('age_group')
        
    activity = process_activity_matchups(activity)
        
    back_week = request.args.get('back_week')
    back_day = request.args.get('back_day')
    
    return render_template(
        'activity_detail.html',
        activity=activity,
        back_week=back_week,
        back_day=back_day
    )

@app.route('/activity/<int:activity_id>/set-winner', methods=['POST'])
def set_winner(activity_id):
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
        
    winner = request.form.get('winner')
    valid_winners = [activity['team1'], activity['team2'], 'Pareggio']
    
    if winner not in valid_winners:
        flash('Scelta del vincitore non valida.', 'error')
        return redirect(url_for('activity_detail', activity_id=activity_id))
        
    database.update_scheduled_activity(
        activity['id'], activity['title'], activity['description'], activity['day_of_week'],
        activity['start_time'], activity['end_time'], activity['week_start'],
        activity['category'], activity['optional_activity'], activity['field'],
        activity['referees_needed'], activity['activity_type'],
        activity['team1'], activity['team2'], activity['team3'], activity['team4'],
        winner, activity['second_place'], activity['third_place'], activity['fourth_place']
    )
    flash(f'Risultato salvato: {winner}!', 'success')
    return redirect(url_for('activity_detail', activity_id=activity_id))

@app.route('/activity/<int:activity_id>/set-ranking', methods=['POST'])
def set_ranking(activity_id):
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
        
    first = request.form.get('first')
    second = request.form.get('second')
    third = request.form.get('third')
    fourth = request.form.get('fourth')
    
    participating_teams = [activity['team1'], activity['team2'], activity['team3'], activity['team4']]
    submitted_ranking = [first, second, third, fourth]
    
    if any(team not in participating_teams for team in submitted_ranking):
        flash('Tutti i piazzamenti devono corrispondere alle squadre partecipanti.', 'error')
        return redirect(url_for('activity_detail', activity_id=activity_id))
        
    if len(set(submitted_ranking)) < 4:
        flash('Ogni squadra deve occupare una posizione unica.', 'error')
        return redirect(url_for('activity_detail', activity_id=activity_id))
        
    database.update_scheduled_activity(
        activity['id'], activity['title'], activity['description'], activity['day_of_week'],
        activity['start_time'], activity['end_time'], activity['week_start'],
        activity['category'], activity['optional_activity'], activity['field'],
        activity['referees_needed'], activity['activity_type'],
        activity['team1'], activity['team2'], activity['team3'], activity['team4'],
        first, second, third, fourth
    )
    flash('Classifica del Grande Gioco salvata con successo!', 'success')
    return redirect(url_for('activity_detail', activity_id=activity_id))

@app.route('/activity/<int:activity_id>/set-matchup-winner', methods=['POST'])
def set_matchup_winner(activity_id):
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
        
    matchup_index = int(request.form.get('matchup_index', 0))
    winner = request.form.get('winner')
    
    matchups = []
    if activity.get('matchups_json'):
        try:
            matchups = json.loads(activity['matchups_json'])
        except Exception:
            pass
            
    if not matchups:
        matchups = [{
            'team1': activity['team1'],
            'team2': activity['team2'],
            'winner': activity['winner']
        }]
        
    if matchup_index >= len(matchups):
        flash('Indice abbinamento non valido.', 'error')
        return redirect(url_for('activity_detail', activity_id=activity_id))
        
    matchup = matchups[matchup_index]
    valid_winners = [matchup.get('team1'), matchup.get('team2'), 'Pareggio']
    if winner not in valid_winners:
        flash('Scelta del vincitore non valida.', 'error')
        return redirect(url_for('activity_detail', activity_id=activity_id))
        
    matchup['winner'] = winner
    
    main_winner = winner if matchup_index == 0 else activity['winner']
    
    database.update_scheduled_activity(
        activity['id'], activity['title'], activity['description'], activity['day_of_week'],
        activity['start_time'], activity['end_time'], activity['week_start'],
        activity['category'], activity['optional_activity'], activity['field'],
        activity['referees_needed'], activity['activity_type'],
        activity['team1'], activity['team2'], activity['team3'], activity['team4'],
        main_winner, activity['second_place'], activity['third_place'], activity['fourth_place'],
        json.dumps(matchups)
    )
    flash('Risultato dell\'abbinamento salvato con successo!', 'success')
    return redirect(url_for('activity_detail', activity_id=activity_id))

@app.route('/activity/<int:activity_id>/set-matchup-ranking', methods=['POST'])
def set_matchup_ranking(activity_id):
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
        
    matchup_index = int(request.form.get('matchup_index', 0))
    first = request.form.get('first')
    second = request.form.get('second')
    third = request.form.get('third')
    fourth = request.form.get('fourth')
    
    matchups = []
    if activity.get('matchups_json'):
        try:
            matchups = json.loads(activity['matchups_json'])
        except Exception:
            pass
            
    if not matchups:
        matchups = [{
            'team1': activity['team1'],
            'team2': activity['team2'],
            'team3': activity['team3'],
            'team4': activity['team4'],
            'winner': activity['winner'],
            'second_place': activity['second_place'],
            'third_place': activity['third_place'],
            'fourth_place': activity['fourth_place']
        }]
        
    if matchup_index >= len(matchups):
        flash('Indice abbinamento non valido.', 'error')
        return redirect(url_for('activity_detail', activity_id=activity_id))
        
    matchup = matchups[matchup_index]
    participating = [matchup.get('team1'), matchup.get('team2'), matchup.get('team3'), matchup.get('team4')]
    ranking = [first, second, third, fourth]
    
    if any(t not in participating for t in ranking) or len(set(ranking)) < 4:
        flash('Tutti i piazzamenti devono corrispondere alle squadre partecipanti dell\'abbinamento e le posizioni devono essere uniche.', 'error')
        return redirect(url_for('activity_detail', activity_id=activity_id))
        
    matchup['winner'] = first
    matchup['second_place'] = second
    matchup['third_place'] = third
    matchup['fourth_place'] = fourth
    
    main_w = first if matchup_index == 0 else activity['winner']
    main_s = second if matchup_index == 0 else activity['second_place']
    main_t = third if matchup_index == 0 else activity['third_place']
    main_f = fourth if matchup_index == 0 else activity['fourth_place']
    
    database.update_scheduled_activity(
        activity['id'], activity['title'], activity['description'], activity['day_of_week'],
        activity['start_time'], activity['end_time'], activity['week_start'],
        activity['category'], activity['optional_activity'], activity['field'],
        activity['referees_needed'], activity['activity_type'],
        activity['team1'], activity['team2'], activity['team3'], activity['team4'],
        main_w, main_s, main_t, main_f,
        json.dumps(matchups)
    )
    flash('Classifica dell\'abbinamento salvata con successo!', 'success')
    return redirect(url_for('activity_detail', activity_id=activity_id))

@app.route('/admin/leaderboard')
@login_required
@category_required
def admin_leaderboard():
    week_param = request.args.get('week')
    today = datetime.now().date()
    current_monday = get_monday(today)
    
    selected_monday = current_monday
    if week_param:
        try:
            selected_monday = datetime.strptime(week_param, '%Y-%m-%d').date()
            selected_monday = get_monday(selected_monday)
        except ValueError:
            selected_monday = current_monday
            
    selected_monday_str = selected_monday.strftime('%Y-%m-%d')
    week_end = selected_monday + timedelta(days=4)
    week_range_str = f"dal {selected_monday.strftime('%d/%m/%Y')} al {week_end.strftime('%d/%m/%Y')}"
    
    prev_week = (selected_monday - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (selected_monday + timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Prepara la matrice scores[team][day] = points
    age_group = session['age_group']
    teams = get_teams_for_category(age_group)
    scores = {team: {day: 0 for day in DAY_NAMES} for team in teams}
    
    activities = database.get_scheduled_activities(week_start=selected_monday_str, age_group=age_group)
    
    for act in activities:
        if act['category'] == 'gioco':
            day = act['day_of_week']
            if day not in DAY_NAMES:
                continue
                
            matchups = []
            if act.get('matchups_json'):
                try:
                    matchups = json.loads(act['matchups_json'])
                except Exception:
                    pass
            
            if not matchups:
                matchups = [{
                    'team1': act['team1'],
                    'team2': act['team2'],
                    'team3': act['team3'],
                    'team4': act['team4'],
                    'winner': act['winner'],
                    'second_place': act['second_place'],
                    'third_place': act['third_place'],
                    'fourth_place': act['fourth_place']
                }]
                
            for matchup in matchups:
                if act['activity_type'] == 'torneo':
                    win = matchup.get('winner')
                    if win:
                        if win == 'Pareggio':
                            t1, t2 = matchup.get('team1'), matchup.get('team2')
                            if t1 in scores: scores[t1][day] += 50
                            if t2 in scores: scores[t2][day] += 50
                        else:
                            t1, t2 = matchup.get('team1'), matchup.get('team2')
                            winner_team = win
                            loser_team = t2 if winner_team == t1 else t1
                            if winner_team in scores: scores[winner_team][day] += 70
                            if loser_team in scores: scores[loser_team][day] += 30
                            
                elif act['activity_type'] == 'grande_gioco':
                    first = matchup.get('winner')
                    second = matchup.get('second_place')
                    third = matchup.get('third_place')
                    fourth = matchup.get('fourth_place')
                    
                    if first:
                        if first in scores: scores[first][day] += 200
                        if second in scores: scores[second][day] += 150
                        if third in scores: scores[third][day] += 100
                        if fourth in scores: scores[fourth][day] += 50
                    
    # Calcola i totali
    totals = {}
    for team in teams:
        totals[team] = sum(scores[team].values())
        
    sorted_teams = sorted(teams, key=lambda t: totals[t], reverse=True)
    
    # Opzioni settimane (mostriamo le scorse 2, la corrente e le prossime 2)
    weeks_options = []
    for i in range(5):
        mon = current_monday + timedelta(weeks=i - 2)
        sun = mon + timedelta(days=4)
        weeks_options.append({
            'value': mon.strftime('%Y-%m-%d'),
            'label': f"Settimana {mon.strftime('%d/%m/%Y')} - {sun.strftime('%d/%m/%Y')}"
        })
        
    return render_template(
        'admin_leaderboard.html',
        scores=scores,
        totals=totals,
        sorted_teams=sorted_teams,
        selected_week=selected_monday_str,
        prev_week=prev_week,
        next_week=next_week,
        week_range_str=week_range_str,
        days=DAY_NAMES,
        weeks_options=weeks_options
    )

@app.route('/delete-activity/<int:activity_id>', methods=['POST'])
@login_required
def delete_activity(activity_id):
    activity = database.get_scheduled_activity_by_id(activity_id)
    if not activity:
        flash('Attività non trovata.', 'error')
        return redirect(url_for('index'))
        
    database.delete_scheduled_activity(activity_id)
    flash(f'L\'attività "{activity["title"]}" è stata rimossa dal calendario.', 'success')
    
    back_week = request.form.get('back_week')
    back_day = request.form.get('back_day')
    if back_week and back_day:
        return redirect(url_for('schedule', week=back_week, day=back_day))
    return redirect(url_for('schedule'))

# --- Rotte di Autenticazione ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = database.get_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'Bentornato, {username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Credenziali non valide. Riprova.', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        invite_code = request.form.get('invite_code')
        
        if not username or not password:
            flash('Inserisci username e password.', 'error')
            return redirect(url_for('register'))
            
        if invite_code != REGISTRATION_INVITE_CODE:
            flash('Codice invito non valido. Non sei autorizzato a registrarti come amministratore.', 'error')
            return redirect(url_for('register'))
            
        password_hash = generate_password_hash(password)
        success = database.create_user(username, password_hash)
        
        if success:
            flash('Registrazione completata con successo! Ora puoi accedere.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Questo username è già registrato.', 'error')
            
    return render_template('register.html', invite_code_hint=REGISTRATION_INVITE_CODE)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Disconnessione effettuata con successo.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
