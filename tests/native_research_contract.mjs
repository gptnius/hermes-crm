// Real adapter receipts/previews are supplied on stdin by the Python bridge.
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';
import vm from 'node:vm';
const context=vm.createContext({URL,URLSearchParams,TextEncoder,crypto:webcrypto,console});
const module=new vm.SourceTextModule(await readFile(new URL('../desktop/research.js',import.meta.url),'utf8'),{context});
await module.link(()=>new vm.SyntheticModule(['createElement','useEffect','useRef','useState'],function(){for(const name of ['createElement','useEffect','useRef','useState'])this.setExport(name,()=>{});},{context}));await module.evaluate();
let raw='';for await(const chunk of process.stdin)raw+=chunk;
const input=JSON.parse(raw),target={kind:input.kind,id:input.id};
if(process.argv.includes('--validate-receipt')) {
 const path='/'+input.request.path.replace(/^\//,'');
 console.log(module.namespace.confirmedResearchReceipt(path,input.request.body.data,input.result,target));
} else if(process.argv.includes('--validate-preview')) {
 const client={current:()=>true,request:async path=>path.includes('/preview?')?input.preview:path.includes('/research/evidence/')?input.evidence:Promise.reject(Error('Unexpected request'))};
 const session=module.namespace.researchSession(client,'synthetic-token',target);
 await session.evidence(input.evidence.id);
 const preview=await session.preview(input.preview.id);
 console.log(!!preview && preview.id===input.preview.id);
} else throw Error('Choose a bridge validation mode.');
