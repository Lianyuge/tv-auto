import requests
import re
from datetime import datetime, timezone, timedelta
import os
import sys
import logging
import time
import base64
import shutil
import urllib.parse
from logging.handlers import RotatingFileHandler
from collections import defaultdict

# ==================== 全局对象 ====================
logger = None
CONFIG = None

# ==================== 日志系统 (最先初始化) ====================
def setup_logging():
    """配置日志系统"""
    # 创建日志目录
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 设置日志文件名（按日期）
    log_date = datetime.now().strftime('%Y%m%d')
    log_filename = f"{log_dir}/tv_auto_update_{log_date}.log"

    # 配置日志格式
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # 创建logger
    _logger = logging.getLogger('TVAutoUpdater')
    _logger.setLevel(logging.INFO)

    # 清除已有的handler，避免重复
    if _logger.handlers:
        _logger.handlers.clear()

    # 文件处理器（按大小轮转，最大5MB，保留3个备份）
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', date_format))

    # 添加处理器到logger
    _logger.addHandler(file_handler)
    _logger.addHandler(console_handler)

    return _logger

# ==================== 配置部分 ====================
def get_config():
    """加载配置，此函数现在可以安全地使用logger"""
    m3u_sources = []

    # 支持最多20个源
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
            "央视吉林": 0,  # 从源1获取
            "央视辽宁": 2,  # 从源3获取
        },
        "target_file": "index.html",
        "download_dir": "downloaded_sources",
        # 特殊分组处理
        "special_groups": {
            "冰茶体育": {
                "source_index": 1,  # 从源2获取
                "new_group_name": "连宇体育",  # 重命名为连宇体育
                "position": "end"  # 放到文件最后
            }
        },
        # 更新时间频道配置
        "update_channel": {
            "group_title": "更新时间",
            "fixed_link": "https://zhanglianyu.oss-cn-beijing.aliyuncs.com/new.mp4"
        },
        # !!! 修改后的咪咕体育分组处理配置 !!!
        "migu_sports": {
            "source_index": 3,  # 从源4获取（M3U_SOURCE_4）
            "migu_pattern": r"咪咕体育-\d{8}",  # 匹配分组标题
            "groups": {
                "today": "今日咪咕",
                "yesterday": "咪咕体育回看", 
                "tomorrow": "咪咕体育预告",
                "other": "咪咕体育其他"
            }
        },
        # 频道名称映射表
        "channel_name_mapping": {
            "吉视都市": ["吉林都市", "吉视都市", "吉林电视台都市频道"],
            "吉视生活": ["吉林生活", "吉视生活", "吉林电视台生活频道"],
            "吉视影视": ["吉林影视", "吉视影视", "吉林电视台影视台"],
            "吉视综艺": ["吉林综艺", "吉视综艺", "吉林电视台综艺频道"],
            "吉视乡村": ["吉林乡村", "吉林电视台乡村频道", "吉林乡村频道"],
        },
        # ==================== Cloudflare Worker 代理配置 ====================
        # !!! 重要：以下三个值必须与 Cloudflare Worker 代码中的设置完全一致 !!!
        "proxy_config": {
            "enabled": True,  # 是否启用代理（设为 False 则使用原始链接）
            "worker_url": "https://crimson-sound-09ba.lianyu1868.workers.dev/",  # 你的 Cloudflare Worker 地址
            "access_key": "Ff905113",  # 访问密钥，与 Worker 中的 VALID_KEY 一致
            "encryption_key": "Ff905113%"  # 加密密钥，与 Worker 中的 decryptionKey 一致
        },
        # ==================== 海外频道代理配置 ====================
        "overseas_proxy": {
            "enabled": True,  # 是否启用海外频道代理
            "worker_url": "https://royal-morning-52a8.lianyu1868.workers.dev/",  # 通用代理 Worker 地址
            "source_index": 6,  # M3U_SOURCE_7 对应的索引（从0开始，所以M3U_SOURCE_7是索引6）
            "new_group_name": "大陆以外",  # 新的分组名称
            # 可选：可以添加需要代理的特定域名，为空则代理所有
            "proxy_domains": []  # 例如: ["example.com", "iptv-server.com"]
        }
    }

# ==================== 工具函数 ====================
def get_beijing_time():
    """获取北京时间"""
    utc_time = datetime.now(timezone.utc)
    beijing_time = utc_time + timedelta(hours=8)
    return beijing_time

def normalize_channel_name(channel_name, channel_mapping):
    """标准化频道名称：如果名称在映射表中，返回标准名称"""
    if not channel_mapping:
        return channel_name
    for standard_name, variants in channel_mapping.items():
        if channel_name in variants:
            return standard_name
    return channel_name

