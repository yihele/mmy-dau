#!/usr/bin/env python3
# 云端定时任务：把临时通道里的打卡记录搬进 Gitee 仓库，只留最近 30 天
import os, json, base64, urllib.request, urllib.parse, datetime, sys

TOKEN = os.environ.get("GITEE_TOKEN", "").strip()
OWNER = os.environ.get("GITEE_OWNER", "yihele")
REPO = os.environ.get("GITEE_REPO", "mmy")
BR = os.environ.get("GITEE_BRANCH", "master")
FEED = os.environ.get("DAU_FEED", "https://ntfy.sh/mmy-dau-7k2p9x4t/json?poll=1")
KEEP = int(os.environ.get("DAU_KEEP_DAYS", "30"))

API = "https://gitee.com/api/v5/repos/%s/%s/contents/" % (OWNER, REPO)
TZ = datetime.timezone(datetime.timedelta(hours=8))


def api_get(path):
    url = API + urllib.parse.quote(path) + "?access_token=" + TOKEN + "&ref=" + BR
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def api_put(path, text, sha):
    body = {"access_token": TOKEN,
            "content": base64.b64encode(text.encode("utf-8")).decode(),
            "message": "打卡明细 " + path, "branch": BR}
    method = "PUT"
    if sha:
        body["sha"] = sha
    else:
        method = "POST"
    req = urllib.request.Request(API + urllib.parse.quote(path), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "User-Agent": "mmy-dau"}, method=method)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status


def api_del(path, sha):
    body = {"access_token": TOKEN, "message": "清理 30 天前的打卡明细", "sha": sha, "branch": BR}
    req = urllib.request.Request(API + urllib.parse.quote(path), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "User-Agent": "mmy-dau"}, method="DELETE")
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status


def main():
    if not TOKEN:
        print("缺 GITEE_TOKEN")
        return 1
    raw = urllib.request.urlopen(FEED, timeout=25).read().decode("utf-8", "ignore")
    msgs = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if o.get("event") == "message" and o.get("message"):
            msgs.append(o)
    print("拉到消息 %d 条" % len(msgs))
    if not msgs:
        return 0

    groups = {}
    for o in msgs:
        d = datetime.datetime.fromtimestamp(o["time"], TZ)
        groups.setdefault(d.strftime("%Y-%m-%d"), []).append(str(o["message"]).strip())

    for day, lines in sorted(groups.items()):
        path = "dau/%s.txt" % day
        info = api_get(path)
        old, sha = "", None
        if isinstance(info, dict) and info.get("content"):
            old = base64.b64decode(info["content"]).decode("utf-8", "ignore")
            sha = info.get("sha")
        merged, added = old, 0
        for ln in lines:
            if ln and ln not in merged:
                merged = (merged + "\n" + ln) if merged else ln
                added += 1
        if not added:
            print("%s 无新增" % day)
            continue
        try:
            print("%s 写入 %d 条 → HTTP %s" % (day, added, api_put(path, merged, sha)))
        except Exception as e:
            print("%s 写入失败 %s" % (day, e))

    info = api_get("dau")
    if isinstance(info, list):
        now = datetime.datetime.now(TZ)
        for it in info:
            nm = it.get("name", "")
            if not nm.endswith(".txt"):
                continue
            try:
                d = datetime.datetime.strptime(nm[:10], "%Y-%m-%d").replace(tzinfo=TZ)
            except Exception:
                continue
            if (now - d).days > KEEP:
                try:
                    print("删除过期 %s → HTTP %s" % (nm, api_del(it["path"], it["sha"])))
                except Exception as e:
                    print("删除失败 %s %s" % (nm, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
