import os,json,time,threading,random,urllib.request as U,urllib.parse as P,re
from engine_client import EngineClient
from gateway import register_gateway
import socket
socket.setdefaulttimeout(30)
from datetime import datetime,timedelta,timezone

# 固定北京时间，避免容器默认 UTC 导致计划晚 8 小时执行。
APP_TZ=timezone(timedelta(hours=8))
os.environ["TZ"]="CST-8"
if hasattr(time,"tzset"): time.tzset()
from collections import deque
from flask import Flask, request, Response, jsonify

engine=EngineClient()
MDL=engine.base_url
DATA=os.environ.get("HUB_DATA_DIR",os.environ.get("DATA","/data/tasks")); JD=os.path.join(DATA,"jobs"); os.makedirs(JD,exist_ok=True)
SCF=os.path.join(DATA,"schedule.json")
CATS=[("华语经典","华语经典"),("欧美","欧美经典"),("日语","日语经典"),("韩语KPOP","韩语 KPOP"),("粤语","粤语 经典"),("古风","古风"),("民谣","民谣"),("R&B","R&B"),("说唱","说唱"),("电子","电子"),("动漫OST","动漫 OST"),("影视金曲","影视金曲"),("摇滚","摇滚"),("爵士","爵士"),("轻音乐钢琴","轻音乐"),("怀旧金曲","怀旧 金曲"),("流行","流行 热门"),("情歌","情歌")]
KWMAP=dict(CATS)
LIVE=re.compile(r"(伴奏|纯音乐|翻唱|cover|remix|dj版|ktv|capella|二胡|古筝|钢琴|口琴|萨克斯|长笛|版本|女声版|男声版|对唱版|加速|慢速|3d)",re.I)
DJN=re.compile(r"(dj|remix|mashup|串烧|prog\s?house|抖音版|加速版|加快版)",re.I)
def skip_reason(name,artist,album):
    if any(DJN.search(v) for v in (name,artist,album)):
        return "DJ/混音"
    if LIVE.search(name) or LIVE.search(album):
        return "非原唱"
    return ""
def load_cookie():
    # Cookie 由下载引擎统一维护；任务层通过内部接口读取，避免跨容器直接操作数据库。
    return engine.netease_cookie()

NHD={"Referer":"https://music.163.com/","User-Agent":"Mozilla/5.0"}
lock=threading.RLock(); JOBS=[]; SEEN=set()
SF=os.path.join(DATA,"seen.txt")
if os.path.exists(SF): SEEN=set(x.strip() for x in open(SF) if x.strip())
CACHE={}
DONEF=os.path.join(DATA,"done_pl.txt")
DONE=set(x.strip() for x in open(DONEF)) if os.path.exists(DONEF) else set()
def dsafe():
    try:
        with open(DONEF,"w",encoding="utf-8") as f: f.write("\n".join(list(DONE)[-800:]))
    except Exception: pass
def done_reset():
    DONE.clear(); dsafe()
def jload():
    global JOBS
    p=os.path.join(DATA,"jobs.json")
    if os.path.exists(p):
        try: JOBS=json.load(open(p,encoding="utf-8"))
        except Exception: JOBS=[]
    for j in JOBS:
        if j.get("status") in ("running","queued"):
            j.update(status="interrupted", active={}, stage="进程重启，任务中断", finished=time.strftime("%F %T"))
jload()
def jsave():
    with lock:
        tmp=os.path.join(DATA,"jobs.json.tmp")
        with open(tmp,"w",encoding="utf-8") as f: json.dump(JOBS[-200:],f,ensure_ascii=False)
        os.replace(tmp,os.path.join(DATA,"jobs.json"))
def jlog(j,msg):
    with lock: j["updated"]=time.strftime("%F %T")
    try:
        with open(os.path.join(JD,str(j["id"])+".log"),"a",encoding="utf-8") as f: f.write(time.strftime("%H:%M:%S")+" "+msg+"\n")
    except Exception: pass
def persist(sid):
    with open(SF,"a") as f: f.write(sid+"\n")
def ng(url,tries=6):
    last=None
    for i in range(tries):
        try:
            return json.loads(U.urlopen(U.Request(url,headers={**NHD,"Cookie":load_cookie()}),timeout=25).read().decode("utf-8","replace")),None
        except U.error.HTTPError as e:
            last="HTTP %s"%e.code; time.sleep(15*(i+1) if e.code==405 else 2*(i+1))
        except Exception as e:
            last=repr(e)[:50]; time.sleep(2*(i+1))
    return None,last
