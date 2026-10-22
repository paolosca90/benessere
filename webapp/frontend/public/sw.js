// Non memorizzare MAI dati sanitari, richieste API o pagine autenticate.
const CACHE="benessere-offline-v1";
self.addEventListener("install", event => {
 event.waitUntil(caches.open(CACHE).then(c=>c.add("/offline.html")));
 self.skipWaiting();
});
self.addEventListener("activate", event=>event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", event => {
 const u=new URL(event.request.url);
 if(event.request.mode!=="navigate"||u.origin!==self.location.origin)return;
 event.respondWith(fetch(event.request).catch(()=>caches.match("/offline.html")));
});
