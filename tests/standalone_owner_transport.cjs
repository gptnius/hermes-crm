// Emit actual UI transport calls for the Python in-process FastAPI integration test.
const vm=require('node:vm'),fs=require('node:fs');
const element={dataset:{},addEventListener(){},innerHTML:''};
const c={crypto:require('node:crypto').webcrypto,URLSearchParams,Intl,Date,setTimeout,clearTimeout,document:{querySelector(){return element},addEventListener(){}},window:{addEventListener(){}},location:{hash:'#tasks'}};
vm.createContext(c);const run=x=>vm.runInContext(x,c);
run(fs.readFileSync(require('node:path').join(__dirname,'../hermes_crm/static/app.js'),'utf8').replace(/initialize\(\);\s*$/,''));
if(process.argv.includes('--validate-receipt')) {
 c.receipt=JSON.parse(fs.readFileSync(0,'utf8'));
 console.log(run("ownerReceipt({path:receipt.request.path.split('?')[0],payload:JSON.stringify(receipt.request.body),id:receipt.request.path.startsWith('tasks/') ? receipt.result.id : null},receipt.result)"));
} else (async()=>{
 run("relationshipWorkspace='SYNTHETIC_SCOPE';var transport=[];api=async(path,method='GET',body,key)=>{transport.push({path,method,body,key});if(method==='GET')return {version:0,required:false,default_owner_label:null};if(path==='task-owner-policy')return {...body.data,version:body.data.version+1};return {...body,id:'synthetic-task',version:method==='PATCH' ? 2 : 1};}");
 await run("relationshipRead('task-owner-policy')");
 await run("ownerWrite('task-owner-policy','PATCH',{data:{version:0,required:true,default_owner_label:'Reviewed owner'}})");
 await run("ownerWrite('tasks','POST',{title:'Synthetic UI contract',due_at:'2030-01-01T12:00:00.123456Z',status:'open',priority:'normal',notes:'',contact_id:null,deal_id:null,owner_label:'Reviewed owner',owner_source:'default',owner_policy_version:1})");
 await run("ownerWrite('tasks/synthetic-task','PATCH',{version:1,title:'Synthetic UI contract',due_at:'2030-01-01T12:00:00.123456+00:00',status:'done',priority:'normal',notes:'',contact_id:null,deal_id:null,owner_label:'Reviewed owner',owner_source:'default',owner_policy_version:1})");
 console.log(run('JSON.stringify(transport)'));
})().catch(error=>{console.error(error);process.exitCode=1});
