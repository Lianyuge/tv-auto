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

# 频道名称映射配置
CHANNEL_NAME_MAPPING = {
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
}

def log_message(msg):
    """记录日志信息"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}")

def parse_m3u_content(content):
    """解析M3U内容，支持标准格式和非标准格式"""
    channels = []
    lines = content.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 跳过空行和注释行（除了#EXTINF）
        if not line or (line.startswith('#') and not line.startswith('#EXTINF:')):
            i += 1
            continue
        
        # 情况1：标准M3U格式 - #EXTINF行
        if line.startswith('#EXTINF:'):
            extinf_line = line
            i += 1
            
            # 寻找下一个非空非注释行作为URL
            while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith('#')):
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
                    log_message(f"解析标准格式: {channel_info['channel_name']}")
        
        # 情况2：非标准格式 - 逗号分隔的频道名和URL
        elif ',' in line:
            # 检查是否为URL格式（包含http://或https://）
            parts = line.split(',', 1)
            if len(parts) == 2:
                channel_name_part = parts[0].strip()
                url_part = parts[1].strip()
                
                # 验证URL部分是否为有效的URL
                if url_part.startswith(('http://', 'https://')):
                    # 创建模拟的EXTINF行
                    extinf_line = f'#EXTINF:-1,{channel_name_part}'
                    
                    channel_info = {
                        'extinf': extinf_line,
                        'url': url_part,
                        'channel_name': channel_name_part,
                        'group': ''  # 非标准格式通常没有分组信息
                    }
                    
                    channels.append(channel_info)
                    log_message(f"解析非标准格式: {channel_name_part}")
        
        # 情况3：可能是URL行，但前面没有#EXTINF（跳过，避免重复解析）
        elif line.startswith(('http://', 'https://')):
            # 这可能是前面#EXTINF行的URL，已经处理过了，跳过
            pass
        
        i += 1
    
    return channels

def fetch_m3u_source(source_url):
    """获取M3U源内容"""
    try:
        if not source_url:
            log_message("源URL为空，跳过")
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
        
    except requests.exceptions.RequestException as e:
        log_message(f"网络请求失败: {str(e)}")
        return []
    except Exception as e:
        log_message(f"获取源失败: {str(e)}")
        return []

def extract_channel_key(channel_name):
    """从频道名称中提取关键标识"""
    if not channel_name:
        return ""
    
    # 清理常见前缀后缀
    clean_name = channel_name.lower()
    
    # 处理数字频道（如100, 101等）
    if re.match(r'^\d+$', clean_name):
        return clean_name
    
    # 提取CCTV、卫视等标识
    patterns = [
        r'(cctv[-\s]?\d+)',
        r'(cctv[-\s]?[a-z\d]+)',
        r'([a-z]+[-\s]?卫视)',
        r'(北京|天津|河北|山西|内蒙古|辽宁|吉林|黑龙江|上海|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|广西|海南|重庆|四川|贵州|云南|西藏|陕西|甘肃|青海|宁夏|新疆)[-\s]?(卫视|台)',
        r'(凤凰|中天|东森|TVB|翡翠|明珠|澳亚|澳门)[-\s]?[^,]*',
        r'(CETV[-\s]?\d+)',
        r'(湖南|浙江|江苏|东方|北京|安徽|山东|广东|深圳|天津|重庆|黑龙江|湖北|四川|东南|江西|广西|河南|河北|云南|陕西|贵州|甘肃|宁夏|青海|新疆|西藏|内蒙古|兵团|厦门|海峡|三沙)[-\s]?(卫视|台)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, clean_name, re.IGNORECASE)
        if match:
            key = match.group(1).upper()
            # 清理空格和特殊字符
            key = re.sub(r'[^\w\u4e00-\u9fa5]+', '', key)
            return key
    
    # 如果没有匹配到，返回清理后的名称
    return re.sub(r'[^\w\u4e00-\u9fa5]+', '', clean_name)

def get_channel_aliases(channel_name):
    """获取频道的所有别名"""
    aliases = [channel_name]
    
    # 检查频道名称映射
    for base_name, alias_list in CHANNEL_NAME_MAPPING.items():
        # 如果当前频道名称是映射中的基础名称
        if base_name == channel_name:
            aliases.extend(alias_list)
        # 如果当前频道名称是映射中的别名
        elif channel_name in alias_list:
            aliases.append(base_name)
            aliases.extend([a for a in alias_list if a != channel_name])
    
    # 去重
    unique_aliases = []
    seen = set()
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            unique_aliases.append(alias)
    
    return unique_aliases

def find_channel_in_sources(channel_name, sources_data, group_name=None):
    """在多个源中查找频道"""
    if not channel_name:
        return []
    
    # 获取所有可能的别名
    aliases = get_channel_aliases(channel_name)
    
    found_channels = []
    already_found_urls = set()  # 避免重复添加相同URL
    
    for source_name, channels in sources_data.items():
        for channel in channels:
            source_channel_name = channel.get('channel_name', '')
            if not source_channel_name:
                continue
                
            # 检查当前频道的名称是否与任何别名匹配
            for alias in aliases:
                # 直接名称匹配（忽略大小写和空格）
                alias_clean = re.sub(r'\s+', '', alias.lower())
                channel_name_clean = re.sub(r'\s+', '', source_channel_name.lower())
                
                # 完全匹配或包含匹配
                if (alias_clean == channel_name_clean or 
                    alias_clean in channel_name_clean or
                    channel_name_clean in alias_clean):
                    
                    if channel['url'] not in already_found_urls:
                        if not group_name or channel.get('group', '') == group_name:
                            found_channels.append({
                                'source': source_name,
                                'channel': channel,
                                'matched_alias': alias
                            })
                            already_found_urls.add(channel['url'])
                        break
                
                # 关键标识匹配
                else:
                    alias_key = extract_channel_key(alias)
                    channel_key = extract_channel_key(source_channel_name)
                    if alias_key and channel_key and alias_key == channel_key:
                        if channel['url'] not in already_found_urls:
                            if not group_name or channel.get('group', '') == group_name:
                                found_channels.append({
                                    'source': source_name,
                                    'channel': channel,
                                    'matched_alias': alias
                                })
                                already_found_urls.add(channel['url'])
                            break
    
    return found_channels

def read_existing_index():
    """读取现有的index.html文件"""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取M3U头部
        header_match = re.search(r'^#EXTM3U.*?(?=#EXTINF:)', content, re.DOTALL | re.MULTILINE)
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
    except Exception as e:
        log_message(f"读取index.html失败: {str(e)}")
        return '#EXTM3U x-tvg-url="https://epg.v1.mk/fy.xml"\n', []

def update_channel_urls(existing_channels, sources_data):
    """更新频道URL"""
    updated_channels = []
    channel_line_map = {}  # 记录每个分组每个频道的线路数
    
    log_message(f"开始更新 {len(existing_channels)} 个频道")
    
    # 第一次遍历：统计每个频道的线路数
    for channel in existing_channels:
        group = channel.get('group', '')
        base_name = channel.get('base_name', '')
        line = channel.get('line', 1)
        
        if group and base_name:
            key = f"{group}||{base_name}"
            if key not in channel_line_map:
                channel_line_map[key] = []
            channel_line_map[key].append(line)
    
    # 第二次遍历：更新URL
    for channel_idx, channel in enumerate(existing_channels):
        group = channel.get('group', '')
        base_name = channel.get('base_name', '')
        line = channel.get('line', 1)
        
        if not group or not base_name:
            log_message(f"跳过无效频道: {channel.get('extinf', '未知')}")
            updated_channels.append(channel)
            continue
        
        key = f"{group}||{base_name}"
        total_lines = max(channel_line_map.get(key, [1]))
        
        # 获取对应的源
        source_key = GROUP_SOURCE_MAP.get(group)
        if not source_key:
            log_message(f"未找到分组 {group} 的源映射，保持原URL")
            updated_channels.append(channel)
            continue
        
        # 特殊处理：连宇体育
        if group == '连宇体育':
            log_message(f"处理特殊分组: {group}")
            found_channels = []
            if 'M3U_SOURCE_7' in sources_data:
                for src_channel in sources_data['M3U_SOURCE_7']:
                    if src_channel.get('group') == '冰茶体育':
                        found_channels.append({
                            'source': 'M3U_SOURCE_7',
                            'channel': src_channel
                        })
            
            if found_channels:
                channel['url'] = found_channels[0]['channel']['url']
                log_message(f"更新 {base_name} 的URL (连宇体育)")
            else:
                log_message(f"未在M3U_SOURCE_7中找到分组为'冰茶体育'的频道，保持原URL")
        
        # 特殊处理：体育回看
        elif group == '体育回看':
            log_message(f"处理特殊分组: {group}")
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
                log_message(f"更新 {base_name} 的URL (体育回看)")
            else:
                log_message(f"未在M3U_SOURCE_7中找到分组为'体育回看'的频道，保持原URL")
        
        # 线路1：从指定源获取
        elif line == 1:
            if source_key in sources_data and sources_data[source_key]:
                # 在指定源中查找匹配的频道
                found_channels = find_channel_in_sources(base_name, {source_key: sources_data[source_key]})
                if found_channels:
                    channel['url'] = found_channels[0]['channel']['url']
                    log_message(f"更新 {base_name} 线路{line} 的URL (来自{source_key})")
                    if len(found_channels) > 1:
                        log_message(f"  找到 {len(found_channels)} 个匹配项，使用第一个")
                else:
                    log_message(f"未在{source_key}中找到频道: {base_name}，保持原URL")
        
        # 其他线路：从所有源中获取不同的URL
        else:
            all_sources = {k: v for k, v in sources_data.items() if v}
            found_channels = find_channel_in_sources(base_name, all_sources)
            
            if found_channels:
                # 去重，确保每个线路使用不同的URL
                used_urls = set()
                # 收集当前频道组中已经使用的URL
                for existing in existing_channels:
                    if existing.get('base_name') == base_name and existing.get('group') == group:
                        used_urls.add(existing.get('url', ''))
                
                # 为当前线路选择一个新的URL
                new_url_found = False
                for found in found_channels:
                    if found['channel']['url'] not in used_urls:
                        channel['url'] = found['channel']['url']
                        used_urls.add(found['channel']['url'])
                        new_url_found = True
                        log_message(f"更新 {base_name} 线路{line} 的URL (新源: {found.get('matched_alias', '未知')})")
                        break
                
                # 如果没有找到新的URL，使用第一个找到的
                if not new_url_found and found_channels:
                    channel['url'] = found_channels[0]['channel']['url']
                    log_message(f"更新 {base_name} 线路{line} 的URL (使用第一个找到的源: {found_channels[0].get('matched_alias', '未知')})")
        
        updated_channels.append(channel)
    
    return updated_channels

def create_final_m3u(header, channels):
    """创建最终的M3U内容"""
    lines = [header.strip()]
    
    for channel in channels:
        # 构建频道名称（包含线路信息）
        base_name = channel.get('base_name', '')
        line = channel.get('line', 1)
        
        if line > 1 and base_name:
            channel_name = f"{base_name} 线路{line}"
        else:
            channel_name = base_name
        
        # 更新EXTINF行中的频道名称
        extinf_line = channel['extinf']
        # 替换频道名称部分
        if ',' in extinf_line:
            parts = extinf_line.rsplit(',', 1)
            # 保持原有的tvg-id、tvg-name等属性
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
    log_message("=" * 50)
    log_message("开始更新IPTV M3U列表")
    log_message("=" * 50)
    
    # 记录频道映射配置
    log_message("频道名称映射配置:")
    for base_name, aliases in CHANNEL_NAME_MAPPING.items():
        log_message(f"  {base_name}: {aliases}")
    
    # 1. 获取所有M3U源数据
    sources_data = {}
    for source_key, source_url in M3U_SOURCES.items():
        if source_url:
            log_message(f"处理源: {source_key}")
            channels = fetch_m3u_source(source_url)
            sources_data[source_key] = channels
            log_message(f"从{source_key}获取到 {len(channels)} 个频道")
        else:
            log_message(f"{source_key} 未配置，跳过")
    
    # 统计源数据
    total_channels_in_sources = sum(len(channels) for channels in sources_data.values())
    log_message(f"从所有源中获取到 {total_channels_in_sources} 个频道")
    
    # 2. 读取现有的index.html
    header, existing_channels = read_existing_index()
    log_message(f"读取到 {len(existing_channels)} 个现有频道")
    
    # 3. 更新频道URL
    updated_channels = update_channel_urls(existing_channels, sources_data)
    
    # 4. 生成最终的M3U内容
    final_content = create_final_m3u(header, updated_channels)
    
    # 5. 写入文件
    try:
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(final_content)
        
        log_message(f"更新完成，共 {len(updated_channels)} 个频道")
        log_message("index.html 已成功保存")
        
        # 统计更改数量
        changed_count = 0
        for i, (old, new) in enumerate(zip(existing_channels, updated_channels)):
            if old.get('url') != new.get('url'):
                changed_count += 1
        
        log_message(f"共更新了 {changed_count} 个频道的URL")
        
    except Exception as e:
        log_message(f"写入文件失败: {str(e)}")
        raise
    
    log_message("=" * 50)
    log_message("更新完成")
    log_message("=" * 50)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log_message(f"程序执行失败: {str(e)}")
        raise
