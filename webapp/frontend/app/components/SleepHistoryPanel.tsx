"use client";
import {useCallback,useEffect,useState} from "react";
import {Moon,RefreshCcw} from "lucide-react";

type StageName="awake"|"light"|"deep"|"rem"|"sleeping"|"unknown"|"out_of_bed";
type Item={stage:StageName,start:string,end:string};
type Session={
 start:string;end:string;origin:string;duration_min:number|null;
 source:string;stage_minutes:Record<"deep"|"light"|"rem"|"awake",number|null>;
};
type History={
 date:string;status:"missing"|"summary_only"|"timed_history";
 night_session:Session|null;stages:Item[];
 history_only:boolean;live_stage_available:boolean;strap_alarm_verified:boolean;
 message:string;
};
const terms:Record<StageName,string>={
 awake:"Veglia",light:"Sonno leggero",deep:"Sonno profondo",
 rem:"REM",sleeping:"Sonno, fase non identificata",unknown:"Fase sconosciuta",
 out_of_bed:"Fuori dal letto"
};
const localTime=(ts:string)=>new Date(ts).toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit"});
const duration=(a:string,b:string)=>Math.round((new Date(b).getTime()-new Date(a).getTime())/60000);
function today(){
 const d=new Date();const local=new Date(d.getTime()-d.getTimezoneOffset()*60000);
 return local.toISOString().slice(0,10);
}

export default function SleepHistoryPanel(){
 const [day,setDay]=useState(today);
 const [data,setData]=useState<History|null>(null);
 const [error,setError]=useState("");
 const [loading,setLoading]=useState(true);
 const reload=useCallback(async()=>{
  setLoading(true);setError("");
  try{
   const response=await fetch("/api/sleep-stage-history?day="+encodeURIComponent(day),{cache:"no-store"});
   const result=await response.json();
   if(!response.ok)throw Error(result.detail||result.error||"Non disponibile");
   setData(result);
  }catch(e){setError(e instanceof Error?e.message:"Errore di lettura");setData(null)}
  finally{setLoading(false)}
 },[day]);
 useEffect(()=>{void reload()},[reload]);
 return <section className="card" style={{marginTop:16}}>
  <div className="row"><h3><Moon size={17}/> Fasi del sonno — verifica dati</h3></div>
  <p className="small">Fasi ricavate soltanto da sessioni di sonno completate e
   sincronizzate. Non sono dati in tempo reale e non attivano lo strap.</p>
  <div className="row" style={{flexWrap:"wrap",gap:10}}>
   <label className="field"><span>Notte (data del risveglio)</span>
    <input type="date" value={day} onChange={e=>setDay(e.target.value)}/>
   </label>
   <button className="btn secondary" type="button" onClick={()=>void reload()} disabled={loading}>
    <RefreshCcw size={14}/> Aggiorna</button>
  </div>
  {loading&&<div className="small">Lettura dello storico…</div>}
  {error&&<div className="notice warn" role="alert">{error}</div>}
  {data&&!loading&&<>
   <div className="notice">{data.message}</div>
   {data.night_session&&<div className="small">
    Sessione {localTime(data.night_session.start)}–{localTime(data.night_session.end)}
    {" · "}Fonte {data.night_session.source} ({data.night_session.origin})
    {" · "}Durata sessione {data.night_session.duration_min??"non disponibile"} minuti
   </div>}
   {data.status==="summary_only"&&data.night_session&&
    <div className="grid four">
     {(Object.keys(data.night_session.stage_minutes) as (keyof Session["stage_minutes"])[]).map(key=>
      <div key={key} className="activity">
       <b>{terms[key]}</b>
       <div>{data.night_session!.stage_minutes[key]??"—"} min</div>
      </div>
     )}
    </div>}
   {data.stages.length>0&&<div className="stack" style={{marginTop:12}}>
    {data.stages.map((stage,index)=><div className="activity" key={index}>
     <div className="row" style={{flexWrap:"wrap"}}>
      <b>{localTime(stage.start)}–{localTime(stage.end)}</b>
      <span className="pill">{terms[stage.stage]}</span>
      <span className="small">{duration(stage.start,stage.end)} min</span>
     </div>
    </div>)}
   </div>}
   <div className="small" style={{marginTop:12}}>
    Stato sveglia adattiva: <b>non attiva</b>. Fase live: non verificata.
    Vibrazione comandata da Benessere: non verificata.
    La sveglia Zepp deve rimanere programmata autonomamente.
   </div>
  </>}
 </section>;
}
