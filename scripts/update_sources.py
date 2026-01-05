#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV自动更新脚本 - 优化版
说明：根据index.html中的频道名称，从指定M3U源获取直播源地址并更新
避免重复源，优化匹配逻辑，新增更多分组规则
"""

import requests
import re
from datetime import datetime
import logging
import sys
import os
import hashlib

# ==================== 配置区域 ====================

# 从环境变量获取M3U源地址（优先使用环境变量）
def get_m3u_sources_from_env():
    """从环境变量获取M3U源地址"""
    sources = {}
    
    # 尝试从环境变量获取
    for i in range(1, 5):
        env_key = f"M3U_SOURCE_{i}"
        env_value = os.environ.get(env_key)
        
        if env_value and not env_value.startswith("http://example.com"):
            sources[env_key] = env_value
            print(f"✓ 从环境变量获取到 {env_key}")
        elif env_value:
            print(f"⚠ {env_key} 使用的是默认example.com，将跳过此源")
    
    return sources

# 分组与源的映射规则（新增更多规则）
GROUP_SOURCE_MAP = {
    "央视": "M3U_SOURCE_1",
    "咪咕频道": "M3U_SOURCE_5", 
    "地方卫视": "M3U_SOURCE_3",  # 修改为M3U_SOURCE_3
    "付费频道": "M3U_SOURCE_3",
    "辽宁地方": "M3U_SOURCE_1",  # 线路1频道
    "吉林地方": "M3U_SOURCE_4",  # 线路1频道
    "冰茶体育": "M3U_SOURCE_2",  # 特殊分组：整个分组重新获取
    "体育回看": "M3U_SOURCE_2",  # 特殊分组：整个分组重新获取
    "咪视界bc": "M3U_SOURCE_2",  # 新增规则
    "粤语频道": "M3U_SOURCE_2",  # 新增规则
    "超清频道": "M3U_SOURCE_2",  # 新增规则
    "其他频道": "M3U_SOURCE_1",  # 新增规则
    "教育频道": "M3U_SOURCE_1",  # 新增规则
    # 未配置的分组将从所有可用的M3U源中查找
}

# 需要完整重新获取的特殊分组
SPECIAL_GROUPS = ["冰茶体育", "体育回看"]

# 文件路径
INPUT_FILE = "index.html"      # 输入文件（模板）
OUTPUT_FILE = "index.html"     # 输出文件（更新后）
LOG_FILE = "update_log.txt"    # 日志文件

# 频道名称清洗规则（用于匹配）
CLEAN_PATTERNS = [
    (r'^CCTV-?', 'CCTV'),          # CCTV-1 -> CCTV1
    (r'^央视-?', 'CCTV'),          # 央视1 -> CCTV1
    (r'[-\s]', ''),                # 移除空格和短横线
    (r'\(.*?\)', ''),              # 移除括号内容
    (r'\[.*?\]', ''),              # 移除方括号内容
    (r'标清|高清|HD|SD|直播|频道|台', ''), # 移除画质标识
]

# 频道名称别名映射（提高匹配成功率）
CHANNEL_ALIAS = {
    "CCTV1": ["CCTV1", "CCTV-1", "央视1", "CCTV1综合", "中央1"],
    "CCTV2": ["CCTV2", "CCTV-2", "央视2", "CCTV2财经", "中央2"],
    "CCTV3": ["CCTV3", "CCTV-3", "央视3", "CCTV3综艺", "中央3"],
    "CCTV4": ["CCTV4", "CCTV-4", "央视4", "CCTV4中文国际", "中央4"],
    "CCTV5": ["CCTV5", "CCTV-5", "央视5", "CCTV5体育", "中央5"],
    "CCTV5+": ["CCTV5+", "CCTV5PLUS", "CCTV5体育赛事"],
    "CCTV6": ["CCTV6", "CCTV-6", "央视6", "CCTV6电影", "中央6"],
    "CCTV7": ["CCTV7", "CCTV-7", "央视7", "CCTV7国防军事", "中央7"],
    "CCTV8": ["CCTV8", "CCTV-8", "央视8", "CCTV8电视剧", "中央8"],
    "CCTV9": ["CCTV9", "CCTV-9", "央视9", "CCTV9纪录", "中央9"],
    "CCTV10": ["CCTV10", "CCTV-10", "央视10", "CCTV10科教", "中央10"],
    "CCTV11": ["CCTV11", "CCTV-11", "央视11", "CCTV11戏曲", "中央11"],
    "CCTV12": ["CCTV12", "CCTV-12", "央视12", "CCTV12社会与法", "中央12"],
    "CCTV13": ["CCTV13", "CCTV-13", "央视13", "CCTV13新闻", "中央13"],
    "CCTV14": ["CCTV14", "CCTV-14", "央视14", "CCTV14少儿", "中央14"],
    "CCTV15": ["CCTV15", "CCTV-15", "央视15", "CCTV15音乐", "中央15"],
    "CCTV16": ["CCTV16", "CCTV-16", "央视16", "CCTV16奥林匹克"],
    "CCTV17": ["CCTV17", "CCTV-17", "央视17", "CCTV17农业农村"],
}

# ==================== 日志设置 ====================

def setup_logging():
    """配置日志"""
    logger = logging.getLogger('IPTV_Updater')
    logger.setLevel(logging.INFO)
    
    # 文件处理器
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# ==================== 核心函数 ====================

def clean_channel_name(channel_name: str) -> str:
    """清洗频道名称用于匹配"""
    cleaned = channel_name.strip()
    
    for pattern, replacement in CLEAN_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    
    # 特殊处理CCTV频道
    cctv_match = re.search(r'CCTV(\d+)', cleaned, re.IGNORECASE)
    if cctv_match:
        return f"CCTV{cctv_match.group(1)}"
    
    # 特殊处理CCTV5+
    if "CCTV5+" in cleaned or "CCTV5PLUS" in cleaned.upper():
        return "CCTV5+"
    
    # 特殊处理卫视频道
    if "卫视" in cleaned:
        # 提取卫视名称，如"浙江卫视" -> "浙江"
        ws_match = re.search(r'([\u4e00-\u9fa5]+)卫视', cleaned)
        if ws_match:
            return f"{ws_match.group(1)}卫视"
    
    return cleaned.upper()

def get_channel_aliases(channel_name: str) -> list:
    """获取频道的所有别名"""
    cleaned_name = clean_channel_name(channel_name)
    
    # 查找别名映射
    for base_name, aliases in CHANNEL_ALIAS.items():
        if cleaned_name == base_name:
            return aliases + [base_name]
    
    # 如果没有找到映射，返回清洗后的名称
    return [cleaned_name, channel_name]

def parse_m3u_line(line: str):
    """解析M3U的一行（EXTINF行）"""
    if not line.startswith('#EXTINF:'):
        return None
    
    # 解析EXTINF行
    line = line.strip()
    
    # 提取频道名称（逗号后面的部分）
    channel_name = ""
    tvg_info = {}
    
    # 查找最后一个逗号
    last_comma = line.rfind(',')
    if last_comma > 0:
        channel_name = line[last_comma + 1:].strip()
        
        # 提取属性
        attr_part = line[8:last_comma]  # 去掉#EXTINF:
        # 解析属性
        tvg_id_match = re.search(r'tvg-id="([^"]*)"', attr_part)
        tvg_name_match = re.search(r'tvg-name="([^"]*)"', attr_part)
        group_match = re.search(r'group-title="([^"]*)"', attr_part)
        logo_match = re.search(r'tvg-logo="([^"]*)"', attr_part)
        
        if tvg_id_match:
            tvg_info['tvg-id'] = tvg_id_match.group(1)
        if tvg_name_match:
            tvg_info['tvg-name'] = tvg_name_match.group(1)
        if group_match:
            tvg_info['group-title'] = group_match.group(1)
        if logo_match:
            tvg_info['tvg-logo'] = logo_match.group(1)
    else:
        # 简单格式
        channel_name = line.split(',')[-1].strip()
    
    return channel_name, line, tvg_info

def fetch_m3u_content(source_url: str):
    """获取M3U源内容"""
    try:
        logger.info(f"获取M3U源: {source_url[:50]}...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(source_url, headers=headers, timeout=30)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            content = response.text.splitlines()
            logger.info(f"成功获取，行数: {len(content)}")
            return content
        else:
            logger.error(f"获取失败，状态码: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"获取M3U源时出错: {str(e)}")
        return []

def build_channel_map(m3u_content: list):
    """从M3U内容构建频道映射字典，避免重复"""
    channel_map = {}
    url_set = set()  # 用于去重，避免相同URL的频道
    current_extinf = None
    current_tvg_info = {}
    duplicate_count = 0
    
    for line in m3u_content:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#EXTINF:'):
            # 解析EXTINF行
            parsed = parse_m3u_line(line)
            if parsed:
                channel_name, extinf_line, tvg_info = parsed
                current_extinf = extinf_line
                current_tvg_info = tvg_info
        elif current_extinf and not line.startswith('#'):
            # 这是URL行
            url_line = line
            
            # 计算URL的MD5用于去重
            url_hash = hashlib.md5(url_line.encode()).hexdigest()
            
            # 如果URL已经存在，跳过这个频道
            if url_hash in url_set:
                duplicate_count += 1
                current_extinf = None
                current_tvg_info = {}
                continue
                
            url_set.add(url_hash)
            
            channel_name_from_extinf = current_extinf.split(',')[-1].strip()
            
            # 清洗频道名称用于匹配
            clean_name = clean_channel_name(channel_name_from_extinf)
            
            # 获取所有可能的别名
            aliases = get_channel_aliases(channel_name_from_extinf)
            
            # 为每个别名添加映射
            for alias in aliases:
                if alias not in channel_map:
                    channel_map[alias] = []
                
                # 存储频道信息
                channel_map[alias].append((
                    channel_name_from_extinf,
                    current_extinf,
                    url_line,
                    current_tvg_info.get('group-title', '')
                ))
            
            current_extinf = None
            current_tvg_info = {}
    
    if duplicate_count > 0:
        logger.info(f"移除 {duplicate_count} 个重复URL的频道")
    
    return channel_map

def extract_special_group_from_source(source_url: str, target_group: str):
    """从M3U源中提取特定分组的全部内容"""
    logger.info(f"提取特殊分组 '{target_group}'")
    m3u_content = fetch_m3u_content(source_url)
    if not m3u_content:
        return []
    
    special_group_lines = []
    in_target_group = False
    current_extinf = None
    url_set = set()  # 用于去重
    
    for line in m3u_content:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#EXTINF:'):
            # 检查是否属于目标分组
            if f'group-title="{target_group}"' in line or target_group in line:
                in_target_group = True
                current_extinf = line
            else:
                in_target_group = False
                current_extinf = None
        elif in_target_group and current_extinf and not line.startswith('#'):
            # 检查URL是否重复
            url_hash = hashlib.md5(line.encode()).hexdigest()
            if url_hash not in url_set:
                url_set.add(url_hash)
                special_group_lines.append(current_extinf)
                special_group_lines.append(line)
            current_extinf = None
    
    logger.info(f"找到 {len(special_group_lines)//2} 个频道在分组 '{target_group}' (去重后)")
    return special_group_lines

def process_index_html():
    """处理index.html文件，提取频道信息和分组"""
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            content = f.read().splitlines()
        
        logger.info(f"读取 {INPUT_FILE}，行数: {len(content)}")
        
        # 存储文件头部（非频道内容）
        header_lines = []
        channels_by_group = {}
        current_group = None
        current_extinf = None
        current_channel_name = None
        
        for i, line in enumerate(content):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('#EXTM3U'):
                header_lines.append(line)
            elif line.startswith('#EXTINF:'):
                current_extinf = line
                
                # 提取分组信息
                group_match = re.search(r'group-title="([^"]+)"', line)
                if group_match:
                    current_group = group_match.group(1)
                else:
                    # 如果没有group-title，尝试从频道名称推断
                    channel_part = line.split(',')[-1]
                    current_group = "未分组"
                
                # 提取频道名称
                if ',' in line:
                    current_channel_name = line.split(',')[-1].strip()
                else:
                    current_channel_name = "未知频道"
                
                # 初始化分组列表
                if current_group not in channels_by_group:
                    channels_by_group[current_group] = []
                
            elif current_extinf and not line.startswith('#'):
                # 这是URL行，存储频道信息
                channels_by_group[current_group].append((
                    current_channel_name,
                    current_extinf,
                    line
                ))
                current_extinf = None
                current_channel_name = None
            else:
                # 其他行（注释等）
                header_lines.append(line)
        
        # 记录提取的信息
        for group, channels in channels_by_group.items():
            logger.info(f"分组 '{group}': {len(channels)} 个频道")
        
        return header_lines, channels_by_group
        
    except Exception as e:
        logger.error(f"处理 {INPUT_FILE} 时出错: {str(e)}")
        return [], {}

def find_best_match_in_single_source(channel_name: str, channel_map: dict):
    """在单个源中查找最佳匹配"""
    # 获取频道的所有别名
    aliases = get_channel_aliases(channel_name)
    
    # 按优先级尝试别名匹配
    for alias in aliases:
        if alias in channel_map:
            # 返回第一个匹配项
            for _, extinf_line, url_line, _ in channel_map[alias]:
                return extinf_line, url_line
    
    # 模糊匹配（包含关系）
    clean_name = clean_channel_name(channel_name)
    
    # 尝试在channel_map中查找包含关系
    for map_name, channel_list in channel_map.items():
        if clean_name in map_name or map_name in clean_name:
            for _, extinf_line, url_line, _ in channel_list:
                return extinf_line, url_line
    
    # 尝试部分匹配（针对CCTV频道）
    if 'CCTV' in clean_name:
        cctv_num_match = re.search(r'CCTV(\d+)', clean_name, re.IGNORECASE)
        if cctv_num_match:
            cctv_num = cctv_num_match.group(1)
            for map_name, channel_list in channel_map.items():
                if f'CCTV{cctv_num}' in map_name.upper():
                    for _, extinf_line, url_line, _ in channel_list:
                        return extinf_line, url_line
    
    return None

def find_best_match_in_all_sources(channel_name: str, all_source_maps: dict):
    """在所有源中查找最佳匹配"""
    # 按照优先级在所有源中查找
    for source_key, channel_map in all_source_maps.items():
        result = find_best_match_in_single_source(channel_name, channel_map)
        if result:
            logger.debug(f"  在 {source_key} 中找到匹配: {channel_name}")
            return result
    return None

def update_channels(channels_by_group: dict, all_source_maps: dict, m3u_sources: dict):
    """更新所有频道的URL，避免重复"""
    updated_lines = []
    total_channels = 0
    updated_count = 0
    failed_count = 0
    used_urls = set()  # 记录已使用的URL，避免重复
    
    for group_name, channels in channels_by_group.items():
        logger.info(f"\n处理分组: {group_name}")
        
        # 检查是否为特殊分组
        if group_name in SPECIAL_GROUPS:
            logger.info(f"特殊分组 '{group_name}'，执行完整重新获取")
            
            # 获取对应的M3U源
            source_key = GROUP_SOURCE_MAP.get(group_name)
            if not source_key:
                logger.error(f"分组 '{group_name}' 未配置M3U源，将从所有源中查找")
                # 对于未配置的特殊分组，保留原始内容
                for _, extinf_line, old_url in channels:
                    updated_lines.append(extinf_line)
                    updated_lines.append(old_url)
                continue
                
            source_url = m3u_sources.get(source_key)
            if not source_url or "example.com" in source_url:
                logger.warning(f"M3U源 {source_key} 未配置或使用默认值，无法更新特殊分组 '{group_name}'")
                # 保留原始内容
                for _, extinf_line, old_url in channels:
                    updated_lines.append(extinf_line)
                    updated_lines.append(old_url)
                continue
            
            # 提取整个分组（已去重）
            special_lines = extract_special_group_from_source(source_url, group_name)
            if special_lines:
                updated_lines.extend(special_lines)
                updated_count += len(special_lines) // 2
                total_channels += len(special_lines) // 2
                logger.info(f"成功更新特殊分组 '{group_name}'，频道数: {len(special_lines)//2}")
            else:
                logger.warning(f"未找到特殊分组 '{group_name}' 的内容，保留原始")
                for _, extinf_line, old_url in channels:
                    updated_lines.append(extinf_line)
                    updated_lines.append(old_url)
            continue
        
        # 普通分组处理
        source_key = GROUP_SOURCE_MAP.get(group_name)
        
        # 为每个频道查找匹配的URL
        for channel_name, extinf_line, old_url in channels:
            total_channels += 1
            
            # 保持EXTINF行不变，只更新URL
            updated_lines.append(extinf_line)
            
            matched = False
            new_url = None
            
            # 如果分组有配置的源，优先从该源查找
            if source_key:
                source_url = m3u_sources.get(source_key)
                if source_url and source_key in all_source_maps and "example.com" not in source_url:
                    channel_map = all_source_maps.get(source_key, {})
                    result = find_best_match_in_single_source(channel_name, channel_map)
                    if result:
                        _, new_url = result
                        matched = True
            
            # 如果未在配置源中找到，则从所有源中查找
            if not matched:
                result = find_best_match_in_all_sources(channel_name, all_source_maps)
                if result:
                    _, new_url = result
                    matched = True
            
            # 如果找到了新URL，检查是否重复
            if matched and new_url:
                # 计算URL的MD5用于去重
                url_hash = hashlib.md5(new_url.encode()).hexdigest()
                if url_hash in used_urls:
                    logger.warning(f"  ⚠ 跳过重复URL: {channel_name}")
                    updated_lines.append(old_url)
                    failed_count += 1
                else:
                    used_urls.add(url_hash)
                    updated_lines.append(new_url)
                    updated_count += 1
                    logger.info(f"  ✓ {channel_name}")
            else:
                # 使用原始URL
                updated_lines.append(old_url)
                failed_count += 1
                logger.warning(f"  ✗ 未匹配: {channel_name}，使用原URL")
    
    logger.info(f"\n更新统计:")
    logger.info(f"总频道数: {total_channels}")
    logger.info(f"成功更新: {updated_count}")
    logger.info(f"更新失败: {failed_count}")
    
    # 计算成功率
    if total_channels > 0:
        success_rate = (updated_count / total_channels) * 100
        logger.info(f"更新成功率: {success_rate:.2f}%")
    
    return updated_lines

def fetch_all_source_maps(m3u_sources: dict):
    """获取所有源的频道映射"""
    all_source_maps = {}
    
    for source_key, source_url in m3u_sources.items():
        # 跳过未配置的源
        if "example.com" in source_url:
            logger.warning(f"跳过未配置的源: {source_key}")
            continue
            
        logger.info(f"正在处理源: {source_key}")
        m3u_content = fetch_m3u_content(source_url)
        if m3u_content:
            channel_map = build_channel_map(m3u_content)
            all_source_maps[source_key] = channel_map
            logger.info(f"  ✓ 成功构建频道映射，唯一频道数: {len(channel_map)}")
        else:
            logger.warning(f"  ✗ 无法获取源内容: {source_key}")
    
    logger.info(f"总共获取到 {len(all_source_maps)} 个可用的源")
    return all_source_maps

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始IPTV自动更新 - 优化版")
    logger.info("=" * 60)
    
    start_time = datetime.now()
    
    try:
        # 0. 获取M3U源地址
        m3u_sources = get_m3u_sources_from_env()
        
        # 检查是否有配置的M3U源
        if not m3u_sources:
            logger.error("错误：未找到任何M3U源配置")
            logger.info("请设置环境变量: M3U_SOURCE_1, M3U_SOURCE_2, M3U_SOURCE_3, M3U_SOURCE_4")
            return 1
        
        logger.info(f"已配置 {len(m3u_sources)} 个M3U源")
        
        # 1. 获取所有源的频道映射
        logger.info("\n正在获取所有源的频道映射...")
        all_source_maps = fetch_all_source_maps(m3u_sources)
        
        if not all_source_maps:
            logger.error("错误：无法获取任何源的频道映射，请检查M3U源地址是否正确")
            return 1
        
        # 2. 读取并解析index.html
        header_lines, channels_by_group = process_index_html()
        if not channels_by_group:
            logger.error("未找到任何频道信息，请检查文件格式")
            return 1
        
        # 3. 更新频道URL
        updated_channel_lines = update_channels(channels_by_group, all_source_maps, m3u_sources)
        
        # 4. 生成最终内容
        final_content = []
        
        # 添加头部
        final_content.extend(header_lines)
        
        # 移除头部中可能存在的更新时间注释
        final_content = [line for line in final_content if "更新时间" not in line]
        
        # 添加频道内容
        final_content.extend(updated_channel_lines)
        
        # 添加更新时间
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        final_content.append(f"\n# 更新时间：{current_time}")
        
        # 5. 写入文件
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(final_content))
        
        # 6. 输出统计信息
        end_time = datetime.now()
        duration = (end_time - start_time).seconds
        
        logger.info("\n" + "=" * 60)
        logger.info("更新完成！")
        logger.info(f"输出文件: {OUTPUT_FILE}")
        logger.info(f"日志文件: {LOG_FILE}")
        logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"耗时: {duration} 秒")
        
        # 检查是否有重复频道
        total_channels = sum(len(channels) for channels in channels_by_group.values())
        updated_channels = len(updated_channel_lines) // 2
        if updated_channels < total_channels:
            logger.warning(f"注意：输出频道数({updated_channels})少于输入频道数({total_channels})，可能是去重导致")
        
        logger.info("=" * 60)
        
        # 7. 备份原始文件（可选）
        backup_file = f"index_backup_{start_time.strftime('%Y%m%d_%H%M%S')}.html"
        try:
            with open(INPUT_FILE, 'r', encoding='utf-8') as f_in, \
                 open(backup_file, 'w', encoding='utf-8') as f_out:
                f_out.write(f_in.read())
            logger.info(f"原始文件已备份至: {backup_file}")
        except:
            logger.warning("无法创建备份文件")
        
    except Exception as e:
        logger.error(f"更新过程中出现错误: {str(e)}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    # 检查必要文件
    if not os.path.exists(INPUT_FILE):
        logger.error(f"错误：找不到输入文件 {INPUT_FILE}")
        logger.info("请将脚本放在与 index.html 相同的目录中")
        sys.exit(1)
    
    # 运行主程序
    exit_code = main()
    sys.exit(exit_code)
