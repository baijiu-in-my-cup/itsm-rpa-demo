from datetime import datetime
import pathlib
from itsm_collect_app.rpa_app.pdriver import PwApi, PwDriver
from itsm_collect_app.schema import *
from itsm_collect_app.rpa_app.evaluate import EvaluateMachine
from loguru import logger
from collections import deque
from itsm_collect_app.rpa_app.common import run_time_to_day
from itsm_collect_app.infrastructure.sql_api import SqlApi
from itsm_collect_app.settings import Config
import os
from uuid import uuid4
from itsm_collect_app.rpa_app.errors import TaskSettingException
import random

cwd = os.path.dirname(__file__)
tasks_dir = os.path.join(os.path.dirname(cwd), 'static', 'tasks')

info_file_log = logger.bind(name="info_file_log")
flet_app_log = logger.bind(name="flet_app_log")

class Handler:
    def __init__(self, sql_api: SqlApi, config: Config, cache_task_info_id_max_len: int = 100):
        self.cache_task_info_id = deque(maxlen=cache_task_info_id_max_len)
        self.sql_api = sql_api
        self.config = config


    async def __aenter__(self) -> 'Handler':
        # await self.databases.connect()
        # self.sql_api = SqlApi(self.databases)
        self.driver = await PwDriver(self.config).start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        try:
            # await self.databases.disconnect()
            await self.driver.stop()
        except Exception:
            pass

    async def start(self) -> 'Handler':
        return await self.__aenter__()

    async def stop(self) -> None:
        return await self.__aexit__()

    async def get_group_data(self, task_name: str = '待分派工单') -> Optional[List[GroupData]]:
        json_data = await PwApi.get_group_data(self.driver)
        return [item for item in json_data.data if item.task_name == task_name]

    async def get_file_list(self, business_key:str) -> Optional[List[FileRow]]:
        json_data = await PwApi.get_file_list(self.driver, business_key)
        return json_data.rows

    async def get_feed_list(self,business_key:str)->Optional[List[FeedRow]]:
        json_data = await PwApi.get_feed_list(self.driver, business_key)
        return json_data.rows

    async def wait_for_timeout(self, sleep_time: int = 120) -> None:
        await PwApi.wait_for_timeout(self.driver, sleep_time)
        # await asyncio.sleep(sleep_time)

    async def goto_task_page(self, order: GroupData) -> Optional[List[TrackTrace]]:
        return await PwApi.goto_task_page(self.driver, order)

    async def goto_view_page(self, business_key: str) -> Optional[Tuple[GroupData, List[TrackTrace]]]:
        return await PwApi.goto_view_page(self.driver, business_key)

    async def val_login(self) -> None:
        await self.driver.login()

    async def submit(self, submit_person: Person, submit_reply: str, record_log: RecordLog) -> None:
        # screenshot_base64 = await PwApi.submit(self.driver, submit_person, submit_reply)
        # record_log.screenshot_base64 = screenshot_base64
        await PwApi.submit(self.driver, submit_person, submit_reply)
        await self.sql_api.add_record_log(record_log)
        return

    async def test_run(self, business_key: str, task_desc: str) -> None:
        order, track_trace_rows = await self.goto_view_page(business_key)
        file_rows = await self.get_file_list(order.business_key)
        feed_rows = await self.get_feed_list(order.business_key)
        evaluate_machine = EvaluateMachine(order, track_trace_rows, file_rows,feed_rows)
        task_data = await self.sql_api.get_task_data()
        for task_model in task_data:
            task_model.condition.filter_content.pop(0)
            if task_desc and task_model.task_desc != task_desc:
                continue
            task_result = await evaluate_machine.recursive_evaluate(task_model.task_desc, task_model.condition)
            if task_result is True:
                logger.info(f'【{order.business_key}】->【{task_model.task_desc}】')
                flet_app_log.info(f'【{order.business_key}】-> 【{task_model.task_desc}】')
                break

    async def get_pd_person(self, submit_person: List[Person], task_id: str) -> Person:
        if len(submit_person) == 0:
            raise Exception('can selected person sum is 0')
        if len(submit_person) == 1:
            return submit_person[0]
        can_select_persons = [p for p in submit_person if p.sign == 0]
        if not can_select_persons:
            random_index = random.randrange(len(submit_person))
            person = submit_person[random_index]
            person.sign = 1
            await self.sql_api.update_submit_person(task_id, [p.model_dump() for p in submit_person])
            return person
        person = random.sample(can_select_persons, 1)[0]
        for p in submit_person:
            if p.name== person.name:
                p.sign = 1
                break
        await self.sql_api.update_submit_person(task_id, [p.model_dump() for p in submit_person])
        return person

    async def run(self, ack_run_time_to_day:bool=False) -> None:
        if run_time_to_day(human_ack=ack_run_time_to_day,config=self.config) is False:
            flet_app_log.debug("不再派单时间,休息180秒...")
            await self.wait_for_timeout(180)
            return
        group_data = await self.get_group_data()
        for order in group_data:
            if order.task_info_id in self.cache_task_info_id:
                continue
            self.cache_task_info_id.append(order.task_info_id)
            track_trace_rows = await self.goto_task_page(order)
            feed_rows = await self.get_feed_list(order.business_key)
            file_rows = await self.get_file_list(order.business_key)
            evaluate_machine = EvaluateMachine(order, track_trace_rows, file_rows,feed_rows)
            task_data = await self.sql_api.get_task_data()
            for task_model in task_data:
                if not task_model.is_activate:
                    continue
                if task_model.task_type==TaskTypeAndPersonRoleEnum.RING_SEND.value:
                    if not task_model.end_time:
                        raise TaskSettingException(f'【{task_model.task_desc}】请设置派单时间')
                    if datetime.now().time() > datetime.strptime(task_model.end_time,"%H:%M").time():
                        raise TaskSettingException(f'【{task_model.task_desc}】不在人员派单时间内，不判断')
                task_result = await evaluate_machine.recursive_evaluate(task_model.task_desc, task_model.condition)
                if task_result is True:
                    info_file_log.info(f'【{order.business_key}】匹配 -> 【{task_model.task_desc}】')
                    flet_app_log.success(f'【{order.business_key}】匹配 -> 【{task_model.task_desc}】')
                    if task_model.task_type==TaskTypeAndPersonRoleEnum.RING_SEND.value:
                        submit_person_data = await self.get_pd_person(task_model.submit_person, task_model.task_id)
                    elif task_model.task_type==TaskTypeAndPersonRoleEnum.COMMON.value:
                        submit_person_data=task_model.submit_person[0]
                    else:
                        raise TaskSettingException(f'【{task_model.task_desc}】非法任务类型')
                    record_log = RecordLog(
                        record_id=str(uuid4()),
                        business_key=order.business_key,
                        task_desc=task_model.task_desc,
                        order_desc=order.worksheet_desc,
                        create_time=datetime.now(),
                        submit_name=submit_person_data.name,
                    )
                    await self.submit(submit_person_data, task_model.submit_reply, record_log)
                    break
        flet_app_log.debug('休息180秒...')
        await self.wait_for_timeout(180)
        return
