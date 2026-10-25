import flet as ft
from flet.core.page import RouteChangeEvent, ViewPopEvent, ControlEvent
from loguru import logger
from itsm_collect_app.desktop_app.views.index import IndexView
from itsm_collect_app.desktop_app.views.record_log import RecordLogView
from itsm_collect_app.desktop_app.views.task import TaskView
from itsm_collect_app.settings import Config
from itsm_collect_app.infrastructure.sql_api import SqlApi


class DesktopApp:
    def __init__(self, page: ft.Page, sql_api: SqlApi,config:Config):
        self.page = page
        self.page.auto_update = True
        self.sql_api = sql_api
        self.config=config
        self.navigation_bar = ft.NavigationBar(
            on_change=self.view_route_change,
            data={'event_name': 'nav_change'},
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.SETTINGS_SUGGEST_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS_SUGGEST,
                    label="运行设置",
                    data={'route': '/rparun'}
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.BOOKMARK_BORDER,
                    selected_icon=ft.Icons.BOOKMARK,
                    label="工单记录",
                    data={'route': '/recordlog'}
                ),
            ]
        )

    async def show_error_banner(self, error):
        banner = ft.Banner(
            bgcolor=ft.colors.AMBER_100,
            content=ft.Text(
                value=f'{error}!',
            ),
            actions=[
                ft.TextButton(text="确认", on_click=lambda _: self.page.close(banner)),
            ]
        )
        self.page.open(banner)

    async def view_route_change(self, e: ControlEvent):
        selected_index = e.control.selected_index
        selected_route = e.control.destinations[selected_index].data['route']
        if selected_route != self.page.route:
            await self.page.go_async(selected_route)

    async def route_change(self, route: RouteChangeEvent):
        logger.debug(f'flet web app route change:{route.route}')
        troute = ft.TemplateRoute(route.route)
        route_views = [view for view in self.page.views if view.route == troute.route]
        if route_views:
            self.page.views.remove(route_views[0])
            self.page.views.append(route_views[0])
        elif troute.match('/rparun'):
            self.navigation_bar.selected_index = 0
            self.page.views.append(
                await IndexView(self.page, self.sql_api, route='/rparun', navigation_bar=self.navigation_bar,
                                show_error_banner=self.show_error_banner,config=self.config).async_build()
            )
        elif troute.match('/recordlog'):
            self.navigation_bar.selected_index = 1
            self.page.views.append(
                await RecordLogView(self.page, self.sql_api, route='/recordlog', navigation_bar=self.navigation_bar,
                                    show_error_banner=self.show_error_banner).async_build()
            )
        elif troute.match("/task/:task_id/:task_desc"):
            self.page.views.append(
                await TaskView(
                    self.page, self.sql_api, route=troute.route,
                    show_error_banner=self.show_error_banner,
                    controls=[
                        ft.AppBar(title=ft.Text(troute.task_desc), bgcolor=ft.colors.GREEN_100),
                    ]
                ).async_build(troute.task_id)
            )
        await self.page.update_async()

    async def view_pop(self, e: ViewPopEvent):
        self.page.views.pop()
        top_view = self.page.views[-1]
        await self.page.go_async(top_view.route)

    async def on_disconnect(self,e):
        await self.sql_api.dump_person_data()

    async def build(self):
        self.page.window.maximized = True
        self.page.on_disconnect  = self.on_disconnect
        self.page.on_route_change = self.route_change
        self.page.on_view_pop = self.view_pop
        await self.page.go_async('/rparun')