def parse_migu_date_from_header(header_line):
    """从咪咕体育分组标题行提取日期"""
    # 匹配"咪咕体育-YYYYMMDD"格式
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
    
    # 分割逗号，取最后一个部分
    parts = line.split(',')
    channel_info = parts[-1].strip()
    
    return channel_info

def encrypt_url(url, key):
    """加密URL（XOR + Base64），与 Cloudflare Worker 中的解密函数对应"""
    try:
        key_bytes = key.encode('utf-8')
        url_bytes = url.encode('utf-8')
        encrypted = bytearray()
        for i in range(len(url_bytes)):
            encrypted.append(url_bytes[i] ^ key_bytes[i % len(key_bytes)])
        # 使用 urlsafe_b64encode 避免链接中出现特殊字符问题
        return base64.urlsafe_b64encode(encrypted).decode('utf-8')
    except Exception as e:
        logger.error(f"加密URL时出错: {e}")
        return None

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
    """从m3u文件中提取所有频道信息"""
    channels = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')

        for i in range(len(lines) - 1):
            line = lines[i]
            if line.startswith('#EXTINF'):
                if ',' in line:
                    # 提取频道名称
                    channel_name = extract_channel_name_from_extinf(line)
                    
                    # 提取group-title
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
                            'line_index': i  # 添加行索引用于调试
                        })

    except Exception as e:
        logger.error(f"解析文件 {file_path} 时出错: {e}")

    return channels

def extract_and_proxy_overseas_channels(file_path, source_index):
    """从指定源文件提取频道并应用海外代理"""
    overseas_config = CONFIG.get("overseas_proxy", {})
    
    if not overseas_config.get("enabled", False):
        return []
    
    target_source_index = overseas_config.get("source_index", 6)
    if source_index != target_source_index:
        return []
    
    new_group_name = overseas_config.get("new_group_name", "大陆以外")
    worker_url = overseas_config.get("worker_url", "")
    proxy_domains = overseas_config.get("proxy_domains", [])
    
    if not worker_url:
        logger.warning("海外代理已启用但未配置 worker_url")
        return []
    
    channels = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        for i in range(len(lines) - 1):
            line = lines[i]
            if line.startswith('#EXTINF'):
                if ',' in line:
                    # 提取频道名称
                    channel_name = extract_channel_name_from_extinf(line)
                    
                    # 提取原始group-title
                    group_match = re.search(r'group-title="([^"]*)"', line)
                    original_group_title = group_match.group(1) if group_match else ""
                    
                    if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                        original_link = lines[i + 1].strip()
                        
                        # 检查是否需要代理（如果配置了proxy_domains则检查，否则全部代理）
                        should_proxy = True
                        if proxy_domains:
                            should_proxy = any(domain in original_link for domain in proxy_domains)
                        
                        final_link = original_link
                        if should_proxy and original_link.startswith('http'):
                            try:
                                # 对原始链接进行 URL 编码
                                encoded_url = urllib.parse.quote(original_link, safe='')
                                # 构建代理链接
                                proxy_link = f"{worker_url}/?url={encoded_url}"
                                final_link = proxy_link
                                logger.debug(f"为海外频道应用代理: {channel_name[:30]}...")
                            except Exception as e:
                                logger.warning(f"处理海外代理链接失败 {channel_name}: {e}")
                        
                        # 构建新的 EXTINF 行，使用新的分组名称
                        if 'group-title=' in line:
                            new_extinf_line = re.sub(
                                r'group-title="[^"]*"',
                                f'group-title="{new_group_name}"',
                                line
                            )
                        else:
                            # 如果没有group-title，添加一个
                            new_extinf_line = f'{line} group-title="{new_group_name}"'
                        
                        channels.append({
                            'name': channel_name,
                            'group': new_group_name,
                            'original_group': original_group_title,
                            'link': final_link,
                            'extinf_line': new_extinf_line,
                            'source': source_index,
                            'is_overseas': True,
                            'original_link': original_link  # 保存原始链接用于调试
                        })
        
        logger.info(f"从海外源提取了 {len(channels)} 个频道，已应用代理并分组到 '{new_group_name}'")
        if channels:
            logger.debug(f"海外频道示例: {channels[0]['name'][:50]}... -> {channels[0]['link'][:50]}...")
    
    except Exception as e:
        logger.error(f"解析海外源文件 {file_path} 时出错: {e}", exc_info=True)
    
    return channels

