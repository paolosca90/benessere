"""Benessere v0.3 — dashboard responsive, dati reali, benchmark e massimali."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from benessere import db as store
from benessere import health_metrics, health_sync, housekeeping, ingest, maxes, nutrition, progress_photos, readiness, reminders, seed_wods, workout_details, workouts, wods
from benessere import ui_theme as ui

st.set_page_config(
    page_title="Benessere | Dashboard",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="collapsed",
)
ui.apply_theme()

TYPE_LABELS = {
    "strength": "Forza", "metcon": "Metcon", "gymnastics": "Gymnastics",
    "skill": "Skill", "tennis": "Tennis", "other": "CrossFit / altro",
}
MEAL_LABELS = {"breakfast": "Colazione", "lunch": "Pranzo", "dinner": "Cena", "snack": "Spuntino"}
SCORES = {"time": "Tempo", "amrap": "AMRAP", "load": "Carico", "reps": "Ripetizioni"}
NAV = ("Panoramica", "Salute", "Allenamenti", "WOD", "Benchmark", "Massimali", "Foto progressi", "Alimentazione", "Impostazioni")

@st.cache_resource
def get_conn(database_file: str):
    # La cache è separata per percorso DB; evita dati stantii da altri ambienti.
    from pathlib import Path
    connection = store.connect(Path(database_file))
    housekeeping.migrate(connection, Path(database_file))
    return connection

conn = get_conn(str(store.db_path().resolve()))

def df_view(data, *, height=None):
    opts = {"height": height} if height is not None else {}
    st.dataframe(pd.DataFrame(data), width="stretch", hide_index=True, **opts)

def show_session_blocks(workout_id, score_min=None):
    """Cronologia della sessione, con minuti relativi alla sessione o al WOD."""
    blocks=workout_details.blocks_for(conn,workout_id)
    if not blocks:
        return
    rows=[]
    for block in blocks:
        reference=block["time_reference"]
        start=block["start_offset_min"]
        stop=block["end_offset_min"]
        when="Da definire"
        if start is not None:
            where="sessione" if reference=="workout" else "WOD" if reference=="wod" else "inizio sconosciuto"
            when=f"{where} +{start:g}′"
            if stop is not None:
                when+=f" → +{stop:g}′"
        reps=(f"{block['sets']}×{block['repetitions']}" if block["sets"] and block["repetitions"]
              else f"{block['repetitions']} rep" if block["repetitions"] else "—")
        rows.append({
            "Fase":block["label"],
            "Collocazione":when,
            "Esercizio":block["exercise"],
            "Serie × reps":reps,
            "Peso":f"{block['weight_kg']:g} kg" if block["weight_kg"] is not None else "—",
            "Durata dichiarata":f"{block['reported_duration_min']:g} min" if block["reported_duration_min"] is not None else "—",
            "Note":block["notes"]
        })
    df_view(rows,height=min(500,92+45*len(rows)))
    if score_min is None:
        found=conn.execute("SELECT wr.score_value,w.score_type FROM workouts s JOIN wod_results wr ON s.wod_result_id=wr.id JOIN wods w ON wr.wod_id=w.id WHERE s.id=?",(workout_id,)).fetchone()
        if found and found["score_type"]=="time":
            score_min=found["score_value"]/60
    for warning in workout_details.timeline_warnings(blocks,score_min):
        st.warning("Orari da verificare: "+warning)
    st.caption("Partenze relative al WOD: non sono ore assolute della sessione. I tempi dichiarati non vengono trasformati in orari di fine non verificati.")

def mini_totals(day_s):
    return nutrition.day_totals(conn, day_s)

def targets(day):
    return nutrition.compute_targets(conn, day)

def macro_tiles(eaten, target=None):
    cols = st.columns(4)
    metrics = [
        ("Energia", f"{eaten['kcal']:,.0f}", "kcal", "target_kcal"),
        ("Proteine", f"{eaten['protein_g']:,.0f}", "g", "protein_g"),
        ("Carboidrati", f"{eaten['carbs_g']:,.0f}", "g", "carbs_g"),
        ("Grassi", f"{eaten['fat_g']:,.0f}", "g", "fat_g"),
    ]
    for col, (title, val, unit, key) in zip(cols, metrics):
        with col:
            st.metric(title, f"{val} {unit}")
            if target and target.get(key) is not None and target[key] > 0:
                # Non colorare i surplus come errori: sono solo dati.
                st.progress(min(eaten[key if key != "target_kcal" else "kcal"] / target[key], 1.0),
                            text=f"Target {target[key]:.0f} {unit}")

def quick_meal(day):
    with st.form("quick_meal", clear_on_submit=True):
        meal = st.selectbox("Tipo", list(MEAL_LABELS), format_func=lambda k: MEAL_LABELS[k])
        description = st.text_input("Cosa hai mangiato?", placeholder="Alimenti, porzioni e condimenti")
        kcal = st.number_input("Calorie (stima, kcal)", min_value=0.0, max_value=10000.0, value=None)
        cols = st.columns(3)
        p = cols[0].number_input("Proteine (g)", min_value=0.0, max_value=800.0, value=None)
        c = cols[1].number_input("Carbo (g)", min_value=0.0, max_value=1500.0, value=None)
        f = cols[2].number_input("Grassi (g)", min_value=0.0, max_value=800.0, value=None)
        if st.form_submit_button("Registra pasto", type="primary", use_container_width=True):
            if not description.strip():
                st.error("Inserisci una descrizione del pasto.")
            elif None in (kcal,p,c,f):
                st.error("Inserisci calorie e macronutrienti, anche se stimati.")
            else:
                nutrition.log_meal(conn, meal, kcal,p,c,f,description.strip(),
                                   ts=f"{day}T{datetime.now():%H:%M:%S}")
                st.success("Pasto registrato.")
                st.rerun()

def quick_workout(day):
    with st.form("quick_workout", clear_on_submit=True):
        typ = st.selectbox("Tipo di allenamento", list(TYPE_LABELS), format_func=lambda k: TYPE_LABELS[k])
        dur = st.number_input("Durata (min)", min_value=1, max_value=360, value=None)
        know_rpe = st.checkbox("Conosco la percezione dello sforzo (RPE)")
        rpe = st.slider("RPE dichiarato", 1.0, 10.0, 7.0, .5) if know_rpe else None
        notes = st.text_area("Esercizi e note", placeholder="Carichi, serie, ripetizioni, risultato...")
        if st.form_submit_button("Registra allenamento", type="primary", use_container_width=True):
            if dur is None:
                st.error("Inserisci la durata effettiva.")
            else:
                workouts.add_workout(conn, workouts.Workout(date=day,type=typ,duration_min=dur,rpe=rpe,notes=notes))
                st.success("Allenamento salvato.")
                st.rerun()

def overview():
    today = date.today()
    day = st.date_input("Giornata", value=today, key="overview_day")
    s = day.isoformat()
    ui.hero("Il tuo benessere, in un posto solo", f"{day:%d/%m/%Y} · Dati reali, nessuna demo", kicker="PANORAMICA")
    col1, col2, col3 = st.columns(3)
    count = conn.execute("SELECT COUNT(*) n FROM workouts WHERE date=?", (s,)).fetchone()["n"]
    meals = mini_totals(s)
    result_count = conn.execute("SELECT COUNT(*) n FROM wod_results WHERE date=?", (s,)).fetchone()["n"]
    col1.metric("Sessioni", count)
    col2.metric("Pasti registrati", meals["count"])
    col3.metric("Risultati WOD", result_count)
    sensor=health_metrics.snapshot(conn, day, 7)
    ui.section("Sensori e recupero")
    sleep=sensor["sleep_today"]
    heart=sensor["last_heart"]
    activity=sensor["today"]
    measures=st.columns(3)
    measures[0].metric("Sonno / sessione",
                       f"{sleep['duration_h']:.1f} h" if sleep and sleep["duration_h"] is not None else "—")
    measures[1].metric("Battito rilevato", f"{heart['bpm']} bpm" if heart else "—")
    measures[2].metric("Passi", f"{activity['steps']:,}" if activity and activity["steps"] is not None else "—")
    st.caption("Misure osservate, non valori predefiniti. Serie e sincronizzazione nella sezione Salute.")
    ui.section("Alimentazione della giornata")
    plan = targets(day)
    if plan is None:
        missing = ", ".join(nutrition.profile_missing(conn))
        st.info(f"Profilo da completare per il calcolo dei target: {missing}. I consumi registrati rimangono visibili.")
    macro_tiles(meals, plan.as_dict() if plan else None)
    c1, c2 = st.columns(2, gap="large")
    with c1:
        ui.section("Recupero")
        r = readiness.readiness(conn, day)
        if r and r["score"] is not None:
            st.metric("Readiness dai dati disponibili", f"{r['score']} / 100")
            for comp, score in r["components"].items():
                st.progress(score/100,text=f"{comp.upper()}: {score}")
        else:
            ui.empty("Nessuna readiness calcolabile: servono dati effettivi di sonno, HRV o attività.")
        if r:
            with st.expander("Qualità e copertura dati"):
                for flag in r.get("flags",[]):st.caption(flag)
    with c2:
        ui.section("Ultime attività")
        history = conn.execute("SELECT date,type,duration_min,notes FROM workouts WHERE date<=? ORDER BY date DESC,id DESC LIMIT 4",(s,)).fetchall()
        if not history:
            ui.empty("Ancora nessun allenamento registrato.")
        for w in history:
            ui.card(TYPE_LABELS.get(w["type"],w["type"]),
                    f"{w['duration_min']:g} min · {(w['notes'] or 'Nessuna nota')[:130]}",w["date"])
    ui.section("Aggiungi un dato")
    tab1,tab2=st.tabs(["Pasto","Allenamento"])
    with tab1: quick_meal(s)
    with tab2: quick_workout(s)

def health_page():
    ui.hero("Salute e recupero", "Sonno, frequenza cardiaca, HRV, passi e calorie dal monitoraggio reale.", kicker="HEALTH / MONITORAGGIO")
    a,b=st.columns([2,1])
    period=a.selectbox("Intervallo", [7,14,30,90], index=2, format_func=lambda n:f"Ultimi {n} giorni")
    reference=b.date_input("Fino al",date.today(),key="health_reference")
    data=health_metrics.snapshot(conn,reference,period)
    status=data["sync"]
    if status["last_sync"]:
        st.success(f"Health Connect collegato · ultimo invio {status['last_sync']} · Ultimi campioni FC importati: {status['last_new_hr']}")
    else:
        st.warning("Nessuna sincronizzazione Health Connect registrata sulla VPS. Collega il telefono per ottenere i dati.")
    ui.section("Valori osservati")
    hr=data["last_heart"]
    sleep=data["sleep_today"]
    daily=data["today"]
    hrv=data["hrv_today"]
    tiles=st.columns(4)
    tiles[0].metric("FC rilevata", f"{hr['bpm']} bpm" if hr else "—")
    tiles[1].metric("Sonno / sessione", f"{sleep['duration_h']:.1f} h" if sleep and sleep["duration_h"] is not None else "—")
    tiles[2].metric("Passi", f"{daily['steps']:,}" if daily and daily["steps"] is not None else "—")
    tiles[3].metric("HRV RMSSD", f"{hrv['rmssd_ms']:.1f} ms" if hrv and hrv["rmssd_ms"] is not None else "—")
    if hr:st.caption(f"Ultima misura FC nell'intervallo: {hr['at'][:16].replace('T',' ')} · Fonte: {hr['source']}")
    if sleep and sleep["accuracy"]!="fasi":st.caption("Sonno: durata della sessione a letto, non quantità di sonno effettiva.")
    ui.section("Copertura del monitoraggio")
    cc=data["counts"]
    cols=st.columns(4)
    for col,label,value in zip(cols,("Giorni attività","Notti sonno","Notti HRV","Campioni FC"),
                                (cc["days"],cc["sleep_nights"],cc["hrv_nights"],cc["heart_samples"])):
        col.metric(label,value)
    tabs=st.tabs(["Battiti","Sonno","Attività","HRV & altre misure"])
    with tabs[0]:
        ui.section("Frequenza cardiaca nel tempo")
        if data["hr_hourly"]:
            frame=pd.DataFrame(data["hr_hourly"])
            st.line_chart(frame.set_index("at")[["average_bpm","min_bpm","max_bpm"]],height=260)
            st.caption("Medie/minimi/massimi dei campioni registrati ogni ora. Non sono una misura continua garantita.")
        else:ui.empty("Nessun battito importato nell'intervallo. Controlla le autorizzazioni Health Connect.")
    with tabs[1]:
        ui.section("Durata rilevata per notte")
        valid=[r for r in data["sleeps"] if r["duration_h"] is not None]
        if valid:
            frame=pd.DataFrame(valid)
            st.bar_chart(frame.set_index("date")["duration_h"],height=270)
            st.dataframe(frame[["date","duration_h","accuracy","deep_min","light_min","rem_min","source"]].rename(
                columns={"date":"Notte","duration_h":"Ore","accuracy":"Tipo misura","deep_min":"Profondo (min)",
                         "light_min":"Leggero (min)","rem_min":"REM (min)","source":"Fonte"}),
                hide_index=True,use_container_width=True)
        else:ui.empty("Nessun dato sonno importato nell'intervallo.")
    with tabs[2]:
        ui.section("Movimento e consumo")
        if data["daily"]:
            frame=pd.DataFrame(data["daily"])
            kinds=["steps","active_kcal","total_kcal"]
            present=[x for x in kinds if frame[x].notna().any()]
            if present:
                chosen=st.selectbox("Indicatore",present,format_func=lambda x:{
                    "steps":"Passi","active_kcal":"Calorie attive","total_kcal":"Calorie totali"}[x])
                st.bar_chart(frame.set_index("date")[chosen],height=260)
            st.dataframe(frame.rename(columns={"date":"Data","steps":"Passi",
                         "active_kcal":"Kcal attive","total_kcal":"Kcal totali",
                         "resting_hr":"FC a riposo","weight_kg":"Peso (kg)","source":"Fonte"}),
                         use_container_width=True,hide_index=True)
        else:ui.empty("Nessuna attività registrata nell'intervallo.")
    with tabs[3]:
        ui.section("Variabilità cardiaca (HRV)")
        if data["hrv"]:
            frame=pd.DataFrame(data["hrv"])
            keys=[k for k in ("rmssd_ms","sdnn_ms") if frame[k].notna().any()]
            if keys:st.line_chart(frame.set_index("date")[keys],height=230)
            else:ui.empty("Le registrazioni HRV non contengono valori numerici validi.")
        else:ui.empty("HRV non ancora disponibile. Non viene stimata a partire dai battiti medi.")
        rr=data["last_spo2"]
        st.metric("Ultima saturazione registrata",f"{rr['pct']:.0f}%" if rr else "—")
        if rr:st.caption(f"Fonte: {rr['source']} · {rr['ts']}")
        if daily and daily["resting_hr"] is not None:
            st.metric("FC a riposo registrata",f"{daily['resting_hr']} bpm")
    ui.section("Osservazioni sui dati disponibili")
    for observation in health_metrics.observations(data):
        ui.card("Dato / copertura",observation)
    st.caption("Benessere è uno strumento di monitoraggio personale. Non sostituisce diagnosi, terapie o visite mediche.")
    with st.expander("Come arrivano i dati / diagnostica"):
        st.markdown("**Amazfit → Zepp → Health Connect → app Android Benessere → VPS → dashboard.**")
        st.markdown("Il dispositivo e Zepp devono condividere i dati con Health Connect. "
                    "L'app Android richiede permessi per FC, sonno, passi e calorie e deve sincronizzare verso l'endpoint Benessere.")
        st.markdown("Se la sincronizzazione non appare, apri l'app Android, verifica Health Connect e premi **Sincronizza ora**.")
        st.json({"ultimo_invio":status["last_sync"],"nuovi_campioni_ultimo_invio":status["last_new_hr"],
                 "sessioni_memorizzate":status["stored_sessions"],"copertura":cc})
 
def training_page():
    ui.hero("Allenamenti", "Sessioni, carichi dichiarati e storico senza dati inventati.", kicker="TRAINING LOG")
    with st.expander("Registra una nuova sessione", expanded=False):
        with st.form("training_form", clear_on_submit=True):
            cols=st.columns(3)
            dt=cols[0].date_input("Data",date.today(),key="training_date")
            typ=cols[1].selectbox("Disciplina",list(TYPE_LABELS),format_func=lambda k:TYPE_LABELS[k])
            duration=cols[2].number_input("Minuti effettivi",min_value=1,max_value=360,value=None)
            rpe_known=st.checkbox("RPE noto (opzionale)")
            rpe=st.slider("Intensità RPE",1.0,10.0,7.0,.5) if rpe_known else None
            cols2=st.columns(2)
            avg=cols2[0].number_input("FC media (opzionale)",min_value=30,max_value=230,value=None)
            maxhr=cols2[1].number_input("FC massima (opzionale)",min_value=30,max_value=240,value=None)
            start_known=st.checkbox("Orario iniziale conosciuto",value=False)
            clock=st.time_input("Ora di inizio",value=datetime.strptime("08:00","%H:%M").time()) if start_known else None
            note=st.text_area("Note",placeholder="WOD, ripetizioni, carichi reali...")
            if st.form_submit_button("Salva sessione",type="primary"):
                if duration is None:
                    st.error("Indica la durata.")
                else:
                    workouts.add_workout(conn,workouts.Workout(date=dt.isoformat(),type=typ,duration_min=duration,
                        rpe=rpe,avg_hr=avg,max_hr=maxhr,notes=note,start_time=clock.strftime("%H:%M") if clock else None))
                    st.success("Sessione salvata.")
                    st.rerun()
    ui.section("Andamento del carico")
    r=workouts.fitness_fatigue(conn,horizon=60)
    if any(x["load"] for x in r):
        frame=pd.DataFrame(r)
        st.line_chart(frame.set_index("date")[["ctl","atl","tsb"]],height=250)
        st.caption("Forma, fitness e fatica sono stime basate esclusivamente su carichi calcolabili.")
    else:
        ui.empty("Il grafico si attiverà con frequenza cardiaca o RPE reali.")
    ui.section("Storico sessioni")
    rows=workouts.workouts_between(conn,"1900-01-01","9999-12-31")
    if rows:
        with st.expander("Aggiungi un blocco a una sessione",expanded=False):
            with st.form("extra_training_block",clear_on_submit=True):
                recent=list(reversed(rows[-60:]))
                rid=st.selectbox("Sessione",list(range(len(recent))),
                    format_func=lambda i:f"{recent[i]['date']} · {recent[i]['start_time'] or 'ora sconosciuta'} · #{recent[i]['id']}")
                phase=st.selectbox("Tipologia",["strength","wod","skill","warmup","other"],
                    format_func=lambda k:{"strength":"Forza","wod":"WOD","skill":"Tecnica",
                                         "warmup":"Riscaldamento","other":"Altro"}[k])
                label=st.text_input("Nome blocco",placeholder="Es. EMOM 0'–10' oppure WOD A")
                exercise=st.text_input("Esercizio",placeholder="Es. Back Squat")
                part=st.columns(3)
                sets=part[0].number_input("Serie / round",min_value=1,max_value=1000,value=None)
                reps=part[1].number_input("Ripetizioni",min_value=1,max_value=10000,value=None)
                weight=part[2].number_input("Carico kg",min_value=0.5,max_value=1000.0,value=None,step=0.5)
                ref=st.selectbox("Offset riferito all'inizio di",["unspecified","workout","wod"],
                    format_func=lambda k:{"unspecified":"Non specificato","workout":"Sessione intera","wod":"WOD"}[k])
                tw=st.columns(3)
                start_offset=tw[0].number_input("Inizio relativo (min)",min_value=0.0,max_value=360.0,value=None)
                end_offset=tw[1].number_input("Fine relativa (min)",min_value=0.0,max_value=360.0,value=None)
                duration_block=tw[2].number_input("Durata dichiarata (min)",min_value=0.1,max_value=360.0,value=None)
                notes_block=st.text_input("Note sul blocco")
                if st.form_submit_button("Aggiungi blocco",type="primary"):
                    try:
                        workout_details.append_block(conn,recent[rid]["id"],{
                            "phase":phase,"label":label,"exercise":exercise,
                            "sets":sets,"repetitions":reps,"weight_kg":weight,
                            "time_reference":ref,"start_offset_min":start_offset,
                            "end_offset_min":end_offset,
                            "reported_duration_min":duration_block,"notes":notes_block})
                        st.success("Blocco registrato nella sessione esistente.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        df_view([{"Data":x["date"],"Inizio":x["start_time"] or "Non registrato",
                  "Tipo":TYPE_LABELS.get(x["type"],x["type"]),"Durata sessione (min)":x["duration_min"],
                  "RPE":x["rpe"],"Carico":x["load"],"Note":x["notes"],"Origine":x["source"]} for x in reversed(rows)],
                height=370)
        for workout in reversed(rows):
            blocks=workout_details.blocks_for(conn,workout["id"])
            if blocks:
                with st.expander(f"{workout['date']} · sessione {workout['start_time'] or 'ora non nota'} · {len(blocks)} blocchi",expanded=False):
                    show_session_blocks(workout["id"])
    else:ui.empty("Nessun allenamento registrato.")

def personal_wods_page():
    ui.hero("I tuoi WOD", "Allenamenti personalizzati, risultati e progressi reali.", kicker="WOD PERSONALI")
    if "wod_notice" in st.session_state:
        st.success(st.session_state.pop("wod_notice"))
    templates={b.name for b in seed_wods.BENCHMARKS}
    all_wods=wods.list_wods(conn)
    personal=[w for w in all_wods if w["name"] not in templates and w["category"] not in ("strength",)]
    if personal:
        for item in reversed(personal):
            hist=wods.results_for(conn,item["name"])
            with st.expander(f"{item['name']} · {SCORES.get(item['score_type'],item['score_type'])} · {len(hist)} risultati"):
                st.write(item["description"] or "Nessuna descrizione.")
                if hist:
                    df_view([{"Data":x["date"],"Punteggio":x["score_display"],"Versione":x["scaling"],
                              "Note":x["notes"]} for x in reversed(hist)])
                    for result in reversed(hist):
                        associated=conn.execute("SELECT id,start_time FROM workouts WHERE wod_result_id=?",(result["id"],)).fetchone()
                        if associated:
                            st.markdown(f"**Sessione del {result['date']} · inizio {associated['start_time'] or 'non noto'}**")
                            show_session_blocks(associated["id"],result["score_value"]/60 if item["score_type"]=="time" else None)
    else:ui.empty("Nessun WOD personale. Registra il primo qui sotto.")
    ui.section("Crea un WOD")
    with st.form("create_personal_wod",clear_on_submit=True):
        name=st.text_input("Nome WOD",placeholder="Es. WOD del box — 21 ottobre")
        kind=st.selectbox("Modalità risultato",list(SCORES),format_func=lambda x:SCORES[x])
        desc=st.text_area("Movimenti e schema")
        if st.form_submit_button("Crea WOD",type="primary"):
            if not name.strip():st.error("Il nome è obbligatorio.")
            else:
                try:
                    wods.add_wod(conn,wods.Wod(name=name.strip(),score_type=kind,
                        category="custom",description=desc,custom=1))
                    st.session_state["wod_notice"]="WOD creato."
                    st.rerun()
                except ValueError as e:st.error(str(e))
    if personal:
        ui.section("Registra un risultato")
        with st.form("result_personal",clear_on_submit=True):
            name=st.selectbox("WOD", [x["name"] for x in personal])
            sdt=st.date_input("Data",date.today(),key="personal_wod_date")
            score=st.text_input("Risultato",placeholder="17:00 o 12+35 o 100")
            scale=st.selectbox("Versione",["unspecified","rx","scaled","rx+"],
                 format_func=lambda x:{"unspecified":"Non specificata","rx":"RX","scaled":"Scaled","rx+":"RX+"}[x])
            notes=st.text_input("Note")
            if st.form_submit_button("Salva risultato",type="primary"):
                try:
                    wods.add_result(conn,name,sdt.isoformat(),score,scaling=scale,notes=notes)
                    st.session_state["wod_notice"]="Risultato salvato."
                    st.rerun()
                except ValueError as e:st.error(str(e))

def benchmark_page():
    ui.hero("Benchmark CrossFit", "Girls, Hero e test standard. Catalogo di riferimento separato dai risultati personali.",kicker="BENCHMARK")
    benchmarks=[b for b in seed_wods.BENCHMARKS if b.category!="strength"]
    groups=[("girl","The Girls"),("hero","Hero WOD"),("engine","Engine"),("skill","Skill"),("open","Open / altro")]
    recorded=0
    for b in benchmarks:recorded+=len(wods.results_for(conn,b.name))
    c1,c2=st.columns(2)
    c1.metric("Benchmark disponibili",len(benchmarks))
    c2.metric("Risultati registrati",recorded)
    for group,label in groups:
        bs=[b for b in benchmarks if b.category==group]
        if not bs:continue
        ui.section(label)
        for b in bs:
            hist=wods.results_for(conn,b.name)
            with st.expander(f"{b.name} · {SCORES.get(b.score_type,b.score_type)} · {len(hist)} risultati"):
                st.write(b.description)
                if hist:
                    df_view([{"Data":x["date"],"Risultato":x["score_display"],"Versione":x["scaling"],
                             "Note":x["notes"]} for x in reversed(hist)])
                else:
                    st.caption("Nessun risultato personale: la descrizione è solo un benchmark, non un allenamento svolto.")
    ui.section("Registra un benchmark svolto")
    with st.form("benchmark_result",clear_on_submit=True):
        idx=st.selectbox("Benchmark",range(len(benchmarks)),format_func=lambda i:benchmarks[i].name)
        dt=st.date_input("Data risultato",date.today(),key="benchmark_date")
        score=st.text_input("Risultato",placeholder="Es. 04:35 oppure 15+12")
        scaling=st.selectbox("Versione",["unspecified","rx","scaled","rx+"],
           format_func=lambda x:{"unspecified":"Non indicata","rx":"RX","scaled":"Scaled","rx+":"RX+"}[x])
        note=st.text_input("Note / carichi / modifiche")
        if st.form_submit_button("Registra benchmark",type="primary"):
            b=benchmarks[idx]
            try:
                wods.parse_score(b.score_type,score)
                wods.add_wod(conn,b)
                wods.add_result(conn,b.name,dt.isoformat(),score,scaling=scaling,notes=note)
                st.success("Risultato benchmark registrato.")
                st.rerun()
            except ValueError as e:st.error(str(e))

def maxes_page():
    ui.hero("Massimali", "Una scheda per ogni alzata. Storico cronologico e migliori 1RM effettivamente registrati.",
            kicker="STRENGTH / RECORD")
    best=maxes.best_by_lift(conn)
    allrows=maxes.history(conn)
    c1,c2,c3=st.columns(3)
    c1.metric("Esercizi con 1RM",len(best))
    c2.metric("Test registrati",len(allrows))
    c3.metric("Ultimo test",maxes.readable_date(allrows[0]["date"]) if allrows else "—")
    ui.section("Inserisci un massimale")
    with st.form("new_max",clear_on_submit=True):
        category=st.selectbox("Tipo di risultato",["lift","complex"],format_func=lambda x:{"lift":"Alzata singola / massimale","complex":"Complex multi-movimento"}[x])
        lift=st.selectbox("Esercizio",list(maxes.LIFTS)+["Altro (personalizzato)"]) if category=="lift" else "Altro (personalizzato)"
        custom=st.text_input("Nome esercizio / dettagli complex") if lift=="Altro (personalizzato)" else None
        exact_day=st.checkbox("Conosco il giorno esatto del test",value=True)
        a,b,c=st.columns(3)
        day=a.date_input("Data",date.today(),key="max_date") if exact_day else a.text_input("Mese (AAAA-MM)",value=f"{date.today():%Y-%m}")
        weight=b.number_input("Peso (kg)",min_value=0.5,max_value=1000.0,step=0.5,value=None)
        reps=c.number_input("Ripetizioni",min_value=1,max_value=100,value=1) if category=="lift" else 1
        note=st.text_input("Note (opzionali)",placeholder="Es. esecuzione, tecnica, sensazioni")
        if st.form_submit_button("Salva test",type="primary",use_container_width=True):
            name=custom.strip() if custom is not None else lift
            if weight is None:st.error("Inserisci il peso effettivo.")
            elif not name:st.error("Inserisci il nome dell'esercizio.")
            else:
                try:
                    maxes.add_max(conn,name,day.isoformat() if exact_day else day,weight,reps=int(reps),notes=note,category=category)
                    st.success("Massimale registrato.")
                    st.rerun()
                except ValueError as e:st.error(str(e))
    ui.section("I tuoi record 1RM")
    if best:
        df_view([{"Esercizio":x["lift"],"Record (kg)":x["weight_kg"],"Data":maxes.readable_date(x["date"])} for x in best])
    else:ui.empty("Ancora nessun massimale inserito. I benchmark di riferimento non sono considerati PR.")
    ui.section("Record complex")
    complexes=maxes.best_complexes(conn)
    if complexes:
        df_view([{"Complex":x["lift"],"Record (kg)":x["weight_kg"],"Data":maxes.readable_date(x["date"])} for x in complexes])
    else:ui.empty("Nessun complex ancora registrato.")
    ui.section("Storico cronologico")
    if allrows:
        names=sorted({x["lift"] for x in allrows})
        selection=st.selectbox("Filtra esercizio",["Tutti gli esercizi"]+names)
        filtered=allrows if selection=="Tutti gli esercizi" else maxes.history(conn,selection)
        df_view([{"Data":maxes.readable_date(x["date"]),"Categoria":"Complex" if x["category"]=="complex" else "Massimale",
                 "Esercizio":x["lift"],"Peso (kg)":x["weight_kg"],
                 "Ripetizioni":x["reps"] if x["category"]=="lift" else "—","Note":x["notes"]} for x in filtered],height=330)
        chartrows=[x for x in filtered if x["reps"]==1 and x["category"]=="lift" and len(x["date"])==10]
        if selection!="Tutti gli esercizi" and len(chartrows)>=2:
            df=pd.DataFrame([{"Data":x["date"],"kg":x["weight_kg"]} for x in reversed(chartrows)])
            st.line_chart(df.set_index("Data")["kg"],height=230)
    else:ui.empty("Qui compariranno tutti i tentativi ordinati dal più recente al più vecchio.")

def photos_page():
    ui.hero("Foto progressi", "Archivio privato per confrontare le foto nel tempo, affiancate per data e inquadratura.",kicker="PROGRESS / PHOTO LOG")
    st.caption("Foto conservate soltanto sul server Benessere protetto, senza pubblicazione esterna. Metadati EXIF/GPS rimossi.")
    allphotos=progress_photos.entries(conn)
    st.metric("Foto archiviate",len(allphotos))
    with st.expander("Carica foto",expanded=not bool(allphotos)):
        with st.form("new_progress_photo",clear_on_submit=True):
            taken=st.date_input("Data della foto",date.today(),key="photo_taken")
            labels={"front":"Fronte","side":"Profilo","back":"Schiena","other":"Altro"}
            angle=st.selectbox("Inquadratura",list(labels),format_func=lambda x:labels[x])
            upload=st.file_uploader("Foto JPG, PNG o WebP (max 10 MB)",type=["jpg","jpeg","png","webp"])
            note=st.text_input("Note (luce, posa, condizioni)",placeholder="Per confronti attendibili usa condizioni simili")
            confirmed=st.checkbox("Confermo di voler archiviare questa foto personale nell'app privata")
            if st.form_submit_button("Salva foto",type="primary",use_container_width=True):
                if upload is None or not confirmed:
                    st.error("Seleziona una foto e conferma il salvataggio.")
                else:
                    try:
                        photo_id=progress_photos.add_photo(conn,store.db_path(),taken.isoformat(),angle,upload.getvalue(),note)
                        st.success(f"Foto archiviata (ID {photo_id})")
                        st.rerun()
                    except (ValueError,OSError) as error:
                        st.error(str(error))
    ui.section("Galleria per data")
    if allphotos:
        labels={"front":"Fronte","side":"Profilo","back":"Schiena","other":"Altro"}
        with st.container():
            for p in allphotos:
                with st.expander(f"{p['taken_on']} · {labels.get(p['angle'],p['angle'])} · Foto #{p['id']}"):
                    st.image(progress_photos.photo_bytes(store.db_path(),p["filename"]),use_container_width=True)
                    if p["notes"]: st.caption(p["notes"])
        ui.section("Confronto prima / dopo")
        eligible=st.selectbox("Stessa inquadratura",list(progress_photos.ANGLES),
              format_func=lambda x:labels[x],key="compare_angle")
        options=[p for p in allphotos if p["angle"]==eligible]
        if len(options)>=2:
            options=list(reversed(options))
            def picture_label(i):
                p=options[i]
                return f"{p['taken_on']} · #{p['id']}"
            left,right=st.columns(2)
            earlier=left.selectbox("Prima",range(len(options)),format_func=picture_label,key="photo_before")
            later=right.selectbox("Dopo",range(len(options)),format_func=picture_label,index=len(options)-1,key="photo_after")
            if earlier == later:
                st.info("Seleziona due foto distinte.")
            else:
                left.image(progress_photos.photo_bytes(store.db_path(),options[earlier]["filename"]),
                           caption=picture_label(earlier),use_container_width=True)
                right.image(progress_photos.photo_bytes(store.db_path(),options[later]["filename"]),
                            caption=picture_label(later),use_container_width=True)
                st.caption("Il confronto visivo non è una misura affidabile della percentuale di massa grassa. "
                           "Per valutarne l'evoluzione mantieni luce, posa, distanza e orario coerenti.")
        else:ui.empty("Servono almeno due foto della stessa inquadratura per il confronto.")
        with st.expander("Elimina una foto",expanded=False):
            opt={f"#{x['id']} · {x['taken_on']} · {labels.get(x['angle'],x['angle'])}":x["id"] for x in allphotos}
            choice=st.selectbox("Foto da eliminare",list(opt))
            if st.checkbox("Confermo l'eliminazione permanente",key="confirm_photo_delete"):
                if st.button("Elimina definitivamente",type="secondary"):
                    progress_photos.remove_photo(conn,store.db_path(),opt[choice])
                    st.success("Foto eliminata.")
                    st.rerun()
    else:
        ui.empty("Nessuna foto ancora salvata. Carica la prima immagine per iniziare il confronto.")

def food_page():
    ui.hero("Alimentazione", "Pasti, calorie e macronutrienti: solo consumi registrati.",kicker="FOOD JOURNAL")
    day=st.date_input("Giornata",date.today(),key="food_date")
    s=day.isoformat()
    consumed=mini_totals(s)
    t=targets(day)
    if t is None:
        st.info("Target non disponibile: completa peso, altezza, età, sesso e obiettivo nelle Impostazioni.")
    macro_tiles(consumed,t.as_dict() if t else None)
    ui.section("Pasti registrati")
    food=nutrition.meals_for_day(conn,s)
    if food:
        for meal in food:
            stamp=meal["ts"][11:16]
            label=MEAL_LABELS.get(meal["meal"],meal["meal"])
            desc=meal["description"] or "Senza descrizione"
            ui.card(f"{stamp} · {label} · {meal['kcal']:g} kcal",
                    f"{desc} | P {meal['protein_g']:g} g · C {meal['carbs_g']:g} g · G {meal['fat_g']:g} g")
    else:ui.empty("Nessun pasto registrato per la giornata.")
    with st.expander("Registra un pasto",expanded=False):
        quick_meal(s)

def settings_page():
    ui.hero("Impostazioni", "Profilo personale, sincronizzazioni e controllo dei tuoi dati.",kicker="PREFERENZE")
    missing=nutrition.profile_missing(conn)
    if missing:
        st.info("Completa questi campi per attivare i target nutrizionali: "+", ".join(missing))
    with st.form("profile"):
        sex=store.profile_get(conn,"sex")
        goal=store.profile_get(conn,"goal")
        a,b,c=st.columns(3)
        sex_opts=["m","f"]
        sex_select=a.selectbox("Sesso",sex_opts,index=sex_opts.index(sex) if sex in sex_opts else None,
                               placeholder="Seleziona",format_func=lambda x:{"m":"Maschile","f":"Femminile"}[x])
        age=b.number_input("Età",min_value=14,max_value=100,
                           value=int(store.profile_get_float(conn,"age")) if store.profile_get_float(conn,"age") is not None else None)
        h=c.number_input("Altezza (cm)",min_value=90,max_value=240,
                         value=float(store.profile_get_float(conn,"height_cm")) if store.profile_get_float(conn,"height_cm") is not None else None)
        a,b,c=st.columns(3)
        weight=a.number_input("Peso corporeo (kg)",min_value=20.,max_value=350.,step=.1,
                              value=float(store.profile_get_float(conn,"weight_kg")) if store.profile_get_float(conn,"weight_kg") is not None else None)
        goals=["cut","maintain","bulk"]
        g=b.selectbox("Obiettivo",goals,index=goals.index(goal) if goal in goals else None,placeholder="Seleziona",
                      format_func=lambda x:{"cut":"Definizione","maintain":"Mantenimento","bulk":"Massa"}[x])
        rhr=c.number_input("FC a riposo (facoltativa)",min_value=30,max_value=120,
                           value=int(store.profile_get_float(conn,"resting_hr")) if store.profile_get_float(conn,"resting_hr") is not None else None)
        body_fat=st.number_input("Massa grassa stimata (% — non misurazione clinica)",min_value=1.,max_value=65.,step=.1,
                 value=float(store.profile_get_float(conn,"body_fat_pct_estimate")) if store.profile_get_float(conn,"body_fat_pct_estimate") is not None else None)
        sleep=st.number_input("Fabbisogno sonno (ore, facoltativo)",min_value=4.,max_value=12.,step=.25,
                              value=float(store.profile_get_float(conn,"sleep_need_h")) if store.profile_get_float(conn,"sleep_need_h") is not None else None)
        if st.form_submit_button("Salva profilo",type="primary"):
            values={"sex":sex_select,"age":age,"height_cm":h,"weight_kg":weight,"goal":g,
                    "resting_hr":rhr,"sleep_need_h":sleep,"body_fat_pct_estimate":body_fat}
            for key,value in values.items():
                if value is not None:
                    store.profile_set(conn,key,value)
            st.success("Profilo aggiornato.")
            st.rerun()
    ui.section("Origine dei dati")
    for title,table in (("Allenamenti","workouts"),("Pasti","meals"),("Risultati WOD","wod_results"),
                        ("Massimali","strength_maxes"),("Sonno","sleeps"),("HRV","hrv_daily")):
        count=conn.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]
        st.caption(f"{title}: {count} record")
    hc=health_sync.status(conn)
    if hc.get("last_sync"):
        st.success("Health Connect · Ultima sincronizzazione: "+str(hc["last_sync"]))
    else:
        st.info("Health Connect: nessun invio ancora registrato.")
    with st.expander("Sincronizzazione Zepp (avanzato)"):
        st.write("Usa soltanto token già autorizzati.")
        if st.button("Sincronizza gli ultimi 7 giorni"):
            try:st.json(ingest.sync(conn,7))
            except RuntimeError as e:st.error(str(e))
    ui.section("Esporta i tuoi dati")
    if st.button("Prepara l'esportazione JSON"):
        names=("profile","workouts","wods","wod_results","meals","strength_maxes",
               "days","sleeps","hrv_daily","temp_daily")
        dump={table:[dict(x) for x in conn.execute(f"SELECT * FROM {table}")] for table in names}
        st.download_button("Scarica backup JSON",json.dumps(dump,ensure_ascii=False,indent=2),
                           file_name="benessere_export.json",mime="application/json")

# Navigation sempre visibile anche da telefono, senza sidebar obbligatoria.
st.markdown('<div class="ben-kicker">BENESSERE · PERSONAL HEALTH HUB</div>',unsafe_allow_html=True)
page=st.radio("Vai alla sezione",NAV,horizontal=True,label_visibility="collapsed",key="nav")
if page=="Panoramica":overview()
elif page=="Salute":health_page()
elif page=="Allenamenti":training_page()
elif page=="WOD":personal_wods_page()
elif page=="Benchmark":benchmark_page()
elif page=="Massimali":maxes_page()
elif page=="Foto progressi":photos_page()
elif page=="Alimentazione":food_page()
else:settings_page()
