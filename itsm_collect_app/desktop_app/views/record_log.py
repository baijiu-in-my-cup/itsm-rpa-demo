from itsm_collect_app.schema import *
import flet as ft
from flet.core.types import OptionalControlEventCallable, ControlEvent
from flet.core.datatable import DataColumnSortEvent
from itsm_collect_app.infrastructure.sql_api import SqlApi
from loguru import logger
from itsm_collect_app.rpa_app.errors import IgnoreError
from collections import defaultdict
from datetime import datetime
import asyncio


class FilterColumn(ft.Column):
    def __init__(self, event_handler: Optional[OptionalControlEventCallable],
                 dropdown_options: Optional[List[str]] = None, *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.isolated = True
        self.event_handler = event_handler
        self.dropdown_options = dropdown_options
        self.search_code = ft.Ref[ft.TextField]()
        self.search_desc = ft.Ref[ft.Dropdown]()
        self.search_time = ft.Ref[ft.RadioGroup]()

    def build(self):
        _ = ft.TextField(
            ref=self.search_code, label='工单编号',
        )
        _ = ft.Dropdown(
            label="处理类型",
            ref=self.search_desc,
            options=[
                ft.dropdown.Option(key=option, text=option) for option in self.dropdown_options or []
            ],
        )

        _ = ft.RadioGroup(
            ref=self.search_time,
            value='NOW',
            content=ft.Row(
                controls=[
                    ft.Radio(value="NOW", label="今天"),
                    ft.Radio(value="ALL", label="全部")
                ]
            )
        )
        self.controls = [
            ft.Row(
                controls=[
                    self.search_code.current, self.search_desc.current, self.search_time.current,
                    ft.OutlinedButton(text="搜索", on_click=self.event_handler,
                                      data={'event_name': 'update_data'}, ),
                    ft.OutlinedButton(text="重置", on_click=self.event_handler,
                                      data={'event_name': 'reset_data'}, ),
                ]
            ),
        ]

    def before_update(self):
        self.build()


class RecordLogColumn(ft.Column):
    def __init__(self, event_handler: Optional[OptionalControlEventCallable], data: Optional[RecordLogItems] = None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.isolated = True
        self.data: RecordLogItems = data or RecordLogItems()
        self.event_handler = event_handler
        self.list_view = ft.Ref[ft.ListView]()
        self.add_up = ft.Ref[ft.Text]()

    def build(self):
        _ = ft.Text(
            ref=self.add_up,
            value=f'总计：{self.data.total}        ',
            weight=ft.FontWeight.BOLD,
            spans=[
                ft.TextSpan(
                    text=f'{item.task_desc}:{item.count}      '
                ) for item in self.data.task_count
            ], selectable=True
        )
        _ = ft.ListView(
            ref=self.list_view,
            expand=True,
        )
        if self.data and self.data.data:
            self.list_view.current.controls = [
                ft.Container(
                    border=ft.border.only(bottom=ft.BorderSide(width=1)),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                expand=1,
                                content=ft.Text(
                                    value=datetime.strftime(row.create_time, "%Y-%m-%d %H:%M:%S.%f")[:-3],
                                    selectable=True)),
                            ft.Container(
                                expand=1,
                                content=ft.Text(value=row.submit_name, selectable=True)),
                            ft.Container(
                                expand=1,
                                content=ft.Text(value=row.business_key, selectable=True)),
                            ft.Container(expand=1, content=ft.Text(value=row.task_desc, selectable=True)),
                            ft.Container(expand=9, content=ft.Text(value=row.order_desc, selectable=True)),
                            # ft.Container(
                            #     tooltip='鼠标滑轮缩放',
                            #     expand=9, content=ft.InteractiveViewer(
                            #         min_scale=0.1,
                            #         max_scale=15,
                            #         content=ft.Image(src_base64=row.screenshot_base64 if row.screenshot_base64 else ""),
                            #     )
                            # )
                        ]
                    )
                ) for row in self.data.data
            ]

        self.controls = [
            self.add_up.current,
            ft.Container(
                border=ft.border.only(bottom=ft.BorderSide(width=2)),
                content=ft.Row(
                    controls=[
                        ft.Container(expand=1, content=ft.Text("提交时间", selectable=True)),
                        ft.Container(expand=1, content=ft.Text("提交人", selectable=True)),
                        ft.Container(expand=1, content=ft.Text("工单编号", selectable=True)),
                        ft.Container(expand=1, content=ft.Text("任务描述", selectable=True)),
                        ft.Container(expand=9, content=ft.Text("需求描述", selectable=True)),
                        # ft.Container(expand=9, content=ft.Text("表格截图", selectable=True)),
                    ]
                )
            ),
            self.list_view.current,
        ]

    def before_update(self):
        self.build()


