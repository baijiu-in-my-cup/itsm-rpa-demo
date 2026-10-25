import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi.testclient import TestClient
from loguru import logger
logger.remove()
from mock_itsm.app import app

c = TestClient(app)
ok = True

# 1) 未登录访问 index -> 重定向到 login
r = c.get('/itsm/index', follow_redirects=False)
print('index(no auth) ->', r.status_code, r.headers.get('location'))
assert r.status_code == 302 and '/login' in r.headers['location']

# 2) 登录页 HTML 含关键元素
r = c.get('/itsm/login')
assert 'id="loginForm"' in r.text and 'id="staffId"' in r.text and 'id="valImg"' in r.text
print('login page ok, len=', len(r.text))

# 3) 验证码图片
r = c.get('/itsm/captcha.png')
assert r.status_code == 200 and r.headers['content-type'].startswith('image/png')
print('captcha ok, bytes=', len(r.content))

# 4) 提交错误密码 -> 出现 loginPrompt
r = c.post('/itsm/login', data={'staffId': 'demo', 'staffPwd': 'wrong', 'validCode': 'x'}, follow_redirects=False)
assert 'loginPrompt' in r.text
print('wrong pwd -> prompt ok')

# 5) 正确登录 (TestClient 会维持 cookie)
r = c.post('/itsm/login', data={'staffId': 'demo', 'staffPwd': 'demo123', 'validCode': 'D3M0'}, follow_redirects=True)
assert r.status_code == 200 and '/itsm/index' in str(r.url)
print('login success -> index ok')

# 6) 工单列表
r = c.get('/itsm/admin/Workindex/worklistGro')
data = r.json()['data']
print('gro count=', len(data), 'names=', [d['task_name'] for d in data][:1])
assert all(d['task_name'] == '待分派工单' for d in data)

# 7) 文件/反馈
bk = data[0]['business_key']
assert c.get(f'/itsm/file/getFileList?businessKey={bk}').json()['total'] >= 1
assert c.get(f'/itsm/admin/bpmFeedBak/getBpmFeedBak?businessKey={bk}').json()['total'] >= 1
print('file/feed ok')

# 8) 工单表单页含需求描述 + 跟踪表 + 提交按钮 + iframe
tid = data[0]['task_info_id']
r = c.get(f'/itsm/admin/bpmProcess/viewTaskForm?taskInfoId={tid}')
for token in ['需求描述', 'id="bigtabel1"', 'id="example-advanced"', 'data-operation-type="提交"', 'name="submit-frame"']:
    assert token in r.text, token
assert '提示 - ITSM系统' not in r.text
print('task form ok')

# 9) 提交弹窗页
r = c.get(f'/itsm/admin/submitForm?businessKey={bk}')
for token in ['id="userList"', 'data-dept=', 'id="selectedHandler"', 'id="dealOpinion"', 'id="confirmSubmit"']:
    assert token in r.text, token
print('submit form ok')

# 10) doSubmit 标记已分派 -> 列表数量减少
before = len(c.get('/itsm/admin/Workindex/worklistGro').json()['data'])
c.post('/itsm/admin/doSubmit', json={'businessKey': bk, 'handler': '张伟', 'depts': ['技术支持中心'], 'opinion': 'x'})
after = len(c.get('/itsm/admin/Workindex/worklistGro').json()['data'])
assert after == before - 1
print(f'doSubmit ok, tickets {before}->{after}')

# 11) /reset 一键复位 -> 待分派工单恢复初始数量
r = c.post('/itsm/admin/reset')
assert r.json()['code'] == 0 and r.json()['pending'] == before
restored = len(c.get('/itsm/admin/Workindex/worklistGro').json()['data'])
assert restored == before, f'reset 应恢复 {before}, 实际 {restored}'
print(f'reset ok, tickets {after}->{restored}')

print('\nALL MOCK CHECKS PASSED')
