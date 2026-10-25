"""
Mock ITSM 服务 —— 为 itsm-rpa-demo 提供可本地运行的假系统。

它同时提供:
  1) 登录页 (含验证码图片, 配合 ddddocr 演示; 校验只认账号/密码, 忽略验证码值)
  2) 工单列表 / 文件列表 / 反馈列表 三个 JSON 接口 (RPA 走 page.request 调用)
  3) 工单表单 HTML 页 (含"处理跟踪"表格 + "需求描述" + 提交按钮 + 提交弹窗 iframe)
  4) 提交动作 doSubmit (标记工单已分派, 下次列表不再返回, 演示可见"工单被处理")

启动:  uvicorn mock_itsm.app:app --port 8000
       或  python -m mock_itsm.app
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

app = FastAPI(title="Mock ITSM for RPA demo")

# ---------------- 演示账号 (与 rpa-data/config.ini 中 user/pwd 对应) ----------------
DEMO_USER = "demo"
DEMO_PWD = "demo123"
AUTH_COOKIE = "itsm_mock_token"

# ---------------- 人员/部门字典 (供提交弹窗渲染) ----------------
DEPARTMENTS: List[str] = [
    "技术支持中心", "账号权限组", "故障处理组", "一线值班组",
    "信息安全中心", "安全运营组",
    "共享服务中心", "财务结算组",
]
USERS: List[str] = [
    "张伟", "李娜", "王强", "刘洋", "陈静", "杨帆", "赵磊", "孙悦", "周涛", "吴敏",
]

# 处理跟踪表头 (顺序必须与 TrackTrace 的中文别名一致)
TRACK_HEADER = ["状态", "操作", "环节名称", "环节处理组/人", "所属行政部门",
                "开始时间", "完成时间", "处理意见", "环节附件"]

_now = lambda: datetime.now().strftime("%Y-%m-%d %H:%M")


def _tr(step: str, dept: str, group: str, opinion: str) -> List[str]:
    """构造一行处理跟踪记录(补齐固定列)。"""
    return ["处理中", "提交", step, group, dept, _now(), "", opinion, ""]


# ---------------- 工单数据 (内存态) ----------------
# 每条: task_info_id / business_key / title / desc / dispatched / track(rows) / files / feeds
def _build_tickets() -> Dict[str, Dict[str, Any]]:
    """构造初始工单数据。供首次加载与 /reset 一键复位复用(时间戳按当前刷新)。"""
    return {
    "TI-1001": dict(
        business_key="TK20251001001", title="权限申请-报表系统查看权限",
        desc="申请开通报表系统查看权限，详见附件权限申请清单。", dispatched=False,
        track=[_tr("提交申请", "技术支持中心", "申请人", "提交权限申请")],
        files=[("权限申请.xlsx", "xlsx"), ("现场截图.png", "png")],
        feeds=["已收到工单，等待处理。"],
    ),
    "TI-1002": dict(
        business_key="TK20251001002", title="密码重置申请",
        desc="员工忘记系统登录密码，申请密码重置。", dispatched=False,
        track=[_tr("一线受理", "技术支持中心", "一线值班组", "已核实身份")],
        files=[],
        feeds=["已联系用户核实身份。"],
    ),
    "TI-1003": dict(
        business_key="TK20251001003", title="疑似账号被盗安全事件",
        desc="收到安全事件报告：疑似账号异地登录，存在可疑行为。", dispatched=False,
        track=[_tr("受理", "信息安全中心", "安全运营组", "初步排查")],
        files=[],
        feeds=["监控发现可疑登录告警，请尽快处置。"],
    ),
    "TI-1004": dict(
        business_key="TK20251001004", title="服务器磁盘故障报修",
        desc="核心服务器磁盘故障，需要尽快修复。", dispatched=False,
        track=[_tr("待分派", "技术支持中心", "故障处理组", "等待分派")],
        files=[],
        feeds=["监控告警：磁盘使用率 98%。"],
    ),
    "TI-1005": dict(
        business_key="TK20251001005", title="楼层网络打印机故障",
        desc="3 楼网络打印机故障，无法打印。", dispatched=False,
        track=[_tr("待分派", "技术支持中心", "一线值班组", "等待分派")],
        files=[],
        feeds=["多名用户反馈打印异常。"],
    ),
    "TI-1006": dict(
        business_key="TK20251001006", title="ITSM 使用方法咨询",
        desc="咨询 ITSM 系统工单如何填写。", dispatched=False,
        track=[_tr("受理", "技术支持中心", "一线值班组", "解答使用问题")],
        files=[],
        feeds=["属于使用咨询，无需派单。"],
    ),
    }


TICKETS: Dict[str, Dict[str, Any]] = _build_tickets()


def _authed(request: Request) -> bool:
    return request.cookies.get(AUTH_COOKIE) == "ok"


# ---------------- 登录 ----------------
@app.get("/itsm/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_HTML


@app.post("/itsm/login")
def login_submit(staffId: str = Form(""), staffPwd: str = Form(""), validCode: str = Form("")):
    # 演示环境: 只校验账号密码, 忽略验证码值(验证码仅用于演示 OCR 采集流程)
    if staffId == DEMO_USER and staffPwd == DEMO_PWD:
        resp = RedirectResponse(url="/itsm/index", status_code=302)
        resp.set_cookie(AUTH_COOKIE, "ok")
        return resp
    return HTMLResponse(LOGIN_HTML.replace("<!--PROMPT-->",
                     '<div id="loginPrompt">用户名或密码错误</div>'))


@app.get("/itsm/captcha.png")
def captcha():
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (100, 40), "white")
        d = ImageDraw.Draw(img)
        d.text((18, 10), "D3M0", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png")
    except Exception:
        return Response(_FALLBACK_PNG, media_type="image/png")


@app.get("/itsm/index", response_class=HTMLResponse)
def index(request: Request):
    if not _authed(request):
        return RedirectResponse(url="/itsm/login", status_code=302)
    pending = sum(1 for t in TICKETS.values() if not t["dispatched"])
    return f"""<html><head><meta charset="utf-8"><title>ITSM 工作台</title></head>
    <body style="font-family:sans-serif;padding:24px">
      <h2>ITSM 工作台 (Mock)</h2>
      <p>已登录。当前待分派工单：<b id="pending">{pending}</b> 条</p>
      <button id="resetBtn" style="padding:8px 18px;background:#2d8cf0;color:#fff;border:0;border-radius:4px;cursor:pointer">重置演示</button>
      <span id="resetStatus" style="color:#19be6b;margin-left:8px"></span>
      <script>
      document.getElementById('resetBtn').addEventListener('click',async()=>{{
        const r=await fetch('/itsm/admin/reset',{{method:'POST'}});
        const j=await r.json();
        document.getElementById('pending').textContent=j.pending;
        document.getElementById('resetStatus').textContent='已重置为 '+j.pending+' 条待分派工单';
      }});
      </script>
    </body></html>"""


# ---------------- JSON 接口 (RPA 通过 page.request 调用) ----------------
@app.get("/itsm/admin/Workindex/worklistGro")
@app.get("/itsm/admin/Workindex/worklistPer")
def worklist():
    data = []
    for tid, t in TICKETS.items():
        if t["dispatched"]:
            continue
        data.append({
            "accept_user_name": "", "business_key": t["business_key"],
            "create_time": _now(), "expiration_time": "", "orgName": "技术支持中心",
            "process_base_id": int(tid.split("-")[1]), "systemName": "ITSM",
            "task_info_id": tid, "task_name": "待分派工单",
            "worksheet_title": t["title"], "worksheet_desc": t["desc"],
        })
    return {"code": 0, "count": len(data), "data": data, "msg": ""}


@app.get("/itsm/file/getFileList")
def file_list(businessKey: str = ""):
    rows = []
    for t in TICKETS.values():
        if t["business_key"] == businessKey:
            for idx, (name, ftype) in enumerate(t["files"], start=1):
                rows.append({
                    "create_by_name": "申请人", "create_date": _now(), "file_id": idx,
                    "file_name": name, "file_type": ftype, "file_size": "10KB",
                    "md5": "0" * 32, "rela_id": str(idx),
                })
    return {"total": len(rows), "rows": rows}


@app.get("/itsm/admin/bpmFeedBak/getBpmFeedBak")
def feed_list(businessKey: str = ""):
    rows = []
    for t in TICKETS.values():
        if t["business_key"] == businessKey:
            for i, content in enumerate(t["feeds"], start=1):
                rows.append({
                    "business_key": businessKey, "contact_phone": "13800000000",
                    "feedbak_content": content, "feedbak_org_id": 5722,
                    "feedbak_org_path": "示例公司/技术支持中心", "feedbak_time": _now(),
                    "feedbak_user_id": 263615, "feedbak_user_name": "系统支持",
                    "id": 1825000 + i, "real_name": "系统支持",
                    "orgName": "示例公司/技术支持中心", "mobile": "13800000000",
                })
    return {"total": len(rows), "rows": rows}


# ---------------- 工单表单页 (DOM 交互) ----------------
@app.get("/itsm/admin/bpmProcess/viewTaskForm", response_class=HTMLResponse)
def view_task_form(taskInfoId: str = ""):
    t = TICKETS.get(taskInfoId)
    if not t:
        return HTMLResponse("<html><head><title>提示 - ITSM系统</title></head><body>工单不存在</body></html>")
    body_rows = "".join(
        f"<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in t["track"]
    )
    # 末尾追加一行占位(驱动 rows[:-1] 会忽略最后一行, 与原 ITSM 表格结构一致)
    body_rows += f'<tr><td colspan="{len(TRACK_HEADER)}">—</td></tr>'
    header = "".join(f"<th>{h}</th>" for h in TRACK_HEADER)
    return TASK_FORM_HTML.format(
        title=t["title"], desc=t["desc"], header=header, rows=body_rows,
        business_key=t["business_key"],
    )


@app.get("/itsm/admin/submitForm", response_class=HTMLResponse)
def submit_form(businessKey: str = ""):
    dept_links = "".join(f'<a href="javascript:;" data-dept="{d}">{d}</a>' for d in DEPARTMENTS)
    user_items = "".join(f'<li><span data-user="{u}">{u}</span></li>' for u in USERS)
    return SUBMIT_FORM_HTML.format(business_key=businessKey, dept_links=dept_links, user_items=user_items)


@app.post("/itsm/admin/doSubmit")
async def do_submit(request: Request):
    payload = await request.json()
    bk = payload.get("businessKey")
    for t in TICKETS.values():
        if t["business_key"] == bk:
            t["dispatched"] = True
    _APPEND_SUBMIT_LOG(payload)
    return {"code": 0, "msg": "ok"}


def _APPEND_SUBMIT_LOG(payload: Dict[str, Any]):
    """把每次派单动作写入 mock 目录下的 jsonl, 便于演示核对。"""
    import os
    path = os.path.join(os.path.dirname(__file__), "submitted.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


@app.post("/itsm/admin/reset")
def reset_demo():
    """一键复位演示数据: 工单恢复初始 6 张(dispatched=False), 并清空派单日志。
    便于录屏时反复从干净状态开始, 无需重启服务。"""
    import os
    TICKETS.clear()
    TICKETS.update(_build_tickets())
    path = os.path.join(os.path.dirname(__file__), "submitted.jsonl")
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    pending = sum(1 for t in TICKETS.values() if not t["dispatched"])
    return {"code": 0, "msg": "ok", "pending": pending}


# ---------------- 页面模板 ----------------
LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>ITSM 登录 (Mock)</title>
<style>body{font-family:sans-serif;background:#f3f5f7}#loginForm{width:320px;margin:80px auto;
background:#fff;padding:28px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
#loginForm input{width:100%;margin:8px 0;padding:8px;box-sizing:border-box}
#valImg{height:40px;background:#eee;border:1px solid #ccc;margin:8px 0}
#btnSubmit{width:100%;padding:10px;background:#2d8cf0;color:#fff;border:0;border-radius:4px;cursor:pointer}
#loginPrompt{color:#ed4014}</style></head>
<body><form id="loginForm" action="/itsm/login" method="post">
<h3 style="text-align:center">ITSM 系统登录</h3>
<!--PROMPT-->
<label>工号</label><input id="staffId" name="staffId" autocomplete="off">
<label>密码</label><input id="staffPwd" name="staffPwd" type="password">
<label>验证码</label><img id="valImg" src="/itsm/captcha.png" alt="code"><input id="validCode" name="validCode" autocomplete="off">
<button type="submit" id="btnSubmit">登 录</button>
</form></body></html>"""

