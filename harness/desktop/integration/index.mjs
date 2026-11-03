import {readFile} from 'node:fs/promises';
export const name='qunxing-desktop-session';
export const inject=['connection'];
export function apply(ctx){
  ctx.connection.fetch.register({path:'/api/qx-brand/logo.png',methods:['GET'],requestBody:'buffered',fetch:async()=>
    new Response(await readFile(new URL('./assets/qunxing-black-gold.png',import.meta.url)),{
      headers:{'content-type':'image/png','cache-control':'public, max-age=86400','x-content-type-options':'nosniff'}
    })});
}
