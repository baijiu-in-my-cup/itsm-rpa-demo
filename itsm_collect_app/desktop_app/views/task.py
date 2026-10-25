from itsm_collect_app.schema import *
import flet as ft
from flet.core.types import OptionalControlEventCallable, ControlEvent
from itsm_collect_app.infrastructure.sql_api import SqlApi


class BasicDescColumn(ft.Column):
    def __init__(
            self,
            event_handler: Optional[OptionalControlEventCallable],
            data: Optional[List[Task]] = None,
            person_options: Optional[List[Person]] = None,
            *args,
            **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.isolated = True
        self.event_handler = event_handler
        self.data = not data or data[0]
        self.person_options = person_options

        self.task_desc = ft.Ref[ft.TextField]()
        self.submit_person = ft.Ref[ft.TextField]()
        self.submit_reply = ft.Ref[ft.TextField]()

    def build(self):
        _ = ft.TextField(
            ref=self.task_desc,
            value=not self.data or self.data.task_desc,
            label="任务描述",
            read_only=True,
        )
        _ = ft.TextField(
            ref=self.submit_person,
            value=not self.data or ','.join([p.name for p in self.data.submit_person]),
            label="提交人员",
            read_only=True,
        )
        # _ = ft.Dropdown(
        #     label='提交人员',
        #     ref=self.submit_person,
        #     value=not self.data or self.data.submit_person[-1],
        #     options=[
        #         ft.dropdown.Option(
        #             key=option.name,
        #             content=ft.Text(
        #                 value=f'{option.name}',
        #                 spans=[
        #                     ft.TextSpan('   '),
        #                     ft.TextSpan(
        #                         text='/'.join(option.department), style=ft.TextStyle(
        #                             size=12
        #                         )
        #                     )
        #                 ]
        #             )
        #         ) for option in self.person_options
        #     ]
        # )
        _ = ft.TextField(
            read_only=True,
            ref=self.submit_reply,
            value=not self.data or self.data.submit_reply,
            label="回复意见",
        )

        self.controls = [
            ft.Row(
                controls=[
                    ft.Container(content=self.task_desc.current, expand=1),
                    ft.Container(content=self.submit_person.current, expand=1),
                    ft.Container(content=self.submit_reply.current, expand=1),
                ]
            )
        ]


class ConditionDescColumn(ft.Column):
    def __init__(
            self,
            event_handler: Optional[OptionalControlEventCallable],
            data: Optional[List[Task]] = None,
            *args,
            **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.isolated = True
        self.event_handler = event_handler
        self.data: "FilterContent" = not data or data[0].condition
        self.key_to_desc = {"or": "或", "and": "与", True: "存在", False: "不存在"}

    def _build_sub_filter_content(
            self,
            data: Union[
                "FileFilterContent", "TrackTraceFilterContent", "WorkSheetFilterContent"
            ],
            level: int,
    ):
        container = ft.Container(
            margin=ft.margin.only(left=level * 15),
            content=ft.ListTile(
                title=ft.Text(
                    value='存在' if data.is_or_not else '不存在',
                    color=ft.Colors.BLACK if data.is_or_not else ft.Colors.RED,
                    selectable=True,
                    spans=[
                        ft.TextSpan(
                            text=" ",
                            spans=[
                                ft.TextSpan(text=k),
                                ft.TextSpan(text="："),
                                ft.TextSpan(text=str(v), style=ft.TextStyle(weight=ft.FontWeight.BOLD, )),
                                ft.TextSpan(text="  "),
                            ]
                        ) for k, v in data.model_dump(by_alias=True, exclude_none=True, exclude={'is_or_not'}).items() if v
                    ]
                ),
            )
        )
        return container

    def _build_filter_content(
            self,
            data: Union[
                "FilterContent",
                "FileFilterContent",
                "TrackTraceFilterContent",
                "WorkSheetFilterContent",
                "FeedFilterContent",
            ],
            level: int = 0,
    ):
        if type(data) in (
                FileFilterContent,
                TrackTraceFilterContent,
                WorkSheetFilterContent,
                FeedFilterContent,
        ):
            return self._build_sub_filter_content(data, level=level)

        col_container = ft.Container(
            margin=ft.margin.only(left=level * 15),
            content=ft.ExpansionTile(
                icon_color=ft.colors.GREEN,
                affinity=ft.TileAffinity.LEADING,
                visual_density=ft.VisualDensity.COMFORTABLE,
                maintain_state=True,
                initially_expanded=True,
                title=ft.Text(
                    value='判断关系',
                    selectable=True,
                    spans=[
                        ft.TextSpan(text=":"),
                        ft.TextSpan(
                            text=self.key_to_desc.get(data.filter_type, None),
                            style=ft.TextStyle(weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                        )
                    ]
                ),
            ),
        )
        for sub_filter in data.filter_content:
            col_container.content.controls.append(
                self._build_filter_content(sub_filter, level=level + 1)
            )
        return col_container

    def build(self):
        if not self.data:
            return
        self.controls = [self._build_filter_content(self.data, level=0)]


class TaskView(ft.View):
    def __init__(
            self,
            page: ft.Page,
            sql_api: SqlApi,
            show_error_banner: Callable[..., Coroutine[Any, Any, Any]],
            *args,
            **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.page = page
        self.sql_api = sql_api
        self.show_error_banner = show_error_banner
        self.basic_desc_col = ft.Ref[BasicDescColumn]()
        self.condition_desc_col = ft.Ref[ConditionDescColumn]()

    async def event_handler(self, e: ControlEvent):
        async def pack_up():
            ...

        event_handlers = {"pack_up": pack_up}
        event_name = e.control.data.get("event_name", "")
        if event_name in event_handlers:
            try:
                await event_handlers[event_name]()
            except Exception as error:
                await self.show_error_banner(error)

    async def async_build(self, task_id: str):
        task_data = await self.sql_api.get_task_data(task_id)
        _ = BasicDescColumn(
            event_handler=self.event_handler,
            data=task_data or task_data[0],
            ref=self.basic_desc_col,
        )
        _ = ConditionDescColumn(
            event_handler=self.event_handler,
            data=task_data or task_data[0],
            ref=self.condition_desc_col,
            scroll=ft.ScrollMode.AUTO,
        )
        self.controls.append(
            ft.Container(
                expand=True,
                content=ft.Column(
                    spacing=30,
                    controls=[
                        ft.Container(
                            content=self.basic_desc_col.current,
                        ),
                        ft.Container(
                            expand=True,
                            content=self.condition_desc_col.current,
                        ),
                    ],
                ),
            )
        )
        return self
