const fs=require("fs"),vm=require("vm"),assert=require("assert");
const nodes={};
function element(){return {innerHTML:"",textContent:"",style:{},dataset:{},value:"",classList:{toggle(){}},appendChild(){},scrollIntoView(){},querySelectorAll(){return []},scrollTop:0,clientHeight:360,scrollHeight:360}}
const get=id=>nodes[id]||(nodes[id]=element());
const jobs=[{id:2,status:"running",cats:["流行"],saved:1,skip:0,fail:0,att:1},{id:1,status:"done",cats:["欧美"],saved:5,skip:0,fail:0,att:5}];
const context={document:{getElementById:get,createElement:element},setTimeout(){},alert(){},console,
fetch:async path=>({json:async()=>{
 if(path==="/api/jobs")return {jobs};
 if(path==="/api/schedule")return {schedule:{}};
 if(path.startsWith("/api/log"))return {job:1,lines:["[OK] test"]};
 if(path.startsWith("/api/jobs/")){const j=jobs.find(x=>x.id===+path.split("/").pop());return {job:{...j,active:[],elapsed:60}}}
 throw Error(path);
}})};
["saved","skip","fail","att","cur","en","freq","tm","wd","dy","tgt","per","w","nxt","wdWrap","dyWrap"].forEach(id=>context[id]=get(id));
vm.createContext(context);
const html=fs.readFileSync("templates/index.html","utf8");
vm.runInContext(html.match(/<script>([\s\S]*)<\/script>/)[1],context);
(async()=>{
 await new Promise(r=>setImmediate(r));
 vm.runInContext("pick(1)",context);
 await new Promise(r=>setImmediate(r));
 await vm.runInContext("tick()",context);
 assert.equal(vm.runInContext("selJob",context),1,"历史选择不可被运行中任务覆盖");
 assert.match(get("detailTitle").innerHTML,/#1/);
 assert.equal(get("saved").textContent,5);
 assert.match(get("detailBody").innerHTML,/旧版任务/);
 const safe=vm.runInContext('esc("<script>alert(1)</script>")',context);
 assert(!safe.includes("<script>"));
 vm.runInContext("followLatest()",context);
 await new Promise(r=>setImmediate(r));
 assert.equal(vm.runInContext("selJob",context),2);
 vm.runInContext('selectCats(["粤语","流行","欧美"])',context);
 assert.equal(JSON.stringify(vm.runInContext("sel()",context)),JSON.stringify(["粤语","流行","欧美"]));
 vm.runInContext("copyJob()",context);
 assert.equal(JSON.stringify(vm.runInContext("sel()",context)),JSON.stringify(["流行"]));
 assert.match(get("editHint").textContent,/#2/);
 assert.equal(get("runtimeEdit").style.display,"");
 console.log("PASS: history selection, details, escaping, category order, copy task, runtime editing");
})().catch(e=>{console.error(e);process.exitCode=1});
