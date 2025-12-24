#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import requests
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode

# 从环境变量获取M3U源
M3U_SOURCES = {
    'M3U_SOURCE_1': os.getenv('M3U_SOURCE_1', ''),
    'M3U_SOURCE_2': os.getenv('M3U_SOURCE_2', ''),
    'M3U_SOURCE_3': os.getenv('M3U_SOURCE_3', ''),
    'M3U_SOURCE_4': os.getenv('M3U_SOURCE_4', ''),
    'M3U_SOURCE_5': os.getenv('M3U_SOURCE_5', ''),
    'M3U_SOURCE_6': os.getenv('M3U_SOURCE_6', ''),
    'M3U_SOURCE_7': os.getenv('M3U_SOURCE_7', '')
}

# 分组对应的源映射
GROUP_SOURCE_MAP = {
    '央视吉林': 'M3U_SOURCE_1',
    '央视辽宁': 'M3U_SOURCE_2',
    '央视咪咕': 'M3U_SOURCE_3',
    '央视付费频道': 'M3U_SOURCE_1',
    '卫视频道': 'M3U_SOURCE_1',
    '吉林本地': 'M3U_SOURCE_4',
    '辽宁本地': 'M3U_SOURCE_5',
    '港澳台': 'M3U_SOURCE_6',
    '咪视界': 'M3U_SOURCE_7',
    '连宇体育': 'M3U_SOURCE_7',
    '体育回看': 'M3U_SOURCE_7'
}

