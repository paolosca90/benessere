"use client";
import {useCallback,useEffect,useState} from "react";
import {Activity,CalendarDays,HeartPulse,RefreshCcw} from "lucide-react";
import {ResponsiveContainer,LineChart,Line,CartesianGrid,XAxis,YAxis,Tooltip} from "recharts";

type Hr = {
 status:"sufficient"|"partial"|"unavailable"|"time_missing";
 average_bpm:number|null;max_bpm:number|null;min_bpm:number|null;
 sample_count:number;sampled_minutes:number;minute_bin_coverage_pct:number|null;
 sources:string[];reason:string|null;
 series:{offset_min:number;bpm:number|null;samples:number}[];
};
type Session = {
 id:number;type:string;duration_min:number;start_time:string|null;
 rpe:number|null;session_rpe_au:number|null;hr:Hr;
};
type Reference = {days:number;median:number|null};
type Report = {
 date:string;workouts:Session[];
 training:{session_rpe_au:number|null;workout_minutes:number;rpe_sessions:number;sessions:number};
 day:{
  steps:number|null;active_kcal:number|null;total_kcal:number|null;
  resting_hr_bpm:number|null;resting_hr_source:string|null;
  hrv_rmssd_ms:number|null;hrv_source:string|null;
  sleep_minutes:number|null;sleep_basis:string|null;sleep_source:string|null;
  historical_hr_samples:number;historical_hr_sources:Record<string,number>;
 };
 baselines:{hrv:Reference;resting_hr:Reference};
 sync:{last_sync:string|null};
 observations:string[];limitations:string[];
};
function todayLocal(){
 const now=new Date();const adjusted=new Date(now.getTime()-now.getTimezoneOffset()*60000);
 return adjusted.toISOString().slice(0,10);
}
const num=(v:number|null|undefined,unit="")=>v==null?"Non disponibile":
 new Intl.NumberFormat("it-IT",{maximumFractionDigits:1}).format(v)+(unit?" "+unit:"");
