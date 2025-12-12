import requests
import re
from datetime import datetime, timezone, timedelta
import os
import sys
import logging
import time
import base64
import shutil
from logging.handlers import RotatingFileHandler
from collections import defaultdict

# ==================== 全局对象 ====================
logger = None
CONFIG = None

# ==================== 日志系统 (最先初始化) ====================
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
        logger.error("错误: 未在环境变量中找到任何M3U源URL (M3U_SOURCE_1 等)")
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
        "migu_sports": {
            "source_index": 3,
            "migu_pattern": r"咪咕体育-\d{8}",
            "groups": {
                "today": "今日咪咕",
                "yesterday": "咪咕体育回看", 
                "tomorrow": "咪咕体育预告",
                "other": "咪咕体育其他"
            }
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
            "长春娱乐": ["长春娱乐", "CRT娱乐"],
            "长春市民": ["长春市民", "CRT市民"],
            
        },
        # 吉视相关频道规则：这些频道统一从源1获取
        "jishi_rules": {
            "enabled": True,
            "source_index": 0,  # 源1
            "channel_prefixes": ["吉视", "吉林"],  # 匹配频道名前缀
            "groups": ["吉林本地"]  # 只在指定分组中生效
        },
        "proxy_config": {
            "enabled": True,
            "worker_url": "https://link.dzpp.uk",
            "access_key": "Ff905113",
            "encryption_key": "Ff905113%"
        }
    }

# ==================== 工具函数 ====================
def get_beijing_time():
    """获取北京时间"""
    utc_time = datetime.now(timezone.utc)
    beijing_time = utc_time + timedelta(hours=8)
    return beijing_time

def normalize_channel_name(channel_name, channel_mapping):
    """标准化频道名称"""
    if not channel_mapping:
        return channel_name
    for standard_name, variants in channel_mapping.items():
        if channel_name in variants:
            return standard_name
    return channel_name

def parse_migu_date_from_header(header_line):
    """从咪咕体育分组标题行提取日期"""
    match = re.search(r'咪咕体育-(\d{8})', header_line)
    if match:
        date_str = match.group(1)
        try:
            return datetime.strptime(date_str, '%Y%m%d').date()
        except ValueError:
            return None
    return None

def classify_migu_date(channel_date, beijing_date):
    """根据日期对咪咕体育频道进行分类"""
    if not channel_date:
        return "other"
    
    date_diff = (channel_date - beijing_date.date()).days
    
    if date_diff == 0:
        return "today"
    elif date_diff == -1:
        return "yesterday"
    elif date_diff == 1:
        return "tomorrow"
    else:
        return "other"

def extract_channel_name_from_extinf(line):
    """从#EXTINF行提取频道名称"""
    if ',' not in line:
        return line.strip()
    
    parts = line.split(',')
    channel_info = parts[-1].strip()
    
    return channel_info

def encrypt_url(url, key):
    """加密URL（XOR + Base64）"""
    try:
        key_bytes = key.encode('utf-8')
        url_bytes = url.encode('utf-8')
        encrypted = bytearray()
        for i in range(len(url_bytes)):
            encrypted.append(url_bytes[i] ^ key_bytes[i % len(key_bytes)])
        return base64.urlsafe_b64encode(encrypted).decode('utf-8')
    except Exception as e:
        logger.error(f"加密URL时出错: {e}")
        return None

