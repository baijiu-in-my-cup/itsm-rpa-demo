from flet.core.time_picker import TimePicker
from datetime import time
from itsm_collect_app.schema import *
import flet as ft
from flet.core.types import OptionalControlEventCallable, ControlEvent
from itsm_collect_app.infrastructure.sql_api import SqlApi
from loguru import logger
from collections import defaultdict
from collections import deque
from itsm_collect_app.rpa_app.manage import RpaManage
from itsm_collect_app.settings import Config
from itsm_collect_app.rpa_app.errors import TaskSettingException
from itsm_collect_app.rpa_app.common import run_time_to_day

error_file_log = logger.bind(name='error_file_log')
flet_app_log = logger.bind(name="flet_app_log")


class EditPersonDialog(ft.AlertDialog):
    def __init__(self, data: List[Person], event_handler: Optional[OptionalControlEventCallable], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = data
        self.task_id = None
        self.task_desc = None
        self.event_handler = event_handler
        self.submit_person: Optional[List[Person]] = None
        self.actions_alignment = ft.MainAxisAlignment.END
        self.check_boxs_refs: Optional[List[ft.Ref[ft.Checkbox]]] = None
        self.check_boxs_persons: Optional[List[Person]] = None

    def build(self):
        if not self.data or not self.task_id:
            return
        self.title = ft.Text(f"{self.task_desc}-编辑人员")
        self.check_boxs_persons = [
            option
            for option in self.data if
            option.department == self.submit_person[0].department
        ]
        self.check_boxs_refs = [
            ft.Ref[ft.Checkbox]() for _ in self.check_boxs_persons
        ]
        self.content = ft.Container(
            width=500,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Checkbox(ref=ref, data={'data': person.model_dump()},
                                        value=True if person.name in [p.name for p in
                                                                      self.submit_person] else False),
                            ft.Text(
                                value=f'{person.name}',
                                spans=[
                                    ft.TextSpan('   '),
                                    ft.TextSpan(
                                        text='/'.join(person.department), style=ft.TextStyle(
                                            size=12
                                        )
                                    )
                                ]
                            )
                        ]
                    ) for ref, person in zip(self.check_boxs_refs, self.check_boxs_persons)
                ]
            )
        )
        self.actions = [
            ft.TextButton("保存", on_click=self.event_handler,
                          data={'event_name': 'on_click_edit_person_dialog', 'type': 'save'}),
            ft.TextButton("取消", on_click=self.event_handler,
                          data={'event_name': 'on_click_edit_person_dialog', 'type': 'cancel'}),
        ]

    def before_update(self):
        self.build()


