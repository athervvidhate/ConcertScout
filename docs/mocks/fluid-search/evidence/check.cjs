// Bounded check for the study. At 1440 and 390, with and without reduced motion:
// the home demo plays to its third step and (with motion) loops back to an empty start by itself, without
// the band changing height or any panel clipping its content;
// every study Search reaches its results with the right number of Concerts (0 shows the empty state),
// with no errors or sideways scroll and no leftover name copies; Grid and List show the same Concerts;
// a card opens its Ticket with the photo in place, Save in the Ticket updates the nav count, and Escape
// closes it, returns the photo at exactly the card's size and focus to the card; an unknown Search offers the replayed ones.
const {chromium}=require('/Users/atherv/.t3/worktrees/concert-scout/t3-952cd47d/frontend/node_modules/@playwright/test');
const path=require('node:path'),assert=require('node:assert/strict');
const page='file://'+path.resolve(__dirname,'../index.html');
const study=[['house-chicago',8],['techno-detroit',4],['khruangbin-chicago',3],['boise-shoegaze',2],['four-tet-boise',1],['sparse-answer',0]];
(async()=>{const b=await chromium.launch();
for(const [w,h] of [[1440,900],[390,844]])for(const reducedMotion of ['no-preference','reduce']){
 const ctx=await b.newContext({viewport:{width:w,height:h},reducedMotion}),p=await ctx.newPage(),errors=[];
 p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>m.type()==='error'&&errors.push(m.text()));
 const motion=reducedMotion!=='reduce';
 const settle=()=>p.waitForTimeout(motion?1900:150);
 const wide=()=>p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);
 const results=async()=>{await p.waitForFunction(()=>document.body.dataset.state==='working',null,{timeout:5000});
  await p.waitForFunction(()=>document.body.dataset.state==='results',null,{timeout:20000});await settle();};
 await p.goto(page);await p.waitForTimeout(300);
 assert.equal(await p.locator('#howReplay,.facts-band').count(),0,'removed sections are back');
 const band=()=>p.evaluate(()=>[document.querySelector('#how').offsetHeight,[...document.querySelectorAll('.how-demo')].some(d=>d.scrollHeight>d.clientHeight+1)]);
 await p.locator('#how').scrollIntoViewIfNeeded();await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(50);
 const [bandH]=await band();
 await p.waitForFunction(()=>document.querySelectorAll('.how-step.done').length===3,null,{timeout:15000});
 assert.equal(await p.locator('.demo-pick').count(),3);
 assert.deepEqual(await band(),[bandH,false],'How band resized or clipped when full');
 if(motion)await p.waitForFunction(()=>!document.querySelector('.how-step.done')&&!document.querySelector('#demoPicks').children.length,null,{timeout:8000});
 assert.deepEqual(await band(),[bandH,false],'How band resized when emptied');
 assert.equal(await wide(),true,`home overflows at ${w}`);
 await p.evaluate(()=>scrollTo(0,0));
 for(const [id,n] of study){
  await p.locator(`[data-study="${id}"]`).click();await results();
  assert.equal(await p.locator('.name-fly, body > .name').count(),0,`${id} left name copies`);
  assert.equal(await p.locator('#results [data-card]').count(),n,`${id} cards`);
  if(n===0)assert.equal(await p.locator('.empty').count(),1);
  if(n>1){
   assert.equal(await p.locator('#views [role=radio]').count(),2);
   for(const v of ['list','grid']){await p.locator(`#views [data-view=${v}]`).click();await settle();assert.equal(await p.locator('#results [data-card]').count(),n,`${id} ${v}`);}
  }
  assert.equal(await wide(),true,`${id} overflows at ${w}`);
 }
 // Ticket
 await p.locator('[data-study="khruangbin-chicago"]').click();await results();
 const card=p.locator('#results [data-card]').nth(1);
 await card.locator('.card-open').click();await p.waitForTimeout(motion?1500:200);
 assert.equal(await p.evaluate(()=>document.querySelector('#ticket').open),true);
 assert.equal(await p.locator('.fly-photo').count(),0,'photo copy left after opening');
 assert.equal(await p.evaluate(()=>getComputedStyle(document.querySelector('#ticketImg')).opacity),'1');
 const photo=await p.locator('.ticket-photo').boundingBox(),sheet=await p.locator('.ticket-sheet').boundingBox();
 assert.ok(photo.width>100&&sheet.y>=0&&sheet.y+sheet.height<=h+1,'Ticket off screen');
 assert.ok((await p.locator('#close').boundingBox()).width>40,'close button hidden');
 await p.locator('#ticketSave').click();
 assert.equal(await p.locator('#badge .badge-num').innerText(),'1');
 await p.keyboard.press('Escape');await p.waitForTimeout(motion?1200:200);
 assert.equal(await p.evaluate(()=>document.querySelector('#ticket').open),false);
 assert.equal(await p.locator('.fly-photo').count(),0,'photo copy left after closing');
 assert.equal(await card.locator('img').evaluate((i)=>getComputedStyle(i).opacity),'1');
 assert.equal(await card.locator('img').evaluate((i)=>getComputedStyle(i).transform),'none','card photo left scaled');
 const [ib,cb]=[await card.locator('img').boundingBox(),await card.boundingBox()];
 assert.ok(Math.abs(ib.width-cb.width)<1&&Math.abs(ib.height-cb.height)<1,'card photo not at card size');
 assert.equal(await p.evaluate(()=>document.activeElement.className),'card-open');
 await p.fill('#query','metal in Denver');await p.keyboard.press('Enter');
 assert.match(await p.locator('#note').innerText(),/replays eight real Searches/);
 assert.deepEqual(errors,[]);console.log(w,reducedMotion,'passed');await ctx.close()}
await b.close()})().catch(e=>{console.error(e.message);process.exit(1)});
