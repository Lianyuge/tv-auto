import requests
import re
from datetime import datetime, timezone, timedelta
import os
import sys
import logging
import base64
from logging.handlers import RotatingFileHandler
from collections import defaultdict

# ==================== 全局对象 ====================
logger = None
CONFIG = None

# ==================== 日志系统 ====================
def setup_logging():
    """配置日志系统"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_date = datetime.now().strftime('%Y%m%d')
    log_filename = f"{log_dir}/tv_auto_update_{log_date}.log"

    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    _logger = logging.getLogger('TVAutoUpdater')
    _logger.setLevel(logging.INFO)

    if _logger.handlers:
        _logger.handlers.clear()

    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', date_format))

    _logger.addHandler(file_handler)
    _logger.addHandler(console_handler)

    return _logger

# ==================== 配置部分 ====================
def get_config():
    """加载配置"""
    m3u_sources = []
    for i in range(1, 21):
        env_name = f"M3U_SOURCE_{i}"
        source_url = os.getenv(env_name)
        if source_url:
            m3u_sources.append(source_url)

    if not m3u_sources:
        logger.error("错误: 未在环境变量中找到任何M3U源URL")
        sys.exit(1)

    return {
        "m3u_sources": m3u_sources,
        "group_rules": {
            "央视吉林": 0,  
            "央视辽宁": 2,
        },
        "target_file": "index.html",
        "download_dir": "downloaded_sources",
        "special_groups": {
            "冰茶体育": {
                "source_index": 1,
                "new_group_name": "连宇体育",
                "position": "end"
            }
        },
        "update_channel": {
            "group_title": "更新时间",
            "fixed_link": "https://zhanglianyu.oss-cn-beijing.aliyuncs.com/new.mp4"
        },
        "channel_name_mapping": {
            "吉视都市": ["吉林都市", "吉视都市", "吉林电视台都市频道", "吉林都市频道"],
            "吉视生活": ["吉林生活", "吉视生活", "吉林电视台生活频道", "吉林生活频道"],
            "吉视影视": ["吉林影视", "吉视影视", "吉林电视台影视台", "吉林影视台"],
            "吉视综艺": ["吉林综艺", "吉视综艺", "吉林电视台综艺频道", "吉林综艺频道"],
            "吉视乡村": ["吉林乡村", "吉林电视台乡村频道", "吉林乡村频道"],
            "吉林东北": ["吉林东北", "吉视东北", "吉林电视台东北频道", "东北频道"],
            "吉林新闻": ["吉林新闻", "吉视新闻", "吉林电视台新闻频道", "新闻频道"],
            "吉林公共": ["吉林公共", "吉视公共", "吉林电视台公共频道", "公共频道"],
            "长春综合": ["长春综合", "CRT综合"],
            "长春文旅体育": ["长春娱乐", "CRT娱乐", "长春文旅体育"],
            "长春市民生活": ["长春市民", "CRT市民", "长春市民生活"],
            "辽宁都市1": ["100"],
            "辽宁影视剧1": ["101"],
            "辽宁教育青少1": ["102"],
            "辽宁生活1": ["103"],
            "辽宁公共1": ["104"],
            "辽宁北方1": ["105"],
            "辽宁经济1": ["106"],
            "辽宁体育休闲1": ["107"],
            "辽宁移动电视1": ["108"],
        },
        "jishi_rules": {
            "enabled": True,
            "source_index": 0, 
            "channel_prefixes": ["吉视", "吉林"],
            "groups": ["吉林本地"]
        }
    }

# ==================== 工具函数 ====================
def get_beijing_time():
    utc_time = datetime.now(timezone.utc)
    beijing_time = utc_time + timedelta(hours=8)
    return beijing_time

def normalize_channel_name(channel_name, channel_mapping):
    if not channel_mapping:
        return channel_name
    for standard_name, variants in channel_mapping.items():
        if channel_name in variants:
            return standard_name
    return channel_name

def extract_channel_name_from_extinf(line):
    if ',' not in line:
        return line.strip()
    parts = line.split(',')
    return parts[-1].strip()

def detect_file_format(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for _ in range(5):
                line = f.readline()
                if not line: break
                if line.strip().startswith('#EXTM3U'): return 'standard'
                if ',' in line and not line.startswith('#'): return 'simple'
        return 'unknown'
    except Exception:
        return 'unknown'

def is_jishi_channel(channel_name, group_title):
    jishi_config = CONFIG.get("jishi_rules", {})
    if not jishi_config.get("enabled", False):
        return False
    allowed_groups = jishi_config.get("groups", [])
    if allowed_groups and group_title not in allowed_groups:
        return False
    prefixes = jishi_config.get("channel_prefixes", [])
    normalized_name = normalize_channel_name(channel_name, CONFIG.get("channel_name_mapping", {}))
    for prefix in prefixes:
        if channel_name.startswith(prefix) or normalized_name.startswith(prefix):
            return True
    return False

# ==================== 核心下载解析 ====================
def download_m3u_files():
    if not os.path.exists(CONFIG["download_dir"]):
        os.makedirs(CONFIG["download_dir"])
    downloaded_files = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    for i, url in enumerate(CONFIG["m3u_sources"]):
        try:
            logger.info(f"正在下载源 {i + 1}...")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            filename = f"{CONFIG['download_dir']}/source_{i + 1}.m3u"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(response.text)
            downloaded_files.append(filename)
        except Exception as e:
            logger.error(f"  ✗ 下载源 {i + 1} 失败: {e}")
    return downloaded_files

def extract_channels(file_path, source_index):
    channels = []
    fmt = detect_file_format(file_path)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if fmt == 'standard':
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith('#EXTINF'):
                    name = extract_channel_name_from_extinf(line)
                    group = re.search(r'group-title="([^"]*)"', line)
                    group_title = group.group(1) if group else ""
                    if i + 1 < len(lines) and lines[i+1].strip() and not lines[i+1].startswith('#'):
                        channels.append({
                            'name': name, 'group': group_title, 'link': lines[i+1].strip(),
                            'extinf_line': line, 'source': source_index
                        })
        else: # Simple format
            for line in lines:
                line = line.strip()
                if line and ',' in line and not line.startswith('#'):
                    parts = line.split(',', 1)
                    name, link = parts[0].strip(), parts[1].strip()
                    channels.append({
                        'name': name, 'group': "未分类", 'link': link,
                        'extinf_line': f'#EXTINF:-1 group-title="未分类",{name}', 'source': source_index
                    })
    except Exception as e:
        logger.error(f"解析出错 {file_path}: {e}")
    return channels

def extract_special_group_channels(all_channels):
    special_channels = []
    for group_name, config in CONFIG["special_groups"].items():
        for channel in all_channels:
            if channel['group'] == group_name and channel['source'] == config["source_index"]:
                new_line = channel['extinf_line'].replace(f'group-title="{group_name}"', f'group-title="{config["new_group_name"]}"')
                special_channels.append({**channel, 'group': config["new_group_name"], 'extinf_line': new_line})
    return special_channels

def find_channel_by_rules(channel_name, group_title, all_channels):
    special_group_names = [config["new_group_name"] for config in CONFIG["special_groups"].values()]
    if group_title in special_group_names: return None

    normalized_target_name = normalize_channel_name(channel_name, CONFIG.get("channel_name_mapping", {}))

    # 规则1: 吉视频道优先从源1获取
    if is_jishi_channel(channel_name, group_title):
        target_source = CONFIG["jishi_rules"]["source_index"]
        for channel in all_channels:
            if normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {})) == normalized_target_name and channel['source'] == target_source:
                return channel

    # 规则2: 分组规则锁定
    if group_title in CONFIG["group_rules"]:
        target_source = CONFIG["group_rules"][group_title]
        for channel in all_channels:
            if normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {})) == normalized_target_name and channel['source'] == target_source:
                return channel

    # 规则3: 通用顺序查找
    for source_index in range(len(CONFIG["m3u_sources"])):
        for channel in all_channels:
            if normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {})) == normalized_target_name and channel['source'] == source_index:
                return channel
    return None

# ==================== 文件更新 ====================
def update_target_file(all_channels, special_channels):
    try:
        if not os.path.exists(CONFIG["target_file"]):
            with open(CONFIG["target_file"], 'w', encoding='utf-8') as f: f.write("#EXTM3U\n")

        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            lines = f.read().split('\n')

        new_lines = []
        updated_count = 0
        special_titles = [f"# {c['new_group_name']}分组" for c in CONFIG["special_groups"].values()]
        special_titles.append(f"# {CONFIG['update_channel']['group_title']}分组")
        
        in_skip_section = False
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.strip() in special_titles: in_skip_section = True
            if in_skip_section:
                if line.strip() == "" and i+1 < len(lines) and lines[i+1].strip() not in special_titles:
                    in_skip_section = False
                i += 1
                continue

            if line.startswith('#EXTINF'):
                name = extract_channel_name_from_extinf(line)
                group = re.search(r'group-title="([^"]*)"', line)
                group_title = group.group(1) if group else ""
                match = find_channel_by_rules(name, group_title, all_channels)
                
                new_lines.append(line)
                if match:
                    new_lines.append(match['link'])
                    updated_count += 1
                elif i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                    new_lines.append(lines[i+1])
                i += 1
            else:
                if line.strip(): new_lines.append(line)
            i += 1

        if not new_lines or not new_lines[0].startswith('#EXTM3U'): new_lines.insert(0, '#EXTM3U')

        # 重新添加特殊分组
        for sc in special_channels:
            new_lines.append(f"\n# {sc['group']}分组")
            new_lines.append(sc['extinf_line'])
            new_lines.append(sc['link'])

        # 更新时间
        update_group = CONFIG["update_channel"]["group_title"]
        new_lines.append(f"\n# {update_group}分组")
        new_lines.append(f'#EXTINF:-1 group-title="{update_group}",最后更新：{get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")}')
        new_lines.append(CONFIG["update_channel"]["fixed_link"])

        with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        logger.info(f"更新完成，处理了 {updated_count} 个常规频道")
    except Exception as e:
        logger.error(f"更新失败: {e}")

def main():
    global logger, CONFIG
    logger = setup_logging()
    CONFIG = get_config()
    
    files = download_m3u_files()
    all_channels = []
    for i, f in enumerate(files):
        all_channels.extend(extract_channels(f, i))
    
    special_channels = extract_special_group_channels(all_channels)
    update_target_file(all_channels, special_channels)

if __name__ == "__main__":
    main()
