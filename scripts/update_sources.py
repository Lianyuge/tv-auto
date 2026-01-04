#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV自动更新脚本
说明：根据index.html中的频道名称，从指定M3U源获取直播源地址并更新
支持从环境变量或GitHub Secrets获取M3U源地址
"""

import requests
import re
from datetime import datetime
import logging
import sys
import os
import json

# ==================== 配置区域 ====================

# 从环境变量获取M3U源地址（优先使用环境变量）
def get_m3u_sources_from_env():
    """从环境变量获取M3U源地址"""
    sources = {}
    
    # 尝试从环境变量获取
    for i in range(1, 5):
        env_key = f"M3U_SOURCE_{i}"
        env_value = os.environ.get(env_key)
        
        if env_value:
            sources[env_key] = env_value
            print(f"✓ 从环境变量获取到 {env_key}")
        else:
            # 如果环境变量没有，使用默认值（仅用于本地测试）
            default_sources = {
                "M3U_SOURCE_1": "http://example.com/source1.m3u",  # 央视源
                "M3U_SOURCE_2": "http://example.com/source2.m3u",  # 咪咕源
                "M3U_SOURCE_3": "http://example.com/source3.m3u",  # 卫视/付费源
                "M3U_SOURCE_4": "http://example.com/source4.m3u"   # 吉林源
            }
            if env_key in default_sources:
                sources[env_key] = default_sources[env_key]
                print(f"⚠ 使用默认值 {env_key} (环境变量未设置)")
    
    return sources

# 分组与源的映射规则
GROUP_SOURCE_MAP = {
    "央视": "M3U_SOURCE_1",
    "咪咕频道": "M3U_SOURCE_2", 
    "地方卫视": "M3U_SOURCE_3",
    "付费频道": "M3U_SOURCE_3",
    "辽宁地方": "M3U_SOURCE_1",  # 线路1频道
    "吉林地方": "M3U_SOURCE_4",  # 线路1频道
    "冰茶体育": "M3U_SOURCE_2",  # 特殊分组：整个分组重新获取
    "体育回看": "M3U_SOURCE_2"   # 特殊分组：整个分组重新获取
}

# 需要完整重新获取的特殊分组
SPECIAL_GROUPS = ["冰茶体育", "体育回看"]

# 文件路径
INPUT_FILE = "index.html"      # 输入文件（模板）
OUTPUT_FILE = "index.html"     # 输出文件（更新后）
LOG_FILE = "update_log.txt"    # 日志文件

# 频道名称清洗规则（用于匹配）
CLEAN_PATTERNS = [
    (r'CCTV-?', 'CCTV'),           # CCTV-1 -> CCTV1
    (r'[-\s]', ''),                # 移除空格和短横线
    (r'\(.*?\)', ''),              # 移除括号内容
    (r'\[.*?\]', ''),              # 移除方括号内容
    (r'标清|高清|HD|SD|直播', ''), # 移除画质标识
    (r'频道|台', ''),              # 移除频道/台字
    (r'^.*?卫视', '卫视'),         # 统一卫视格式
]

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
    
    return cleaned.upper()

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
        
        if tvg_id_match:
            tvg_info['tvg-id'] = tvg_id_match.group(1)
        if tvg_name_match:
            tvg_info['tvg-name'] = tvg_name_match.group(1)
        if group_match:
            tvg_info['group-title'] = group_match.group(1)
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
    """从M3U内容构建频道映射字典"""
    channel_map = {}
    current_extinf = None
    current_tvg_info = {}
    
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
            channel_name_from_extinf = current_extinf.split(',')[-1].strip()
            
            # 清洗频道名称用于匹配
            clean_name = clean_channel_name(channel_name_from_extinf)
            
            if clean_name not in channel_map:
                channel_map[clean_name] = []
            
            # 存储频道信息
            channel_map[clean_name].append((
                channel_name_from_extinf,
                current_extinf,
                url_line,
                current_tvg_info.get('group-title', '')
            ))
            
            current_extinf = None
            current_tvg_info = {}
    
    logger.info(f"构建频道映射，唯一频道数: {len(channel_map)}")
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
    
    for line in m3u_content:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#EXTINF:'):
            # 检查是否属于目标分组
            if f'group-title="{target_group}"' in line or target_group in line:
                in_target_group = True
                current_extinf = line
                special_group_lines.append(line)
            else:
                in_target_group = False
                current_extinf = None
        elif in_target_group and current_extinf and not line.startswith('#'):
            # 添加URL行
            special_group_lines.append(line)
            current_extinf = None
    
    logger.info(f"找到 {len(special_group_lines)//2} 个频道在分组 '{target_group}'")
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
                    current_group = "未知分组"
                
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

def find_best_match(channel_name: str, channel_map: dict):
    """在频道映射中查找最佳匹配"""
    clean_name = clean_channel_name(channel_name)
    
    # 1. 精确匹配（清洗后的名称）
    if clean_name in channel_map:
        # 返回第一个匹配项
        for _, extinf_line, url_line, _ in channel_map[clean_name]:
            return extinf_line, url_line
    
    # 2. 模糊匹配（包含关系）
    for map_name, channel_list in channel_map.items():
        if clean_name in map_name or map_name in clean_name:
            for _, extinf_line, url_line, _ in channel_list:
                return extinf_line, url_line
    
    # 3. 尝试匹配部分（针对CCTV频道）
    if 'CCTV' in clean_name:
        cctv_num_match = re.search(r'CCTV(\d+)', clean_name, re.IGNORECASE)
        if cctv_num_match:
            cctv_num = cctv_num_match.group(1)
            for map_name, channel_list in channel_map.items():
                if f'CCTV{cctv_num}' in map_name.upper():
                    for _, extinf_line, url_line, _ in channel_list:
                        return extinf_line, url_line
    
    logger.warning(f"未找到匹配的频道: {channel_name} (清洗后: {clean_name})")
    return None

def update_channels(channels_by_group: dict, m3u_sources: dict):
    """更新所有频道的URL"""
    updated_lines = []
    total_channels = 0
    updated_count = 0
    failed_count = 0
    
    for group_name, channels in channels_by_group.items():
        logger.info(f"\n处理分组: {group_name}")
        
        # 检查是否为特殊分组
        if group_name in SPECIAL_GROUPS:
            logger.info(f"特殊分组 '{group_name}'，执行完整重新获取")
            
            # 获取对应的M3U源
            source_key = GROUP_SOURCE_MAP.get(group_name)
            if not source_key:
                logger.error(f"分组 '{group_name}' 未配置M3U源")
                continue
                
            source_url = m3u_sources.get(source_key)
            if not source_url:
                logger.error(f"未找到M3U源: {source_key}")
                continue
            
            # 检查是否为默认URL（example.com）
            if "example.com" in source_url:
                logger.error(f"M3U源 {source_key} 未正确配置，使用默认值，无法更新分组 '{group_name}'")
                # 保留原始内容
                for _, extinf_line, old_url in channels:
                    updated_lines.append(extinf_line)
                    updated_lines.append(old_url)
                continue
            
            # 提取整个分组
            special_lines = extract_special_group_from_source(source_url, group_name)
            if special_lines:
                updated_lines.extend(special_lines)
                updated_count += len(special_lines) // 2
                total_channels += len(special_lines) // 2
            else:
                logger.warning(f"未找到特殊分组 '{group_name}' 的内容，保留原始")
                for _, extinf_line, old_url in channels:
                    updated_lines.append(extinf_line)
                    updated_lines.append(old_url)
            continue
        
        # 普通分组处理
        source_key = GROUP_SOURCE_MAP.get(group_name)
        if not source_key:
            logger.warning(f"分组 '{group_name}' 未配置M3U源，跳过")
            continue
            
        source_url = m3u_sources.get(source_key)
        if not source_url:
            logger.error(f"未找到M3U源: {source_key}")
            continue
        
        # 检查是否为默认URL（example.com）
        if "example.com" in source_url:
            logger.warning(f"M3U源 {source_key} 未正确配置，使用默认值，跳过分组 '{group_name}'")
            # 保留原始内容
            for _, extinf_line, old_url in channels:
                updated_lines.append(extinf_line)
                updated_lines.append(old_url)
                total_channels += 1
            continue
        
        # 获取并构建该源的频道映射
        logger.info(f"从 {source_key} 获取频道映射")
        m3u_content = fetch_m3u_content(source_url)
        if not m3u_content:
            logger.error(f"无法从 {source_key} 获取内容，跳过分组 {group_name}")
            # 保留原始内容
            for _, extinf_line, old_url in channels:
                updated_lines.append(extinf_line)
                updated_lines.append(old_url)
                total_channels += 1
            continue
            
        channel_map = build_channel_map(m3u_content)
        
        # 为每个频道查找匹配的URL
        for channel_name, extinf_line, old_url in channels:
            total_channels += 1
            
            # 保持EXTINF行不变，只更新URL
            updated_lines.append(extinf_line)
            
            # 查找匹配的URL
            match_result = find_best_match(channel_name, channel_map)
            if match_result:
                new_extinf, new_url = match_result
                updated_lines.append(new_url)
                updated_count += 1
                logger.info(f"  ✓ 更新: {channel_name}")
            else:
                # 使用原始URL
                updated_lines.append(old_url)
                failed_count += 1
                logger.warning(f"  ✗ 未匹配: {channel_name}，使用原URL")
    
    logger.info(f"\n更新统计:")
    logger.info(f"总频道数: {total_channels}")
    logger.info(f"成功更新: {updated_count}")
    logger.info(f"更新失败: {failed_count}")
    
    return updated_lines

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始IPTV自动更新")
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
        for key, value in m3u_sources.items():
            # 不显示完整的URL以防泄露
            display_value = value if len(value) < 50 else value[:50] + "..."
            logger.info(f"  {key}: {display_value}")
        
        # 1. 读取并解析index.html
        header_lines, channels_by_group = process_index_html()
        if not channels_by_group:
            logger.error("未找到任何频道信息，请检查文件格式")
            return 1
        
        # 2. 更新频道URL
        updated_channel_lines = update_channels(channels_by_group, m3u_sources)
        
        # 3. 生成最终内容
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
        
        # 4. 写入文件
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(final_content))
        
        # 5. 输出统计信息
        end_time = datetime.now()
        duration = (end_time - start_time).seconds
        
        logger.info("\n" + "=" * 60)
        logger.info("更新完成！")
        logger.info(f"输出文件: {OUTPUT_FILE}")
        logger.info(f"日志文件: {LOG_FILE}")
        logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"耗时: {duration} 秒")
        logger.info("=" * 60)
        
        # 6. 备份原始文件（可选）
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
