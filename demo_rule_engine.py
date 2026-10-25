"""
规则引擎演示脚本(无需浏览器/无需登录, 纯离线展示核心亮点)。

它做三件事:
  1) 加载 rpa-data/tasks/*.json 为强类型 Task 模型(校验规则 DSL 合法);
  2) 直接从 Mock ITSM 的数据源取工单/文件/反馈;
  3) 用 EvaluateMachine 递归求值, 打印"每张工单命中哪条规则"。

运行(在本目录 itsm-rpa-demo 下):
    python demo_rule_engine.py
"""
import asyncio
import glob
import os
import sys

# 保证可导入 itsm_collect_app 与 mock_itsm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from itsm_collect_app.schema import (
    Task, GroupData, TrackTrace, FileRow, FeedRow,
)
from itsm_collect_app.rpa_app.evaluate import EvaluateMachine
from mock_itsm import app as mock

# 保持演示输出清爽: 关闭引擎内部的逐条 DEBUG 日志
from loguru import logger
logger.remove()

TASKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rpa-data', 'tasks')


def load_tasks() -> list[Task]:
    import json
    tasks = []
    for path in sorted(glob.glob(os.path.join(TASKS_DIR, '*.json'))):
        with open(path, encoding='utf-8') as f:
            tasks.append(Task(**json.load(f)))
    return tasks


def build_ticket_inputs(business_key: str):
    """从 mock 数据构造 EvaluateMachine 需要的四类输入。"""
    ticket = next(t for t in mock.TICKETS.values() if t['business_key'] == business_key)

    work_sheet = GroupData(
        business_key=business_key,
        worksheet_title=ticket['title'],
        worksheet_desc=ticket['desc'],
        task_name='待分派工单',
    )
    track_rows = [
        TrackTrace.model_validate(dict(zip(mock.TRACK_HEADER, row)))
        for row in ticket['track']
    ]
    file_rows = [FileRow(**r) for r in mock.file_list(businessKey=business_key)['rows']]
    feed_rows = [FeedRow(**r) for r in mock.feed_list(businessKey=business_key)['rows']]
    return work_sheet, track_rows, file_rows, feed_rows


async def main():
    tasks = load_tasks()
    print(f'已加载 {len(tasks)} 条任务规则:')
    for t in tasks:
        p = t.submit_person[0].name if t.submit_person else '-'
        print(f'  - {t.task_desc:<12} (类型={t.task_type}, 提交人={p})')

    print('\n工单 -> 规则匹配结果')
    print('-' * 60)
    for tid, ticket in mock.TICKETS.items():
        bk = ticket['business_key']
        work_sheet, track_rows, file_rows, feed_rows = build_ticket_inputs(bk)
        machine = EvaluateMachine(work_sheet, track_rows, file_rows, feed_rows)
        matched = None
        for task in tasks:
            if await machine.recursive_evaluate(task.task_desc, task.condition) is True:
                matched = task
                break
        title = ticket['title']
        if matched:
            print(f'[{bk}] {title:<22} => 命中【{matched.task_desc}】-> 派给 {matched.submit_person[0].name}')
        else:
            print(f'[{bk}] {title:<22} => 未命中任何规则(不派单)')


if __name__ == '__main__':
    asyncio.run(main())