TASK_FORM_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:sans-serif;padding:20px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border:1px solid #dcdfe6;padding:6px 8px;font-size:13px;text-align:left}}
th{{background:#f8f8f9}}button[data-operation-type]{{padding:8px 18px;background:#19be6b;color:#fff;
border:0;border-radius:4px;cursor:pointer}}#submit-frame{{width:100%;height:360px;border:1px solid #ccc;
margin-top:12px}}</style></head>
<body>
<h3>工单详情</h3>
<table>
  <tr><td>需求标题</td><td>{title}</td></tr>
  <tr><td>需求描述</td><td>{desc}</td></tr>
</table>
<h3>处理跟踪</h3>
<div id="bigtabel1">
  <table id="example-advanced">
    <thead><tr>{header}</tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<button data-operation-type="提交" onclick="document.getElementById('submit-frame').style.display='block'">提交</button>
<iframe name="submit-frame" id="submit-frame" src="/itsm/admin/submitForm?businessKey={business_key}" style="display:none"></iframe>
</body></html>"""

SUBMIT_FORM_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>提交</title>
<style>body{{font-family:sans-serif;padding:16px}}a[data-dept]{{display:inline-block;margin:4px;
padding:4px 10px;border:1px solid #2d8cf0;border-radius:4px;color:#2d8cf0;text-decoration:none}}
a.on{{background:#2d8cf0;color:#fff}}#deptChips span{{display:inline-block;background:#e8f4ff;
margin:2px;padding:2px 8px;border-radius:4px;font-size:12px}}
#userList li{{cursor:pointer;list-style:none;padding:2px}}#userList li:hover{{background:#f0f9eb}}
#selectedHandler{{display:inline-block;min-width:120px;color:#19be6b;font-weight:bold}}
textarea#dealOpinion{{width:100%;height:60px}}#confirmSubmit{{margin-top:10px;padding:8px 20px;
background:#19be6b;color:#fff;border:0;border-radius:4px;cursor:pointer}}#status{{color:#2d8cf0}}</style>
</head><body>
<h4>提交实施 (businessKey: {business_key})</h4>
<div><b>选择部门:</b><br>{dept_links}</div>
<div id="deptChips"></div>
<div style="margin-top:12px"><b>已选处理人:</b><span id="selectedHandler"></span></div>
<ul id="userList">{user_items}</ul>
<div><b>处理意见:</b><textarea id="dealOpinion"></textarea></div>
<button id="confirmSubmit">确认提交</button> <span id="status"></span>
<script>
document.querySelectorAll('a[data-dept]').forEach(a=>a.addEventListener('click',()=>{{
  a.classList.toggle('on');
  const box=document.getElementById('deptChips');
  if(a.classList.contains('on')){{box.insertAdjacentHTML('beforeend','<span>'+a.dataset.dept+'</span>');}}
  else{{[...box.children].forEach(s=>{{if(s.textContent===a.dataset.dept)s.remove();}});}}
}}));
document.querySelectorAll('#userList span[data-user]').forEach(s=>{{
  const pick=()=>document.getElementById('selectedHandler').textContent=s.dataset.user;
  s.addEventListener('click',pick); s.addEventListener('dblclick',pick);
}});
document.getElementById('confirmSubmit').addEventListener('click',async()=>{{
  const handler=document.getElementById('selectedHandler').textContent;
  const opinion=document.getElementById('dealOpinion').value;
  const depts=[...document.querySelectorAll('a[data-dept].on')].map(a=>a.dataset.dept);
  const r=await fetch('/itsm/admin/doSubmit',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{businessKey:'{business_key}',handler,depts,opinion}})}});
  const j=await r.json();
  document.getElementById('status').textContent=j.code===0?'提交成功':'提交失败';
}});
</script></body></html>"""

# 1x1 透明 PNG, 仅在 Pillow 不可用时兜底
_FALLBACK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d47414d410000b18e7cbec65a000000204348524d0000000100000001"
    "00000001000000010000000100000001000000010000757cfd5b0000000a49454e44ae426082"
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
