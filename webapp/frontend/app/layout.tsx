import type { Metadata, Viewport } from "next";
import "./globals.css";
export const metadata: Metadata = {
 title:"Benessere | Health & Performance",
 description:"Dashboard privata, salute e allenamenti",
 applicationName:"Benessere",manifest:"/manifest.webmanifest"
};
export const viewport: Viewport = {width:"device-width",initialScale:1,
 viewportFit:"cover",themeColor:"#08131f"};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>) {
 return <html lang="it"><body>{children}</body></html>;
}