def npost(url,data,tries=4):
    last=None
    for i in range(tries):
        try: return json.loads(U.urlopen(U.Request(url,data=P.urlencode(data).encode(),headers={**NHD,"Cookie":load_cookie(),"Content-Type":"application/x-www-form-urlencoded"}),timeout=30).read().decode("utf-8","replace")),None
        except Exception as e: last=repr(e)[:50]; time.sleep(2*(i+1))
    return None,last
def search_pl(kw,job,n=40):
    now=time.time(); cc=CACHE.get(kw)
    if cc and now-cc[0]<1200: return cc[1]
    jlog(job,"[INFO] 拉取歌单池 %s"%kw)
    o,err=ng("https://music.163.com/api/search/get/web?"+P.urlencode({"s":kw,"type":1000,"offset":0,"limit":n}))
    pool=[]
    if o:
        for p in ((o.get("result") or {}).get("playlists") or []):
            if (p.get("trackCount") or 0)>=10: pool.append((str(p["id"]),p.get("name"),p.get("trackCount")))
        pool=pool[:n]
        if pool: CACHE[kw]=(now,pool)
    else: jlog(job,"[WARN] 搜索受限(%s)"%(err or "empty"))
    return pool
def pl_ids(pid):
    o,err=ng("https://music.163.com/api/v3/playlist/detail?id="+str(pid))
    return [str(t["id"]) for t in (o or {}).get("playlist",{}).get("trackIds",[])] if o else []
def detail(ids):
    out=[]
    for b in range(0,len(ids),200):
        o,err=npost("https://music.163.com/api/song/detail",{"ids":json.dumps(ids[b:b+200])})
        if o: out+=o.get("songs",[])
    return out
def mdl_login(): return None  # 内部服务令牌代替管理员密码登录。
def hdr(session=None): return engine.headers()
def reached(job):
    t=job.get("target",0)
    return (t and job["saved"]>=t) or job["stop"]
def dl_target_hit(job):
    t=job.get("target",0); return job["stop"] or (t and job["saved"]>=t)
def _download_one(job,song,H):
    sid=str(song.get("id"))
    with lock:
        if sid in SEEN: job["skip"]+=1; return
        if dl_target_hit(job): return
        job["att"]+=1
    nm=song.get("name",""); ar="/".join(a.get("name","") for a in (song.get("ar") or song.get("artists") or [])); al=(song.get("al") or song.get("album") or {}).get("name","")
    reason=skip_reason(nm,ar,al)
    if reason:
        with lock: job["skip"]+=1; SEEN.add(sid)
        persist(sid); jlog(job,"[SKIP] %s: %s - %s"%(reason,ar,nm)); return
    q=P.urlencode({"id":sid,"source":"netease","name":nm,"artist":ar,"album":al,"save_local":"1"})
    for i in range(4):
        with lock:
            item=job.get("active",{}).get(str(threading.get_ident()))
            if item is not None: item["attempt"]=i+1
        with lock: hit=dl_target_hit(job)
        if hit: return
        time.sleep(random.uniform(1.0,1.8))
        try:
            res=json.loads(U.urlopen(U.Request(MDL+"/music/download?"+q,data=b"",headers=H,method="POST"),timeout=75).read().decode("utf-8","replace"))
            kind="skip" if res.get("skipped") else ("save" if (res.get("saved") or res.get("status")=="ok") else "badr")
            with lock:
                if kind=="skip": job["skip"]+=1; SEEN.add(sid)
                elif kind=="save": job["saved"]+=1; SEEN.add(sid)
                else: job["fail"]+=1
            if kind=="skip": persist(sid)
            elif kind=="save": persist(sid); jlog(job,"[OK] %s - %s"%(ar,nm))
            elif kind=="badr": jlog(job,"[FAIL?] %s - %s"%(ar,nm))
            return
        except Exception as e:
            if i==3:
                with lock: job["fail"]+=1
                jlog(job,"[FAIL] %s - %s %s"%(ar,nm,repr(e)[:40]))
            else:
                jlog(job,"[WARN] 重试 %s - %s (%d/4)"%(ar,nm,i+2))
                time.sleep(2*(i+1))