class AddPersonDialog(ft.AlertDialog):
    def __init__(self, data: Dict[int, Set[str]], event_handler: Optional[OptionalControlEventCallable], *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.data = data
        self.task_id = None
        self.event_handler = event_handler
        self.name = ft.Ref[ft.TextField]()
        self.department = {level: ft.Ref[ft.Dropdown]() for level in self.data.keys()}
        self.actions_alignment = ft.MainAxisAlignment.END
        self.title = ft.Text("新增人员")
        self.role = ft.Ref[ft.RadioGroup]()

    def build(self):
        if not self.data:
            return

        controls = [
            ft.Dropdown(
                ref=self.department[level],
                options=[
                    ft.dropdown.Option(
                        key=option,
                        content=ft.Text(
                            value=f'{option}',
                        )
                    ) for option in options
                ]
            ) for level, options in self.data.items()
        ]

        controls.append(
            ft.TextField(
                ref=self.name,
                label='姓名', helper_text='请输入',
            )
        )
        # controls.append(
        #     ft.RadioGroup(
        #         ref=self.role,
        #         value="2",
        #         content=ft.Row(
        #             controls=[
        #                 ft.Radio(value="2", label="加入轮询派单"),
        #                 ft.Radio(value="1", label="不加入轮询派单")
        #             ]
        #         )
        #     )
        # )

        self.content = ft.Container(
            width=500,
            height=250,
            content=ft.Column(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=controls
            )
        )
        self.actions = [
            ft.TextButton("保存", on_click=self.event_handler,
                          data={'event_name': 'on_click_add_person_dialog', 'type': 'save'}),
            ft.TextButton("取消", on_click=self.event_handler,
                          data={'event_name': 'on_click_add_person_dialog', 'type': 'cancel'}),
        ]

    def before_update(self):
        self.build()


class TaskColumn(ft.Column):
    def __init__(self, data: List[Task], event_handler: Optional[OptionalControlEventCallable], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.isolated = True
        self.data = data
        self.event_handler = event_handler

    def build(self):
        if not self.data:
            return

        self.data.sort(key=lambda task: task.submit_person[0].name)

        self.controls = [
            ft.DataTable(
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                show_checkbox_column=True,
                data_row_max_height=float('inf'),
                columns=[
                    ft.DataColumn(ft.Text('开关', selectable=True)),
                    ft.DataColumn(ft.Text("任务描述", selectable=True)),
                    ft.DataColumn(ft.Text("派单人员", selectable=True)),
                    # ft.DataColumn(ft.Text("时间选择", selectable=True)),
                ],
                rows=[
                    ft.DataRow(
                        cells=[
                            ft.DataCell(
                                content=ft.Switch(value=bool(row.is_activate), on_change=self.event_handler,
                                                  data={'event_name': 'update_task_is_activate',
                                                        'task_id': row.task_id}),
                            ),
                            ft.DataCell(
                                content=ft.Text(value=row.task_desc,
                                                color=ft.Colors.GREEN if row.task_type == TaskTypeAndPersonRoleEnum.RING_SEND.value else None),
                                on_tap=self.event_handler,
                                # show_edit_icon=True,
                                data={'event_name': 'go_to_task_detail', 'task_id': row.task_id,
                                      'task_desc': row.task_desc}
                            ),
                            ft.DataCell(
                                content=ft.Text(
                                    value=','.join([task_person.name for task_person in row.submit_person]),
                                    width=200, ),
                                # show_edit_icon=True,
                                on_tap=self.event_handler,
                                data={'event_name': 'edit_task_submit_person', 'task_id': row.task_id,
                                      'task_desc': row.task_desc, 'submit_person': row.submit_person}
                            ),
                            # ft.DataCell(
                            #     content=ft.Row(
                            #         controls=[
                            #             ft.Text(value=row.end_time),
                            #             ft.OutlinedButton(text='删除',on_click=self.event_handler,data={'event_name': 'end_time_delete','task_id':row.task_id})
                            #         ] if row.end_time else [ft.Text(value='未设置')]
                            #     ),
                            #     on_tap=self.event_handler,data={'event_name': 'set_task_end_time', 'task_id': row.task_id,}
                            # )
                        ],
                    ) for row in self.data
                ]
            ),
        ]

    def before_update(self):
        self.build()


class AckRunTimeDialog(ft.AlertDialog):
    def __init__(self, event_handler: Optional[OptionalControlEventCallable], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_handler = event_handler
        self.submit_person: Optional[List[Person]] = None
        self.actions_alignment = ft.MainAxisAlignment.CENTER

    def build(self):
        self.content = ft.Container(
            content=ft.Text(
                value=f"今天是非工作日，确认运行吗？",
                weight=ft.FontWeight.W_500,
                text_align=ft.TextAlign.CENTER,
            )
        )
        self.actions = [
            ft.TextButton(
                "确认",
                on_click=self.event_handler,
                data={"event_name": "on_click_ack_run_time_dialog", "type": "ok"},
            ),
            ft.TextButton(
                "取消",
                on_click=self.event_handler,
                data={"event_name": "on_click_ack_run_time_dialog", "type": "cancel"},
            ),
        ]

    def before_update(self):
        self.build()


class RpaRunLogColumn(ft.Column):
    def __init__(self, event_handler: Optional[OptionalControlEventCallable], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.isolated = True
        self.event_handler = event_handler
        # self.max_logs = 100  # 最多显示 100 条日志
        self.logs = deque(maxlen=100)
        logger.add(self.log_to_ui, format="{time:YYYY-MM-DD HH:mm:ss.SSS}|{level}|{message}",
                   filter=lambda record: record["extra"].get("name", "") == "flet_app_log")
        self.flet_app_log = logger.bind(name="flet_app_log")

    def log_to_ui(self, message):
        # if len(self.controls) >= self.max_logs:
        #     self.controls.pop(0)  # 移除最旧的日志
        # self.controls=self.controls[-self.max_logs:]

        time, level, msg = message.split('|')
        color = {
            "DEBUG": ft.colors.BLACK,
            "INFO": ft.colors.BLACK,
            "SUCCESS": ft.colors.GREEN,
            "WARNING": ft.colors.ORANGE,
            "ERROR": ft.colors.RED,
        }.get(level, ft.colors.BLACK)
        size = {
            "INFO": 18,
            "SUCCESS": 18,
            "WARNING": 18,
            "ERROR": 20,
        }.get(level, 16)
        weight = {
            "SUCCESS": ft.FontWeight.BOLD,
            "ERROR": ft.FontWeight.BOLD,
        }.get(level, ft.FontWeight.NORMAL)
        log_control = ft.Container(
            content=ft.Text(
                spans=[
                    ft.TextSpan(f'{time}', ft.TextStyle(color=ft.colors.BLACK, size=size, weight=weight)),
                    ft.TextSpan("：", ft.TextStyle(color=ft.colors.BLACK, size=size, weight=weight)),
                    ft.TextSpan(f'{msg}', ft.TextStyle(color=color, size=size, weight=weight))
                ],
                selectable=True,
                overflow=ft.TextOverflow.CLIP,
            ),
        )
        self.logs.append(log_control)
        self.controls = list(self.logs)
        self.update()


class TimePickDialog(ft.AlertDialog):
    def __init__(self,event_handler: Optional[OptionalControlEventCallable], *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.event_handler = event_handler
        self.actions_alignment = ft.MainAxisAlignment.END

    @property
    def time_range(self)->str:
        return self._get_attr("time_range")

    @time_range.setter
    def time_range(self, value: str):
        if value not in ("AM", "PM"):
            raise ValueError("time_range must be 'AM' or 'PM'")
        self._set_attr("time_range", value)

    @property
    def time_start(self) -> time:
        v = self._get_attr("time_start")  # format HH:MM
        return time(*map(int, v.split(":")))

    @time_start.setter
    def time_start(self, value: time):
        self._set_attr("time_start", value.strftime("%H:%M"))

    @property
    def time_end(self) -> time:
        v = self._get_attr("time_end")  # format HH:MM
        return time(*map(int, v.split(":")))

    @time_end.setter
    def time_end(self, value: time):
        self._set_attr("time_end", value.strftime("%H:%M"))

    def _build_time_picker(self,value:time):
        text=value.strftime("%H:%M")
        hour_value, minute_value = text.split(":")
        return ft.Row(
            wrap=False,
            expand=True,
            controls=[
                ft.TextField(value=hour_value,counter_text="时",expand=True,input_filter=ft.NumbersOnlyInputFilter()),
                ft.Text(":",weight=ft.FontWeight.BOLD),
                ft.TextField(value=minute_value,counter_text="分",expand=True,input_filter=ft.NumbersOnlyInputFilter()),
            ]
        )

    def _validate_hour(self,value:str):
        if not value.isdigit():
            return False
        hour=int(value)
        if hour<0 or hour>23:
            return False
        return True

    def _validate_minute(self,value:str):
        if not value.isdigit():
            return False
        minute=int(value)
        if minute<0 or minute>59:
            return False
        return True

    def _reset_text_fields(self,controls:List[ft.TextField],error_text:str="请输入正确的时间"):
        for control in controls:
            control.error_text = error_text
            control.value = ""
            control.update()

    # 数据校验
    async def _validate_time_picker(self,e:ft.ControlEvent):
        time_start_row,time_end_row=self.content.content.controls[0],self.content.content.controls[1]
        time_start_hour,time_start_minute=time_start_row.controls[-1].controls[0],time_start_row.controls[-1].controls[-1]
        time_end_hour,time_end_minute=time_end_row.controls[-1].controls[0],time_end_row.controls[-1].controls[-1]

        if not self._validate_hour(time_start_hour.value):
            self._reset_text_fields([time_start_hour])
            return
        if not self._validate_hour(time_end_hour.value):
            self._reset_text_fields([time_end_hour])
            return
        if not self._validate_minute(time_start_minute.value):
            self._reset_text_fields([time_start_hour])
            return
        if not self._validate_minute(time_end_minute.value):
            self._reset_text_fields([time_end_hour])
            return
        time_start_value=time(hour=int(time_start_hour.value),minute=int(time_start_minute.value))
        time_end_value=time(hour=int(time_end_hour.value),minute=int(time_end_minute.value))
        if time_start_value>=time_end_value:
            self._reset_text_fields([time_start_hour],"开始时间不能大于结束时间")
            return

        if self.time_range == "AM":
            am_start=time(hour=0,minute=0)
            am_end=time(hour=12,minute=59)
            if time_start_value<am_start or time_end_value>am_end:
                self._reset_text_fields([time_start_hour,time_end_hour], "开始时间不在上午时间段内")
                return
        if self.time_range == "PM":
            pm_start=time(hour=12,minute=0)
            pm_end=time(hour=23,minute=59)
            if time_start_value<pm_start or time_end_value>pm_end:
                self._reset_text_fields([time_start_hour,time_end_hour], "开始时间不在下午时间段内")
                return
        e.control.data['time_range']=self.time_range
        self.time_start=time_start_value
        self.time_end=time_end_value
        await self.event_handler(e)

    def build(self):

        self.content = ft.Container(
            width=500,
            height=150,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("开始时间：",weight=ft.FontWeight.BOLD),
                            self._build_time_picker(value=self.time_start),
                        ]
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("结束时间：", weight=ft.FontWeight.BOLD),
                            self._build_time_picker(value=self.time_end),
                        ]
                    )
                ]
            ),
            expand=True,
        )
        self.actions = [
            ft.TextButton("取消", on_click=self._validate_time_picker,
                          data={'event_name': 'on_click_time_pick_dialog', 'type': 'cancel'}),
            ft.TextButton("确定", on_click=self._validate_time_picker,data={'event_name': 'on_click_time_pick_dialog', 'type': 'ok'}),
        ]

    def before_update(self):
        self.build()