def extract_migu_sports_channels_from_file(file_path, source_index):
    """从源文件直接提取咪咕体育频道（适配无EXTINF格式）"""
    migu_config = CONFIG.get("migu_sports")
    if not migu_config or source_index != migu_config["source_index"]:
        return {}
    
    beijing_time = get_beijing_time()
    groups = migu_config["groups"]
    
    # 按分类存储频道
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
        skip_count = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # 跳过空行
            if not line:
                i += 1
                continue
            
            # 检查是否是咪咕体育分组标题行
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
                    logger.warning(f"咪咕体育日期解析失败: {line}")
                    current_migu_date = None
            
            # 如果当前有活跃的咪咕分组，检查下面的频道行（格式：频道名称,链接）
            if current_migu_date and ',' in line and not line.startswith('#'):
                # 分割频道名称和链接
                parts = line.split(',', 1)
                if len(parts) == 2:
                    channel_name, link = parts[0].strip(), parts[1].strip()
                    
                    # 验证链接看起来像URL
                    if link.startswith('http'):
                        # 构建EXTINF行（因为目标文件需要标准M3U格式）
                        # 注意：原始文件没有tvg-id等属性，我们只添加必需的
                        extinf_line = f'#EXTINF:-1 group-title="{current_group_name}",{channel_name}'
                        
                        # ==================== 处理咪咕链接：使用 Cloudflare Worker 代理 ====================
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
                                else:
                                    logger.warning(f"加密咪咕链接失败，使用原始链接: {channel_name}")
                            else:
                                logger.warning("Cloudflare Worker 配置不完整，使用原始咪咕链接")
                        # ==================== 代理处理结束 ====================
                        
                        classified_channels[current_group_name].append({
                            'name': channel_name,
                            'group': current_group_name,
                            'link': final_link,  # 这里存储的是处理后的链接（原始或代理）
                            'extinf_line': extinf_line,
                            'source': source_index,
                            'migu_date': current_migu_date,
                            'category': current_category
                        })
                        
                        migu_channels_found += 1
                        
                        if migu_channels_found <= 5:  # 只记录前5个频道
                            logger.debug(f"  咪咕频道: {channel_name} -> {current_group_name}")
                    else:
                        logger.warning(f"  忽略无效链接行: {line[:50]}...")
                else:
                    logger.warning(f"  无法解析频道行: {line[:50]}...")
            
            # 如果不是咪咕体育分组行，也不包含逗号（不是频道行），则跳过
            elif not line.startswith('#') and ',' not in line:
                skip_count += 1
                if skip_count <= 3:  # 只记录前3个被跳过的行
                    logger.debug(f"  跳过非频道行: {line[:50]}...")
            
            i += 1
        
        logger.info(f"从文件 {os.path.basename(file_path)} 解析出 {migu_channels_found} 个咪咕体育频道")
        
        # 统计并记录日志
        total_migu = sum(len(channels) for channels in classified_channels.items())
        logger.info(f"总计分类咪咕频道: {total_migu} 个")
        
        for group_name, channels in classified_channels.items():
            logger.info(f"  - {group_name}: {len(channels)} 个频道")
            if channels:
                # 显示前3个频道作为示例
                example_channels = channels[:3]
                for chan in example_channels:
                    logger.debug(f"    示例频道: {chan['name'][:50]}...")
        
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

        # 从指定源中提取该分组的频道
        for channel in all_channels:
            if channel['group'] == group_name and channel['source'] == source_index:
                # 创建新的频道信息，修改分组名称
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
    """整合所有源的咪咕体育频道"""
    migu_config = CONFIG.get("migu_sports")
    if not migu_config:
        logger.info("未配置咪咕体育分组")
        return {}
    
    source_index = migu_config["source_index"]
    
    # 找到对应的下载文件
    migu_file = None
    for file_path in downloaded_files:
        if f"source_{source_index + 1}_" in file_path:
            migu_file = file_path
            break
    
    if not migu_file:
        logger.warning(f"未找到源{source_index + 1}的下载文件")
        return {}
    
    # 使用新函数从文件直接解析
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
                # 提取频道名称
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
    """根据规则查找匹配的频道 (支持名称映射)"""
    # 跳过特殊分组的频道（它们会单独处理）
    special_group_names = [config["new_group_name"] for config in CONFIG["special_groups"].values()]
    if group_title in special_group_names:
        return None

    # 跳过咪咕体育分组
    migu_config = CONFIG.get("migu_sports")
    if migu_config and group_title in migu_config["groups"].values():
        return None

    # 标准化目标频道名称
    normalized_target_name = normalize_channel_name(channel_name, CONFIG.get("channel_name_mapping", {}))

    # 规则1: 如果分组在规则中，从指定源查找
    if group_title in CONFIG["group_rules"]:
        target_source = CONFIG["group_rules"][group_title]
        for channel in all_channels:
            # 标准化源频道名称进行比较
            normalized_source_name = normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {}))
            if (channel['group'] == group_title and
                    normalized_source_name == normalized_target_name and
                    channel['source'] == target_source):
                # 记录名称映射使用情况
                if channel['name'] != channel_name:
                    logger.debug(
                        f"名称映射匹配: 目标'{channel_name}' -> 源'{channel['name']}' (标准化为 '{normalized_target_name}')")
                return channel

    # 规则2: 其他分组从所有源中按顺序查找
    for source_index in range(len(CONFIG["m3u_sources"])):
        for channel in all_channels:
            normalized_source_name = normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {}))
            if normalized_source_name == normalized_target_name and channel['source'] == source_index:
                if channel['name'] != channel_name:
                    logger.debug(
                        f"名称映射匹配: 目标'{channel_name}' -> 源'{channel['name']}' (标准化为 '{normalized_target_name}')")
                return channel

    return None

