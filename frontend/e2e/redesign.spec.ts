import {writeFile} from "node:fs/promises";
import {expect,test,type Page} from "@playwright/test";

const picks = Array.from({length:8},(_,i) => ({concert:{id:`layout-${i}`,name:`Source Concert ${i+1}`,artists:[{name:`Source Artist ${i+1}`}],date:"2027-05-15",venue:`Source Hall ${i+1}`,city:"Chicago",url:`https://tickets.example/${i}`,image:"/spotify-logo-white.svg"},reason:"A source-backed recommendation."}));
const interpreted={place:"Chicago",artists:["Source Artist"],genres:[]};
function stream(count:number) {
  return [["status",{step:"interpret",message:"Reading your Search"}],["interpreted",interpreted],["candidates",{names:[...picks.map(p=>p.concert.artists[0].name),"Other Source Artist"],total:12}],["poster",{recommendations:picks.slice(0,count)}],["done",{}]].map(([event,data])=>`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
}
async function overflow(page:Page) {
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const reducedMotion of ["reduce","no-preference"] as const) {
  test(`all Poster counts, views and Ticket focus work with ${reducedMotion}`,async({page},info)=>{
    await page.emulateMedia({reducedMotion});
    const errors:string[]=[];
    page.on("pageerror",error=>errors.push(error.message));
    let count=0;
    await page.route("**/search",route=>route.fulfill({contentType:"text/event-stream",body:stream(count)}));
    await page.goto("/");
    for (const n of [0,1,2,3,4,8]) {
      count=n;
      await page.getByRole("textbox",{name:"Search",exact:true}).fill(`Search ${n}`);
      await page.getByRole("button",{name:"Search",exact:true}).click();
      await expect(page.locator(".concert-card")).toHaveCount(n);
      if (!n) {await expect(page.getByRole("heading",{name:"Nothing here fits"})).toBeVisible();continue;}
      const ids=await page.getByRole("button",{name:/^Open Ticket for/}).evaluateAll(els=>els.map(e=>e.getAttribute("aria-label")));
      await page.getByRole("button",{name:"List view"}).click();
      await expect(page.locator(".concerts-list .concert-card")).toHaveCount(n);
      expect(await page.getByRole("button",{name:/^Open Ticket for/}).evaluateAll(els=>els.map(e=>e.getAttribute("aria-label")))).toEqual(ids);
      await page.getByRole("button",{name:"Grid view"}).click();
      const trigger=page.getByRole("button",{name:"Open Ticket for Source Artist 1",exact:true});
      await trigger.click();
      const dialog=page.getByRole("dialog",{name:"Ticket for Source Artist 1",exact:true});
      await expect(dialog).toBeVisible();
      await expect(dialog).toHaveCSS("opacity","1");
      await expect(dialog.getByRole("link",{name:"Tickets for Source Concert 1"})).toHaveAttribute("href","https://tickets.example/0");
      await expect(dialog.locator(".price")).toHaveCount(0);
      await expect(dialog.getByRole("button",{name:"Skip",exact:true})).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await overflow(page);
    }
    await page.screenshot({path:info.outputPath("poster.png"),fullPage:true});
    expect(errors).toEqual([]);
  });
}

test("cached home examples make no Search request and work without the bot widget",async({page},info)=>{
  let searches=0;
  page.on("request",r=>{if(r.url().endsWith("/search")) searches++;});
  await page.route("**/challenges.cloudflare.com/**",route=>route.abort());
  await page.route("**/examples",route=>route.fulfill({json:{examples:[{text:"Tame Impala in London next summer",interpreted,candidates:{names:["Source Artist 1","Other Source Artist"],total:12},poster:{recommendations:picks.slice(0,3)}}]}}));
  await page.goto("/");
  await expect(page.getByRole("region",{name:"Found by real Searches"})).toBeVisible();
  const how=page.locator(".how");
  const height=await how.evaluate(e=>e.getBoundingClientRect().height);
  await page.screenshot({path:info.outputPath("home.png"),fullPage:true});
  await how.scrollIntoViewIfNeeded();
  await page.waitForTimeout(7000);
  expect(await how.evaluate(e=>e.getBoundingClientRect().height)).toBeCloseTo(height,0);
  await page.getByRole("button",{name:"Tame Impala in London next summer",exact:true}).click();
  await expect(page.locator(".concert-card")).toHaveCount(3);
  expect(searches).toBe(0);
  await overflow(page);
});

test("Save persists across views, navigation and reload; a missing photo stays absent",async({page})=>{
  await page.route("**/search",route=>route.fulfill({contentType:"text/event-stream",body:stream(2)}));
  await page.goto("/");
  await page.getByRole("textbox",{name:"Search",exact:true}).fill("UKG in SF");
  await page.getByRole("button",{name:"Search",exact:true}).click();
  await page.locator(".card-open").first().click();
  await page.getByRole("button",{name:"Save",exact:true}).click();
  await expect(page.getByRole("button",{name:"Saved",exact:true})).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(page.locator(".card-saved")).toHaveText("Saved");
  await page.getByRole("button",{name:"List view"}).click();
  await expect(page.locator(".card-saved")).toHaveText("Saved");
  await page.goto("/saved");
  await page.reload();
  await expect(page.getByRole("link",{name:"Tickets for Source Concert 1"})).toBeVisible();
  await page.getByRole("button",{name:"Remove",exact:true}).click();
  await expect(page.getByText("Nothing saved yet.",{exact:false})).toBeVisible();
});

test("theme follows system and manual choice persists without flashing the logo",async({page})=>{
  await page.emulateMedia({colorScheme:"dark"});
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-mode","dark");
  await expect(page.locator(".site-brand .brand-dark")).toBeVisible();
  await page.getByRole("button",{name:"Menu",exact:true}).click();
  await page.getByRole("menuitem",{name:"Switch light / dark mode"}).click();
  await expect(page.locator("html")).toHaveAttribute("data-mode","light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-mode","light");
  await expect(page.locator(".site-brand .brand-light")).toBeVisible();
  expect((await page.request.get("/icon.svg")).ok()).toBe(true);
  expect((await page.request.get("/favicon.ico")).ok()).toBe(true);
});

test("live API stream keeps source facts, missing values and the Poster through Privacy",async({page})=>{
  await page.goto("/");
  await page.getByRole("textbox",{name:"Search",exact:true}).fill("UKG in SF");
  const response=page.waitForResponse(r=>r.url().endsWith("/search"));
  await page.getByRole("button",{name:"Search",exact:true}).click();
  const body=await (await response).text();
  expect(body).toContain("event: done");
  expect(body).not.toContain("unknown-id");
  await expect(page.locator(".concert-card")).toHaveCount(2);
  await page.getByRole("button",{name:"Open Ticket for Contract Artist",exact:true}).click();
  await expect(page.locator(".ticket .venue")).toContainText("Source Hall");
  await expect(page.locator(".ticket .price")).toHaveText("$38");
  await expect(page.locator(".ticket .artist-name")).toHaveCSS("text-transform","uppercase");
  expect((await page.locator(".ticket .artist-name").boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await expect(page.getByRole("link",{name:"Tickets for Contract Concert One"})).toHaveAttribute("href","https://tickets.example/one");
  await expect(page.locator(".dialog-photo img")).toHaveAttribute("src","/spotify-logo-white.svg");
  await page.locator(".other-dates summary").click();
  await expect(page.locator(".other-chips a")).toHaveAttribute("href","https://tickets.example/three");
  await expect(page.locator(".other-place")).toContainText("Oakland");
  await page.keyboard.press("Escape");
  await page.getByRole("button",{name:"Open Ticket for Second Contract Artist",exact:true}).click();
  await expect(page.locator(".dialog-photo,.ticket .price")).toHaveCount(0);
  await expect(page.locator(".ticket .venue")).not.toContainText(/AM|PM/);
  await page.keyboard.press("Escape");
  const opened=page.waitForEvent("popup");
  await page.getByRole("link",{name:"Privacy",exact:true}).click();
  const privacy=await opened;
  await expect(privacy.getByRole("heading",{name:"Privacy",exact:true})).toBeVisible();
  await privacy.close();
  await expect(page.locator(".concert-card")).toHaveCount(2);
});

test("Poster presentation stays under one second after its response and records frame timing",async({page},info)=>{
  await page.emulateMedia({reducedMotion:"no-preference"});
  await page.addInitScript(()=>{
    const timing={received:0,usable:0,gaps:[] as number[]};
    Object.assign(window,{posterTiming:timing});
    let previous=0;
    function frame(now:number) {
      if(timing.received && !timing.usable) {
        if(previous) timing.gaps.push(now-previous);
        const trigger=document.querySelector<HTMLElement>('.card-open');
        if(trigger && trigger.getBoundingClientRect().height>0 && Number(getComputedStyle(trigger.parentElement!).opacity)>=.99) timing.usable=performance.now();
      }
      previous=now;
      if(!timing.usable)requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  });
  await page.route("**/search",async route=>{
    await page.evaluate(()=>{(window as unknown as {posterTiming:{received:number}}).posterTiming.received=performance.now();});
    await route.fulfill({contentType:"text/event-stream",body:stream(8)});
  });
  await page.goto("/");
  await page.getByRole("textbox",{name:"Search",exact:true}).fill("UKG in SF");
  await page.getByRole("button",{name:"Search",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>(window as unknown as {posterTiming:{usable:number}}).posterTiming.usable)).toBeGreaterThan(0);
  const timing=await page.evaluate(()=>(window as unknown as {posterTiming:{received:number;usable:number;gaps:number[]}}).posterTiming);
  expect(timing.usable-timing.received).toBeLessThan(1000);
  const metrics=JSON.stringify({responseToUsableMs:timing.usable-timing.received,frames:timing.gaps.length,maxFrameGapMs:Math.max(...timing.gaps)});
  await writeFile(info.outputPath("presentation-timing.json"),metrics);
  await info.attach("presentation-timing",{body:metrics,contentType:"application/json"});
});
