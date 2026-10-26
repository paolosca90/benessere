"use client";
import {useEffect,useState} from "react";
import {Activity,Radio,WifiOff} from "lucide-react";
import {LineChart,Line,ResponsiveContainer,YAxis,Tooltip} from "recharts";

type LiveData={
 status:"live"|"offline";
 bpm:number|null;
 last_bpm:number|null;
 last_received_at:string|null;
 seconds_since_last:number|null;
 source:string|null;
 points:{at:string,bpm:number}[];
 expiry_seconds:number;
};

export type LiveHeartSnapshot = Pick<LiveData,"status"|"bpm"|"last_received_at">;

export default function LiveHeartPanel({onSnapshot}:{onSnapshot?:(snapshot:LiveHeartSnapshot|null)=>void}){
 const [data,setData]=useState<LiveData|null>(null);
 const [error,setError]=useState("");
 useEffect(()=>{
  let active=true;
  async function poll(){
   if(document.visibilityState!=="visible")return;
   try {
    const r=await fetch("/api/live-heart-rate",{cache:"no-store"});
    if(!r.ok)throw new Error("HTTP "+r.status);
    const result=await r.json() as LiveData;
    if(active){setData(result);setError("");onSnapshot?.(result);}
   }catch{
    if(active){setData(null);setError("Collegamento alla FC live non disponibile");onSnapshot?.(null);}
   }
  }
  void poll();
  const interval=window.setInterval(()=>{void poll()},3000);
  return ()=>{active=false;window.clearInterval(interval)};
 },[onSnapshot]);
 const live=data?.status==="live";
 const samples=data?.points||[];
 return <section className="card" aria-live="polite">
  <div className="row">
   <div className="cardlabel"><Activity size={16}/> Helio Strap · FC diretta</div>
   <span className={"pill "+(!live?"muted":"")} style={!live?{color:"#b5c7d1",background:"#253947"}:{}}>
    {live?<><Radio size={12}/> Live</>:<><WifiOff size={12}/> Non connesso</>}
   </span>
  </div>
  <div className="big" style={live?{color:"var(--accent)"}:{}}>
   {live?data?.bpm:"—"} <span style={{fontSize:15,fontWeight:500,color:"var(--muted)"}}>bpm</span>
  </div>
  <div className="small">
   {error?error:live?"Bluetooth 180D · ricevuto negli ultimi 15 secondi":
    data?.last_received_at?"Ultimo dato ricevuto: "+new Date(data.last_received_at).toLocaleString("it-IT")+
      " (non è una misura live)":"In attesa dell'invio dalla app Android"}
  </div>
  {live&&samples.length>=2?<div className="chart" style={{height:140,marginTop:12}} aria-label="Frequenza cardiaca live negli ultimi due minuti">
   <ResponsiveContainer width="100%" height="100%">
    <LineChart data={samples}>
     <YAxis hide domain={["dataMin - 5","dataMax + 5"]}/>
     <Tooltip contentStyle={{background:"#0c2030",border:"1px solid #315164",borderRadius:10}}
      labelFormatter={()=>"FC Bluetooth"} formatter={(value)=>[value+" bpm","FC"]}/>
     <Line dataKey="bpm" type="monotone" stroke="#5ae1cb" strokeWidth={2}
      dot={false} isAnimationActive={false}/>
    </LineChart>
   </ResponsiveContainer>
  </div>:null}
  <div className="small" style={{marginTop:10}}>
   Dati separati da Health Connect. Per restare online servono nuovi battiti ogni 15 secondi:
   mantieni Benessere Android aperta in primo piano, con schermo attivo e Bluetooth connesso.
  </div>
 </section>;
}