def update_target_file(all_channels, target_channels, special_channels, migu_channels, overseas_channels=None):
    """更新目标文件中的链接"""
    if overseas_channels is None:
        overseas_channels = []
    
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
        
        # 定义所有特殊分组的标题（用于过滤重复）
        special_group_titles = []
        
        # 添加连宇体育分组标题
        for group_name, config in CONFIG["special_groups"].items():
            special_group_titles.append(f"# {config['new_group_name']}分组")
        
        # 添加咪咕体育分组标题
        migu_config = CONFIG.get("migu_sports")
        if migu_config:
            for group_name in migu_config["groups"].values():
                special_group_titles.append(f"# {group_name}分组")
        
        # 添加更新时间分组标题
        update_group_name = CONFIG["update_channel"]["group_title"]
        special_group_titles.append(f"# {update_group_name}分组")
        
        # 添加海外频道分组标题
        overseas_config = CONFIG.get("overseas_proxy", {})
        if overseas_config.get("enabled", False):
            overseas_group_name = overseas_config.get("new_group_name", "大陆以外")
            special_group_titles.append(f"# {overseas_group_name}分组")
        
        # 跟踪是否在特殊分组区域
        in_special_group = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 检查是否进入特殊分组区域
            if line.strip() in special_group_titles:
                in_special_group = True
                i += 1
                continue
                
            # 如果在特殊分组区域，跳过所有行直到遇到下一个非特殊分组内容
            if in_special_group:
                # 如果遇到空行，可能表示特殊分组结束
                if line.strip() == "":
                    # 检查下一行是否还是特殊分组
                    if i + 1 < len(lines) and lines[i + 1].strip() in special_group_titles:
                        i += 1
                        continue
                    else:
                        in_special_group = False
                else:
                    # 跳过特殊分组内的所有行
                    i += 1
                    continue
            
            # 处理普通行
            if line.startswith('#EXTINF'):
                channel_name = extract_channel_name_from_extinf(line)
                group_match = re.search(r'group-title="([^"]*)"', line)
                group_title = group_match.group(1) if group_match else ""

                # 根据规则查找匹配的频道
                matched_channel = find_channel_by_rules(channel_name, group_title, all_channels)

                if matched_channel:
                    # 检查下一行是否是链接
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        old_link = lines[i + 1]
                        new_link = matched_channel['link']

                        if old_link != new_link:
                            logger.info(f"更新 '{channel_name}' [{group_title}] (来自源{matched_channel['source'] + 1})")
                            new_lines.append(line)
                            new_lines.append(new_link)
                            updated_count += 1
                        else:
                            # 链接相同，保留原链接
                            new_lines.append(line)
                            new_lines.append(old_link)

                        i += 1  # 跳过链接行
                    else:
                        # 没有找到链接行，添加新链接
                        new_link = matched_channel['link']
                        new_lines.append(line)
                        new_lines.append(new_link)
                        logger.info(f"添加 '{channel_name}' [{group_title}] (来自源{matched_channel['source'] + 1})")
                        updated_count += 1
                else:
                    # 没有找到匹配的频道，保持原样
                    new_lines.append(line)
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        new_lines.append(lines[i + 1])
                        i += 1
            else:
                # 非EXTINF行，保持原样
                new_lines.append(line)

            i += 1

        # 确保文件以EXTM3U开头
        if not new_lines or not new_lines[0].startswith('#EXTM3U'):
            new_lines.insert(0, '#EXTM3U')
        
        # 添加空行分隔
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")

        # 添加特殊分组的频道到文件末尾
        if special_channels:
            new_lines.append(f"# {CONFIG['special_groups']['冰茶体育']['new_group_name']}分组")
            for channel in special_channels:
                new_lines.append(channel['extinf_line'])
                new_lines.append(channel['link'])
                logger.info(f"添加特殊分组: '{channel['name']}' [{channel['group']}]")
                updated_count += 1
            new_lines.append("")
        
        # 添加咪咕体育分组
        if migu_channels:
            for group_name, channels in migu_channels.items():
                if channels:  # 只添加有频道的分组
                    new_lines.append(f"# {group_name}分组")
                    for channel in channels:
                        # 确保频道有EXTINF行
                        if 'extinf_line' in channel:
                            new_lines.append(channel['extinf_line'])
                        else:
                            # 如果没有，创建一个
                            extinf_line = f'#EXTINF:-1 group-title="{channel["group"]}",{channel["name"]}'
                            new_lines.append(extinf_line)
                        
                        new_lines.append(channel['link'])
                        logger.info(f"添加咪咕分组: '{channel['name']}' [{channel['group']}]")
                        updated_count += 1
                    new_lines.append("")
        
        # 添加海外频道分组
        if overseas_channels:
            overseas_config = CONFIG.get("overseas_proxy", {})
            overseas_group_name = overseas_config.get("new_group_name", "大陆以外")
            new_lines.append(f"# {overseas_group_name}分组")
            for channel in overseas_channels:
                new_lines.append(channel['extinf_line'])
                new_lines.append(channel['link'])
                logger.info(f"添加海外频道: '{channel['name']}' [{channel['group']}]")
                updated_count += 1
            new_lines.append("")
        
        # 添加更新时间频道（放在最最后）
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

    # 1. 最先初始化日志系统
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("开始执行直播源自动更新任务")
    logger.info(f"启动时间 (北京时间): {get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        # 2. 加载配置 (现在可以安全使用logger)
        CONFIG = get_config()
        logger.info(f"已加载配置，共有 {len(CONFIG['m3u_sources'])} 个源地址")

        # 记录频道名称映射表（用于调试）
        if CONFIG.get("channel_name_mapping"):
            logger.info("已启用频道名称映射，将处理以下名称变体：")
            for std_name, variants in CONFIG["channel_name_mapping"].items():
                if len(variants) > 1:  # 只打印有变体的
                    logger.info(f"  '{std_name}': {variants}")

        # 3. 从目标文件中提取所有频道信息
        target_channels = extract_target_channels()

        # 4. 下载m3u文件
        downloaded_files = download_m3u_files()

        if not downloaded_files:
            logger.error("没有成功下载任何文件，任务终止")
            return

        # 5. 从所有源文件中提取频道信息
        all_channels = []
        overseas_channels = []  # 单独存储海外频道
        
        for source_index, file_path in enumerate(downloaded_files):
            channels = extract_all_channels_from_m3u(file_path, source_index)
            all_channels.extend(channels)
            logger.info(f"从源{source_index + 1}解析出 {len(channels)} 个频道")
            
            # 提取并处理海外频道（从特定源）
            overseas_config = CONFIG.get("overseas_proxy", {})
            if overseas_config.get("enabled", False) and source_index == overseas_config.get("source_index", 6):
                oversea_chs = extract_and_proxy_overseas_channels(file_path, source_index)
                overseas_channels.extend(oversea_chs)
                logger.info(f"从海外源{source_index + 1}提取了 {len(oversea_chs)} 个频道到'大陆以外'分组")

        # 6. 提取特殊分组的频道
        special_channels = extract_special_group_channels(all_channels)
        
        # 7. 提取并分类咪咕体育频道（使用新方法）
        migu_channels = extract_migu_sports_channels(all_channels, downloaded_files)
        
        # 8. 更新目标文件（将海外频道作为特殊分组添加到文件末尾）
        update_target_file(all_channels, target_channels, special_channels, migu_channels, overseas_channels)

        # 9. 清理下载的临时源文件（新增步骤）
        try:
            download_dir = CONFIG["download_dir"]
            if os.path.exists(download_dir):
                shutil.rmtree(download_dir)
                logger.info(f"已清理临时下载目录: {download_dir}")
            else:
                logger.debug(f"临时下载目录不存在，无需清理: {download_dir}")
        except Exception as e:
            logger.warning(f"清理临时文件时出现错误: {e}")

        # 10. 任务完成，输出统计
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
        # 捕获配置错误导致的sys.exit
        logger.critical("因配置错误，任务提前终止。")
        raise
    except Exception as e:
        logger.critical(f"任务执行失败，原因: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
