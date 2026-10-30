// Offline build: launch Chromium with DevTools port 9228 and serve the repo on
// 4174, then `node scripts/motion/render.mjs [output-directory]`.
import fs from 'node:fs/promises';
import path from 'node:path';
const destination = path.resolve(process.argv[2] || 'dist/motion-frames');
await fs.mkdir(destination, { recursive: true });
const pages = await (await fetch('http://127.0.0.1:9228/json/list')).json();
const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
let serial=0;
const waiting=new Map();
ws.addEventListener('message', ({ data }) => {
 const message=JSON.parse(data);
 if (!message.id) return;
 const pending=waiting.get(message.id);
 waiting.delete(message.id);
 message.error ? pending.reject(message.error) : pending.resolve(message.result);
});
const cdp=(method,params={})=>new Promise((resolve,reject)=>{
 const id=++serial;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));
});
await cdp('Page.enable');
await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:480,deviceScaleFactor:1,mobile:false});
await cdp('Page.navigate',{url:'http://127.0.0.1:4174/scripts/motion/scene.html'});
await new Promise(resolve=>setTimeout(resolve,1000));
for(let frame=0;frame<240;frame++) {
 const result=await cdp('Runtime.evaluate',{expression:`window.renderFrame(${frame})`});
 if(result.exceptionDetails) throw new Error('Animation source failed');
 const shot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 await fs.writeFile(path.join(destination,String(frame).padStart(4,'0')+'.png'),Buffer.from(shot.data,'base64'));
 if(frame%40===0) console.log(`Rendered ${frame}/240 frames`);
}
ws.close();
console.log(`Rendered 12-second loop to ${destination}`);
