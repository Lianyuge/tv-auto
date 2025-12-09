import requests
import re
from datetime import datetime, timezone, timedelta
import os
import sys
import logging
import time
from logging.handlers import RotatingFileHandler

# ==================== 全局日志对象初始化占位 ====================
logger = None

# ==================== 配置部分 ====================
def get_config():
    m3u_sources = []
    
    # 支持最多20个源
    for i in range(1, 21):
        env_name = f"M3U_SOURCE_{i}"
        source_url = os.getenv(env_name)
        if source_url:
            m3u_sources.append(source_url)
    
    if not m3u_sources:
        logger.error("错误: 未找到任何M3U源URL")
        sys.exit(1)
    
    return {
        "m3u_sources": m3u_sources,
        "group_rules": {
            "央视吉林": 0,   # 从源1获取
            "央视辽宁": 2,   # 从源3获取
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
        # !!! 新增：频道名称映射表 (解决“吉林都市”和“吉视都市”匹配问题) !!!
        "channel_name_mapping": {
            "吉视都市": ["吉林都市", "吉视都市", "吉林电视台都市频道"],
            "吉林都市": ["吉林都市", "吉视都市", "吉林电视台都市频道"],
            "吉视影视": ["吉林影视", "吉视影视", "吉林电视台影视台"],
            "吉林影视": ["吉林影视", "吉视影视", "吉林电视台影视台"],
            "吉林乡村": ["吉林乡村", "吉林电视台乡村频道", "吉林乡村频道"],
            # 您可以继续在此处添加更多名称映射
        }
    }

CONFIG = None  # 将在main中初始化

# ==================== 工具函数 ====================
def get_beijing_time():
    """获取北京时间"""
    utc_time = datetime.now(timezone.utc)
    beijing_time = utc_time + timedelta(hours=8)
    return beijing_time.strftime('%Y-%m-%d %H:%M:%S')

def normalize_channel_name(channel_name, channel_mapping):
    """标准化频道名称：如果名称在映射表中，返回标准名称"""
    if not channel_mapping:
        return channel_name
    for standard_name, variants in channel_mapping.items():
        if channel_name in variants:
            return standard_name
    return channel_name

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
            logger.info(f"正在下载源 {i+1}: {safe_url}...")
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            filename = f"{CONFIG['download_dir']}/source_{i+1}_{datetime.now().strftime('%Y%m%d')}.m3u"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(response.text)
            downloaded_files.append(filename)
            logger.info(f"✓ 成功下载源 {i+1}")
            
        except Exception as e:
            logger.error(f"✗ 下载失败源 {i+1}: {e}")
    
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
                    channel_name = line.split(',')[-1].strip()
                    
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
                            'source': source_index
                        })
    
    except Exception as e:
        logger.error(f"解析文件 {file_path} 时出错: {e}")
    
    return channels

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
                    'group': new_group_name,  # 使用新分组名
                    'link': channel['link'],
                    'extinf_line': new_extinf_line,
                    'source': channel['source'],
                    'original_group': group_name  # 保留原始分组名用于日志
                })
        
        count = len([c for c in special_channels if c['original_group'] == group_name])
        logger.info(f"从源{source_index+1}找到 {count} 个'{group_name}'频道，将重命名为'{new_group_name}'")
    
    return special_channels

def extract_target_channels():
    """从目标文件中提取所有频道信息"""
    target_channels = []
    
    try:
        if not os.path.exists(CONFIG["target_file"]):
            logger.info(f"目标文件 {CONFIG['target_file']} 不存在")
            return target_channels
        
        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        for i in range(len(lines) - 1):
            line = lines[i]
            if line.startswith('#EXTINF'):
                if ',' in line:
                    channel_name = line.split(',')[-1].strip()
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
        
        logger.info(f"从目标文件中提取了 {len(target_channels)} 个频道")
        
    except Exception as e:
        logger.error(f"解析目标文件时出错: {e}")
    
    return target_channels

def find_channel_by_rules(channel_name, group_title, all_channels):
    """根据规则查找匹配的频道 (支持名称映射)"""
    # 跳过特殊分组的频道（它们会单独处理）
    special_group_names = [config["new_group_name"] for config in CONFIG["special_groups"].values()]
    if group_title in special_group_names:
        return None
    
    # !!! 关键修改：标准化目标频道名称 !!!
    normalized_target_name = normalize_channel_name(channel_name, CONFIG.get("channel_name_mapping", {}))
    
    # 规则1: 如果分组在规则中，从指定源查找
    if group_title in CONFIG["group_rules"]:
        target_source = CONFIG["group_rules"][group_title]
        for channel in all_channels:
            # !!! 关键修改：标准化源频道名称进行比较 !!!
            normalized_source_name = normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {}))
            if (channel['group'] == group_title and 
                normalized_source_name == normalized_target_name and 
                channel['source'] == target_source):
                # 记录名称映射使用情况
                if channel['name'] != channel_name:
                    logger.debug(f"名称映射匹配: 目标'{channel_name}' -> 源'{channel['name']}' (标准化为 '{normalized_target_name}')")
                return channel
    
    # 规则2: 其他分组从所有源中按顺序查找
    for source_index in range(len(CONFIG["m3u_sources"])):
        for channel in all_channels:
            normalized_source_name = normalize_channel_name(channel['name'], CONFIG.get("channel_name_mapping", {}))
            if normalized_source_name == normalized_target_name and channel['source'] == source_index:
                if channel['name'] != channel_name:
                    logger.debug(f"名称映射匹配: 目标'{channel_name}' -> 源'{channel['name']}' (标准化为 '{normalized_target_name}')")
                return channel
    
    return None