def log_message(msg):
    """记录日志信息"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}")

def parse_m3u_content(content):
    """解析M3U内容，返回频道列表"""
    channels = []
    lines = content.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            extinf_line = line
            i += 1
            if i < len(lines):
                url_line = lines[i].strip()
                if url_line and not url_line.startswith('#'):
                    # 提取频道信息
                    channel_info = {
                        'extinf': extinf_line,
                        'url': url_line,
                        'channel_name': '',
                        'group': ''
                    }
                    
                    # 提取频道名称
                    name_match = re.search(r',([^,]+)$', extinf_line)
                    if name_match:
                        channel_name = name_match.group(1).strip()
                        # 清理线路标识
                        channel_name_clean = re.sub(r'\s*线路\d+$', '', channel_name)
                        channel_info['channel_name'] = channel_name_clean
                    
                    # 提取分组
                    group_match = re.search(r'group-title="([^"]+)"', extinf_line)
                    if group_match:
                        channel_info['group'] = group_match.group(1)
                    
                    channels.append(channel_info)
        i += 1
    
    return channels

def fetch_m3u_source(source_url):
    """获取M3U源内容"""
    try:
        if not source_url:
            return []
        
        log_message(f"正在获取源: {source_url[:50]}...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(source_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # 尝试不同的编码
        encodings = ['utf-8', 'gbk', 'gb2312']
        for encoding in encodings:
            try:
                content = response.content.decode(encoding)
                channels = parse_m3u_content(content)
                log_message(f"成功解析 {len(channels)} 个频道")
                return channels
            except UnicodeDecodeError:
                continue
        
        # 如果所有编码都失败，使用默认utf-8并忽略错误
        content = response.content.decode('utf-8', errors='ignore')
        channels = parse_m3u_content(content)
        log_message(f"成功解析 {len(channels)} 个频道 (使用忽略错误模式)")
        return channels
        
    except Exception as e:
        log_message(f"获取源失败: {str(e)}")
        return []

def extract_channel_key(channel_name):
    """从频道名称中提取关键标识"""
    # 清理常见前缀后缀
    clean_name = channel_name.lower()
    
    # 提取CCTV、卫视等标识
    patterns = [
        r'(cctv[-\s]?\d+)',
        r'(cctv[-\s]?[a-z\d]+)',
        r'([a-z]+[-\s]?卫视)',
        r'(北京|天津|河北|山西|内蒙古|辽宁|吉林|黑龙江|上海|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|广西|海南|重庆|四川|贵州|云南|西藏|陕西|甘肃|青海|宁夏|新疆)[-\s]?(卫视|台)',
        r'(凤凰|中天|东森|TVB|翡翠|明珠|澳亚|澳门)[-\s]?[^,]*'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, clean_name, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    # 如果没有匹配到，返回清理后的名称
    return re.sub(r'[^\w\u4e00-\u9fa5]+', '', channel_name)

def find_channel_in_sources(channel_name, sources_data, group_name=None):
    """在多个源中查找频道"""
    channel_key = extract_channel_key(channel_name)
    found_channels = []
    
    for source_name, channels in sources_data.items():
        for channel in channels:
            if channel_key:
                channel_channel_key = extract_channel_key(channel['channel_name'])
                if channel_key == channel_channel_key:
                    if not group_name or channel.get('group', '') == group_name:
                        found_channels.append({
                            'source': source_name,
                            'channel': channel
                        })
    
    return found_channels

def read_existing_index():
    """读取现有的index.html文件"""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取M3U头部
        header_match = re.search(r'^#EXTM3U.*?(?=#EXTINF:)', content, re.DOTALL)
        header = header_match.group(0) if header_match else '#EXTM3U x-tvg-url="https://epg.v1.mk/fy.xml"\n'
        
        # 解析现有频道
        existing_channels = []
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#EXTINF:'):
                extinf_line = line
                i += 1
                if i < len(lines):
                    url_line = lines[i].strip()
                    if url_line and not url_line.startswith('#'):
                        # 提取信息
                        channel_info = {
                            'extinf': extinf_line,
                            'url': url_line,
                            'original_extinf': extinf_line,
                            'original_url': url_line
                        }
                        
                        # 提取分组
                        group_match = re.search(r'group-title="([^"]+)"', extinf_line)
                        if group_match:
                            channel_info['group'] = group_match.group(1)
                        
                        # 提取频道名称和线路
                        name_match = re.search(r',([^,]+)$', extinf_line)
                        if name_match:
                            full_name = name_match.group(1).strip()
                            # 分离基础名称和线路
                            line_match = re.search(r'(.*?)\s*线路(\d+)$', full_name)
                            if line_match:
                                channel_info['base_name'] = line_match.group(1).strip()
                                channel_info['line'] = int(line_match.group(2))
                            else:
                                channel_info['base_name'] = full_name
                                channel_info['line'] = 1
                        
                        existing_channels.append(channel_info)
            i += 1
        
        return header, existing_channels
        
    except FileNotFoundError:
        log_message("index.html 不存在，创建新文件")
        return '#EXTM3U x-tvg-url="https://epg.v1.mk/fy.xml"\n', []

def update_channel_urls(existing_channels, sources_data):
    """更新频道URL"""
    updated_channels = []
    channel_line_map = {}  # 记录每个分组每个频道的线路数
    
    # 第一次遍历：统计每个频道的线路数
    for channel in existing_channels:
        group = channel.get('group', '')
        base_name = channel.get('base_name', '')
        line = channel.get('line', 1)
        
        key = f"{group}||{base_name}"
        if key not in channel_line_map:
            channel_line_map[key] = []
        channel_line_map[key].append(line)
    
    # 第二次遍历：更新URL
    for channel in existing_channels:
        group = channel.get('group', '')
        base_name = channel.get('base_name', '')
        line = channel.get('line', 1)
        
        key = f"{group}||{base_name}"
        total_lines = max(channel_line_map.get(key, [1]))
        
        # 获取对应的源
        source_key = GROUP_SOURCE_MAP.get(group)
        if not source_key:
            log_message(f"未找到分组 {group} 的源映射，跳过")
            updated_channels.append(channel)
            continue
        
        # 特殊处理：连宇体育
        if group == '连宇体育':
            # 从M3U_SOURCE_7中查找分组为"冰茶体育"的频道
            found_channels = []
            if 'M3U_SOURCE_7' in sources_data:
                for src_channel in sources_data['M3U_SOURCE_7']:
                    if src_channel.get('group') == '冰茶体育':
                        found_channels.append({
                            'source': 'M3U_SOURCE_7',
                            'channel': src_channel
                        })
            
            if found_channels:
                # 只取第一个找到的频道
                channel['url'] = found_channels[0]['channel']['url']
                # 更新分组名称
                new_extinf = channel['extinf'].replace('group-title="连宇体育"', 'group-title="连宇体育"')
                channel['extinf'] = new_extinf
            else:
                log_message(f"未在M3U_SOURCE_7中找到分组为'冰茶体育'的频道")
        
        # 特殊处理：体育回看
        elif group == '体育回看':
            # 从M3U_SOURCE_7中查找分组为"体育回看"的频道
            found_channels = []
            if 'M3U_SOURCE_7' in sources_data:
                for src_channel in sources_data['M3U_SOURCE_7']:
                    if src_channel.get('group') == '体育回看':
                        found_channels.append({
                            'source': 'M3U_SOURCE_7',
                            'channel': src_channel
                        })
            
            if found_channels:
                channel['url'] = found_channels[0]['channel']['url']
        
        # 线路1：从指定源获取
        elif line == 1:
            if source_key in sources_data and sources_data[source_key]:
                # 在指定源中查找匹配的频道
                found_channels = find_channel_in_sources(base_name, {source_key: sources_data[source_key]})
                if found_channels:
                    channel['url'] = found_channels[0]['channel']['url']
                else:
                    log_message(f"未在{source_key}中找到频道: {base_name}")
        
        # 其他线路：从所有源中获取不同的URL
        else:
            all_sources = {k: v for k, v in sources_data.items() if v}
            found_channels = find_channel_in_sources(base_name, all_sources)
            
            # 去重，确保每个线路使用不同的URL
            used_urls = set()
            for existing in existing_channels:
                if existing.get('base_name') == base_name and existing.get('group') == group:
                    used_urls.add(existing.get('url', ''))
            
            # 为当前线路选择一个新的URL
            for found in found_channels:
                if found['channel']['url'] not in used_urls:
                    channel['url'] = found['channel']['url']
                    used_urls.add(found['channel']['url'])
                    break
            
            # 如果没有找到新的URL，使用第一个找到的
            if not channel.get('url') and found_channels:
                channel['url'] = found_channels[0]['channel']['url']
        
        updated_channels.append(channel)
    
    return updated_channels

def create_final_m3u(header, channels):
    """创建最终的M3U内容"""
    lines = [header.strip()]
    
    for channel in channels:
        # 构建频道名称（包含线路信息）
        base_name = channel.get('base_name', '')
        line = channel.get('line', 1)
        channel_name = f"{base_name} 线路{line}" if line > 1 else base_name
        
        # 更新EXTINF行中的频道名称
        extinf_line = channel['extinf']
        # 替换频道名称部分
        if ',' in extinf_line:
            parts = extinf_line.rsplit(',', 1)
            new_extinf = f"{parts[0]},{channel_name}"
        else:
            new_extinf = f"{extinf_line},{channel_name}"
        
        lines.append(new_extinf)
        lines.append(channel['url'])
    
    # 添加更新时间
    update_time = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
    lines.append(f'\n# 更新时间: {update_time}')
    
    return '\n'.join(lines)

def main():
    log_message("开始更新IPTV M3U列表")
    
    # 1. 获取所有M3U源数据
    sources_data = {}
    for source_key, source_url in M3U_SOURCES.items():
        if source_url:
            channels = fetch_m3u_source(source_url)
            sources_data[source_key] = channels
        else:
            log_message(f"{source_key} 未配置，跳过")
    
    # 2. 读取现有的index.html
    header, existing_channels = read_existing_index()
    log_message(f"读取到 {len(existing_channels)} 个现有频道")
    
    # 3. 更新频道URL
    updated_channels = update_channel_urls(existing_channels, sources_data)
    
    # 4. 生成最终的M3U内容
    final_content = create_final_m3u(header, updated_channels)
    
    # 5. 写入文件
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(final_content)
    
    log_message(f"更新完成，共 {len(updated_channels)} 个频道")
    log_message("index.html 已保存")

if __name__ == '__main__':
    main()
