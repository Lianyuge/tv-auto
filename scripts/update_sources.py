#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import requests
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode
from collections import defaultdict

# 从环境变量获取M3U源
M3U_SOURCES = {
    'M3U_SOURCE_1': os.getenv('M3U_SOURCE_1', ''),
    'M3U_SOURCE_2': os.getenv('M3U_SOURCE_2', ''),
    'M3U_SOURCE_3': os.getenv('M3U_SOURCE_3', ''),
    'M3U_SOURCE_4': os.getenv('M3U_SOURCE_4', ''),
    'M3U_SOURCE_5': os.getenv('M3U_SOURCE_5', ''),
    'M3U_SOURCE_6': os.getenv('M3U_SOURCE_6', ''),
    'M3U_SOURCE_7': os.getenv('M3U_SOURCE_7', ''),
    'M3U_SOURCE_8': os.getenv('M3U_SOURCE_8', '')
}

# 分组对应的源映射（线路1专用）
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

class ChannelUpdater:
    def __init__(self):
        self.logs = []
        
    def log(self, msg):
        """记录日志信息"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {msg}"
        self.logs.append(log_msg)
        print(log_msg)
    
    def parse_m3u_content(self, content):
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
            
            i += 1
        
        return channels
    
    def fetch_m3u_source(self, source_url, source_name):
        """获取M3U源内容"""
        try:
            if not source_url:
                self.log(f"源 {source_name} URL为空，跳过")
                return []
            
            self.log(f"正在获取源 {source_name}: {source_url[:50]}...")
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
                    channels = self.parse_m3u_content(content)
                    self.log(f"成功从 {source_name} 解析 {len(channels)} 个频道")
                    return channels
                except UnicodeDecodeError:
                    continue
            
            # 如果所有编码都失败，使用默认utf-8并忽略错误
            content = response.content.decode('utf-8', errors='ignore')
            channels = self.parse_m3u_content(content)
            self.log(f"成功从 {source_name} 解析 {len(channels)} 个频道 (使用忽略错误模式)")
            return channels
            
        except requests.exceptions.RequestException as e:
            self.log(f"从 {source_name} 网络请求失败: {str(e)}")
            return []
        except Exception as e:
            self.log(f"获取源 {source_name} 失败: {str(e)}")
            return []
    
    def extract_channel_key(self, channel_name):
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
    
    def get_channel_aliases(self, channel_name):
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
    
    def is_channel_match(self, channel_name1, channel_name2):
        """判断两个频道名称是否匹配"""
        if not channel_name1 or not channel_name2:
            return False
        
        # 获取两个频道的所有别名
        aliases1 = self.get_channel_aliases(channel_name1)
        aliases2 = self.get_channel_aliases(channel_name2)
        
        # 检查是否有共同的别名
        for alias1 in aliases1:
            alias1_clean = re.sub(r'\s+', '', alias1.lower())
            for alias2 in aliases2:
                alias2_clean = re.sub(r'\s+', '', alias2.lower())
                
                # 完全匹配或包含匹配
                if (alias1_clean == alias2_clean or 
                    alias1_clean in alias2_clean or
                    alias2_clean in alias1_clean):
                    return True
        
        # 关键标识匹配
        key1 = self.extract_channel_key(channel_name1)
        key2 = self.extract_channel_key(channel_name2)
        if key1 and key2 and key1 == key2:
            return True
        
        return False
    
    def find_channel_in_source(self, channel_name, source_channels, group_name=None):
        """在指定源的频道列表中查找匹配的频道"""
        if not channel_name:
            return []
        
        found_channels = []
        
        for channel in source_channels:
            source_channel_name = channel.get('channel_name', '')
            if not source_channel_name:
                continue
            
            # 判断是否匹配
            if self.is_channel_match(channel_name, source_channel_name):
                # 如果指定了分组，检查分组是否匹配
                if not group_name or channel.get('group', '') == group_name:
                    found_channels.append(channel)
        
        return found_channels
    
    def read_existing_index(self):
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
                            
                            # 提取频道名称
                            name_match = re.search(r',([^,]+)$', extinf_line)
                            if name_match:
                                full_name = name_match.group(1).strip()
                                # 清理线路标识
                                base_name = re.sub(r'\s*线路\d+$', '', full_name)
                                channel_info['channel_name'] = base_name
                                channel_info['base_name'] = base_name
                            
                            existing_channels.append(channel_info)
                i += 1
            
            return header, existing_channels
            
        except FileNotFoundError:
            self.log("index.html 不存在，创建新文件")
            return '#EXTM3U x-tvg-url="https://epg.v1.mk/fy.xml"\n', []
        except Exception as e:
            self.log(f"读取index.html失败: {str(e)}")
            return '#EXTM3U x-tvg-url="https://epg.v1.mk/fy.xml"\n', []
    
    def process_channels(self, existing_channels, sources_data):
        """处理所有频道"""
        self.log("=" * 60)
        self.log("开始处理频道更新")
        self.log("=" * 60)
        
        # 第一阶段：按照原有规则处理线路1
        self.log("\n第一阶段：按照分组规则处理")
        self.log("-" * 60)
        
        # 按分组和频道名称组织数据
        channel_dict = defaultdict(list)
        
        for channel in existing_channels:
            group = channel.get('group', '')
            base_name = channel.get('base_name', '')
            
            if group and base_name:
                key = f"{group}||{base_name}"
                # 每个频道只需要保留一个EXTINF行作为模板
                if not channel_dict[key]:
                    channel_dict[key].append({
                        'extinf': channel['extinf'],
                        'urls': [],  # 所有播放源URL
                        'group': group,
                        'base_name': base_name
                    })
                # 添加初始URL
                channel_dict[key][0]['urls'].append(channel['url'])
        
        # 处理每个分组和频道
        final_channels = []
        processed_keys = []
        
        for key, channel_list in channel_dict.items():
            group = channel_list[0]['group']
            base_name = channel_list[0]['base_name']
            extinf_template = channel_list[0]['extinf']
            
            self.log(f"\n处理频道: {group} - {base_name}")
            
            # 获取对应的源（线路1专用）
            source_key = GROUP_SOURCE_MAP.get(group)
            
            # 特殊处理：连宇体育
            if group == '连宇体育':
                self.log(f"  特殊分组: {group}")
                found_channels = []
                if 'M3U_SOURCE_7' in sources_data:
                    for src_channel in sources_data['M3U_SOURCE_7']:
                        if src_channel.get('group') == '冰茶体育':
                            found_channels.append(src_channel)
                
                if found_channels:
                    # 清空原有URL，使用找到的第一个URL
                    channel_list[0]['urls'] = [found_channels[0]['url']]
                    self.log(f"  ✓ 更新播放源 (来自M3U_SOURCE_7)")
                else:
                    self.log(f"  ✗ 未在M3U_SOURCE_7中找到分组为'冰茶体育'的频道")
            
            # 特殊处理：体育回看
            elif group == '体育回看':
                self.log(f"  特殊分组: {group}")
                found_channels = []
                if 'M3U_SOURCE_7' in sources_data:
                    for src_channel in sources_data['M3U_SOURCE_7']:
                        if src_channel.get('group') == '体育回看':
                            found_channels.append(src_channel)
                
                if found_channels:
                    # 清空原有URL，使用找到的第一个URL
                    channel_list[0]['urls'] = [found_channels[0]['url']]
                    self.log(f"  ✓ 更新播放源 (来自M3U_SOURCE_7)")
                else:
                    self.log(f"  ✗ 未在M3U_SOURCE_7中找到分组为'体育回看'的频道")
            
            # 其他分组
            else:
                # 线路1：从指定源获取
                if source_key and source_key in sources_data and sources_data[source_key]:
                    found_channels = self.find_channel_in_source(base_name, sources_data[source_key])
                    if found_channels:
                        # 使用找到的第一个频道作为线路1
                        if channel_list[0]['urls']:
                            # 替换第一个URL
                            channel_list[0]['urls'][0] = found_channels[0]['url']
                        else:
                            channel_list[0]['urls'].append(found_channels[0]['url'])
                        
                        self.log(f"  ✓ 更新线路1播放源 (来自{source_key})")
                        
                        # 收集其他源中的相同频道
                        all_other_urls = []
                        for other_source_key, other_channels in sources_data.items():
                            # 跳过指定的源（已经用作线路1）
                            if other_source_key == source_key:
                                continue
                            
                            if other_channels:
                                other_found = self.find_channel_in_source(base_name, other_channels)
                                for found in other_found:
                                    if found['url'] not in all_other_urls:
                                        all_other_urls.append(found['url'])
                        
                        # 添加其他源的URL
                        for url in all_other_urls:
                            if url not in channel_list[0]['urls']:
                                channel_list[0]['urls'].append(url)
                        
                        if all_other_urls:
                            self.log(f"  ✓ 找到 {len(all_other_urls)} 个其他播放源")
                    else:
                        self.log(f"  ✗ 未在{source_key}中找到频道")
                else:
                    self.log(f"  ✗ 源 {source_key} 未配置或无数据")
            
            # 记录处理结果
            processed_keys.append(key)
            
            # 统计当前频道的播放源数量
            url_count = len(channel_list[0]['urls'])
            if url_count > 0:
                self.log(f"  结果: 共 {url_count} 个播放源")
            
            # 添加到最终频道列表
            for url in channel_list[0]['urls']:
                final_channels.append({
                    'extinf': extinf_template,
                    'url': url,
                    'group': group,
                    'base_name': base_name
                })
        
        return final_channels
    
    def create_final_m3u(self, header, channels):
        """创建最终的M3U内容"""
        lines = [header.strip()]
        
        # 添加所有频道（相同的EXTINF行，不同的URL）
        for channel in channels:
            lines.append(channel['extinf'])
            lines.append(channel['url'])
        
        # 添加更新时间
        update_time = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
        lines.append(f'\n# 更新时间: {update_time}')
        
        # 添加处理摘要
        lines.append('\n# 处理摘要:')
        
        # 统计每个频道的播放源数量
        channel_stats = defaultdict(list)
        for channel in channels:
            key = f"{channel['group']}||{channel['base_name']}"
            if channel['url'] not in channel_stats[key]:
                channel_stats[key].append(channel['url'])
        
        lines.append(f"# 总频道数: {len(channel_stats)}")
        lines.append(f"# 总播放源数: {len(channels)}")
        lines.append("#")
        
        # 按分组统计
        group_stats = defaultdict(lambda: {'channels': 0, 'sources': 0})
        for key, urls in channel_stats.items():
            group = key.split('||')[0]
            group_stats[group]['channels'] += 1
            group_stats[group]['sources'] += len(urls)
        
        lines.append("# 分组统计:")
        for group, stats in sorted(group_stats.items()):
            lines.append(f"#   {group}: {stats['channels']}个频道, {stats['sources']}个播放源")
        
        # 添加详细日志
        lines.append('\n# 详细处理日志:')
        for log in self.logs:
            lines.append(f'# {log}')
        
        return '\n'.join(lines)
    
    def run(self):
        """运行主程序"""
        self.log("=" * 60)
        self.log("开始更新IPTV M3U列表")
        self.log("=" * 60)
        
        # 记录频道映射配置
        self.log("频道名称映射配置:")
        for base_name, aliases in CHANNEL_NAME_MAPPING.items():
            self.log(f"  {base_name}: {aliases}")
        
        # 1. 获取所有M3U源数据
        sources_data = {}
        for source_key, source_url in M3U_SOURCES.items():
            if source_url:
                channels = self.fetch_m3u_source(source_url, source_key)
                sources_data[source_key] = channels
            else:
                self.log(f"{source_key} 未配置，跳过")
        
        # 统计源数据
        total_channels_in_sources = sum(len(channels) for channels in sources_data.values())
        self.log(f"从所有源中获取到 {total_channels_in_sources} 个频道")
        
        # 2. 读取现有的index.html
        header, existing_channels = self.read_existing_index()
        self.log(f"读取到 {len(existing_channels)} 个现有频道")
        
        # 3. 处理所有频道
        final_channels = self.process_channels(existing_channels, sources_data)
        
        # 4. 生成最终的M3U内容
        final_content = self.create_final_m3u(header, final_channels)
        
        # 5. 写入文件
        try:
            with open('index.html', 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            # 统计结果
            channel_dict = defaultdict(list)
            for channel in final_channels:
                key = f"{channel['group']}||{channel['base_name']}"
                if channel['url'] not in channel_dict[key]:
                    channel_dict[key].append(channel['url'])
            
            self.log(f"\n更新完成")
            self.log(f"最终结果: {len(channel_dict)} 个频道, {len(final_channels)} 个播放源")
            self.log("index.html 已成功保存")
            
        except Exception as e:
            self.log(f"写入文件失败: {str(e)}")
            raise
        
        self.log("=" * 60)
        self.log("更新完成")
        self.log("=" * 60)

def main():
    updater = ChannelUpdater()
    try:
        updater.run()
    except Exception as e:
        updater.log(f"程序执行失败: {str(e)}")
        raise

if __name__ == '__main__':
    main()