def update_target_file(all_channels, target_channels, special_channels):
    """更新目标文件中的链接"""
    try:
        logger.info("开始更新目标文件...")
        
        if not os.path.exists(CONFIG["target_file"]):
            logger.warning("目标文件不存在，将创建新文件")
            with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
        
        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()
        
        updated_count = 0
        lines = content.split('\n')
        new_lines = []
        
        # 获取所有需要过滤的分组名称
        special_group_new_names = [config["new_group_name"] for config in CONFIG["special_groups"].values()]
        special_group_original_names = list(CONFIG["special_groups"].keys())
        update_group_name = CONFIG["update_channel"]["group_title"]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if line.startswith('#EXTINF'):
                channel_name = line.split(',')[-1].strip() if ',' in line else ""
                group_match = re.search(r'group-title="([^"]*)"', line)
                group_title = group_match.group(1) if group_match else ""
                
                # 跳过特殊分组和更新分组的频道（它们会在最后统一添加）
                if (group_title in special_group_new_names or 
                    group_title in special_group_original_names or
                    group_title == update_group_name):
                    # 跳过这个频道（EXTINF行和链接行）
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        i += 1
                    i += 1
                    continue
                
                # 根据规则查找匹配的频道
                matched_channel = find_channel_by_rules(channel_name, group_title, all_channels)
                
                if matched_channel:
                    # 检查下一行是否是链接
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        old_link = lines[i + 1]
                        new_link = matched_channel['link']
                        
                        if old_link != new_link:
                            logger.info(f"更新 {channel_name} [{group_title}]: 源{matched_channel['source']+1}")
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
                        logger.info(f"添加 {channel_name} [{group_title}]: 源{matched_channel['source']+1}")
                        updated_count += 1
                else:
                    # 没有找到匹配的频道，保持原样
                    new_lines.append(line)
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        new_lines.append(lines[i + 1])
                        i += 1
            else:
                # 非EXTINF行，保持原样（过滤掉旧的备选链接注释）
                if not line.startswith('#备用'):
                    new_lines.append(line)
            
            i += 1
        
        # 确保文件以EXTM3U开头
        if not new_lines or not new_lines[0].startswith('#EXTM3U'):
            new_lines.insert(0, '#EXTM3U')
        
        # 添加特殊分组的频道到文件末尾
        if special_channels:
            new_lines.append("")
            new_lines.append("# 连宇体育分组")
            for channel in special_channels:
                new_lines.append(channel['extinf_line'])
                new_lines.append(channel['link'])
                logger.info(f"添加特殊分组: {channel['name']} [{channel['group']}]")
                updated_count += 1
        
        # 添加更新时间频道（放在最最后）
        beijing_time = get_beijing_time()
        update_channel_name = f"最后更新: {beijing_time} (北京时间)"
        
        new_lines.append("")
        new_lines.append(f"# {update_group_name}分组")
        new_lines.append(f'#EXTINF:-1 tvg-id="update" tvg-name="update" tvg-logo="" group-title="{update_group_name}",{update_channel_name}')
        new_lines.append(CONFIG["update_channel"]["fixed_link"])
        
        logger.info(f"添加更新时间频道: {update_channel_name}")
        
        with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        logger.info(f"更新完成: 共更新 {updated_count} 个频道")
        
    except Exception as e:
        logger.error(f"更新目标文件时出错: {e}", exc_info=True)
        raise

# ==================== 日志与主程序 ====================
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
        maxBytes=5*1024*1024,  # 5MB
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

def main():
    global logger, CONFIG
    start_time = time.time()
    
    # 1. 初始化日志系统
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("开始执行直播源自动更新任务")
    logger.info(f"启动时间 (北京时间): {get_beijing_time()}")
    logger.info("=" * 60)
    
    try:
        # 2. 加载配置
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
        for source_index, file_path in enumerate(downloaded_files):
            channels = extract_all_channels_from_m3u(file_path, source_index)
            all_channels.extend(channels)
            logger.info(f"从源{source_index+1}解析出 {len(channels)} 个频道")
        
        # 6. 提取特殊分组的频道
        special_channels = extract_special_group_channels(all_channels)
        
        # 7. 更新目标文件
        update_target_file(all_channels, target_channels, special_channels)
        
        # 8. 任务完成，输出统计
        end_time = time.time()
        duration = end_time - start_time
        logger.info("=" * 60)
        logger.info("任务执行成功完成")
        logger.info(f"完成时间 (北京时间): {get_beijing_time()}")
        logger.info(f"总耗时: {duration:.2f} 秒")
        logger.info(f"共处理频道源: {len(all_channels)} 个")
        logger.info(f"更新目标文件: {CONFIG['target_file']}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"任务执行失败，原因: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
