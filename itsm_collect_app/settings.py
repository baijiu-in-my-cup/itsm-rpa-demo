from typing import Tuple,Any,Optional
from pydantic import BaseModel,Field
import configparser
import shutil
import datetime
import time
import os
import pathlib

cwd = os.path.dirname(os.path.dirname(__file__))
# static_dir=os.path.join(cwd, 'static')

class App(BaseModel):
    # database_url:str = f"sqlite+aiosqlite:///:memory:"
    title: str = 'ITSM 工单自动分派机器人'
    version: str = 'demo-v1.0'
    description: str = '配置驱动的 ITSM 工单规则匹配与自动分派 RPA demo'
    rpa_dir: str = os.path.join(cwd,'rpa-data')
    # 浏览器可执行文件路径:留空则使用 playwright 自带的 Chromium(python -m playwright install chromium)
    # 也可通过环境变量 ITSM_BROWSER_PATH 指定本机 Chrome/Edge
    executable_path: str = os.environ.get('ITSM_BROWSER_PATH', '')
    screenshots_path:str=os.path.join(rpa_dir,'screenshots')
    database_url:str=f'sqlite+aiosqlite:///{os.path.join(rpa_dir,"itsm.db")}'
    persons_path:str=os.path.join(rpa_dir,'person.json')
    tasks_dir:str=os.path.join(rpa_dir,'tasks')

    def model_post_init(self, __context:Any)->None:
        os.makedirs(self.rpa_dir, exist_ok=True)
        os.makedirs(self.screenshots_path, exist_ok=True)

        # for root, dirs, files in os.walk(static_dir):
        #     # 构建目标目录路径
        #     relative_path = os.path.relpath(root, static_dir)
        #     target_path = os.path.join(self.rpa_path, relative_path)
        #     os.makedirs(target_path, exist_ok=True)
        #
        #     for file in files:
        #         src_file = os.path.join(root, file)
        #         dst_file = os.path.join(target_path, file)
        #
        #         if os.path.exists(dst_file):
        #             print(f'跳过（已存在）: {dst_file}')
        #         else:
        #             try:
        #                 shutil.copy2(src_file, dst_file)
        #                 print(f'已复制: {src_file} -> {dst_file}')
        #             except Exception as e:
        #                 print(f'复制失败 {src_file}: {e}')
        #                 raise


class Itsm(BaseModel):
    name: str = ''
    base_url: str
    index_url: str
    feed_url:str
    gro_url: str
    per_url:str
    task_info_id_url: str
    get_file_list_url: str
    view_business_info: str

    user: str = ''
    pwd: str = ''

    def format_index_url(self):
        return 'GET', self.index_url.format(base_url=self.base_url)

    def format_view_business_info(self, business_key: str):
        data = {'business_key': business_key, 'base_url': self.base_url}
        return 'GET', self.view_business_info.format(**data)

    def format_get_file_list_url(self, business_key: str):
        data = {'business_key': business_key, 'time': int(time.time() * 100), 'base_url': self.base_url}
        return 'GET', self.get_file_list_url.format(**data)

    def format_get_feed_url(self, business_key: str):
        data = {'business_key': business_key, 'time': int(time.time() * 100), 'base_url': self.base_url}
        return 'GET', self.feed_url.format(**data)

    def format_gro_url(self, limit: int = 100) -> Tuple[str, str]:
        data = {'limit': limit, 'time': int(time.time() * 100), 'base_url': self.base_url}
        return 'GET', self.gro_url.format(**data)

    def format_per_url(self, limit: int = 100) -> Tuple[str, str]:
        data = {'limit': limit, 'time': int(time.time() * 100), 'base_url': self.base_url}
        return 'GET', self.per_url.format(**data)

    def format_task_info_id_url(self, task_info_id: str) -> Tuple[str, str]:
        return 'GET', self.task_info_id_url.format(task_info_id=task_info_id, base_url=self.base_url)


class RpaTimeConfig(BaseModel):
    """RPA 时间配置(demo 默认全天可跑,方便演示;生产环境可改为工作时段)"""
    am_start: datetime.time = Field(default_factory=lambda _ :datetime.time(hour=0), description="上午开始时间")
    am_end: datetime.time = Field(default_factory=lambda _ :datetime.time(hour=23, minute=59), description="上午结束时间")
    pm_start: datetime.time = Field(default_factory=lambda _ :datetime.time(hour=0), description="下午开始时间")
    pm_end: datetime.time = Field(default_factory=lambda _ :datetime.time(hour=23, minute=59), description="下午结束时间")

    @property
    def am_start_text(self) -> str:
        return self.am_start.strftime("%H:%M")
    @property
    def am_end_text(self) -> str:
        return self.am_end.strftime('%H:%M')
    @property
    def pm_start_text(self) -> str:
        return self.pm_start.strftime('%H:%M')
    @property
    def pm_end_text(self) -> str:
        return self.pm_end.strftime('%H:%M')

class Config(BaseModel):
    app: App = App()
    rpa_run_time:RpaTimeConfig=Field(default_factory=lambda _ : RpaTimeConfig())
    itsm:Optional[Itsm]=None

    def model_post_init(self, __context: Any) -> None:
        config_ini_path = os.path.join(self.app.rpa_dir, 'config.ini')
        _config = configparser.ConfigParser()
        _config.read(config_ini_path, encoding='utf-8-sig')
        self.itsm=Itsm(**dict(_config.items('Itsm')))
