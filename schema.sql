-- Schema per il database del Gestionale Centro Estivo

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'admin'
);

CREATE TABLE IF NOT EXISTS activity_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduled_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id INTEGER REFERENCES activity_catalog(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    day_of_week TEXT NOT NULL,
    start_time TEXT NOT NULL,       -- es. "09:00"
    end_time TEXT NOT NULL,         -- es. "10:30"
    week_start TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'gioco', -- 'cerchio', 'gioco', 'intervallo', 'pranzo', 'compiti', 'laboratorio_sportivo', 'laboratorio_speciale'
    optional_activity TEXT,         -- Solo per 'cerchio'
    field TEXT,                     -- Solo per 'gioco'
    referees_needed INTEGER NOT NULL DEFAULT 1,
    activity_type TEXT NOT NULL DEFAULT 'torneo', -- 'torneo' (2 squadre) o 'grande_gioco' (4 squadre)
    team1 TEXT,
    team2 TEXT,
    team3 TEXT,
    team4 TEXT,
    winner TEXT,                    -- Squadra vincitrice (1° posto, o 'Pareggio' per torneo)
    second_place TEXT,              -- Per Grande Gioco
    third_place TEXT,               -- Per Grande Gioco
    fourth_place TEXT               -- Per Grande Gioco
);

CREATE TABLE IF NOT EXISTS activity_referees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_activity_id INTEGER REFERENCES scheduled_activities(id) ON DELETE CASCADE,
    referee_name TEXT NOT NULL,
    UNIQUE(scheduled_activity_id, referee_name)
);

-- Inserimento di alcune attività di default nel catalogo
INSERT OR IGNORE INTO activity_catalog (name, description) VALUES 
('Palla Prigioniera', 'Due squadre si sfidano in un campo diviso a metà. L''obiettivo è colpire i giocatori avversari con la palla per "imprigionarli" nella zona dei prigionieri dietro la linea di fondo avversaria.'),
('Roverino', 'Un classico gioco scout e di centro estivo. Le squadre devono far passare un cerchio (il roverino) attraverso un bastone difeso da un avversario per fare punto.'),
('Caccia al Tesoro', 'Un gioco di esplorazione e indovinelli a indizi sparsi per tutta l''area del centro estivo. Vince la squadra che trova per prima il tesoro.'),
('Rubabandiera', 'Due squadre posizionate alle estremità opposte del campo. Al richiamo del proprio numero, i giocatori corrono al centro per afferrare la bandiera (fazzoletto) tenuta dal capo gioco e portarla alla propria base senza farsi toccare.'),
('Staffetta d''Acqua', 'I partecipanti devono trasportare acqua da un secchio all''altro usando bicchieri bucati o spugne. Vince chi riempie di più il secchio finale nel tempo stabilito.'),
('Torneo di Calcio', 'Partite di calcio a ranghi ridotti su campi ridotti, adatte a tutte le età, con spirito amichevole.'),
('Laboratorio Creativo', 'Attività manuale al coperto: pittura, argilla, creazione di braccialetti o lavoretti con materiali di riciclo.');
