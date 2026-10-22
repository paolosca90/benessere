import {NextRequest,NextResponse} from "next/server";
export const runtime="nodejs";
export const dynamic="force-dynamic";
const allowed=new Set(["summary","health-trends","strength","alarm"]);
async function proxy(req:NextRequest,ctx:{params:Promise<{path:string[]}>},method:"GET"|"PUT") {
 const {path}=await ctx.params;
 if(path.length!==1||!allowed.has(path[0])||(method==="PUT"&&path[0]!=="alarm"))
  return NextResponse.json({error:"route non trovata"},{status:404});
 const base=process.env.BENESSERE_API_INTERNAL_URL||"";
 const token=process.env.BENESSERE_WEB_API_TOKEN||"";
 if(!base.startsWith("http://") && !base.startsWith("https://") || token.length<32)
  return NextResponse.json({error:"Backend non configurato"},{status:503});
 try {
  const url=new URL("/v1/"+path[0],base);
  if(method==="GET" && path[0]==="health-trends"){
   const days=req.nextUrl.searchParams.get("days");
   if(days && /^\d+$/.test(days))url.searchParams.set("days",days);
  }
  const res=await fetch(url,{method,cache:"no-store",
   headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"},
   ...(method==="PUT"?{body:JSON.stringify(await req.json())}:{})});
  const payload=await res.json();
  return NextResponse.json(payload,{status:res.status,headers:{"Cache-Control":"no-store"}});
 } catch {
  return NextResponse.json({error:"Backend momentaneamente non raggiungibile"},{status:502});
 }
}
export async function GET(r:NextRequest,c:{params:Promise<{path:string[]}>}){return proxy(r,c,"GET");}
export async function PUT(r:NextRequest,c:{params:Promise<{path:string[]}>}){return proxy(r,c,"PUT");}