class PieChartColumn(ft.Column):
    def __init__(self, event_handler: Optional[OptionalControlEventCallable], data: Optional[List[Task]] = None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.isolated = True
        self.data = data
        self.event_handler = event_handler

    def build(self):
        if not self.data:
            return
        colors = [ft.Colors.BLUE, ft.Colors.GREEN, ft.Colors.PINK, ft.Colors.YELLOW, ft.Colors.PURPLE, ]
        sections = []
        total = 0
        normal_title_style = ft.TextStyle(
            size=18, color=ft.Colors.BLACK, weight=ft.FontWeight.BOLD
        )
        for index, row in enumerate(self.data):
            sections.append(ft.PieChartSection(
                value=row.total,
                title=f'{row.task_desc}:{row.total}',
                badge_position=0.98,
                color=colors[index % len(colors)],
                title_style=normal_title_style
            ))
            total += row.total

        self.controls = [
            ft.Text(
                value=f'总计：{total}',
                size=30,
                weight=ft.FontWeight.BOLD,
            ),
            ft.PieChart(
                sections=sections,
                sections_space=1,
            )
        ]

    def before_update(self):
        self.build()


class RecordLogView(ft.View):
    def __init__(self, page: ft.Page, sql_api: SqlApi, show_error_banner: Callable[..., Coroutine[Any, Any, Any]],
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = page
        self.sql_api = sql_api
        self.show_error_banner = show_error_banner
        self.record_log_column = ft.Ref[RecordLogColumn]()
        self.filter_column = ft.Ref[FilterColumn]()

    def did_mount(self):
        self.running = True
        self.page.run_task(self.update_data)

    def will_unmount(self):
        self.running = False

    async def update_data(self):
        while self.running:
            business_key = self.filter_column.current.search_code.current.value or ''
            task_desc = self.filter_column.current.search_desc.current.value or ''
            now_date = None
            if self.filter_column.current.search_time.current.value == 'NOW':
                now_date = datetime.now().date()
            record_log_data = await self.sql_api.get_record_log(business_key, task_desc, now_date, now_date)
            self.record_log_column.current.data = record_log_data
            await self.record_log_column.current.update_async()
            await asyncio.sleep(60)

    async def event_handler(self, e: ControlEvent):
        async def update_data():
            business_key = self.filter_column.current.search_code.current.value or ''
            task_desc = self.filter_column.current.search_desc.current.value or ''
            now_date = None
            if self.filter_column.current.search_time.current.value == 'NOW':
                now_date = datetime.now().date()
            record_log_data = await self.sql_api.get_record_log(business_key, task_desc, now_date, now_date)
            self.record_log_column.current.data = record_log_data
            await self.record_log_column.current.update_async()

        async def reset_data():
            record_log_data = await self.sql_api.get_record_log()
            self.record_log_column.current.data = record_log_data
            await self.filter_column.current.update_async()
            await self.record_log_column.current.update_async()

        event_handlers = {
            'update_data': update_data,
            'reset_data': reset_data,
        }
        event_name = e.control.data.get('event_name', '')
        if event_name in event_handlers:
            try:
                await event_handlers[event_name]()
            except Exception as error:
                await self.show_error_banner(error)

    async def async_build(self):
        task_data = await self.sql_api.get_task_data()
        record_log_data = await self.sql_api.get_record_log()
        task_options = [item.task_desc for item in task_data]
        _ = FilterColumn(event_handler=self.event_handler, dropdown_options=task_options, ref=self.filter_column, )
        _ = RecordLogColumn(data=record_log_data, event_handler=self.event_handler, ref=self.record_log_column,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        self.controls = [
            ft.Container(
                expand=True,
                content=ft.Column(
                    controls=[
                        self.filter_column.current,
                        self.record_log_column.current
                    ]
                )
            )
        ]
        return self
