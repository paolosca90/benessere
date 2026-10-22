"use client";
import {useCallback,useEffect,useState} from "react";
import {Activity,AlarmClock,Apple,ArrowUpRight,Bell,Dumbbell,HeartPulse,Home,LoaderCircle,Moon,RefreshCcw,Scale,ShieldCheck,TrendingUp,Utensils,Watch,WifiOff} from "lucide-react";
import {ResponsiveContainer,LineChart,Line,CartesianGrid,XAxis,YAxis,Tooltip,BarChart,Bar} from "recharts";
import JournalPanel from "./components/JournalPanel";
import LiveHeartPanel, {type LiveHeartSnapshot} from "./components/LiveHeartPanel";

type Section="oggi"|"salute"|"allenamento"|"alimentazione"|"progressi"|"diario"|"sveglia";
type Numeric=null|number;
type Day={date:string,steps:Numeric,weight_kg:Numeric,active_kcal:Numeric,total_kcal:Numeric,resting_hr:Numeric,source?:string};
type Sleep={date:string,duration_h:Numeric,accuracy?:string,deep_min:Numeric,light_min:Numeric,rem_min:Numeric,source?:string};
type Heart={bpm:number,at:string,source:string};
type Health={sleep:Sleep|null,heart:Heart|null,steps:Numeric,hrv:{rmssd_ms:Numeric}|null,sync:{last_sync:string|null}};
type Workout={id:number,type:string,duration_min:number,start_time:string|null,rpe:Numeric};
type Nutrition={consumed:{kcal:number,protein_g:number,carbs_g:number,fat_g:number,count:number},target:{target_kcal:number,protein_g:number,carbs_g:number,fat_g:number,label:string}|null};
type Summary={date:string,health:Health,nutrition:Nutrition,workouts:Workout[],alarm:{delivery:string}};
type Trends={daily:Day[],sleeps:Sleep[],hr_hourly:{at:string,average_bpm:number,min_bpm:number,max_bpm:number}[],hrv:{date:string,rmssd_ms:Numeric}[],last_heart:Heart|null,counts:{days:number,sleep_nights:number,heart_samples:number,hrv_nights:number},sync:{last_sync:string|null}};
type Strength={maxes:Record<string,unknown>[]};
type Alarm={revision:number,enabled:boolean,deadline:string,window_minutes:number,weekdays:number[],mode:string,delivery:string,updated_at:string|null,device_ack:{revision:number,installed:number,error:string,received_at:string}|null,strap_control:string};
const labels:Record<Section,string>={oggi:"Oggi",salute:"Salute",allenamento:"Allenamento",alimentazione:"Nutrizione",progressi:"Progressi",diario:"Diario",sveglia:"Sveglia"};
const mainSections:Section[]=["oggi","salute","allenamento","alimentazione","progressi"];
const navIcons=[Home,HeartPulse,Dumbbell,Utensils,TrendingUp];
const number=(n:Numeric,precision=0)=> n==null?"—":new Intl.NumberFormat("it-IT",{maximumFractionDigits:precision}).format(n);
const fmt=(s:string|null|undefined)=>s?new Date(s).toLocaleString("it-IT",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}):"Non disponibile";
const pct=(a:number,b:number)=>Math.max(0,Math.min(100,b>0?a/b*100:0));
const humanType=(x:string)=>({metcon:"CrossFit · metcon",strength:"Forza",tennis:"Tennis",other:"CrossFit / altro",gymnastics:"Gymnastics",skill:"Tecnica"} as Record<string,string>)[x]||x;
async function api<T>(url:string,method:"GET"|"PUT"="GET",body?:unknown):Promise<T>{
 const r=await fetch(url,{method,headers:{"Content-Type":"application/json"},
  ...(body?{body:JSON.stringify(body)}:{}),cache:"no-store"});
 const text=await r.text();let json:unknown;
 try{json=JSON.parse(text);}catch{throw new Error("Risposta del server non valida");}
 if(!r.ok)throw new Error((json as {detail?:string,error?:string}).detail||(json as {error?:string}).error||"HTTP "+r.status);
 return json as T;
}
function Card({children,className=""}:{children:React.ReactNode,className?:string}) {
 return <section className={"card "+className}>{children}</section>;
}
function Empty({message}:{message:string}){return <div className="empty">{message}</div>}
function SectionHeader({title,note}:{title:string,note?:string}){return <div className="section-heading"><h2>{title}</h2>{note&&<span className="small">{note}</span>}</div>}
function Value({label,value,unit,icon:Icon,note}:{label:string,value:string,unit?:string,icon:typeof Activity,note?:string}){
 return <Card><div className="cardlabel"><Icon size={15}/>{label}</div><div className="big">{value}{unit&&value!=="—"&&<span style={{fontSize:15,color:"#9ab4c2",fontWeight:500}}> {unit}</span>}</div>{note&&<div className="small">{note}</div>}</Card>;
}
function Progress({label,actual,target,unit}:{label:string,actual:number,target:number,unit:string}){
 return <div><div className="row"><span>{label}</span><span className="small">{number(actual)} / {number(target)} {unit}</span></div>
 <div className="progress"><div style={{width:pct(actual,target)+"%"}}/></div></div>;
}
function TrendsChart({data,kind}:{data:Trends,kind:"heart"|"sleep"|"steps"|"weight"}){
 const points = kind==="heart"?data.hr_hourly.map(x=>({x:x.at.slice(-5),v:x.average_bpm})) :
 kind==="sleep"?data.sleeps.filter(s=>s.duration_h!=null).map(s=>({x:s.date.slice(5),v:s.duration_h})) :
 data.daily.filter(x=>kind==="steps"?x.steps!=null:x.weight_kg!=null).map(x=>({x:x.date.slice(5),v:kind==="steps"?x.steps:x.weight_kg}));
 if(!points.length)return <Empty message="Nessuna misura disponibile nell'intervallo selezionato."/>;
 return <div className="chart" role="img" aria-label={"Andamento misurato di "+kind}>
 <ResponsiveContainer width="100%" height="100%">
 {kind==="sleep"||kind==="steps"?
 <BarChart data={points} margin={{top:9,right:8,left:-16,bottom:0}}>
  <CartesianGrid stroke="#264154" vertical={false}/><XAxis dataKey="x" stroke="#839bae" fontSize={11}/><YAxis stroke="#839bae" fontSize={11}/>
  <Tooltip contentStyle={{background:"#0e2030",border:"1px solid #356070",borderRadius:12}}/><Bar dataKey="v" name={kind==="sleep"?"Ore":"Passi"} fill="#5ae1cb" radius={[6,6,0,0]}/>
 </BarChart>:
 <LineChart data={points} margin={{top:9,right:8,left:-16,bottom:0}}>
  <CartesianGrid stroke="#264154" vertical={false}/><XAxis dataKey="x" stroke="#839bae" fontSize={11}/><YAxis stroke="#839bae" fontSize={11}/>
  <Tooltip contentStyle={{background:"#0e2030",border:"1px solid #356070",borderRadius:12}}/>
  <Line type="monotone" dataKey="v" name={kind==="heart"?"bpm":"kg"} stroke="#5ae1cb" strokeWidth={2.5} connectNulls={false} dot={false}/>
 </LineChart>}
 </ResponsiveContainer></div>;
}
export default function Page(){
 const [section,setSection]=useState<Section>("oggi");
 const [summary,setSummary]=useState<Summary|null>(null);
 const [liveHeart,setLiveHeart]=useState<LiveHeartSnapshot|null>(null);
 const [lastUpdated,setLastUpdated]=useState<Date|null>(null);
 const [trends,setTrends]=useState<Trends|null>(null);
 const [strength,setStrength]=useState<Strength|null>(null);
 const [alarm,setAlarm]=useState<Alarm|null>(null);
 const [loading,setLoading]=useState(true);
 const [saving,setSaving]=useState(false);
 const [error,setError]=useState("");
 const [message,setMessage]=useState("");
 const [days,setDays]=useState(30);
 const load=useCallback(async(silent=false)=>{
  if(!silent){setLoading(true);setError("");}
  try {
   const [s,h,p,a]=await Promise.all([
     api<Summary>("/api/summary"),
     api<Trends>("/api/health-trends?days="+days),
     api<Strength>("/api/strength"),
     api<Alarm>("/api/alarm")
   ]);
   setSummary(s);setTrends(h);setStrength(p);setAlarm(a);setLastUpdated(new Date());setError("");
  }catch(e){setError(e instanceof Error?e.message:"Errore sconosciuto");}
  finally{setLoading(false);}
 },[days]);
 useEffect(()=>{
  void load();
  // Rileggi i dati storici ogni 30s senza causare un nuovo caricamento visibile.
  // La FC Bluetooth diretta ha un polling separato ogni 3s.
  const interval=window.setInterval(()=>{
   if(document.visibilityState==="visible")void load(true);
  },30000);
  const refreshVisible=()=>{
   if(document.visibilityState==="visible")void load(true);
  };
  document.addEventListener("visibilitychange",refreshVisible);
  return ()=>{window.clearInterval(interval);document.removeEventListener("visibilitychange",refreshVisible);};
 },[load]);
 useEffect(()=>{
  if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js").catch(()=>{});
 },[]);
 const saveAlarm=async()=>{
  if(!alarm)return;
  setSaving(true);setError("");setMessage("");
  try{
   const data=await api<Alarm>("/api/alarm","PUT",{
    enabled:alarm.enabled,deadline:alarm.deadline,
    window_minutes:alarm.window_minutes,weekdays:alarm.weekdays,mode:"fixed"
   });
   setAlarm(data);
   setMessage("Salvato sul server. Apri Benessere sul telefono e premi «Applica sveglia dalla web app». L'orario non è ancora attivo finché Android non conferma.");
  }catch(e){setError(e instanceof Error?e.message:"Salvataggio fallito")}
  finally{setSaving(false)}
 };
 const title=labels[section];
 const status=alarm?.delivery==="confirmed"?"Confermata dal telefono":
   alarm?.delivery==="pending_phone"?"Da applicare sul telefono":
   alarm?.delivery==="failed"?"Errore Android":"Da configurare";
 return <div className="shell">
  <aside className="sidebar">
   <div className="brand"><div className="brand-icon"><Activity size={24}/></div><div><b>Benessere</b><span>Health & performance</span></div></div>
   <nav className="nav" aria-label="Navigazione principale">
   {mainSections.map((s,i)=>{const Icon=navIcons[i];return <button key={s} className={"navbtn "+(section===s?"active":"")} onClick={()=>setSection(s)}>
     <Icon size={19}/>{labels[s]}</button>})}
   <button className={"navbtn "+(section==="diario"?"active":"")} onClick={()=>setSection("diario")}><Dumbbell size={19}/>Diario completo</button>
   <button className={"navbtn "+(section==="sveglia"?"active":"")} onClick={()=>setSection("sveglia")}><AlarmClock size={19}/>Sveglia</button>
   </nav><div className="sidebar-foot">Dati personali · accesso riservato<br/>Nessuna misura simulata</div>
  </aside>
  <main className="main">
   <header className="topbar">
    <div><div className="eyebrow">Personal health hub</div><h1>{title}</h1><div className="date">{new Intl.DateTimeFormat("it-IT",{weekday:"long",day:"numeric",month:"long",year:"numeric"}).format(new Date())}</div></div>
    <div className="actions">{lastUpdated&&<span className="small">Riepilogo aggiornato alle {lastUpdated.toLocaleTimeString("it-IT",{hour:"2-digit",minute:"2-digit",second:"2-digit"})}</span>}<button className="iconbtn" aria-label="Ricarica dati" onClick={()=>void load()}><RefreshCcw size={20}/></button>
    <button className="iconbtn" aria-label="Impostazioni sveglia" onClick={()=>setSection("sveglia")}><Bell size={20}/></button></div>
   </header>
   {error&&<div className="notice warn" role="alert">{error}</div>}
   {message&&<div className="notice success" role="status">{message}</div>}
   {loading&&!summary&&<div className="notice"><LoaderCircle size={16}/> Collegamento al database Benessere…</div>}
   {section==="oggi"&&<div className="loading">
    <div className="hero"><div className="eyebrow">Riepilogo quotidiano</div>
    <h2>La tua salute, senza rumore.</h2>
    <p>Allenamento, recupero e alimentazione in un'unica vista. Le misure mancanti rimangono esplicite.</p>
    <div className="quick"><button className="btn secondary" onClick={()=>setSection("diario")}>Registra pasto o allenamento <ArrowUpRight size={14}/></button></div></div>
    <div className="grid four">
     <Value label="Sonno rilevato" icon={Moon} value={number(summary?.health.sleep?.duration_h??null,1)} unit="ore" note={summary?.health.sleep?.accuracy==="fasi"?"Fasi disponibili":"Copertura da verificare"}/>
     <Value label={liveHeart?.status==="live"?"FC diretta · Helio Strap":"Ultimo battito · Health Connect"}
       icon={HeartPulse}
       value={number(liveHeart?.status==="live"?liveHeart.bpm:(summary?.health.heart?.bpm??null))}
       unit="bpm"
       note={liveHeart?.status==="live"?"Bluetooth live · "+fmt(liveHeart.last_received_at):
         summary?.health.heart?.at?fmt(summary.health.heart.at):"Non rilevato"}/>
     <Value label="Passi" icon={Activity} value={number(summary?.health.steps??null)} note="Giornata selezionata"/>
     <Value label="HRV RMSSD" icon={Watch} value={number(summary?.health.hrv?.rmssd_ms??null,1)} unit="ms" note="Solo dati realmente disponibili"/>
    </div>
    <SectionHeader title="Frequenza cardiaca in tempo reale"/>
    <div className="grid two"><LiveHeartPanel onSnapshot={setLiveHeart}/></div>
    <SectionHeader title="Nutrizione" note="Oggi"/>
    <div className="grid two"><Card>
      <div className="cardlabel"><Utensils size={16}/> Energia registrata</div>
      <div className="big">{number(summary?.nutrition.consumed.kcal??null)} <span style={{fontSize:15}}>kcal</span></div>
      {summary?.nutrition.target?<div className="stack">
       <div className="small">Target indicativo: {number(summary.nutrition.target.target_kcal)} kcal · {summary.nutrition.target.label}</div>
       <Progress label="Proteine" actual={summary.nutrition.consumed.protein_g} target={summary.nutrition.target.protein_g} unit="g"/>
       <Progress label="Carboidrati" actual={summary.nutrition.consumed.carbs_g} target={summary.nutrition.target.carbs_g} unit="g"/>
       <Progress label="Grassi" actual={summary.nutrition.consumed.fat_g} target={summary.nutrition.target.fat_g} unit="g"/>
      </div>:<div className="notice">Nessun target verificato per questa giornata.</div>}
     </Card>
     <Card><h3><Dumbbell size={17}/> Allenamenti</h3>{summary?.workouts.length?summary.workouts.map(w=><div className="activity" key={w.id}>
      <div className="row"><b>{humanType(w.type)}</b><span className="pill">{number(w.duration_min)} min</span></div>
      <div className="small">Inizio: {w.start_time||"Non dichiarato"} · RPE: {number(w.rpe)}</div>
     </div>):<Empty message="Nessuna sessione registrata oggi."/>}</Card></div>
    <SectionHeader title="Stato dispositivo"/>
    <div className="notice">{summary?.health.sync.last_sync?"Health Connect sincronizzato: "+fmt(summary.health.sync.last_sync):"Non risulta una sincronizzazione Health Connect confermata."} · Sveglia: {status}.</div>
   </div>}
   {section==="salute"&&<div>
    <div className="row"><div className="muted">Serie reali dal database Benessere</div><select aria-label="Periodo" value={days} onChange={e=>setDays(Number(e.target.value))}>
     <option value={7}>7 giorni</option><option value={14}>14 giorni</option><option value={30}>30 giorni</option><option value={90}>90 giorni</option></select></div>
    <SectionHeader title="Panoramica sensori"/><div className="grid four">
     <Value label="Notti registrate" icon={Moon} value={number(trends?.counts.sleep_nights??null)}/>
     <Value label="Campioni FC" icon={HeartPulse} value={number(trends?.counts.heart_samples??null)}/>
     <Value label="Notti HRV" icon={Activity} value={number(trends?.counts.hrv_nights??null)}/>
     <Value label="Giorni attività" icon={TrendingUp} value={number(trends?.counts.days??null)}/>
    </div>
    <SectionHeader title="Helio Strap · Bluetooth live"/><div className="grid two"><LiveHeartPanel/></div>
    <SectionHeader title="Andamenti"/><div className="grid two">
     <Card><h3>Battito cardiaco (bpm)</h3>{trends&&<TrendsChart data={trends} kind="heart"/>}</Card>
     <Card><h3>Sonno registrato (ore)</h3>{trends&&<TrendsChart data={trends} kind="sleep"/>}</Card>
     <Card><h3>Passi</h3>{trends&&<TrendsChart data={trends} kind="steps"/>}</Card>
     <Card><h3>Peso rilevato (kg)</h3>{trends&&<TrendsChart data={trends} kind="weight"/>}</Card>
    </div><div className="notice">Le durate senza fasi potrebbero riferirsi al tempo della sessione a letto. Le misure non sono diagnosi.</div>
   </div>}
   {section==="allenamento"&&<div><div className="hero"><div className="eyebrow">Training log</div><h2>Ogni sessione conta.</h2><p>Storico di allenamento della giornata, carichi e RPE; i blocchi dettagliati restano consultabili nella dashboard attuale durante la migrazione.</p></div>
     {summary?.workouts.length?summary.workouts.map(w=><Card key={w.id} className="activity"><div className="row"><h3>{humanType(w.type)}</h3><span className="pill">{number(w.duration_min)} min</span></div>
     <div className="small">Ore {w.start_time||"non indicate"} · RPE {number(w.rpe)}</div></Card>):<Empty message="Nessun allenamento in questa giornata. Non significa automaticamente riposo."/>}
   </div>}
   {section==="alimentazione"&&<div>
    <div className="hero"><div className="eyebrow">Piano massa</div><h2>Energia adatta al tuo allenamento.</h2><p>Le quantità provengono dal diario. I target indicativi si attivano soltanto per una giornata classificata.</p></div>
    <div className="grid four">
    <Value label="Calorie" icon={Apple} value={number(summary?.nutrition.consumed.kcal??null)} unit="kcal"/>
    <Value label="Proteine" icon={Utensils} value={number(summary?.nutrition.consumed.protein_g??null)} unit="g"/>
    <Value label="Carboidrati" icon={Activity} value={number(summary?.nutrition.consumed.carbs_g??null)} unit="g"/>
    <Value label="Grassi" icon={Scale} value={number(summary?.nutrition.consumed.fat_g??null)} unit="g"/>
    </div>
    <SectionHeader title="Obiettivo quotidiano"/>
    <Card>{summary?.nutrition.target?<div className="stack">
     <Progress label="Calorie" actual={summary.nutrition.consumed.kcal} target={summary.nutrition.target.target_kcal} unit="kcal"/>
     <Progress label="Proteine" actual={summary.nutrition.consumed.protein_g} target={summary.nutrition.target.protein_g} unit="g"/>
     <Progress label="Carboidrati" actual={summary.nutrition.consumed.carbs_g} target={summary.nutrition.target.carbs_g} unit="g"/>
     <Progress label="Grassi" actual={summary.nutrition.consumed.fat_g} target={summary.nutrition.target.fat_g} unit="g"/>
    </div>:<Empty message="Target non disponibile: completa l'obiettivo massa e il tipo di giornata nell'app attuale."/>}</Card>
   </div>}
   {section==="progressi"&&<div><div className="hero"><div className="eyebrow">Traguardi</div><h2>Misura i progressi, non le impressioni.</h2><p>Confronta peso e massimali senza confondere un complex con un singolo 1RM.</p></div>
     <SectionHeader title="Peso"/><Card>{trends&&<TrendsChart data={trends} kind="weight"/>}</Card>
     <SectionHeader title="Massimali e record" note="Ultimi registrati"/>
     {strength?.maxes.length?<div className="grid two">{strength.maxes.slice(0,14).map((record,i)=>{
       const title=String(record.exercise||record.lift||record.name||record.movement||"Record");
       const amount=record.weight_kg??record.value_kg??record.load_kg??null;
       return <Card key={i}><div className="cardlabel">{title}</div><div className="big">{typeof amount==="number"?number(amount,1)+" kg":"Record"}</div>
       <div className="small">{String(record.date||"Data non specificata")}</div></Card>
     })}</div>:<Empty message="Massimali non disponibili nel servizio di lettura."/>}
   </div>}
   {section==="diario"&&<JournalPanel changed={()=>{void load()}}/>}
   {section==="sveglia"&&<div>
    <div className="hero"><div className="eyebrow">Sonno e risveglio</div><h2>Programma dal web. Esegui sul telefono.</h2>
     <p>L'allarme deve essere confermato dall'app Android. La vibrazione diretta di Helio Strap resta configurabile in Zepp, non in Benessere.</p></div>
    <div className="grid two"><Card>
     <div className="row"><h3>Programmazione</h3><span className="pill">Rev. {alarm?.revision??0}</span></div>
     {!alarm?<Empty message="Configurazione non disponibile."/>:<div className="stack">
      <label className="field"><span>Sveglia attiva</span><input type="checkbox" checked={alarm.enabled} onChange={e=>setAlarm({...alarm,enabled:e.target.checked})}/></label>
      <div className="field"><label htmlFor="time">Orario massimo</label><input id="time" type="time" value={alarm.deadline} onChange={e=>setAlarm({...alarm,deadline:e.target.value})}/></div>
      <div className="field"><label htmlFor="window">Finestra futura (non operativa)</label>
      <select id="window" value={alarm.window_minutes} onChange={e=>setAlarm({...alarm,window_minutes:Number(e.target.value)})}>
       {[15,30,45,60].map(n=><option key={n} value={n}>{n} minuti</option>)}
      </select></div>
      <div className="field"><span>Giorni della settimana</span><div className="weekdays">
       {["L","M","M","G","V","S","D"].map((d,i)=>{
        const day=i+1,selected=alarm.weekdays.includes(day);
        return <button key={day} type="button" aria-label={"Giorno "+day} aria-pressed={selected}
         className={"day "+(selected?"on":"")} onClick={()=>setAlarm({...alarm,weekdays:selected?alarm.weekdays.filter(x=>x!==day):[...alarm.weekdays,day].sort()})}>{d}</button>;
       })}</div></div>
      <button className="btn" disabled={saving||!alarm.weekdays.length} onClick={()=>void saveAlarm()}>{saving?"Salvataggio…":"Salva sul server"}</button>
     </div>}</Card>
     <Card><h3>Stato e sicurezza</h3><div className="big">{status}</div>
      <div className="notice">{alarm?.device_ack?.error||"Le modifiche web non diventano sveglie finché Android non le applica e le conferma."}</div>
      <p className="small">Sul telefono: apri Benessere → «Applica sveglia dalla web app». Controlla notifiche e permesso allarmi esatti.</p>
      <p className="small">Su Helio Strap: Zepp → Dispositivo → Helio Strap → Sveglia. La vibrazione diretta non è ancora integrata.</p>
      <div className="notice warn">Health Connect non fornisce una fase del sonno in tempo reale verificata. Per ora è disponibile soltanto l'allarme fisso sul telefono: conserva una sveglia di riserva.</div>
     </Card></div>
   </div>}
  </main>
  <nav className="mobile-nav" aria-label="Navigazione mobile">
   {mainSections.map((s,i)=>{const Icon=navIcons[i];return <button key={s} className={section===s?"active":""} onClick={()=>setSection(s)}>
    <Icon size={20}/><span>{labels[s]}</span></button>})}
   <button className={section==="diario"?"active":""} onClick={()=>setSection("diario")}><Dumbbell size={20}/><span>Diario</span></button>
  </nav>
 </div>;
}
