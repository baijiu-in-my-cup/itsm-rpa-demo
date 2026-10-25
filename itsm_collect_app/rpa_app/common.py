# type: ignore
from datetime import datetime
import pathlib
import random
import string
import re
from loguru import logger
import json
import os, sys
from typing import List, Dict, Any, Optional,Union
import requests

from itsm_collect_app.settings import Config
flet_app_log = logger.bind(name="flet_app_log")


# 可以考虑 放进 sqlite db 中
def load_data_from_file(file_name: str) -> Dict[str, Any]:
    """ Load data from local json file
    """
    with open(file_name, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data

def dump_data_to_file(data: any, file_name: str = 'dump.json'):
    """ Dumping data to local json file
    """
    logger.info(f'Dumping data to file: {file_name}')
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f'Data dumped to file: {file_name}')

def walk_document_files(directory: str, exclude=None) -> List[str]:
    if exclude is None:
        exclude = ['.ini']
    logger.debug(f"Start walking directory: {directory}")
    if directory is None or len(directory) == 0:
        raise ValueError("Directory is required")
    if not os.path.exists(directory):
        raise ValueError(f"Directory: {directory} not found")

    documents = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            file_ext = os.path.splitext(file)[-1].lower()
            if exclude and file_ext in exclude:
                continue
            documents.append(file_path)
    logger.debug(f"Finish walking directory: {directory}")
    logger.debug(f"Found {len(documents)} files in directory: {directory}")
    return documents


def create_file_name(file_type: str) -> str:
    name_prefix = str(datetime.now().date())
    name_prefix = name_prefix.replace("-", "")
    name_suffix = ''.join(random.sample(string.digits, 8))
    name = f'{name_prefix}{name_suffix}.{file_type}'
    return name


def run_time_to_day(config:Config,human_ack:bool=False) -> bool:
    current_year = datetime.now().year
    days_file_path = pathlib.Path(config.app.rpa_dir) / f"chinese-days/{current_year}.json"
    if not days_file_path.exists():
        flet_app_log.info("找不到当前节假日信息,尝试获取最新节假日信息")
        url = f"https://cdn.jsdelivr.net/npm/chinese-days/dist/years/{current_year}.json"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if "workdays" not in data or "workdays" not in data:
                raise ValueError("Invalid response data")
            days_file_path.parent.mkdir(parents=True, exist_ok=True)
            dump_data_to_file(data, days_file_path)
            flet_app_log.info("成功获取最新节假日信息")
        except Exception as e:
            flet_app_log.error(f"获取最新节假日信息失败: {e}")
    days = load_data_from_file(days_file_path)
    now = datetime.now()
    if not human_ack:
        today_str = now.date().strftime('%Y-%m-%d')
        if today_str in days.get('holidays', []):
            flet_app_log.debug('节假日，停止派单')
            return False
        if now.weekday() in [5, 6] and today_str not in days.get("workdays", []):
            flet_app_log.debug('周末且非调休日,停止派单')
            return False
    now_hour =now.time()
    if config.rpa_run_time.am_start < now_hour < config.rpa_run_time.am_end or config.rpa_run_time.pm_start < now_hour < config.rpa_run_time.pm_end:
        return True
    flet_app_log.warning("如需立刻运行,请修改【上午/下午运行时间】,然后重启机器人")
    return False


def str_match(pattern, text, strict=False):
    clean_pattern = re.sub(r"(?<!\d)[^\w](?!\d)", "", pattern)
    clean_text = re.sub(r"(?<!\d)[^\w](?!\d)", "", text)
    if strict is True:
        result = True if clean_pattern in clean_text else False
        logger.debug(f'严格匹配:{clean_pattern}?{clean_text} 结果= {result}')
        return result

    for char in clean_pattern:
        if char not in clean_text:
            logger.debug(f'模糊匹配:{clean_pattern}?{clean_text} 结果= {False}')
            return False
    logger.debug(f'模糊匹配:{pattern}?{text} 结果= {True}')
    return True


def str_match_enhance(pattern:Union[str,List[str]], text:str, strict=False)->bool:
    if isinstance(pattern,str):
        return str_match(pattern,text,strict)
    for p in pattern:
        if str_match(p, text, strict) is True:
            return True
    return False
