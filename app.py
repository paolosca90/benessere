"""Benessere — app locale del crossfitter.

Avvio:  streamlit run app.py
Aree:   Oggi · Allenamenti · WOD · Alimentazione · Impostazioni
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from benessere import db as store
from benessere import health_sync, ingest, nutrition, readiness, reminders, seed_wods, workouts, wods

st.set_page_config(page_title="Benessere — CrossFit", page_icon="🏋️", layout="wide")

TYPE_LABELS = {
    "strength": "Forza",
    "metcon": "Metcon",
    "gymnastics": "Gymnastics",
    "skill": "Skill",
    "tennis": "Tennis",
    "other": "Altro",
}


@st.cache_resource
def get_conn():
    conn = store.connect()
    seed_wods.seed_if_empty(conn)
    return conn


conn = get_conn()

page = st.sidebar.radio(
    "Naviga",
    ["🏠 Oggi", "🏋️ Allenamenti", "🔥 WOD", "🍽️ Alimentazione", "⚙️ Impostazioni"],
)

# --------------------------------------------------------------- OGGI
if page == "🏠 Oggi":
    st.title("Oggi")
    day_s = date.today().isoformat()

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Readiness")
        r = readiness.readiness(conn)
        if r and r["score"] is not None:
            st.metric("Score", f"{r['score']} / 100")
            for k, v in r["components"].items():
                st.progress(v / 100, text=f"{k}: {v:.0f}")
        else:
            st.info("Dati insufficienti (servono i dati Zepp: token in docs/04).")
        for f in (r["flags"] if r else []):
            st.caption(f"• {f}")

        st.subheader("Carico")
        ff = workouts.fitness_fatigue(conn, horizon=7)[-1]
        st.metric("Forma (TSB)", ff["tsb"], help="CTL − ATL: positivo = riposato")
        st.caption(f"Fitness {ff['ctl']} · Fatica {ff['atl']}")

    with col2:
        st.subheader("Target di oggi")
        t = nutrition.compute_targets(conn).as_dict()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Kcal", t["target_kcal"])
        m2.metric("Proteine", f"{t['protein_g']} g")
        m3.metric("Carboidrati", f"{t['carbs_g']} g")
        m4.metric("Grassi", f"{t['fat_g']} g")
        if t["training_day"]:
            st.caption(f"Giorno di allenamento: +{t['carb_bonus_g']:.0f} g carboidrati periodizzati")

        st.subheader("Pasti di oggi")
        eaten = nutrition.day_totals(conn, day_s)
        if eaten["count"]:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Kcal", eaten["kcal"], delta=f"{eaten['kcal'] - t['target_kcal']:.0f} vs target")
            c2.metric("Proteine", f"{eaten['protein_g']} g", delta=f"{eaten['protein_g'] - t['protein_g']:.0f}")
            c3.metric("Carbo", f"{eaten['carbs_g']} g", delta=f"{eaten['carbs_g'] - t['carbs_g']:.0f}")
            c4.metric("Grassi", f"{eaten['fat_g']} g", delta=f"{eaten['fat_g'] - t['fat_g']:.0f}")
        else:
            st.caption("Nessun pasto registrato ancora.")

        for rem in reminders.pending_meal_reminders(conn):
            st.warning(rem["message"])

    st.divider()
    st.subheader("Registrazione rapida")
    qc1, qc2 = st.columns(2)
    with qc1:
        with st.expander("➕ Pasto veloce"):
            with st.form("quick_meal", clear_on_submit=True):
                meal = st.selectbox("Pasto", ["breakfast", "lunch", "dinner", "snack"])
                desc = st.text_input("Descrizione")
                a, b, c, d = st.columns(4)
                kcal = a.number_input("kcal", 0, 5000, 500)
                p = b.number_input("Prot g", 0.0, 300.0, 30.0)
                cb = c.number_input("Carbo g", 0.0, 500.0, 50.0)
                f = d.number_input("Grassi g", 0.0, 200.0, 15.0)
                if st.form_submit_button("Registra pasto"):
                    nutrition.log_meal(conn, meal, kcal, p, cb, f, desc)
                    st.rerun()
    with qc2:
        with st.expander("➕ Allenamento veloce"):
            with st.form("quick_workout", clear_on_submit=True):
                wtype = st.selectbox("Tipo", list(TYPE_LABELS), format_func=lambda x: TYPE_LABELS[x])
                dur = st.number_input("Durata (min)", 5, 300, 60)
                rpe = st.slider("RPE", 1.0, 10.0, 7.0, 0.5)
                notes = st.text_input("Note (es. 'Front squat 5x5 100kg')")
                if st.form_submit_button("Registra allenamento"):
                    workouts.add_workout(
                        conn,
                        workouts.Workout(date=day_s, type=wtype, duration_min=dur, rpe=rpe, notes=notes),
                    )
                    st.rerun()

# ------------------------------------------------------- ALLENAMENTI
elif page == "🏋️ Allenamenti":
    st.title("Allenamenti")

    with st.expander("➕ Nuova sessione", expanded=False):
        with st.form("add_workout", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            wdate = c1.date_input("Data", date.today()).isoformat()
            wtype = c2.selectbox("Tipo", list(TYPE_LABELS), format_func=lambda x: TYPE_LABELS[x])
            dur = c3.number_input("Durata (min)", 5, 300, 60)
            c4, c5, c6 = st.columns(3)
            rpe = c4.slider("RPE", 1.0, 10.0, 7.0, 0.5)
            avg_hr = c5.number_input("FC media (opz.)", 0, 220, 0)
            max_hr = c6.number_input("FC max (opz.)", 0, 230, 0)
            notes = st.text_area("Note / contenuti (WOD fatto, carichi, serie…)")
            if st.form_submit_button("Registra"):
                wid = workouts.add_workout(
                    conn,
                    workouts.Workout(
                        date=wdate, type=wtype, duration_min=dur, rpe=rpe,
                        avg_hr=avg_hr or None, max_hr=max_hr or None, notes=notes,
                    ),
                )
                st.success(f"Sessione #{wid} registrata (carico {conn.execute('SELECT load FROM workouts WHERE id=?',(wid,)).fetchone()[0]})")

    st.subheader("Fitness · Fatica · Forma")
    ff = pd.DataFrame(workouts.fitness_fatigue(conn, horizon=60))
    if ff["load"].sum() > 0:
        st.line_chart(ff.set_index("date")[["ctl", "atl", "tsb"]], height=280)
    else:
        st.caption("Il grafico appare dopo le prime sessioni.")

    st.subheader("Volume per tipo (6 settimane)")
    vol = workouts.weekly_volume_by_type(conn)
    if vol:
        st.bar_chart(pd.DataFrame([{"Tipo": TYPE_LABELS.get(k, k), "Minuti": v} for k, v in vol.items()]).set_index("Tipo"))
    else:
        st.caption("Nessuna sessione registrata.")

    st.subheader("Storico")
    rows = workouts.workouts_between(conn, (date.today() - timedelta(days=90)).isoformat(), date.today().isoformat())
    if rows:
        df = pd.DataFrame(
            [
                {
                    "Data": r["date"],
                    "Tipo": TYPE_LABELS.get(r["type"], r["type"]),
                    "Minuti": r["duration_min"],
                    "RPE": r["rpe"],
                    "FC media": r["avg_hr"],
                    "Carico": r["load"],
                    "Note": (r["notes"] or "")[:60],
                    "Fonte": r["source"],
                }
                for r in rows
            ]
        )
        st.dataframe(df, use_container_width=True, height=320)
    else:
        st.info("Nessuna sessione: aggiungine una sopra o usa il sync Zepp nelle Impostazioni.")

# --------------------------------------------------------------- WOD
elif page == "🔥 WOD":
    st.title("WOD & Risultati")

    if "flash_wod" in st.session_state:
        st.success(st.session_state.pop("flash_wod"))

    tab1, tab2, tab3 = st.tabs(["📋 Catalogo", "🏆 Personali (PR)", "➕ Nuovo WOD / risultato"])

    with tab1:
        for cat_label in ("girl", "hero", "open", "engine", "strength", "custom"):
            cat_rows = [w for w in wods.list_wods(conn) if w["category"] == cat_label]
            if not cat_rows:
                continue
            st.subheader({"girl": "Le Girls", "hero": "Hero", "open": "Open", "engine": "Engine", "strength": "Massimali", "custom": "I miei WOD"}[cat_label])
            for w in cat_rows:
                with st.expander(f"{w['name']} — {w['score_type']}"):
                    st.caption(w["description"] or "—")
                    hist = wods.results_for(conn, w["name"])
                    if hist:
                        df = pd.DataFrame(
                            [
                                {"Data": r["date"], "Risultato": r["score_display"], "Scaling": r["scaling"], "PR": "✔" if r["is_pr"] else "", "Note": r["notes"] or ""}
                                for r in hist
                            ]
                        )
                        st.dataframe(df, use_container_width=True)
                        if st.button(f"Registra risultato per {w['name']}", key=f"res_{w['id']}"):
                            st.session_state["target_wod"] = w["name"]
                            st.rerun()
                    else:
                        st.caption("Nessun risultato ancora.")

    with tab2:
        pr_list = wods.prs(conn)
        if pr_list:
            st.dataframe(
                pd.DataFrame(pr_list)[["wod", "score", "scaling", "date", "score_type"]].rename(
                    columns={"wod": "WOD", "score": "Best", "scaling": "Scaling", "date": "Data", "score_type": "Tipo"}
                ),
                use_container_width=True,
            )
        else:
            st.info("Nessun PR: registra il primo risultato nella tab Catalogo o qui a fianco.")

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Nuovo WOD custom")
            with st.form("new_wod", clear_on_submit=True):
                name = st.text_input("Nome")
                stype = st.selectbox("Tipo punteggio", ["time", "amrap", "load", "reps"],
                                     format_func=lambda x: {"time": "Tempo (es. Fran)", "amrap": "Round+reps (es. Cindy)", "load": "Chilogrammi (1RM)", "reps": "Ripetizioni"}[x])
                desc = st.text_area("Descrizione")
                if st.form_submit_button("Crea WOD"):
                    if name.strip():
                        wods.add_wod(conn, wods.Wod(name=name.strip(), score_type=stype, description=desc, custom=1))
                        st.success(f"WOD '{name.strip()}' creato")
                    else:
                        st.error("Il nome è obbligatorio")
        with c2:
            st.subheader("Nuovo risultato")
            with st.form("new_result", clear_on_submit=True):
                names = [w["name"] for w in wods.list_wods(conn)]
                target = st.selectbox("WOD", names, index=names.index(st.session_state["target_wod"]) if st.session_state.get("target_wod") in names else 0)
                rdate = st.date_input("Data", date.today()).isoformat()
                score = st.text_input("Punteggio", help="time: 3:45 · amrap: 12+35 · load: 142.5 · reps: 87")
                scaling = st.selectbox("Scaling", ["rx", "scaled", "rx+", "altro"])
                notes = st.text_input("Note")
                if st.form_submit_button("Registra risultato"):
                    try:
                        res = wods.add_result(conn, target, rdate, score, scaling=scaling, notes=notes)
                        st.session_state["flash_wod"] = (
                            f"Registrato {target} → {res['score']}" + (" 🏆 NUOVO PR!" if res["is_pr"] else "")
                        )
                        if res["is_pr"]:
                            st.balloons()
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

# ------------------------------------------------------- ALIMENTAZIONE
elif page == "🍽️ Alimentazione":
    st.title("Alimentazione")
    day = st.date_input("Giornata", date.today()).isoformat()

    t = nutrition.compute_targets(conn, date.fromisoformat(day)).as_dict()
    eaten = nutrition.day_totals(conn, day)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kcal", f"{eaten['kcal']:.0f}", f"{eaten['kcal'] - t['target_kcal']:.0f} vs {t['target_kcal']}")
    c2.metric("Proteine", f"{eaten['protein_g']:.0f} g", f"{eaten['protein_g'] - t['protein_g']:.0f} vs {t['protein_g']}")
    c3.metric("Carboidrati", f"{eaten['carbs_g']:.0f} g", f"{eaten['carbs_g'] - t['carbs_g']:.0f} vs {t['carbs_g']}")
    c4.metric("Grassi", f"{eaten['fat_g']:.0f} g", f"{eaten['fat_g'] - t['fat_g']:.0f} vs {t['fat_g']}")

    st.subheader("Reminder pasti")
    if day == date.today().isoformat():
        rem = reminders.pending_meal_reminders(conn)
        if rem:
            for r in rem:
                st.warning(r["message"])
        else:
            st.success("Pasti di oggi tutti registrati ✔")
    st.caption("Le finestre (colazione entro 10:00, pranzo entro 14:00, cena entro 21:30) avvisano se un pasto non è registrato.")

    st.subheader("Pasti della giornata")
    meals = nutrition.meals_for_day(conn, day)
    if meals:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Ora": r["ts"][11:16], "Pasto": r["meal"], "Descrizione": r["description"],
                     "kcal": r["kcal"], "Prot": r["protein_g"], "Carbo": r["carbs_g"], "Grassi": r["fat_g"]}
                    for r in meals
                ]
            ),
            use_container_width=True,
        )
    else:
        st.caption("Nessun pasto registrato in questa giornata.")

    with st.expander("➕ Registra pasto", expanded=True):
        with st.form("meal_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            meal = c1.selectbox("Pasto", ["breakfast", "lunch", "dinner", "snack"])
            desc = c2.text_input("Descrizione")
            a, b, c, d = st.columns(4)
            kcal = a.number_input("kcal", 0.0, 5000.0, 500.0)
            p = b.number_input("Proteine g", 0.0, 300.0, 30.0)
            cb = c.number_input("Carboidrati g", 0.0, 500.0, 50.0)
            f = d.number_input("Grassi g", 0.0, 200.0, 15.0)
            if st.form_submit_button("Registra", type="primary"):
                nutrition.log_meal(conn, meal, kcal, p, cb, f, desc, ts=f"{day}T{datetime.now().strftime('%H:%M:%S')}")
                st.rerun()

# ------------------------------------------------------- IMPOSTAZIONI
elif page == "⚙️ Impostazioni":
    st.title("Impostazioni")

    st.subheader("Stato attivazione")
    st.success("Dashboard locale attiva")
    st.caption("Avvio rapido Windows: AVVIA_BENESSERE.cmd · Guida: docs/09-attivazione.md")
    sensor_counts = {
        "Notti di sonno": conn.execute("SELECT COUNT(*) FROM sleeps").fetchone()[0],
        "Giorni HRV": conn.execute("SELECT COUNT(*) FROM hrv_daily").fetchone()[0],
        "Campioni FC": conn.execute("SELECT COUNT(*) FROM hr_samples").fetchone()[0],
    }
    st.write(" · ".join(f"{name}: {count}" for name, count in sensor_counts.items()))
    if not any(sensor_counts.values()):
        st.warning("Dati dello strap non ancora importati nel database PC. Attiva Zepp sotto o usa il log manuale.")
    st.subheader("Stato sincronizzazione Android")
    hc_status = health_sync.status(conn)
    if hc_status["last_sync"]:
        st.success(f"Ultimo invio dal telefono: {hc_status['last_sync']}")
        st.caption(f"Nuove FC ultimo invio: {hc_status['last_new_hr']} · Sessioni Health Connect conservate: {hc_status['stored_sessions']}")
    else:
        st.info("Nessun invio Health Connect ricevuto dal telefono. Installa Benessere 0.2 e avvia il server di sync.")
    st.code("python sync_server.py --lan", language="bash")
    st.caption("Il server di sincronizzazione usa la porta 8766 e un token separato. HTTP è adatto solo a una Wi-Fi privata fidata; per la VPS usa HTTPS. Guida: docs/10-sync-android.md")

    st.subheader("Profilo")
    with st.form("profile_form"):
        c1, c2, c3, c4 = st.columns(4)
        sex = c1.selectbox("Sesso", ["m", "f"], index=0 if (store.profile_get(conn, "sex", "m") == "m") else 1)
        age = c2.number_input("Età", 14, 90, int(store.profile_get_float(conn, "age", 35) or 35))
        height = c3.number_input("Altezza cm", 130, 220, int(store.profile_get_float(conn, "height_cm", 175) or 175))
        weight = c4.number_input("Peso kg", 35.0, 200.0, store.profile_get_float(conn, "weight_kg", 75.0) or 75.0)
        c5, c6, c7 = st.columns(3)
        goal = c5.selectbox("Obiettivo", ["cut", "maintain", "bulk"],
                            index=["cut", "maintain", "bulk"].index(store.profile_get(conn, "goal", "maintain")))
        rhr = c6.number_input("FC riposo", 35, 100, int(store.profile_get_float(conn, "resting_hr", 55) or 55))
        sleep_need = c7.number_input("Sonno bisogno (h)", 5.0, 12.0, store.profile_get_float(conn, "sleep_need_h", 7.5) or 7.5, 0.25)
        if st.form_submit_button("Salva profilo"):
            for k, v in {
                "sex": sex, "age": age, "height_cm": height, "weight_kg": weight,
                "goal": goal, "resting_hr": rhr, "sleep_need_h": sleep_need,
            }.items():
                store.profile_set(conn, k, v)
            st.success("Profilo salvato")

    st.subheader("Sincronizzazione Helio Strap (cloud Zepp)")
    st.caption("Stato token: " + ("✅ presente" if ingest.token_present() else "❌ assente — segui docs/04-report-dati.md (cattura HAR + init)"))
    if st.button("Sincronizza ora (ultimi 7 giorni)"):
        with st.spinner("Sync in corso…"):
            try:
                res = ingest.sync(conn, 7)
                st.json(res)
            except RuntimeError as exc:
                st.error(str(exc))

    st.subheader("Collega a ChatGPT / Claude (MCP)")
    st.code("python mcp_server.py --http 8000", language="bash")
    st.info("Il server su localhost è utilizzabile dai client MCP locali. ChatGPT richiede un tunnel sicuro o un endpoint HTTPS remoto autenticato: non può collegarsi direttamente a localhost.")
    st.markdown("Guida: `docs/07-mcp-chatgpt.md` · Attivazione: `docs/09-attivazione.md`")

    st.subheader("Dati")
    dbp = store.db_path()
    st.caption(f"Database: `{dbp}` ({dbp.stat().st_size / 1024:.0f} KB)")
    if st.button("Esporta JSON completo"):
        dump = {}
        for table in ("profile", "workouts", "wods", "wod_results", "meals", "days", "sleeps", "hrv_daily", "temp_daily"):
            dump[table] = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
        st.download_button("Scarica benessere_export.json", json.dumps(dump, ensure_ascii=False, indent=2, default=str), "benessere_export.json", "application/json")