function Stat({label,value,note}:{label:string;value:string;note?:string}){
 return <div className="activity"><b>{label}</b><div className="big" style={{fontSize:23}}>{value}</div>
 {note&&<div className="small">{note}</div>}</div>;
}
const statusLabel:Record<Hr["status"],string>={
 sufficient:"Copertura sufficiente",
 partial:"Copertura parziale",
 unavailable:"Battiti assenti",
 time_missing:"Orario da registrare"
};
export default function ExertionPanel(){
 const [day,setDay]=useState(todayLocal);
 const [report,setReport]=useState<Report|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState("");
 const load=useCallback(async()=>{
  setLoading(true);setError("");
  try{
   const response=await fetch("/api/physiological-load?day="+encodeURIComponent(day),{cache:"no-store"});
   const data=await response.json();
   if(!response.ok)throw new Error(data.detail||data.error||"Analisi non disponibile");
   setReport(data as Report);
  }catch(e){setReport(null);setError(e instanceof Error?e.message:"Errore lettura")}
  finally{setLoading(false)}
 },[day]);
 useEffect(()=>{void load()},[load]);
 const d=report?.day;
 return <div>
  <div className="hero"><div className="eyebrow">Dati misurati e carico dichiarato</div>
   <h2>Carico e recupero</h2>
   <p>Incrocia gli allenamenti con la frequenza cardiaca sincronizzata da Health Connect.
    L'intensità cardiovascolare, lo sforzo muscolare e la fatica percepita non sono equivalenti.</p>
  </div>
  <section className="card" style={{marginBottom:16}}>
   <div className="row" style={{flexWrap:"wrap",gap:12}}>
    <label className="field"><span><CalendarDays size={15}/> Data</span>
     <input type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
    <button className="btn secondary" type="button" onClick={()=>void load()} disabled={loading}>
     <RefreshCcw size={15}/> Aggiorna</button>
    {report&&<span className="small">Ultima sincronizzazione Health Connect: {report.sync.last_sync?
      new Date(report.sync.last_sync).toLocaleString("it-IT"):"non disponibile"}</span>}
   </div>
  </section>
  {loading&&<div className="notice">Lettura dei dati registrati…</div>}
  {error&&<div className="notice warn" role="alert">{error}</div>}
  {!loading&&report&&<>
   <section className="card" style={{marginBottom:16}}>
    <h3><Activity size={17}/> Allenamento e attività della giornata</h3>
    <div className="grid four">
     <Stat label="Sessioni" value={num(report.training.sessions)}/>
     <Stat label="Minuti allenamento" value={num(report.training.workout_minutes,"min")}/>
     <Stat label="Carico session-RPE" value={num(report.training.session_rpe_au,"UA")}
      note="Durata × RPE; soggettivo, non carico cardiaco"/>
     <Stat label="Passi" value={num(d?.steps)} note="Dati giornalieri sincronizzati"/>
     <Stat label="Calorie attive" value={num(d?.active_kcal,"kcal")} note="Stima proveniente dalla fonte"/>
     <Stat label="FC storica" value={num(d?.historical_hr_samples,"campioni")}
      note="La provenienza dallo strap non è ancora verificata"/>
    </div>
   </section>
   <section className="card" style={{marginBottom:16}}>
    <h3><HeartPulse size={17}/> Frequenza cardiaca negli allenamenti</h3>
    {report.workouts.length===0&&<div className="small">Nessun allenamento registrato per questa data.</div>}
    <div className="stack">
     {report.workouts.map(w=><div key={w.id} className="activity">
      <div className="row" style={{flexWrap:"wrap"}}>
       <b>{w.type} · #{w.id} · {w.start_time||"Orario assente"}</b>
       <span className="pill">{statusLabel[w.hr.status]}</span>
      </div>
      <div className="small">Durata {num(w.duration_min,"min")} · RPE {num(w.rpe)}
       · Carico soggettivo {num(w.session_rpe_au,"UA")}</div>
      <div className="grid two" style={{marginTop:10}}>
       <Stat label="FC media dei minuti campionati" value={num(w.hr.average_bpm,"bpm")}/>
       <Stat label="FC massima rilevata" value={num(w.hr.max_bpm,"bpm")}/>
      </div>
      <div className="small">{w.hr.sample_count} campioni · {w.hr.sampled_minutes} minuti campionati ·
       Copertura stimata {num(w.hr.minute_bin_coverage_pct,"%")}</div>
      {w.hr.reason&&<div className="small">{w.hr.reason}</div>}
      {!!w.hr.sources.length&&<div className="small">Fonte archivio: {w.hr.sources.join(", ")}</div>}
      {w.hr.series.length>=2&&<div className="chart" style={{height:190,marginTop:12}}
         role="img" aria-label="Frequenza cardiaca per minuto campionato, con intervalli eventualmente mancanti">
        <ResponsiveContainer width="100%" height="100%">
         <LineChart data={w.hr.series}>
          <CartesianGrid stroke="#264154" vertical={false}/>
          <XAxis dataKey="offset_min" stroke="#839bae" fontSize={11} type="number"
            domain={[0,Math.ceil(w.duration_min)]} tickFormatter={n=>n+"'"} />
          <YAxis stroke="#839bae" fontSize={11} domain={["dataMin - 10","dataMax + 10"]}/>
          <Tooltip contentStyle={{background:"#0e2030",border:"1px solid #356070",borderRadius:10}}
           labelFormatter={n=>"Minuto "+n}/>
          <Line dataKey="bpm" name="FC media campionata" type="linear" stroke="#5ae1cb"
            strokeWidth={2.5} isAnimationActive={false} connectNulls={false}/>
         </LineChart>
        </ResponsiveContainer>
       </div>}
     </div>)}
    </div>
   </section>
   <section className="card" style={{marginBottom:16}}>
    <h3>Sonno e segnali di recupero</h3>
    <div className="grid two">
     <Stat label="Sonno registrato" value={d?.sleep_minutes!=null?num(d.sleep_minutes/60,"ore"):"Non disponibile"}
      note={d?.sleep_basis==="sleep_stages"?"Minuti ricavati dalle fasi":"Durata sessione; sonno effettivo non verificato"}/>
     <Stat label="HRV notturna RMSSD" value={num(d?.hrv_rmssd_ms,"ms")}
      note={report.baselines.hrv.median==null?
        "Baseline non disponibile (servono 7 notti precedenti)":
        "Mediana personale precedenti 14 gg: "+num(report.baselines.hrv.median,"ms")}/>
     <Stat label="FC a riposo" value={num(d?.resting_hr_bpm,"bpm")}
      note={report.baselines.resting_hr.median==null?
        "Baseline non disponibile (servono 7 giorni precedenti)":
        "Mediana personale precedenti 14 gg: "+num(report.baselines.resting_hr.median,"bpm")}/>
    </div>
   </section>
   {!!report.observations.length&&<section className="card">
    <h3>Copertura e limiti</h3>
    <ul>{report.observations.map((message,i)=><li key={i}>{message}</li>)}</ul>
    <p className="small">Questa schermata non misura direttamente lo stress psicologico,
      non diagnostica affaticamento e non attribuisce automaticamente a Helio Strap
      i record provenienti da Health Connect.</p>
   </section>}
  </>}
 </div>;
}
