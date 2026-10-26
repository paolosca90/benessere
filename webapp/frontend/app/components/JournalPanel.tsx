"use client";
import {useCallback,useEffect,useMemo,useState} from "react";
import {Camera,CalendarDays,Check,ClipboardList,Dumbbell,Image as ImageIcon,Plus,RefreshCcw,Scale,Utensils} from "lucide-react";

type Kind="meals"|"workouts"|"wods"|"results"|"maxes"|"photos"|"profile";
type Row=Record<string,unknown>;
type Mode="unspecified"|"crossfit_hard"|"crossfit_light"|"tennis"|"double"|"rest";
const kindInfo:{id:Kind,label:string}[]=[
 {id:"meals",label:"Pasti"},{id:"workouts",label:"Allenamenti"},
 {id:"wods",label:"Catalogo WOD"},{id:"results",label:"Risultati WOD"},
 {id:"maxes",label:"Massimali"},{id:"photos",label:"Foto"},{id:"profile",label:"Profilo"}
];
const modeLabels:Record<Mode,string>={
 unspecified:"Automatico / non determinato",
 crossfit_hard:"CrossFit intenso",crossfit_light:"CrossFit leggero o pesi",
 tennis:"Tennis",double:"Doppia sessione",rest:"Riposo confermato"
};
const workoutLabels:Record<string,string>={
 metcon:"CrossFit — Metcon",strength:"Pesi / Forza",gymnastics:"Gymnastics",skill:"Tecnica",
 tennis:"Tennis",other:"Altro"
};
const mealLabels:Record<string,string>={
 breakfast:"Colazione",lunch:"Pranzo",dinner:"Cena",snack:"Spuntino"
};
function today(){
 const d=new Date();d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,10);
}
async function call(path:string,method:"GET"|"POST"|"PUT"="GET",body?:unknown){
 const response=await fetch("/api/"+path,{method,cache:"no-store",headers:{"Content-Type":"application/json"},
  ...(method!=="GET"?{body:JSON.stringify(body)}:{})});
 const payload=await response.json();
 if(!response.ok)throw new Error(typeof payload.detail==="string"?payload.detail:payload.error||"Operazione non riuscita");
 return payload;
}
const fmt=(x:unknown)=>x==null?"—":String(x);
const number=(x:unknown)=>typeof x==="number"?x.toLocaleString("it-IT",{maximumFractionDigits:1}):"—";
function Item({title,detail,children}:{title:string,detail?:string,children?:React.ReactNode}){
 return <div className="activity"><div className="row" style={{alignItems:"start"}}>
  <div><b>{title}</b>{detail&&<div className="small">{detail}</div>}{children}</div></div></div>;
}
function shortDate(value:unknown){
 const text=String(value||"");
 const match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
 return match?match[3]+"/"+match[2]+"/"+match[1]:text;
}
function shortWodName(value:unknown){
 const title=String(value||"WOD");
 return title.length>52?title.slice(0,49).trimEnd()+"…":title;
}
function WodBoard({record}:{record:Row}){
 const blocks=Array.isArray(record.blocks)?record.blocks.filter((b):b is Row=>!!b&&typeof b==="object"):[];
 const rpe=record.rpe==null?"":` · RPE ${number(record.rpe)}/10`;
 const duration=record.duration_min==null?"":` · ${number(record.duration_min)} min`;
 return <article className="wod-sheet">
  <header className="wod-sheet-head">
   <div><div className="wod-sheet-kicker">Scheda allenamento</div><h4>{shortDate(record.date)} · {workoutLabels[String(record.type)]||"CrossFit"}</h4></div>
   <div className="wod-sheet-summary">{duration.replace(/^ · /,"")}{rpe}</div>
  </header>
  {blocks.length?<div className="wod-sheet-grid">{blocks.map((block,i)=>{
   const label=String(block.label||"");
   const explicit=/^([A-Z])\s*[·.:-]/.exec(label);
   const letter=explicit?explicit[1]:String.fromCharCode(65+i);
   const heading=explicit?label.replace(/^[A-Z]\s*[·.:-]\s*/,""):label||"Blocco";
   const reps=block.repetitions==null?null:(block.sets!=null?`${number(block.sets)} × ${number(block.repetitions)} rep`:`${number(block.repetitions)} rep`);
   const weight=block.weight_kg!=null?`${number(block.weight_kg)} kg`:null;
   const minutes=block.reported_duration_min!=null?`${number(block.reported_duration_min)} min`:null;
   const notes=String(block.notes||"");
   return <section className="wod-step" key={String(block.id||i)}>
    <div className="wod-step-head"><span className="wod-step-letter">{letter}</span><b>{heading}</b></div>
    <div className="wod-step-movement">{String(block.exercise||"Esercizio non indicato")}</div>
    <div className="wod-step-stats">
      {reps&&<span>{reps}</span>}{weight&&<span>{weight}</span>}{minutes&&<span>{minutes}</span>}
    </div>
    {notes&&<div className="wod-step-note">{notes}</div>}
   </section>;
  })}</div>:<div className="wod-no-blocks">I blocchi A–D non sono ancora stati salvati in formato strutturato.</div>}
  {Boolean(record.notes)&&<details className="wod-more"><summary>Note complete e dettagli tecnici</summary><p>{String(record.notes)}</p></details>}
 </article>;
}
export default function JournalPanel({changed}:{changed:()=>void}){
 const [category,setCategory]=useState<Kind>("workouts");
 const [day,setDay]=useState(today);
 const [items,setItems]=useState<Row[]>([]);
 const [wodNames,setWodNames]=useState<Row[]>([]);
 const [mode,setMode]=useState<Mode>("unspecified");
 const [source,setSource]=useState("");
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [message,setMessage]=useState("");
 const [formKey,setFormKey]=useState(0);
 const [file,setFile]=useState<File|null>(null);
 const [newMeal,setMeal]=useState({meal:"breakfast",description:"",kcal:"",protein_g:"",carbs_g:"",fat_g:""});
 const [newWorkout,setWorkout]=useState({type:"metcon",duration_min:"",rpe:"",start_time:"",notes:""});
 const [newMax,setMax]=useState({lift:"Back Squat",weight_kg:"",reps:"1",category:"lift",notes:""});
 const [newWod,setWod]=useState({name:"",score_type:"time",description:""});
 const [newResult,setResult]=useState({wod_name:"",score:"",scaling:"rx",notes:""});
 const [newPhoto,setPhoto]=useState({angle:"front",notes:""});
 const [profile,setProfile]=useState<Record<string,string>>({});
 const [newBlock,setBlock]=useState({workout_id:"",label:"",exercise:"",phase:"wod",weight_kg:"",repetitions:"",sets:"",rpe:""});
 const load=useCallback(async()=>{
   setError("");
   try{
    const search=new URLSearchParams({kind:category,day});
    const [records,modeReply]=await Promise.all([
     call("journal?"+search),
     call("day-mode?day="+encodeURIComponent(day))
    ]);
    setItems(Array.isArray(records.items)?records.items:[]);
    if(category==="profile")setProfile(Object.fromEntries((records.items||[]).map((x:Row)=>[String(x.key),String(x.value)])));
    setMode(modeReply.mode||"unspecified");setSource(modeReply.source||"");
    if(category==="results"){
      const names=await call("journal?kind=wods");setWodNames(names.items||[]);
    }
   }catch(e){setError(e instanceof Error?e.message:"Errore lettura diario");}
 },[category,day]);
 useEffect(()=>{void load()},[load]);
 const submit=async(path:string,body:unknown,reset?:()=>void)=>{
   setBusy(true);setError("");setMessage("");
   try{
     const result=await call(path,"POST",body);
     if(!result.saved && !result.id && !result.wod)throw new Error("Il server non ha confermato la registrazione");
     setMessage("Salvataggio confermato dal server · ID "+fmt(result.id));
     reset?.();setFormKey(k=>k+1);
     await load();changed();
   }catch(e){setError(e instanceof Error?e.message:"Salvataggio fallito")}
   finally{setBusy(false)}
 };
 const saveProfile=async()=>{
  setBusy(true);setError("");setMessage("");
  try{
   const payload:Record<string,string|number>={};
   for(const key of ["goal","sex","weight_kg","height_cm","age","sleep_need_h","resting_hr","body_fat_pct_estimate"]){
    const value=profile[key];
    if(value!=null&&value!=="")payload[key]=(key==="goal"||key==="sex")?value:Number(value);
   }
   const out=await call("profile","PUT",payload);
   if(!out.saved)throw new Error("Salvataggio non confermato");
   setMessage("Profilo aggiornato");await load();changed();
  }catch(e){setError(e instanceof Error?e.message:"Errore profilo")}finally{setBusy(false)}
 };
 const saveMode=async()=>{
  setBusy(true);setError("");setMessage("");
  try{await call("day-mode","PUT",{date:day,mode});setMessage("Tipo giornata aggiornato.");await load();changed()}
  catch(e){setError(e instanceof Error?e.message:"Errore modifica giornata")}finally{setBusy(false)}
 };
 const photoUpload=async()=>{
  if(!file){setError("Seleziona una fotografia");return}
  if(file.size>10*1024*1024){setError("Foto superiore a 10 MB");return}
  const b64=await new Promise<string>((resolve,reject)=>{
   const reader=new FileReader();
   reader.onload=()=>resolve(String(reader.result).split(",")[1]||"");
   reader.onerror=()=>reject(new Error("Lettura foto fallita"));
   reader.readAsDataURL(file);
  });
  await submit("photo",{taken_on:day,angle:newPhoto.angle,notes:newPhoto.notes,image_base64:b64},
    ()=>{setPhoto({angle:"front",notes:""});setFile(null)});
 };
 const allowedWods=useMemo(()=>wodNames.map(x=>String(x.name)),[wodNames]);
 return <div>
  <div className="hero"><div className="eyebrow">Diario unificato</div>
   <h2>Registra e consulta i tuoi dati.</h2>
   <p>Stesso archivio SQLite utilizzato da Android, ChatGPT e Google Sheets. Ogni salvataggio deve essere confermato dal server.</p>
  </div>
  <div className="row" style={{marginBottom:14,flexWrap:"wrap"}}>
    <label className="field"><span>Data</span><input type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
    <button className="btn secondary" onClick={()=>void load()}><RefreshCcw size={15}/> Aggiorna</button>
  </div>
  <section className="card" style={{marginBottom:15}}>
   <div className="row" style={{flexWrap:"wrap"}}>
    <div><b>Tipo di giornata</b><div className="small">Fonte: {source==="manual"?"Scelta manuale":source==="workouts"?"Allenamenti registrati":"Dati insufficienti"}</div></div>
    <select aria-label="Tipo giornata" value={mode} onChange={e=>setMode(e.target.value as Mode)}>
     {(Object.keys(modeLabels) as Mode[]).map(m=><option key={m} value={m}>{modeLabels[m]}</option>)}
    </select>
    <button className="btn secondary" onClick={()=>void saveMode()} disabled={busy}>Salva tipo giorno</button>
   </div>
  </section>
  <div className="journal-tabs" role="group" aria-label="Categorie diario">
   {kindInfo.map(t=><button key={t.id} className={"day "+(category===t.id?"on":"")}
     onClick={()=>{setCategory(t.id);setMessage("");setError("")}}>{t.label}</button>)}
  </div>
  {error&&<div className="notice warn" role="alert">{error}</div>}
  {message&&<div className="notice success" role="status"><Check size={15}/> {message}</div>}
  <div className="grid two">
   <section className="card">
    <h3><Plus size={16}/> Aggiungi {kindInfo.find(x=>x.id===category)?.label.toLowerCase()}</h3>
    {category==="meals"&&<form key={"meal"+formKey} className="stack" onSubmit={e=>{
      e.preventDefault();void submit("meal",{request_key:crypto.randomUUID(),date:day,meal:newMeal.meal,
       description:newMeal.description,kcal:Number(newMeal.kcal),protein_g:Number(newMeal.protein_g),
       carbs_g:Number(newMeal.carbs_g),fat_g:Number(newMeal.fat_g)},
       ()=>setMeal({meal:"breakfast",description:"",kcal:"",protein_g:"",carbs_g:"",fat_g:""}));
     }}>
     <label className="field">Pasto<select value={newMeal.meal} onChange={e=>setMeal({...newMeal,meal:e.target.value})}>
      {Object.entries(mealLabels).map(([val,label])=><option key={val} value={val}>{label}</option>)}
     </select></label>
     <label className="field">Alimenti e quantità<input required maxLength={600} value={newMeal.description} onChange={e=>setMeal({...newMeal,description:e.target.value})} placeholder="Es. 75g crema di riso, 30g whey"/></label>
     <div className="grid two">{([["kcal","Calorie"],["protein_g","Proteine (g)"],["carbs_g","Carboidrati (g)"],["fat_g","Grassi (g)"]] as const).map(([key,label])=><label key={key} className="field">{label}
       <input type="number" required min="0" max={key==="kcal"?10000:1500} step="any"
        value={newMeal[key]} onChange={e=>setMeal({...newMeal,[key]:e.target.value})}/></label>)}</div>
     <button className="btn" disabled={busy}>Salva pasto</button>
    </form>}
    {category==="workouts"&&<form key={"workout"+formKey} className="stack" onSubmit={e=>{
      e.preventDefault();void submit("workout",{request_key:crypto.randomUUID(),date:day,type:newWorkout.type,
        duration_min:Number(newWorkout.duration_min),rpe:newWorkout.rpe?Number(newWorkout.rpe):null,
        start_time:newWorkout.start_time||null,notes:newWorkout.notes},
        ()=>setWorkout({type:"metcon",duration_min:"",rpe:"",start_time:"",notes:""}));
     }}>
     <label className="field">Disciplina<select value={newWorkout.type} onChange={e=>setWorkout({...newWorkout,type:e.target.value})}>{Object.entries(workoutLabels).map(([val,label])=><option key={val} value={val}>{label}</option>)}</select></label>
     <div className="grid two"><label className="field">Durata (min)<input type="number" required min="1" max="360" step="1" value={newWorkout.duration_min} onChange={e=>setWorkout({...newWorkout,duration_min:e.target.value})}/></label>
     <label className="field">RPE (1–10, facoltativo)<input type="number" min="1" max="10" step=".5" value={newWorkout.rpe} onChange={e=>setWorkout({...newWorkout,rpe:e.target.value})}/></label></div>
     <label className="field">Inizio, se conosciuto<input type="time" value={newWorkout.start_time} onChange={e=>setWorkout({...newWorkout,start_time:e.target.value})}/></label>
     <label className="field">Esercizi, carichi e note<textarea rows={4} maxLength={1500} value={newWorkout.notes} onChange={e=>setWorkout({...newWorkout,notes:e.target.value})}/></label>
     <div className="small">Per WOD complessi, i blocchi già salvati restano nello storico. La creazione di nuovi blocchi strutturati è ancora in sviluppo.</div>
     <button className="btn" disabled={busy}>Registra allenamento</button>
    </form>}
    {category==="workouts"&&items.length>0&&<form className="stack" style={{marginTop:22,borderTop:"1px solid #325269",paddingTop:18}} onSubmit={e=>{
      e.preventDefault();void submit("workout-block",{
       workout_id:Number(newBlock.workout_id),label:newBlock.label,exercise:newBlock.exercise,phase:newBlock.phase,
       time_reference:"unspecified",
       weight_kg:newBlock.weight_kg?Number(newBlock.weight_kg):null,
       repetitions:newBlock.repetitions?Number(newBlock.repetitions):null,
       sets:newBlock.sets?Number(newBlock.sets):null,
       rpe:newBlock.rpe?Number(newBlock.rpe):null
      },()=>setBlock({workout_id:"",label:"",exercise:"",phase:"wod",weight_kg:"",repetitions:"",sets:"",rpe:""}));
    }}>
      <h3>Aggiungi blocco a una sessione</h3>
      <label className="field">Allenamento<select required value={newBlock.workout_id} onChange={e=>setBlock({...newBlock,workout_id:e.target.value})}>
        <option value="">Seleziona sessione</option>{items.map(x=><option key={String(x.id)} value={String(x.id)}>{String(x.date)} · {workoutLabels[String(x.type)]||String(x.type)} · #{String(x.id)}</option>)}
      </select></label>
      <label className="field">Fase<select value={newBlock.phase} onChange={e=>setBlock({...newBlock,phase:e.target.value})}>
       <option value="wod">WOD</option><option value="strength">Forza</option><option value="skill">Tecnica</option><option value="warmup">Riscaldamento</option><option value="other">Altro</option></select></label>
      <label className="field">Nome blocco<input required maxLength={70} value={newBlock.label} onChange={e=>setBlock({...newBlock,label:e.target.value})}/></label>
      <label className="field">Esercizio<input required maxLength={180} value={newBlock.exercise} onChange={e=>setBlock({...newBlock,exercise:e.target.value})}/></label>
      <div className="grid two">
       {([["weight_kg","Kg"],["sets","Serie"],["repetitions","Reps"],["rpe","RPE 1–10"]] as const).map(([key,title])=><label key={key} className="field">{title}<input type="number" step={key==="sets"||key==="repetitions"?"1":".5"} min={key==="rpe"?"1":"0"} value={newBlock[key]} onChange={e=>setBlock({...newBlock,[key]:e.target.value})}/></label>)}
      </div>
      <button className="btn" disabled={busy||!newBlock.workout_id}>Salva blocco</button>
     </form>}
    {category==="maxes"&&<form className="stack" onSubmit={e=>{
       e.preventDefault();void submit("max",{lift:newMax.lift,date:day,weight_kg:Number(newMax.weight_kg),
         reps:Number(newMax.reps),category:newMax.category,notes:newMax.notes},
         ()=>setMax({...newMax,weight_kg:""}));
      }}>
      <label className="field">Esercizio<input required value={newMax.lift} onChange={e=>setMax({...newMax,lift:e.target.value})}/></label>
      <label className="field">Categoria<select value={newMax.category} onChange={e=>setMax({...newMax,category:e.target.value})}>
       <option value="lift">Singola alzata</option><option value="complex">Complex</option></select></label>
      <div className="grid two"><label className="field">Kg<input required type="number" step=".5" min=".5" max="1000" value={newMax.weight_kg} onChange={e=>setMax({...newMax,weight_kg:e.target.value})}/></label>
      <label className="field">Repetizioni<input required type="number" min="1" max="100" value={newMax.reps} onChange={e=>setMax({...newMax,reps:e.target.value})}/></label></div>
      <label className="field">Note<input value={newMax.notes} onChange={e=>setMax({...newMax,notes:e.target.value})}/></label>
      <button className="btn" disabled={busy}>Registra carico</button>
     </form>}
    {category==="wods"&&<form className="stack" onSubmit={e=>{
       e.preventDefault();void submit("wod",newWod,()=>setWod({name:"",score_type:"time",description:""}));
      }}>
      <label className="field">Nome WOD<input required value={newWod.name} onChange={e=>setWod({...newWod,name:e.target.value})}/></label>
      <label className="field">Tipo punteggio<select value={newWod.score_type} onChange={e=>setWod({...newWod,score_type:e.target.value})}>
       <option value="time">Tempo</option><option value="amrap">AMRAP</option><option value="load">Carico</option><option value="reps">Reps</option></select></label>
      <label className="field">Descrizione<textarea rows={4} value={newWod.description} onChange={e=>setWod({...newWod,description:e.target.value})}/></label>
      <button className="btn" disabled={busy}>Salva WOD</button>
     </form>}
    {category==="results"&&<form className="stack" onSubmit={e=>{
       e.preventDefault();void submit("result",{wod_name:newResult.wod_name,date:day,score:newResult.score,
        scaling:newResult.scaling,notes:newResult.notes},()=>setResult({...newResult,score:""}));
      }}>
      <label className="field">WOD<select required value={newResult.wod_name} onChange={e=>setResult({...newResult,wod_name:e.target.value})}>
       <option value="">Seleziona WOD</option>{allowedWods.map(x=><option key={x} value={x}>{x}</option>)}</select></label>
      <label className="field">Risultato<input required placeholder="es. 17:00 / 12+35 / 85" value={newResult.score} onChange={e=>setResult({...newResult,score:e.target.value})}/></label>
      <label className="field">Scaling<input value={newResult.scaling} onChange={e=>setResult({...newResult,scaling:e.target.value})}/></label>
      <label className="field">Note<textarea value={newResult.notes} onChange={e=>setResult({...newResult,notes:e.target.value})}/></label>
      <button className="btn" disabled={busy||!newResult.wod_name}>Registra risultato</button>
     </form>}
    {category==="profile"&&<form className="stack" onSubmit={e=>{e.preventDefault();void saveProfile()}}>
      <label className="field">Obiettivo<select value={profile.goal||"bulk"} onChange={e=>setProfile({...profile,goal:e.target.value})}>
       <option value="bulk">Massa</option><option value="maintain">Mantenimento</option><option value="cut">Definizione</option></select></label>
      <label className="field">Sesso registrato<select value={profile.sex||"m"} onChange={e=>setProfile({...profile,sex:e.target.value})}>
       <option value="m">Maschile</option><option value="f">Femminile</option></select></label>
      {([["weight_kg","Peso (kg)"],["height_cm","Altezza (cm)"],["age","Età"],["sleep_need_h","Fabbisogno sonno (ore)"],["resting_hr","FC a riposo"],["body_fat_pct_estimate","Massa grassa stimata (%)"]] as const).map(([key,title])=><label className="field" key={key}>{title}
       <input type="number" step="any" value={profile[key]||""} onChange={e=>setProfile({...profile,[key]:e.target.value})}/></label>)}
      <button className="btn" disabled={busy}>Salva profilo</button>
     </form>}
    {category==="photos"&&<div className="stack">
      <div className="small">Le foto rimangono sul tuo server, non vengono inviate a servizi esterni.</div>
      <label className="field">Inquadratura<select value={newPhoto.angle} onChange={e=>setPhoto({...newPhoto,angle:e.target.value})}>
       <option value="front">Frontale</option><option value="side">Laterale</option><option value="back">Posteriore</option><option value="other">Altra</option></select></label>
      <label className="field">Seleziona foto (max 10 MB)<input type="file" accept="image/*" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
      <label className="field">Note<input maxLength={600} value={newPhoto.notes} onChange={e=>setPhoto({...newPhoto,notes:e.target.value})}/></label>
      <button className="btn" disabled={busy||!file} onClick={()=>void photoUpload()}><Camera size={16}/> Salva foto privata</button>
     </div>}
   </section>
   <section className="card">
    <h3><ClipboardList size={16}/> {category==="workouts"?"Schede per giornata":"Archivio · "+kindInfo.find(x=>x.id===category)?.label}</h3>
    {items.length===0?<div className="empty">Nessun record disponibile. Nessun dato dimostrativo.</div>:
     <div style={{maxHeight:700,overflowY:"auto"}}>
     {items.slice(0,120).map((x,i)=>{
      if(category==="meals")return <Item key={String(x.ts||i)} title={mealLabels[String(x.meal)]||String(x.meal)} detail={String(x.description||"")}>
       <div className="small">{number(x.kcal)} kcal · P {number(x.protein_g)} · C {number(x.carbs_g)} · G {number(x.fat_g)}</div></Item>;
      if(category==="workouts")return <WodBoard key={String(x.id||i)} record={x}/>;
      if(category==="maxes")return <Item key={String(x.id||i)} title={String(x.lift||"")} detail={String(x.date||"")+" · "+String(x.category||"")} >
       <div className="small">{number(x.weight_kg)} kg · {number(x.reps)} rep</div></Item>;
      if(category==="wods")return <Item key={String(x.id||i)} title={shortWodName(x.name)} detail={String(x.score_type||"")}>
       <details className="wod-more"><summary>Movimenti e schema completo</summary>
       <p>{String(x.description||"Nessuna descrizione.")}</p></details></Item>;
      if(category==="results")return <Item key={String(x.id||i)} title={shortDate(x.date)+" · "+shortWodName(x.wod)} detail={"Risultato: "+String(x.score_display||"")+" · "+String(x.scaling||"")}>
       {x.is_pr?<div className="small">Record personale</div>:null}</Item>;
      if(category==="profile")return <Item key={String(x.key||i)} title={String(x.key||"")} detail={String(x.value||"")}/>;
      if(category==="photos")return <div className="activity" key={String(x.id||i)}>
       <div className="small">{String(x.taken_on||"")} · {String(x.angle||"")}</div>
       {/* Browser request inherits reverse-proxy authentication; image never publicly cached. */}
       <img alt={"Foto progressi "+String(x.taken_on||"")} src={"/api/photo/"+String(x.id)} style={{maxWidth:"100%",maxHeight:300,borderRadius:12,marginTop:8}}/>
       <div className="small">{String(x.notes||"")}</div></div>;
      return null;
     })}
     </div>}
   </section>
  </div>
 </div>;
}