def detect_file_format(file_path):
    """检测M3U文件格式"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_lines = []
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                first_lines.append(line.strip())
        
        for line in first_lines:
            if line.startswith('#EXTM3U'):
                return 'standard'
        
        for line in first_lines:
            if line and not line.startswith('#') and ',' in line:
                parts = line.split(',', 1)
                if len(parts) == 2:
                    link = parts[1].strip()
                    if link.startswith('http'):
                        return 'simple'
        
        return 'unknown'
    
    except Exception as e:
        logger.error(f"检测文件格式时出错 {file_path}: {e}")
        return 'unknown'

def is_jishi_channel(channel_name, group_title):
    """判断是否为吉视相关频道"""
    jishi_config = CONFIG.get("jishi_rules", {})
    if not jishi_config.get("enabled", False):
        return False
    
    # 检查分组是否在指定分组中
    allowed_groups = jishi_config.get("groups", [])
    if allowed_groups and group_title not in allowed_groups:
        return False
    
    # 检查频道名前缀
    prefixes = jishi_config.get("channel_prefixes", [])
    for prefix in prefixes:
        if channel_name.startswith(prefix):
            return True
    
    # 检查标准化后的名称是否在映射表中
    normalized_name = normalize_channel_name(channel_name, CONFIG.get("channel_name_mapping", {}))
    for prefix in prefixes:
        if normalized_name.startswith(prefix):
            return True
    
    return False

# ==================== 核心功能函数 ====================
def download_m3u_files():
    """下载所有m3u文件"""
    if not os.path.exists(CONFIG["download_dir"]):
        os.makedirs(CONFIG["download_dir"])

    downloaded_files = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    for i, url in enumerate(CONFIG["m3u_sources"]):
        try:
            safe_url = url.split('?')[0] if '?' in url else url
            logger.info(f"正在下载源 {i + 1}: {safe_url}...")

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            filename = f"{CONFIG['download_dir']}/source_{i + 1}_{datetime.now().strftime('%Y%m%d')}.m3u"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(response.text)
            downloaded_files.append(filename)
            logger.info(f"  ✓ 成功下载源 {i + 1}")

        except requests.exceptions.Timeout:
            logger.error(f"  ✗ 下载源 {i + 1} 超时: {url.split('?')[0]}...")
        except requests.exceptions.RequestException as e:
            logger.error(f"  ✗ 下载源 {i + 1} 失败: {e}")
        except Exception as e:
            logger.error(f"  ✗ 处理源 {i + 1} 时发生未知错误: {e}")

    return downloaded_files

def extract_all_channels_from_m3u(file_path, source_index):
    """从标准M3U文件中提取所有频道信息"""
    channels = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')

        for i in range(len(lines) - 1):
            line = lines[i]
            if line.startswith('#EXTINF'):
                if ',' in line:
                    channel_name = extract_channel_name_from_extinf(line)
                    
                    group_match = re.search(r'group-title="([^"]*)"', line)
                    group_title = group_match.group(1) if group_match else ""

                    if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                        link = lines[i + 1].strip()
                        channels.append({
                            'name': channel_name,
                            'group': group_title,
                            'link': link,
                            'extinf_line': line,
                            'source': source_index,
                        })

    except Exception as e:
        logger.error(f"解析文件 {file_path} 时出错: {e}")

    return channels

def extract_simple_format_channels(file_path, source_index, default_group="吉林本地"):
    """解析简化格式的M3U文件（频道名,链接）"""
    channels = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        logger.info(f"开始解析简化格式文件 {os.path.basename(file_path)}，共 {len(lines)} 行")
        
        seen_channels = set()
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if ',' in line:
                parts = line.split(',', 1)
                if len(parts) == 2:
                    channel_name, link = parts[0].strip(), parts[1].strip()
                    
                    if not link.startswith('http'):
                        continue
                    
                    normalized_name = normalize_channel_name(
                        channel_name, 
                        CONFIG.get("channel_name_mapping", {})
                    )
                    
                    channel_key = f"{normalized_name}_{source_index}"
                    if channel_key in seen_channels:
                        continue
                    
                    seen_channels.add(channel_key)
                    
                    extinf_line = f'#EXTINF:-1 group-title="{default_group}",{normalized_name}'
                    
                    if "吉林" in normalized_name or "吉视" in normalized_name:
                        logo_name = normalized_name.replace("吉林", "吉视").replace("电视台", "").replace("频道", "")
                        logo_url = f"https://tu.dzpp.uk/tv/{logo_name}.png"
                        extinf_line = f'#EXTINF:-1 tvg-id="{normalized_name}" tvg-name="{normalized_name}" tvg-logo="{logo_url}" group-title="{default_group}",{normalized_name}'
                    
                    channels.append({
                        'name': normalized_name,
                        'group': default_group,
                        'link': link,
                        'extinf_line': extinf_line,
                        'source': source_index,
                        'original_name': channel_name,
                        'format': 'simple'
                    })
        
        logger.info(f"从简化格式中解析出 {len(channels)} 个频道")
        
        if channels:
            logger.debug(f"频道示例: {channels[0]['name']} -> {channels[0]['link'][:60]}...")
        
    except Exception as e:
        logger.error(f"解析简化格式文件 {file_path} 时出错: {e}", exc_info=True)
    
    return channels

def extract_migu_sports_channels_from_file(file_path, source_index):
    """从源文件提取咪咕体育频道"""
    migu_config = CONFIG.get("migu_sports")
    if not migu_config or source_index != migu_config["source_index"]:
        return {}
    
    beijing_time = get_beijing_time()
    groups = migu_config["groups"]
    
    classified_channels = defaultdict(list)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        logger.info(f"开始解析源文件: {os.path.basename(file_path)}，共 {len(lines)} 行")
        
        current_migu_date = None
        current_category = None
        current_group_name = None
        
        i = 0
        migu_channels_found = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            migu_match = re.search(r'咪咕体育-(\d{8})', line)
            if migu_match and '#genre#' in line:
                date_str = migu_match.group(1)
                try:
                    current_migu_date = datetime.strptime(date_str, '%Y%m%d').date()
                    current_category = classify_migu_date(current_migu_date, beijing_time)
                    current_group_name = groups.get(current_category, groups["other"])
                    
                    logger.info(f"发现咪咕体育分组: {line} -> 日期: {current_migu_date}, 分类: {current_category}, 分组: {current_group_name}")
                    i += 1
                    continue
                except ValueError:
                    current_migu_date = None
            
            if current_migu_date and ',' in line and not line.startswith('#'):
                parts = line.split(',', 1)
                if len(parts) == 2:
                    channel_name, link = parts[0].strip(), parts[1].strip()
                    
                    if link.startswith('http'):
                        extinf_line = f'#EXTINF:-1 group-title="{current_group_name}",{channel_name}'
                        
                        final_link = link
                        proxy_config = CONFIG.get("proxy_config", {})
                        
                        if proxy_config.get("enabled", False) and "migu.lifit.uk" in link:
                            worker_url = proxy_config.get("worker_url", "")
                            access_key = proxy_config.get("access_key", "")
                            encryption_key = proxy_config.get("encryption_key", "")
                            
                            if worker_url and access_key and encryption_key:
                                encrypted_token = encrypt_url(link, encryption_key)
                                if encrypted_token:
                                    final_link = f"{worker_url}/?t={encrypted_token}&k={access_key}"
                                    logger.debug(f"已将咪咕链接替换为代理链接: {channel_name[:30]}...")
                        
                        classified_channels[current_group_name].append({
                            'name': channel_name,
                            'group': current_group_name,
                            'link': final_link,
                            'extinf_line': extinf_line,
                            'source': source_index,
                            'migu_date': current_migu_date,
                            'category': current_category
                        })
                        
                        migu_channels_found += 1
            
            i += 1
        
        logger.info(f"从文件 {os.path.basename(file_path)} 解析出 {migu_channels_found} 个咪咕体育频道")
        
        for group_name, channels in classified_channels.items():
            logger.info(f"  - {group_name}: {len(channels)} 个频道")
        
        return dict(classified_channels)
    
    except Exception as e:
        logger.error(f"解析咪咕体育文件 {file_path} 时出错: {e}", exc_info=True)
        return {}

def extract_special_group_channels(all_channels):
    """提取特殊分组的频道（冰茶体育）"""
    special_channels = []

    for group_name, config in CONFIG["special_groups"].items():
        source_index = config["source_index"]
        new_group_name = config["new_group_name"]

        for channel in all_channels:
            if channel['group'] == group_name and channel['source'] == source_index:
                new_extinf_line = channel['extinf_line'].replace(
                    f'group-title="{group_name}"',
                    f'group-title="{new_group_name}"'
                )

                special_channels.append({
                    'name': channel['name'],
                    'group': new_group_name,
                    'link': channel['link'],
                    'extinf_line': new_extinf_line,
                    'source': channel['source'],
                    'original_group': group_name
                })

        count = len([c for c in special_channels if c['original_group'] == group_name])
        logger.info(f"从源{source_index + 1}找到 {count} 个'{group_name}'频道，将重命名为'{new_group_name}'")

    return special_channels

def extract_migu_sports_channels(all_channels, downloaded_files):
    """整合咪咕体育频道"""
    migu_config = CONFIG.get("migu_sports")
    if not migu_config:
        logger.info("未配置咪咕体育分组")
        return {}
    
    source_index = migu_config["source_index"]
    
    migu_file = None
    for file_path in downloaded_files:
        if f"source_{source_index + 1}_" in file_path:
            migu_file = file_path
            break
    
    if not migu_file:
        logger.warning(f"未找到源{source_index + 1}的下载文件")
        return {}
    
    return extract_migu_sports_channels_from_file(migu_file, source_index)

def extract_target_channels():
    """从目标文件中提取所有频道信息"""
    target_channels = []

    try:
        if not os.path.exists(CONFIG["target_file"]):
            logger.info(f"目标文件 {CONFIG['target_file']} 不存在，将创建新文件。")
            return target_channels

        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')

        for i in range(len(lines) - 1):
            line = lines[i]
            if line.startswith('#EXTINF'):
                channel_name = extract_channel_name_from_extinf(line)
                group_match = re.search(r'group-title="([^"]*)"', line)
                group_title = group_match.group(1) if group_match else ""

                if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                    link = lines[i + 1].strip()
                    target_channels.append({
                        'name': channel_name,
                        'group': group_title,
                        'link': link,
                        'extinf_line': line
                    })

        logger.info(f"从目标文件中读取了 {len(target_channels)} 个待更新频道")

    except Exception as e:
        logger.error(f"解析目标文件时出错: {e}")

    return target_channels

def find_channel_by_rules(channel_name, group_title, all_channels):
    """根据规则查找匹配的频道"""
    special_group_names = [config["new_group_name"] for config in CONFIG["special_groups"].values()]
    if group_title in special_group_names:
        return None

    migu_config = CONFIG.get("migu_sports")
    if migu_config and group_title in migu_config["groups"].values():
        return None

    normalized_target_name = normalize_channel_name(channel_name, CONFIG.get("channel_name_mapping", {}))

    # 规则1: 如果是吉视相关频道，从源1获取
    if is_jishi_channel(channel_name, group_title):
        target_source = CONFIG["jishi_rules"]["source_index"]
        for channel in all_channels:
            normalized_source_name = normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {}))
            if normalized_source_name == normalized_target_name and channel['source'] == target_source:
                if channel['name'] != channel_name:
                    logger.debug(f"吉视频道匹配: 目标'{channel_name}' -> 源'{channel['name']}' (标准化为 '{normalized_target_name}')")
                return channel

    # 规则2: 如果分组在规则中，从指定源查找
    if group_title in CONFIG["group_rules"]:
        target_source = CONFIG["group_rules"][group_title]
        for channel in all_channels:
            normalized_source_name = normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {}))
            if normalized_source_name == normalized_target_name and channel['source'] == target_source:
                if channel['name'] != channel_name:
                    logger.debug(f"分组规则匹配: 目标'{channel_name}' -> 源'{channel['name']}' (标准化为 '{normalized_target_name}')")
                return channel

    # 规则3: 其他频道从所有源中按顺序查找
    for source_index in range(len(CONFIG["m3u_sources"])):
        for channel in all_channels:
            normalized_source_name = normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {}))
            if normalized_source_name == normalized_target_name and channel['source'] == source_index:
                if channel['name'] != channel_name:
                    logger.debug(f"通用匹配: 目标'{channel_name}' -> 源'{channel['name']}' (标准化为 '{normalized_target_name}')")
                return channel

    return None

def update_target_file(all_channels, target_channels, special_channels, migu_channels):
    """更新目标文件中的链接"""
    try:
        logger.info("开始更新目标文件 index.html ...")

        if not os.path.exists(CONFIG["target_file"]):
            logger.warning("目标文件不存在，将创建新文件")
            with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")

        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()

        updated_count = 0
        lines = content.split('\n')
        new_lines = []
        
        special_group_titles = []
        
        for group_name, config in CONFIG["special_groups"].items():
            special_group_titles.append(f"# {config['new_group_name']}分组")
        
        migu_config = CONFIG.get("migu_sports")
        if migu_config:
            for group_name in migu_config["groups"].values():
                special_group_titles.append(f"# {group_name}分组")
        
        update_group_name = CONFIG["update_channel"]["group_title"]
        special_group_titles.append(f"# {update_group_name}分组")
        
        in_special_group = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if line.strip() in special_group_titles:
                in_special_group = True
                i += 1
                continue
                
            if in_special_group:
                if line.strip() == "":
                    if i + 1 < len(lines) and lines[i + 1].strip() in special_group_titles:
                        i += 1
                        continue
                    else:
                        in_special_group = False
                else:
                    i += 1
                    continue
            
            if line.startswith('#EXTINF'):
                channel_name = extract_channel_name_from_extinf(line)
                group_match = re.search(r'group-title="([^"]*)"', line)
                group_title = group_match.group(1) if group_match else ""

                matched_channel = find_channel_by_rules(channel_name, group_title, all_channels)

                if matched_channel:
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        old_link = lines[i + 1]
                        new_link = matched_channel['link']

                        if old_link != new_link:
                            logger.info(f"更新 '{channel_name}' [{group_title}] (来自源{matched_channel['source'] + 1})")
                            new_lines.append(line)
                            new_lines.append(new_link)
                            updated_count += 1
                        else:
                            new_lines.append(line)
                            new_lines.append(old_link)

                        i += 1
                    else:
                        new_link = matched_channel['link']
                        new_lines.append(line)
                        new_lines.append(new_link)
                        logger.info(f"添加 '{channel_name}' [{group_title}] (来自源{matched_channel['source'] + 1})")
                        updated_count += 1
                else:
                    new_lines.append(line)
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        new_lines.append(lines[i + 1])
                        i += 1
            else:
                new_lines.append(line)

            i += 1

        if not new_lines or not new_lines[0].startswith('#EXTM3U'):
            new_lines.insert(0, '#EXTM3U')
        
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")

        if special_channels:
            new_lines.append(f"# {CONFIG['special_groups']['冰茶体育']['new_group_name']}分组")
            for channel in special_channels:
                new_lines.append(channel['extinf_line'])
                new_lines.append(channel['link'])
                logger.info(f"添加特殊分组: '{channel['name']}' [{channel['group']}]")
                updated_count += 1
            new_lines.append("")
        
        if migu_channels:
            for group_name, channels in migu_channels.items():
                if channels:
                    new_lines.append(f"# {group_name}分组")
                    for channel in channels:
                        if 'extinf_line' in channel:
                            new_lines.append(channel['extinf_line'])
                        else:
                            extinf_line = f'#EXTINF:-1 group-title="{channel["group"]}",{channel["name"]}'
                            new_lines.append(extinf_line)
                        
                        new_lines.append(channel['link'])
                        logger.info(f"添加咪咕分组: '{channel['name']}' [{channel['group']}]")
                        updated_count += 1
                    new_lines.append("")
        
        beijing_time = get_beijing_time()
        beijing_time_str = beijing_time.strftime('%Y-%m-%d %H:%M:%S')
        update_channel_name = f"最后更新: {beijing_time_str} (北京时间)"

        new_lines.append(f"# {update_group_name}分组")
        new_lines.append(
            f'#EXTINF:-1 tvg-id="update" tvg-name="update" tvg-logo="" group-title="{update_group_name}",{update_channel_name}')
        new_lines.append(CONFIG["update_channel"]["fixed_link"])

        logger.info(f"添加更新时间频道: {update_channel_name}")

        with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))

        logger.info(f"文件更新完成，共处理 {updated_count} 个频道")

    except Exception as e:
        logger.error(f"更新目标文件时出错: {e}", exc_info=True)
        raise

# ==================== 主程序 ====================
def main():
    global logger, CONFIG
    start_time = time.time()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("开始执行直播源自动更新任务")
    logger.info(f"启动时间 (北京时间): {get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        CONFIG = get_config()
        logger.info(f"已加载配置，共有 {len(CONFIG['m3u_sources'])} 个源地址")

        if CONFIG.get("channel_name_mapping"):
            logger.info("已启用频道名称映射")

        target_channels = extract_target_channels()

        downloaded_files = download_m3u_files()

        if not downloaded_files:
            logger.error("没有成功下载任何文件，任务终止")
            return

        all_channels = []
        
        for source_index, file_path in enumerate(downloaded_files):
            file_format = detect_file_format(file_path)
            
            if file_format == 'simple':
                logger.info(f"检测到源{source_index + 1}为简化格式，使用简化格式解析器")
                default_group = "吉林本地"
                
                if source_index == 8:
                    default_group = "吉林本地"
                
                channels = extract_simple_format_channels(file_path, source_index, default_group)
            elif file_format == 'standard':
                logger.info(f"检测到源{source_index + 1}为标准M3U格式")
                channels = extract_all_channels_from_m3u(file_path, source_index)
            else:
                logger.warning(f"无法识别源{source_index + 1}的格式，尝试标准解析")
                channels = extract_all_channels_from_m3u(file_path, source_index)
            
            all_channels.extend(channels)
            logger.info(f"从源{source_index + 1}解析出 {len(channels)} 个频道")

        special_channels = extract_special_group_channels(all_channels)
        
        migu_channels = extract_migu_sports_channels(all_channels, downloaded_files)
        
        update_target_file(all_channels, target_channels, special_channels, migu_channels)

        try:
            download_dir = CONFIG["download_dir"]
            if os.path.exists(download_dir):
                shutil.rmtree(download_dir)
                logger.info(f"已清理临时下载目录: {download_dir}")
        except Exception as e:
            logger.warning(f"清理临时文件时出现错误: {e}")

        end_time = time.time()
        duration = end_time - start_time
        logger.info("=" * 60)
        logger.info("任务执行成功完成")
        logger.info(f"完成时间 (北京时间): {get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"总耗时: {duration:.2f} 秒")
        logger.info(f"总计处理频道源: {len(all_channels)} 个")
        logger.info(f"日志文件: logs/tv_auto_update_{datetime.now().strftime('%Y%m%d')}.log")
        logger.info("=" * 60)

    except SystemExit:
        logger.critical("因配置错误，任务提前终止。")
        raise
    except Exception as e:
        logger.critical(f"任务执行失败，原因: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
