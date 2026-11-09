// Synthetic CSS fixtures; no user records or network. Not a full app certification.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
const browser=await chromium.launch({headless:true,chromiumSandbox:true,executablePath:process.env.CHROMIUM_PATH});let cases=0;
try{for(const native of [true,false])for(const colorScheme of ['light','dark'])for(const width of [320,360,640,800,1440])for(const long of [false,true]){
 const context=await browser.newContext({viewport:{width,height:1000},colorScheme});const page=await context.newPage();await page.route('**/*',r=>r.abort());
 const css=fs.readFileSync(path.join(__dirname,'..',native?'desktop/design-system.css':'hermes_crm/static/app.css'),'utf8');
 const card=i=>`<section class="${native?(i===1?'hc-contact-log':'hc-card'):''}"><h3>${['Primary Company','Contact log','Associated tasks','Related Events','Relationship Activities'][i]}</h3><p>${long?'Long_unbroken_synthetic_record_'.repeat(30):'No records yet.'}</p><button type="button" id="action-${i}">Open record ${i}</button></section>`;
 const title=long?'UnbrokenSyntheticContactName'.repeat(8):'Synthetic Contact',subtitle=long?'UnbrokenSyntheticCompanySubtitle'.repeat(8):'Role at Synthetic Company';
 const header=`<section class="hc-record"><nav aria-label="Record navigation"><button>Back to Contacts</button><span aria-current="page"> / ${title}</span></nav><div class="hc-record-header"><div class="hc-row"><div class="hc-identity"><div class="hc-avatar">SC</div><div><div class="hc-eyebrow">CONTACT</div><h2>${title}</h2><p class="hc-muted">${subtitle}</p></div></div><button>Close</button></div></div></section>`;
 const content=native?`<div class="hermes-crm-native"><div class="hc-wrap">${header}<section class="hc-contact-grid">${card(0)}${card(1)}<div class="hc-contact-relationships">${[2,3,4].map(card).join('')}</div></section></div></div>`:`<dialog open><div class="detail-body"><div class="contact-detail-grid">${[0,1,2,3,4].map(card).join('')}</div></div></dialog>`;
 await page.setContent(`<html class="${native&&colorScheme==='dark'?'dark':''}"><head><style>${css}html,body{margin:0;height:100%}</style></head><body>${content}</body></html>`);
 const state=await page.evaluate(native=>{const grid=document.querySelector(native?'.hc-contact-grid':'.contact-detail-grid'),cards=[...grid.querySelectorAll('section')],r=grid.getBoundingClientRect();return{cols:getComputedStyle(grid).gridTemplateColumns.split(' ').length,overflow:document.documentElement.scrollWidth>innerWidth,cardOverflow:cards.some(el=>el.scrollWidth>el.clientWidth+1),rect:cards.map(el=>({left:el.getBoundingClientRect().left,top:el.getBoundingClientRect().top,width:el.getBoundingClientRect().width,bottom:el.getBoundingClientRect().bottom})),width:r.width};},native);
 const name=`${native?'native':'standalone'} ${colorScheme} ${width} ${long?'long':'empty'}`;
 // Root overflow can stay hidden while descendant text clips. Inspect actual
 // element and text-line boxes against the containing record, not just scrollWidth.
 if(native){const clipped=await page.evaluate(()=>{
   const record=document.querySelector('.hc-record').getBoundingClientRect();
   const selectors=['.hc-record>nav>span','.hc-record-header .hc-identity','.hc-identity h2','.hc-identity p'];
   return selectors.flatMap(selector=>[...document.querySelectorAll(selector)].flatMap(el=>{
     const range=document.createRange();range.selectNodeContents(el);
     const boxes=[el.getBoundingClientRect(),...range.getClientRects()];
     return boxes.some(r=>r.width>0&&(r.left<record.left-1||r.right>record.right+1||r.right>innerWidth+1))?[selector]:[];
   }));
 });assert.deepEqual(clipped,[],name+' record heading/breadcrumb text boxes remain visible');}
 assert.equal(state.overflow,false,name);assert.equal(state.cardOverflow,false,name+' card containment');
 if(width===320){assert.equal(state.cols,1,name+' narrow single column');for(let i=1;i<state.rect.length;i++)assert(state.rect[i].top>=state.rect[i-1].bottom,name+' narrow DOM order');}
 if(width===1440){if(native)assert.equal(state.cols,2,name+' exactly two outer columns');else assert(state.cols>=2,name+' wide grid');assert.equal(state.rect[0].top,state.rect[1].top,name+' cards share a row');if(native){assert.equal(state.rect[2].top,state.rect[3].top,name+' tasks and Events share the next row');assert.equal(state.rect[2].left,state.rect[0].left,name+' tasks align with Company');assert.equal(state.rect[3].left,state.rect[1].left,name+' Events align with log');assert.equal(state.rect[4].left,state.rect[0].left,name+' Activities share the same grid');assert.equal(state.rect.length,5,name+' only core relationship cards');}}
 await page.locator('#action-0').focus();for(let i=1;i<5;i++){await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),`action-${i}`,name+' DOM keyboard order');}
 await context.close();cases++;
}console.log(`PASS ${cases} native/standalone contact grid fixtures: empty/long, light/dark, narrow/wide, containment and keyboard order`);}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