def download_one(job,song,H):
    """记录每个工作线程正在处理的歌曲；结束后一定清理运行状态。"""
    key=str(threading.get_ident())
    with lock:
        if dl_target_hit(job): return
        job.setdefault("active",{})[key]={
            "id":str(song.get("id")), "name":song.get("name",""),
            "artist":"/".join(a.get("name","") for a in (song.get("ar") or song.get("artists") or [])),
            "since":time.time(), "attempt":1}
    try:
        _download_one(job,song,H)
    except Exception:
        with lock: job["fail"]+=1
        jlog(job,"[FAIL] 歌曲处理异常，请检查下载服务和存储权限")
    finally:
        with lock:
            job["active"].pop(key,None)
            job["processed"]=job.get("processed",0)+1
            job["updated"]=time.strftime("%F %T")
        jsave()

def set_stage(job,stage,**fields):
    with lock: job.update(stage=stage,updated=time.strftime("%F %T"),**fields)
    jsave()

def run_job(job):
    set_stage(job,"登录下载服务",status="running",started=time.strftime("%F %T"),active={})
    try:
        engine.check_storage()
        H=hdr(mdl_login())
        need=max(1,int(job["per"])); todo=[]
        for c in job["cats"]:
            if job["stop"]: break
            set_stage(job,"搜索歌单",cur="搜索："+c)
            pool=search_pl(KWMAP.get(c,c),job)
            fresh=[x for x in pool if x[0] not in DONE]
            if len(fresh)<need: done_reset(); fresh=pool
            random.shuffle(fresh); todo.extend((c,x) for x in fresh[:need])
        set_stage(job,"准备下载",playlist_total=len(todo),playlist_index=0)
        if not todo:
            with lock: job["status"]="stopped" if job["stop"] else "noresult"
            jlog(job,"[WARN] 已停止" if job["stop"] else "[WARN] 无可用歌单（可能限流）")
            return
        jlog(job,"[INFO] 计划%d张歌单，目标%s首"%(len(todo),job.get("target") or "不限"))
        from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
        # 限制待处理队列，避免一次塞入大量歌曲导致停止后长时间排空。
        with ThreadPoolExecutor(max_workers=job["workers"]) as ex:
            pending=set()
            for i,(c,(pid,pname,tc)) in enumerate(todo):
                with lock:
                    if dl_target_hit(job): break
                set_stage(job,"读取歌单",cur="歌单 %s/%s [%s]"%(i+1,len(todo),c),
                          playlist_index=i+1,playlist_name=pname,playlist_category=c,playlist_tracks=tc)
                jlog(job,"[INFO] >>> [%s] %s %s首"%(c,pname,tc))
                DONE.add(pid); dsafe()
                ids=pl_ids(pid)
                with lock: owned=sum(1 for x in ids if x in SEEN)
                if len(ids)>=20 and owned*100//len(ids)>=85:
                    jlog(job,"[SKIP] 已拥有%d%% 跳过 %s"%(owned*100//len(ids),pname))
                    continue
                set_stage(job,"读取歌曲信息")
                songs=detail(ids)
                set_stage(job,"下载歌曲",playlist_tracks=len(songs))
                for song in songs:
                    while len(pending)>=job["workers"]*2:
                        _,pending=wait(pending,timeout=1,return_when=FIRST_COMPLETED)
                        if dl_target_hit(job): break
                    with lock:
                        if dl_target_hit(job): break
                        job["submitted"]=job.get("submitted",0)+1
                    pending.add(ex.submit(download_one,job,song,H))
                # 当前歌单处理结束后再切换，详情中的歌单与正在下载的歌曲保持对应。
                while pending:
                    _,pending=wait(pending,timeout=1,return_when=FIRST_COMPLETED)
            set_stage(job,"等待下载结束")
        with lock: job["status"]="stopped" if job["stop"] else "done"
        jlog(job,"[INFO] 完成 新增%d 跳过%d 失败%d"%(job["saved"],job["skip"],job["fail"]))
    except Exception as error:
        # 不把可能含 URL、Cookie 等内容的底层异常直接暴露到页面。
        with lock: job.update(status="error",error="任务异常："+type(error).__name__+"，请检查网络、下载服务和存储权限")
        jlog(job,"[FAIL] "+job["error"])
    finally:
        with lock:
            job.update(active={},finished=time.strftime("%F %T"),updated=time.strftime("%F %T"),
                       stage={"done":"已完成","stopped":"已停止","noresult":"无可用歌单","error":"执行失败"}.get(job["status"],"已结束"))
            job["cur"]=job["stage"]
        jsave()

# ---- schedule ----
def compute_next(s,after=None):
    now=after or datetime.now(APP_TZ); h=s.get("hour",3); m=s.get("minute",0)
    if s.get("freq")=="weekly":
        wd=s.get("weekday",0); cand=now.replace(hour=h,minute=m,second=0,microsecond=0)
        cand+=timedelta(days=(wd-now.weekday())%7)
        if cand<=now: cand+=timedelta(days=7)
    elif s.get("freq")=="monthly":
        day=min(s.get("day",1),28); cand=now.replace(day=day,hour=h,minute=m,second=0,microsecond=0)
        if cand<=now:
            nm=now.month%12+1; y=now.year+(1 if nm==1 else 0); cand=cand.replace(year=y,month=nm)
    else:
        cand=now.replace(hour=h,minute=m,second=0,microsecond=0)
        if cand<=now: cand+=timedelta(days=1)
    return cand.timestamp()
def load_sched():
    d={"enabled":False,"freq":"daily","hour":3,"minute":0,"weekday":0,"day":1,
       "target":200,"cats":[],"per":6,"workers":2,"next":0,"last":0,
       "mode":"rotate","rotation_index":0,"clock_timezone":"Asia/Shanghai"}
    with lock:
        try:
            with open(SCF,encoding="utf-8") as f: raw=json.load(f)
        except (OSError,ValueError): raw={}
        d.update(raw)
        if raw and raw.get("clock_timezone")!="Asia/Shanghai":
            d["clock_timezone"]="Asia/Shanghai"
            d["next"]=compute_next(d)
            save_sched(d)
    return d

def save_sched(s):
    with lock:
        tmp=SCF+".tmp"
        with open(tmp,"w",encoding="utf-8") as f: json.dump(s,f,ensure_ascii=False)
        os.replace(tmp,SCF)

def selected_schedule_cats(s,index=None):
    cats=s.get("cats",[])
    if not cats: return []
    if s.get("mode","rotate")=="all": return list(cats)
    i=s.get("rotation_index",0) if index is None else index
    return [cats[int(i)%len(cats)]]

def schedule_view(s):
    view=dict(s)
    view["next_str"]=datetime.fromtimestamp(s["next"],APP_TZ).strftime("%m-%d %H:%M") if s.get("next") else ""
    view["next_cats"]=selected_schedule_cats(s)
    view["rotation_order"]=list(s.get("cats",[]))
    preview=[];stamp=s.get("next",0);index=int(s.get("rotation_index",0))
    for _ in range(min(6,max(1,len(s.get("cats",[]))))):
        if not stamp or not s.get("cats"): break
        preview.append({"time":datetime.fromtimestamp(stamp,APP_TZ).strftime("%m-%d %H:%M"),
                        "cats":selected_schedule_cats(s,index)})
        index+=1
        stamp=compute_next(s,datetime.fromtimestamp(stamp,APP_TZ))
    view["preview"]=preview
    return view

def job_options(d,defaults=None):
    values=dict(defaults or {})
    values.update({k:d[k] for k in ("cats","per","workers","target") if k in d})
    cats=values.get("cats",[])
    if not isinstance(cats,list) or any(not isinstance(c,str) or c not in KWMAP for c in cats):
        raise ValueError("请选择有效的音乐类型")
    values["cats"]=list(dict.fromkeys(cats))
    for key,default,lo,hi in (("per",6,1,40),("workers",2,1,4),("target",0,0,100000)):
        raw=values.get(key,default)
        if isinstance(raw,bool) or not isinstance(raw,int) or not lo<=raw<=hi:
            raise ValueError({"per":"每类歌单须为 1～40","workers":"并发须为 1～4","target":"下载目标须为 0～100000，0 表示不限"}[key])
        values[key]=raw
    return {k:values[k] for k in ("cats","per","workers","target")}

def make_job(cats,per,workers,target,tag):
    with lock:
        job_id=max(int(time.time()*1000),max((j["id"] for j in JOBS),default=0)+1)
        job={"id":job_id,"cats":list(cats),"per":per,"workers":workers,"target":target,"tag":tag,"status":"queued","saved":0,"skip":0,"fail":0,"att":0,"cur":"排队中","stop":False,"created":time.strftime("%F %T"),"active":{},"submitted":0,"processed":0,"stage":"排队中"}
        JOBS.append(job)
    jsave(); jlog(job,"[INFO] 入队[%s] 类型=%s 目标=%s"%(tag,"/".join(cats),target or "不限"))
    threading.Thread(target=run_job,args=(job,),daemon=True).start(); return job
def is_running():
    with lock: return any(j["status"] in ("running","queued") for j in JOBS)
def scheduler_tick(now=None):
    # 与页面保存共用锁，避免保存时覆盖已推进的轮换位置。
    with lock:
        s=load_sched()
        now=time.time() if now is None else now
        if not (s.get("enabled") and s.get("cats") and s.get("next") and
                now>=s["next"] and not is_running()):
            return None
        cats=selected_schedule_cats(s)
        job=make_job(cats,s.get("per",6),s.get("workers",2),int(s.get("target",200)),"定时")
        s["last"]=now
        if s.get("mode","rotate")=="rotate":
            s["rotation_index"]=(int(s.get("rotation_index",0))+1)%len(s["cats"])
        s["next"]=compute_next(s,datetime.fromtimestamp(now,APP_TZ))
        save_sched(s)
        return job

def scheduler():
    while True:
        try: scheduler_tick()
        except Exception: pass
        time.sleep(30)
if os.environ.get("HUB_TESTING",os.environ.get("MUSIC_WEBUI_TESTING"))!="1": threading.Thread(target=scheduler,daemon=True).start()
_WD={"sig":None,"ts":0.0}
def watchdog():
    while True:
        try:
            now=time.time()
            with lock:
                run=[j for j in JOBS if j["status"]=="running"]
                if run:
                    j=run[0]; sig=(j["saved"],j["skip"],j["fail"],j["att"])
                    if _WD["sig"]!=sig: _WD["sig"]=sig; _WD["ts"]=now
                    elif now-_WD["ts"]>900 and not j["stop"]:
                        j["stop"]=True; _WD["ts"]=now
                        try: jlog(j,"[WARN] 停滞超15分钟，自动停止该任务")
                        except Exception: pass
                else:
                    _WD["sig"]=None; _WD["ts"]=now
        except Exception: pass
        time.sleep(30)
if os.environ.get("HUB_TESTING",os.environ.get("MUSIC_WEBUI_TESTING"))!="1": threading.Thread(target=watchdog,daemon=True).start()
app=Flask(__name__)
register_gateway(app,engine)
from hub_features import register_features
register_features(app,engine)
_p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"templates","index.html")
PAGE=open(_p,encoding="utf-8").read() if os.path.exists(_p) else "no page"
@app.route("/")
def home(): return Response(PAGE, mimetype="text/html")
@app.route("/api/jobs")
def api_jobs():
    with lock: arr=[{k:j.get(k) for k in ("id","cats","status","saved","skip","fail","att","cur","target","tag","started","finished","created")} for j in JOBS]
    return jsonify(jobs=list(reversed(arr)))
@app.route("/api/jobs/<int:job_id>")
def job_detail(job_id):
    with lock:
        job=next((j for j in JOBS if j["id"]==job_id),None)
        if job is None: return jsonify(error="任务不存在"),404
        result=json.loads(json.dumps(job))
    # 兼容旧任务：缺少的新指标显示为未知，而不是伪造为 0。
    result["active"]=list(result.get("active",{}).values()) if result.get("status")=="running" else []
    for item in result["active"]: item["elapsed"]=max(0,int(time.time()-item["since"]))
    result["elapsed"]=None
    if result.get("started"):
        try:
            a=datetime.strptime(result["started"],"%Y-%m-%d %H:%M:%S")
            b=datetime.strptime(result["finished"],"%Y-%m-%d %H:%M:%S") if result.get("finished") else datetime.now(APP_TZ).replace(tzinfo=None)
            result["elapsed"]=max(0,int((b-a).total_seconds()))
        except ValueError: pass
    if "submitted" in result:
        result["queued"]=max(0,result["submitted"]-result.get("processed",0)-len(result["active"]))
    return jsonify(job=result)

@app.route("/api/log")
def api_log():
    jid=request.args.get("job","")
    if not jid:
        with lock: act=[j for j in JOBS if j.get("status")=="running"] or JOBS[-1:]
        jid=str(act[-1]["id"]) if act else ""
    if jid and not str(jid).isdigit(): return jsonify(error="无效任务编号"),400
    path=os.path.join(JD,str(jid)+".log")
    lines=[]
    if os.path.exists(path):
        with open(path,encoding="utf-8") as f: lines=[x.rstrip("\n") for x in deque(f,maxlen=300)]
    return jsonify(job=jid,lines=lines)
@app.route("/api/start",methods=["POST"])
def start():
    try:
        d=request.get_json(silent=True)
        if not isinstance(d,dict): raise ValueError("请求格式错误")
        options=job_options(d)
        if not options["cats"]: raise ValueError("请先勾选类型")
    except ValueError as error: return jsonify(ok=False,msg=str(error)),400
    with lock:
        if is_running(): return jsonify(ok=False,msg="running"),409
        job=make_job(**options,tag="手动")
    return jsonify(ok=True,id=job["id"])

@app.route("/api/jobs/<int:job_id>",methods=["PATCH"])
def edit_running_job(job_id):
    d=request.get_json(silent=True)
    if not isinstance(d,dict) or set(d)!={"target"}:
        return jsonify(ok=False,msg="运行中仅支持修改下载目标；类型和并发请载入参数后重新运行"),400
    try: target=job_options({"target":d["target"]})["target"]
    except ValueError as error: return jsonify(ok=False,msg=str(error)),400
    with lock:
        job=next((j for j in JOBS if j["id"]==job_id),None)
        if job is None: return jsonify(ok=False,msg="任务不存在"),404
        if job["status"] not in ("running","queued") or job.get("stop"):
            return jsonify(ok=False,msg="任务已结束或正在停止，请载入参数后重新运行"),409
        previous=job.get("target",0);job["target"]=target
        jlog(job,"[INFO] 修改下载目标 %s → %s"%(previous or "不限",target or "不限"))
        jsave()
    return jsonify(ok=True,msg="下载目标已更新")

@app.route("/api/stop",methods=["POST"])
def stop():
    with lock:
        for j in JOBS:
            if j["status"]=="running": j["stop"]=True; jlog(j,"[INFO] 收到停止")
    return jsonify(ok=True)
@app.route("/api/schedule")
def get_sched(): return jsonify(schedule=schedule_view(load_sched()))

@app.route("/api/schedule",methods=["POST"])
def post_sched():
    d=request.get_json(silent=True)
    if not isinstance(d,dict): return jsonify(ok=False,msg="请求格式错误"),400
    with lock:
        s=load_sched()
        try:
            options=job_options(d,s)
            freq=d.get("freq",s["freq"]);mode=d.get("mode",s.get("mode","rotate"))
            if freq not in ("daily","weekly","monthly"): raise ValueError("频率无效")
            if mode not in ("rotate","all"): raise ValueError("轮换模式无效")
            enabled=d.get("enabled",s["enabled"])
            if not isinstance(enabled,bool): raise ValueError("启用状态无效")
            if enabled and not options["cats"]: raise ValueError("启用定时需先勾选类型")
            weekday=d.get("weekday",s["weekday"]);day=d.get("day",s["day"])
            if type(weekday) is not int or not 0<=weekday<=6: raise ValueError("星期无效")
            if type(day) is not int or not 1<=day<=28: raise ValueError("每月日期须为 1～28")
            hour,minute=s["hour"],s["minute"]
            if "time" in d:
                match=re.fullmatch(r"([01]?[0-9]|2[0-3]):([0-5][0-9])",str(d["time"]))
                if not match: raise ValueError("时间格式须为 HH:MM")
                hour,minute=map(int,match.groups())
            next_cats=selected_schedule_cats(s)
            old_next=next_cats[0] if next_cats else None
            index=options["cats"].index(old_next) if old_next in options["cats"] else 0
            if d.get("reset_rotation") is True: index=0
            s.update(options,enabled=enabled,freq=freq,mode=mode,weekday=weekday,day=day,
                     hour=hour,minute=minute,rotation_index=index,clock_timezone="Asia/Shanghai")
            s["next"]=compute_next(s)
            save_sched(s)
        except (ValueError,TypeError) as error: return jsonify(ok=False,msg=str(error)),400
    return jsonify(ok=True,schedule=schedule_view(s))

@app.route("/api/status")
def status():
    with lock:
        run=[j for j in JOBS if j["status"]=="running"]
        cur=run[0] if run else (JOBS[-1] if JOBS else None)
    if not cur: return jsonify(running=False,saved=0,skip=0,fail=0,att=0,cur="空闲",job=None,status="空闲")
    return jsonify(running=cur["status"]=="running",saved=cur.get("saved",0),skip=cur.get("skip",0),fail=cur.get("fail",0),att=cur.get("att",0),cur=cur.get("cur",""),job=cur["id"],status=cur["status"])
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("HUB_PORT","8000")),threaded=True)
