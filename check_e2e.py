"""
端到端集成自检(无头浏览器): 证明"登录 -> 抓取 -> 规则匹配 -> 提交派单"整条链路
在本地真实可用, 不依赖 Flet GUI。

运行(本目录下): python check_e2e.py
前置: 已安装 playwright 浏览器 ->  python -m playwright install chromium
"""
import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from loguru import logger
logger.remove()

from mock_itsm.app import app as mock_app
from itsm_collect_app.settings import Config
from itsm_collect_app.schema import Person
from itsm_collect_app.rpa_app.pdriver import PwDriver
from itsm_collect_app.rpa_app.evaluate import EvaluateMachine
from itsm_collect_app.schema import Task, TrackTrace, FileRow, FeedRow, GroupData


def start_mock_server():
    cfg = uvicorn.Config(mock_app, host="127.0.0.1", port=8000, log_level="error")
    server = uvicorn.Server(cfg)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.1)
    print("[mock] ITSM 已启动 http://127.0.0.1:8000")


def load_tasks():
    import glob, json
    tasks_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rpa-data', 'tasks')
    return [Task(**json.load(open(p, encoding='utf-8'))) for p in glob.glob(os.path.join(tasks_dir, '*.json'))]


async def main():
    config = Config()
    tasks = load_tasks()

    driver = await PwDriver(config, headless=True).start()
    try:
        # 1) 登录(含验证码 OCR)
        await driver.login()
        print("[e2e] 登录成功, 当前 URL:", driver.page.url)

        # 2) 抓取待办工单列表
        gj = await driver.get_group_data()
        orders = [d for d in gj.data if d.task_name == '待分派工单']
        print(f"[e2e] 待分派工单数: {len(orders)}")
        assert orders, "未取到工单"

        # 3) 取第一张工单 -> 抓处理跟踪/文件/反馈
        order = orders[0]
        track = await driver.goto_task_page(order)
        files = (await driver.get_file_list(order.business_key)).rows
        feeds = (await driver.get_feed_list(order.business_key)).rows
        print(f"[e2e] 工单 {order.business_key} 跟踪{len(track)}行 文件{len(files)} 反馈{len(feeds)}")

        # 4) 规则匹配
        machine = EvaluateMachine(order, track, files, feeds)
        matched = None
        for task in tasks:
            if await machine.recursive_evaluate(task.task_desc, task.condition) is True:
                matched = task
                break
        assert matched, "首张工单(权限申请)应命中规则"
        print(f"[e2e] 命中规则: {matched.task_desc} -> {matched.submit_person[0].name}")

        # 5) 提交派单(DOM 操作提交弹窗 iframe)
        person = Person(**matched.submit_person[0].model_dump())
        before = len([d for d in (await driver.get_group_data()).data if d.task_name == '待分派工单'])
        await driver.submit(person, matched.submit_reply)

        await driver.wait_for_timeout(1)
        after_gj = await driver.get_group_data()
        after = len([d for d in after_gj.data if d.task_name == '待分派工单'])
        print(f"[e2e] 提交后待办: {before} -> {after}")
        assert after == before - 1, "提交未生效"

        print("\nE2E 全流程通过: 登录 / 抓取 / 匹配 / 提交 均 OK")
    finally:
        await driver.stop()


if __name__ == "__main__":
    start_mock_server()
    asyncio.run(main())