class IndexView(ft.View):
    def __init__(self, page: ft.Page, sql_api: SqlApi, show_error_banner: Callable[..., Coroutine[Any, Any, Any]],
                 config: Config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page
        self.sql_api = sql_api
        self.show_error_banner = show_error_banner
        self.task_column = ft.Ref[TaskColumn]()
        self.edit_person_dialog = ft.Ref[EditPersonDialog]()
        self.add_person_dialog = ft.Ref[AddPersonDialog]()
        self.ack_run_time_dialog = ft.Ref[AckRunTimeDialog]()
        self.time_pick_dialog=ft.Ref[TimePickDialog]()
        self.rpa_run_log = ft.Ref[RpaRunLogColumn]()
        self.rpa_btn = ft.Ref[ft.FloatingActionButton]()
        self.config=config
        self.rpa_manage = RpaManage(self.sql_api, config, self.handle_rpa_exception)

        self.am_time_open_button=ft.Ref[ft.Button]()
        self.pm_time_open_button=ft.Ref[ft.Button]()


    async def event_handler(self, e: ControlEvent):
        async def edit_task_submit_person():
            self.edit_person_dialog.current.task_id = e.control.data.get('task_id')
            self.edit_person_dialog.current.task_desc = e.control.data.get('task_desc')
            self.edit_person_dialog.current.submit_person = e.control.data.get('submit_person')
            self.page.open(self.edit_person_dialog.current)

        async def on_click_edit_person_dialog():
            if e.control.data.get('type') == "save":
                submit_objs = []
                for index, checkbox in enumerate(self.edit_person_dialog.current.check_boxs_refs):
                    if checkbox.current.value is True:
                        submit_objs.append(checkbox.current.data.get('data'))
                if not submit_objs:
                    return
                if self.edit_person_dialog.current.submit_person[0].role == TaskTypeAndPersonRoleEnum.COMMON.value:
                    if len(submit_objs) > 1:
                        raise Exception('错误！请重新选择')
                await self.sql_api.update_submit_person(self.edit_person_dialog.current.task_id, submit_objs)
            self.task_column.current.data = await self.sql_api.get_task_data()
            await self.task_column.current.update_async()
            self.page.close(self.edit_person_dialog.current)

        async def on_click_ack_run_time_dialog():
            if e.control.data.get('type') == "ok":
                self.rpa_btn.current.disabled = True
                await self.rpa_btn.current.update_async()
                await self.rpa_manage.start(ack_run_time_to_day=True)
                self.rpa_btn.current.icon = ft.icons.PAUSE_OUTLINED
                self.rpa_btn.current.text = "暂停机器人"
                self.rpa_btn.current.disabled = False
                await self.rpa_btn.current.update_async()
            self.page.close(self.ack_run_time_dialog.current)

        async def rpa_run_set():
            if self.rpa_manage.running is False:
                if not run_time_to_day(config=self.config):
                    self.page.open(self.ack_run_time_dialog.current)
                    return
                self.rpa_btn.current.disabled = True
                await self.rpa_btn.current.update_async()
                await self.rpa_manage.start()
                self.rpa_btn.current.icon = ft.icons.PAUSE_OUTLINED
                self.rpa_btn.current.text = '暂停机器人'
                self.rpa_btn.current.disabled = False

            elif self.rpa_manage.running is True:
                self.rpa_btn.current.disabled = True
                await self.rpa_btn.current.update_async()
                await self.rpa_manage.stop()
                self.rpa_btn.current.icon = ft.icons.PLAY_ARROW_OUTLINED
                self.rpa_btn.current.text = '启动机器人'
                self.rpa_btn.current.disabled = False
            await self.rpa_btn.current.update_async()

        async def add_task_submit_person():
            assert self.page
            self.page.open(self.add_person_dialog.current)

        async def on_click_add_person_dialog():
            assert self.page
            if e.control.data.get('type') == "save":
                name = self.add_person_dialog.current.name.current.value
                if not name:
                    self.add_person_dialog.current.name.current.error_text = '请输入'
                    await self.add_person_dialog.current.name.current.update_async()
                    return
                department = []
                for level, depart_ref in self.add_person_dialog.current.department.items():
                    if not depart_ref.current.value:
                        self.add_person_dialog.current.department[level].current.error_text = '请选择'
                        await self.add_person_dialog.current.department[level].current.update_async()
                        return
                    department.append(depart_ref.current.value)
                # role = int(self.add_person_dialog.current.role.current.value)
                await self.sql_api.add_person_data(name, department, role=1)
                self.edit_person_dialog.current.data = await self.sql_api.get_person_data()
            self.page.close(self.add_person_dialog.current)

        async def go_to_task_detail():
            assert self.page
            task_id = e.control.data.get('task_id')
            task_desc = e.control.data.get('task_desc')
            await self.page.go_async(f'/task/{task_id}/{task_desc}')

        async def set_task_end_time():
            assert self.page

            async def time_picker_on_change(_e):
                await self.sql_api.update_task_end_time(task_id, _e.data)
                self.task_column.current.data = await self.sql_api.get_task_data()
                await self.task_column.current.update_async()

            task_id = e.control.data.get('task_id')
            time_picker = ft.TimePicker(
                confirm_text="确认",
                cancel_text="取消",
                error_invalid_text="不合法的时间",
                help_text="输入您的时间",
                time_picker_entry_mode=ft.TimePickerEntryMode.INPUT_ONLY,
                on_change=time_picker_on_change,
            )
            self.page.open(time_picker)

        async def end_time_delete():
            task_id = e.control.data.get('task_id')
            await self.sql_api.update_task_end_time(task_id, '')
            self.task_column.current.data = await self.sql_api.get_task_data()
            await self.task_column.current.update_async()

        async def update_task_is_activate():
            task_id = e.control.data.get('task_id')
            is_activate = int(e.control.value)
            await self.sql_api.update_task_is_activate(task_id, is_activate)
            self.task_column.current.data = await self.sql_api.get_task_data()
            await self.task_column.current.update_async()

        async def on_click_time_pick_dialog():
            if e.control.data.get('type') == "open":
                self.time_pick_dialog.current.title=ft.Text(e.control.data.get('title_text'))
                time_range=e.control.data.get('time_range')
                if time_range == "AM":
                    self.time_pick_dialog.current.time_start = self.config.rpa_run_time.am_start
                    self.time_pick_dialog.current.time_end = self.config.rpa_run_time.am_end
                elif time_range == "PM":
                    self.time_pick_dialog.current.time_start = self.config.rpa_run_time.pm_start
                    self.time_pick_dialog.current.time_end = self.config.rpa_run_time.pm_end
                self.time_pick_dialog.current.time_range=time_range
                self.page.open(self.time_pick_dialog.current)
                return
            if e.control.data.get('type') == "ok":
                time_range = e.control.data.get('time_range')
                time_start=self.time_pick_dialog.current.time_start
                time_end=self.time_pick_dialog.current.time_end
                if time_range=="AM":
                    self.config.rpa_run_time.am_start=time_start
                    self.config.rpa_run_time.am_end=time_end
                    self.am_time_open_button.current.text=f"上午运行时间：{self.config.rpa_run_time.am_start_text}-{self.config.rpa_run_time.am_end_text}"
                    self.am_time_open_button.current.update()
                elif time_range=="PM":
                    self.config.rpa_run_time.pm_start = time_start
                    self.config.rpa_run_time.pm_end = time_end
                    self.pm_time_open_button.current.text=f"下午运行时间：{self.config.rpa_run_time.pm_start_text}-{self.config.rpa_run_time.pm_end_text}"
                    self.pm_time_open_button.current.update()
            self.page.close(self.time_pick_dialog.current)

        event_handlers = {
            'update_task_is_activate': update_task_is_activate,
            'edit_task_submit_person': edit_task_submit_person,
            'on_click_edit_person_dialog': on_click_edit_person_dialog,
            'rpa_run_set': rpa_run_set,
            'add_task_submit_person': add_task_submit_person,
            'on_click_add_person_dialog': on_click_add_person_dialog,
            'go_to_task_detail': go_to_task_detail,
            'set_task_end_time': set_task_end_time,
            'end_time_delete': end_time_delete,
            'on_click_ack_run_time_dialog': on_click_ack_run_time_dialog,
            'on_click_time_pick_dialog':on_click_time_pick_dialog,
        }
        event_name = e.control.data.get('event_name', '')
        if event_name in event_handlers:
            try:
                await event_handlers[event_name]()
            except Exception as error:
                await self.show_error_banner(error)

    async def handle_rpa_exception(self, exception: Exception):
        if isinstance(exception, TaskSettingException):
            if exception:
                dlg = ft.AlertDialog(
                    title=ft.Text(f'{exception}', selectable=True),
                )
                assert self.page
                self.page.open(dlg)
        flet_app_log.error('机器人停止运行')
        flet_app_log.info(exception)
        self.rpa_btn.current.disabled = True
        await self.rpa_manage.stop()
        self.rpa_btn.current.icon = ft.icons.PLAY_ARROW_OUTLINED
        self.rpa_btn.current.text = '启动机器人'
        self.rpa_btn.current.disabled = False
        await self.rpa_btn.current.update_async()

    async def async_build(self):
        person_data = await self.sql_api.get_person_data()
        level_person_data = defaultdict(set)
        for person in person_data:
            for level, depart in enumerate(person.department):
                level_person_data[level].add(depart)
        task_data = await self.sql_api.get_task_data()
        _ = TaskColumn(event_handler=self.event_handler, data=task_data, ref=self.task_column,
                       scroll=ft.ScrollMode.AUTO)
        _ = RpaRunLogColumn(event_handler=self.event_handler, ref=self.rpa_run_log, scroll=ft.ScrollMode.AUTO,
                            auto_scroll=True)
        _ = EditPersonDialog(event_handler=self.event_handler, data=person_data, ref=self.edit_person_dialog,
                             modal=True)
        _ = AddPersonDialog(data=level_person_data, event_handler=self.event_handler, ref=self.add_person_dialog,
                            modal=True)
        _ = AckRunTimeDialog(event_handler=self.event_handler, ref=self.ack_run_time_dialog, modal=True)

        _ =TimePickDialog(event_handler=self.event_handler, ref=self.time_pick_dialog, modal=True)
        self.controls = [
            ft.Container(
                expand=True,
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.ElevatedButton(
                                        icon=ft.Icons.ADD_BOX,
                                        text="派单人员",
                                        on_click=self.event_handler,
                                        data={"event_name": "add_task_submit_person"},
                                    ),
                                    ft.ElevatedButton(
                                        icon=ft.Icons.TIMER,
                                        text=f"上午运行时间：{self.config.rpa_run_time.am_start_text}-{self.config.rpa_run_time.am_end_text}",
                                        on_click=self.event_handler,
                                        ref=self.am_time_open_button,
                                        data={
                                            "event_name": "on_click_time_pick_dialog",
                                            "type": "open",
                                            "title_text": "上午运行时间",
                                            "time_range":"AM"
                                        },
                                    ),
                                    ft.ElevatedButton(
                                        icon=ft.Icons.TIMER,
                                        text=f"下午运行时间：{self.config.rpa_run_time.pm_start_text}-{self.config.rpa_run_time.pm_end_text}",
                                        on_click=self.event_handler,
                                        ref=self.pm_time_open_button,
                                        data={
                                            "event_name": "on_click_time_pick_dialog",
                                            "type": "open",
                                            "title_text": "下午运行时间",
                                            "time_range": "PM"
                                        },
                                    ),

                                ]
                            )
                        ),
                        ft.Divider(height=10),
                        ft.Container(
                            expand=True,
                            content=ft.Row(
                                expand=True,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                controls=[
                                    ft.Container(
                                        content=self.task_column.current,
                                    ),
                                    ft.VerticalDivider(width=10),
                                    ft.Container(
                                        expand=True,
                                        content=self.rpa_run_log.current,
                                    ),
                                ],
                            ),
                        ),
                    ]
                ),
            )
        ]
        # self.floating_action_button_location = ft.FloatingActionButtonLocation.CENTER_FLOAT
        self.floating_action_button = ft.FloatingActionButton(icon=ft.Icons.PLAY_ARROW_OUTLINED,
                                                              autofocus=True,
                                                              text="启动机器人", on_click=self.event_handler,
                                                              data={'event_name': 'rpa_run_set'}, ref=self.rpa_btn)
        return self
