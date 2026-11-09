// Exports synthetic Storage HTML for an isolated/offscreen browser, never live Hermes.
import {createRequire} from 'node:module';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import vm from 'node:vm';
const require=createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React=require('react'),Renderer=require('react-test-renderer');
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const context=vm.createContext({URLSearchParams});
const module=new vm.SourceTextModule(await readFile(new URL('../desktop/storage-settings.js',import.meta.url),'utf8'),{context});
await module.link(()=>new vm.SyntheticModule(Object.keys(React),function(){for(const [key,value] of Object.entries(React))this.setExport(key,value);},{context}));await module.evaluate();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function html(n){if(n==null)return '';if(Array.isArray(n))return n.map(html).join('');if(typeof n!=='object')return esc(n);const attrs=Object.entries(n.props||{}).filter(([k,v])=>v!=null&&!k.startsWith('on')&&!['ref','children','style'].includes(k)&&v!==false).map(([k,v])=>`${k==='className'?'class':k==='tabIndex'?'tabindex':k}="${esc(v)}"`).join(' ');return `<${n.type} ${attrs}>${html(n.children)}</${n.type}>`;}
const out=process.env.HERMES_CRM_RENDER_DIR;if(!out)throw Error('Set HERMES_CRM_RENDER_DIR to a new owned fixture directory');
await mkdir(out,{recursive:true});const css=await readFile(new URL('../desktop/design-system.css',import.meta.url),'utf8');
for(const backend of ['sqlite','postgres','unavailable']){
  const client={current:()=>true,request:async path=>{
    if(backend==='unavailable')throw Error('Synthetic backend failure');
    if(path!=='/storage/status')throw Error('Visual fixture must never probe');
    return {backend,configuration:'configured',selection_token:'a'.repeat(64)};
  }};
  let tree;await React.act(async()=>{tree=Renderer.create(React.createElement(module.namespace.StorageSettings,{client,profile:'Synthetic profile',canOpenHostSettings:true,openHostSettings:()=>true}));});
  for(const theme of ['light','dark'])await writeFile(`${out}/storage-${backend}-${theme}.html`,`<!doctype html><html class="${theme}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Synthetic Storage fixture</title><style>body{margin:0} ${css}</style><main class="hermes-crm-native"><div class="hc-wrap"><p>ISOLATED FIXTURE · NO CUSTOMER DATA</p><h1>Settings</h1>${html(tree.toJSON())}</div></main></html>`);
  await React.act(async()=>tree.unmount());
}
console.log(`Wrote 6 synthetic fixtures to ${out}`);
