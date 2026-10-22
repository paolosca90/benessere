import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
 return {name:"Benessere — Personal Health",short_name:"Benessere",
 description:"Il tuo diario di salute, allenamenti e nutrizione",
 start_url:"/",display:"standalone",background_color:"#08131F",
 theme_color:"#08131F",lang:"it",icons:[{src:"/icon.svg",sizes:"any",type:"image/svg+xml",purpose:"any"}]};
}
