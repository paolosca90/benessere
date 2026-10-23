"use client";
import {useCallback,useEffect,useMemo,useState} from "react";
import {ClipboardList,RefreshCcw} from "lucide-react";

type Block={
  id:number;position:number;phase:string;label:string;exercise:string;
  repetitions:number|null;sets:number|null;weight_kg:number|null;
  rpe:number|null;time_reference:string;notes:string;
};
type Result={
  id:number;date:string;score_display:string;scaling:string;notes:string;is_pr:number;
  workout_id:number|null;workout_start_time:string|null;workout_duration_min:number|null;
  workout_rpe:number|null;workout_load:number|null;workout_notes:string|null;
  blocks:Block[];
};
type Wod={id:number;name:string;description:string;score_type:string;category:string;results:Result[]};
const amount=(value:number|null|undefined)=>value==null?"Non dichiarato":
  new Intl.NumberFormat("it-IT",{maximumFractionDigits:2}).format(value);
const readableDate=(value:string)=>/^\d{4}-\d{2}-\d{2}$/.test(value)?
  value.slice(8,10)+"/"+value.slice(5,7)+"/"+value.slice(0,4):value;

export default function WodLibraryPanel(){
  const [items,setItems]=useState<Wod[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [showCatalog,setShowCatalog]=useState(false);
  const [search,setSearch]=useState("");
  const reload=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const response=await fetch("/api/wod-library",{cache:"no-store"});
      const payload=await response.json();
      if(!response.ok)throw new Error(payload?.detail||payload?.error||"Lettura WOD non riuscita");
      setItems(Array.isArray(payload.items)?payload.items:[]);
    }catch(e){setError(e instanceof Error?e.message:"Errore lettura WOD")}
    finally{setLoading(false)}
  },[]);
  useEffect(()=>{void reload()},[reload]);
  const visible=useMemo(()=>items
    .filter(w=>(showCatalog||w.results.length>0)&&
      (w.name+" "+w.description).toLocaleLowerCase("it").includes(search.toLocaleLowerCase("it")))
    .sort((a,b)=>(b.results[0]?.date||"").localeCompare(a.results[0]?.date||"")||
      a.name.localeCompare(b.name,"it")),[items,showCatalog,search]);
  return <div>
    <div className="hero">
      <div className="eyebrow">Archivio allenamenti</div>
      <h2>I miei WOD — schede complete</h2>
      <p>Movimenti, ripetizioni, carichi, tempo, RPE e note provengono dallo stesso archivio. I totali di squadra non sono ripetizioni individuali.</p>
    </div>
    <section className="card" style={{marginBottom:16}}>
      <div className="row" style={{flexWrap:"wrap",gap:12}}>
        <label className="field"><span>Cerca WOD</span>
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Nome o movimento" aria-label="Cerca WOD"/>
        </label>
        <label style={{display:"flex",alignItems:"center",gap:8}}>
          <input type="checkbox" checked={showCatalog} onChange={e=>setShowCatalog(e.target.checked)}/>
          Mostra anche quelli mai svolti
        </label>
        <button className="btn secondary" type="button" onClick={()=>void reload()} disabled={loading}>
          <RefreshCcw size={15}/> Aggiorna
        </button>
      </div>
    </section>
    {error&&<div className="notice warn" role="alert">{error}</div>}
    {loading&&<div className="notice">Caricamento dei WOD registrati…</div>}
    {!loading&&!error&&visible.length===0&&<div className="empty">Nessun WOD corrispondente ai filtri. I dati non sono simulati.</div>}
    <div className="stack">
      {visible.map((w,index)=><details key={w.id} className="card" open={index===0}>
        <summary style={{cursor:"pointer",fontWeight:650,listStyle:"auto"}}>
          {w.name} · {w.results.length} {w.results.length===1?"risultato":"risultati"}
        </summary>
        <div style={{marginTop:12}} className="stack">
          <div className="small">{w.description||"Descrizione non registrata"} · Modalità: {w.score_type}</div>
          {w.results.length===0&&<div className="small">Nessun risultato eseguito ancora.</div>}
          {w.results.map(result=><section key={result.id} className="activity">
            <div className="row" style={{flexWrap:"wrap",alignItems:"start"}}>
              <b>{readableDate(result.date)} · {result.score_display}{result.is_pr?" · PR":""}</b>
              <span className="pill">{result.scaling==="unspecified"?"Scaling non dichiarato":result.scaling}</span>
            </div>
            <div className="small">
              {result.workout_id==null?"Nessuna sessione collegata":
                "Sessione #"+result.workout_id+" · inizio "+(result.workout_start_time||"non registrato")+
                " · durata "+amount(result.workout_duration_min)+" min"+
                " · RPE sessione "+amount(result.workout_rpe)+"/10"+
                " · carico stimato "+amount(result.workout_load)}
            </div>
            {result.notes&&<p className="small">Note risultato: {result.notes}</p>}
            {result.workout_notes&&<p className="small">Note allenamento: {result.workout_notes}</p>}
            {result.blocks.length>0?<div className="stack" style={{marginTop:12}}>
              <b><ClipboardList size={15} style={{display:"inline",verticalAlign:"middle"}}/> Movimenti e blocchi ({result.blocks.length})</b>
              {result.blocks.map(block=><div className="activity" key={block.id||block.position}>
                <div className="row"><b>{block.position}. {block.exercise}</b><span className="small">{block.label}</span></div>
                <div className="small">
                  {block.repetitions==null?"Ripetizioni non dichiarate":block.repetitions+" ripetizioni"}
                  {block.sets!=null?" · "+block.sets+" serie":""}
                  {block.weight_kg!=null?" · "+amount(block.weight_kg)+" kg":""}
                  {block.rpe!=null?" · RPE blocco "+amount(block.rpe)+"/10":""}
                </div>
                {block.notes&&<div className="small">{block.notes}</div>}
              </div>)}
            </div>:<div className="small">Non ci sono blocchi dettagliati collegati a questo risultato.</div>}
          </section>)}
        </div>
      </details>)}
    </div>
  </div>;
}
