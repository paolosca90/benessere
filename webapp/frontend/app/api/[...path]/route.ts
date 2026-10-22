import {NextRequest,NextResponse} from "next/server";
export const runtime="nodejs";
export const dynamic="force-dynamic";
const allowed=new Set(["summary","health-trends","strength","alarm","live-heart-rate","journal",
  "meal","workout","workout-block","max","wod","result","photo","day-mode","profile"]);
const kinds=new Set(["meals","workouts","wods","results","maxes","photos","profile"]);
async function proxy(req:NextRequest,ctx:{params:Promise<{path:string[]}>},method:"GET"|"PUT"|"POST") {
 const {path}=await ctx.params;
 if(!path.length||!allowed.has(path[0])||
   (path.length!==1 && !(path.length===2 && path[0]==="photo" && /^\d+$/.test(path[1]))))
  return NextResponse.json({error:"route non trovata"},{status:404});
 if(method==="PUT"&&!["alarm","day-mode","profile"].includes(path[0]))
  return NextResponse.json({error:"metodo non ammesso"},{status:405});
 if(method==="POST"&&!["meal","workout","workout-block","max","wod","result","photo"].includes(path[0]))
  return NextResponse.json({error:"metodo non ammesso"},{status:405});
 const base=process.env.BENESSERE_API_INTERNAL_URL||"";
 const token=process.env.BENESSERE_WEB_API_TOKEN||"";
 if((!base.startsWith("http://")&&!base.startsWith("https://"))||token.length<32)
  return NextResponse.json({error:"Backend non configurato"},{status:503});
 try {
  const url=new URL("/v1/"+path.join("/"),base);
  if(method==="GET"){
   if(path[0]==="health-trends"){
    const days=req.nextUrl.searchParams.get("days");
    if(days&&/^\d+$/.test(days))url.searchParams.set("days",days);
   }
   if(path[0]==="journal"){
    const kind=req.nextUrl.searchParams.get("kind");
    if(!kind||!kinds.has(kind))return NextResponse.json({error:"Categoria non valida"},{status:422});
    url.searchParams.set("kind",kind);
    const day=req.nextUrl.searchParams.get("day");
    if(day&&/^\d{4}-\d\d-\d\d$/.test(day))url.searchParams.set("day",day);
   }
   if(path[0]==="day-mode"){
    const day=req.nextUrl.searchParams.get("day");
    if(day&&/^\d{4}-\d\d-\d\d$/.test(day))url.searchParams.set("day",day);
   }
  }
  const isImage=method==="GET"&&path[0]==="photo"&&path.length===2;
  const res=await fetch(url,{method,cache:"no-store",
   headers:{"Authorization":"Bearer "+token,
     ...(isImage?{}:{"Content-Type":"application/json"})},
   ...(method!=="GET"?{body:JSON.stringify(await req.json())}:{})});
  if(isImage){
   if(!res.ok)return NextResponse.json({error:"Foto non disponibile"},{status:res.status});
   const bytes=await res.arrayBuffer();
   return new NextResponse(bytes,{status:res.status,
     headers:{"Content-Type":"image/jpeg","Cache-Control":"private,no-store"}});
  }
  const payload=await res.json();
  return NextResponse.json(payload,{status:res.status,headers:{"Cache-Control":"private,no-store"}});
 }catch{
  return NextResponse.json({error:"Backend temporaneamente non raggiungibile"},{status:502});
 }
}
export async function GET(r:NextRequest,c:{params:Promise<{path:string[]}>}){return proxy(r,c,"GET");}
export async function PUT(r:NextRequest,c:{params:Promise<{path:string[]}>}){return proxy(r,c,"PUT");}
export async function POST(r:NextRequest,c:{params:Promise<{path:string[]}>}){return proxy(r,c,"POST");}
