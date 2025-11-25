import requests
import re
from datetime import datetime
import os
import sys

# 配置部分
def get_config():
    m3u_sources = []
    
    # 支持最多20个源
    for i in range(1, 21):
        env_name = f"M3U_SOURCE_{i}"
        source_url = os.getenv(env_name)
        if source_url:
            m3u_sources.append(source_url)
            print(f"已加载源 {i}: {source_url.split('?')[0]}...")
    
    if not m3u_sources:
        print("错误: 未找到任何M3U源URL")
        sys.exit(1)
    
    return {
        "m3u_sources": m3u_sources,
        "group_rules": {
            "央视吉林": 0,   # 从源1获取
            "央视辽宁": 2,   # 从源3获取
            # 添加更多分组规则...
            # "央视北京": 4,   # 从源5获取
            # "央视上海": 5,   # 从源6获取
        },
        "target_file": "index.html",
        "download_dir": "downloaded_sources",
        "max_backup_sources": 5,  # 每个频道最多5个备选源
        "min_sources_per_channel": 1,  # 每个频道至少需要1个源
    }

CONFIG = get_config()

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
            print(f"正在下载源 {i+1}: {safe_url}...")
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            filename = f"{CONFIG['download_dir']}/source_{i+1}_{datetime.now().strftime('%Y%m%d')}.m3u"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(response.text)
            downloaded_files.append(filename)
            print(f"✓ 成功下载源 {i+1}")
            
        except Exception as e:
            print(f"✗ 下载失败源 {i+1}: {e}")
    
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
        print(f"解析文件 {file_path} 时出错: {e}")
    
    return channels

def extract_target_channels():
    """从目标文件中提取所有频道信息"""
    target_channels = []
    
    try:
        if not os.path.exists(CONFIG["target_file"]):
            print(f"目标文件 {CONFIG['target_file']} 不存在")
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
        
        print(f"从目标文件中提取了 {len(target_channels)} 个频道")
        
    except Exception as e:
        print(f"解析目标文件时出错: {e}")
    
    return target_channels

def evaluate_link_quality(link):
    """评估链接质量"""
    quality_score = 0
    
    quality_rules = [
        (r'cdn', 2),
        (r'proxy', 1),
        (r'rtp', 1),
        (r'udp', 1),
        (r'https://', 1),
        (r'http://', 0),
    ]
    
    for pattern, score in quality_rules:
        if re.search(pattern, link, re.IGNORECASE):
            quality_score += score
    
    return quality_score

def find_channel_by_rules(channel_name, group_title, all_channels):
    """根据规则查找匹配的频道"""
    # 规则1: 如果分组在规则中，从指定源查找
    if group_title in CONFIG["group_rules"]:
        target_source = CONFIG["group_rules"][group_title]
        for channel in all_channels:
            if (channel['group'] == group_title and 
                channel['name'] == channel_name and 
                channel['source'] == target_source):
                return channel
    
    # 规则2: 其他分组从所有源中按顺序查找
    for source_index in range(len(CONFIG["m3u_sources"])):
        for channel in all_channels:
            if channel['name'] == channel_name and channel['source'] == source_index:
                return channel
    
    return None

def get_optimized_sources(channel_name, all_channels):
    """获取优化排序的多个源"""
    sources = []
    
    # 查找所有匹配的频道
    for channel in all_channels:
        if channel['name'] == channel_name:
            sources.append({
                'link': channel['link'],
                'source': channel['source'],
                'quality_score': evaluate_link_quality(channel['link'])
            })
    
    # 去重
    unique_sources = []
    seen_links = set()
    for source in sources:
        if source['link'] not in seen_links:
            unique_sources.append(source)
            seen_links.add(source['link'])
    
    # 按质量排序
    sorted_sources = sorted(unique_sources, key=lambda x: x['quality_score'], reverse=True)
    
    return sorted_sources[:CONFIG["max_backup_sources"]]

def update_target_file_optimized(all_channels, target_channels):
    """优化版本的目标文件更新"""
    try:
        if not os.path.exists(CONFIG["target_file"]):
            print("目标文件不存在，将创建新文件")
            with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n# 自动生成的直播源文件 - 多源优化版\n")
        
        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()
        
        updated_count = 0
        lines = content.split('\n')
        new_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if line.startswith('#EXTINF'):
                channel_name = line.split(',')[-1].strip() if ',' in line else ""
                group_match = re.search(r'group-title="([^"]*)"', line)
                group_title = group_match.group(1) if group_match else ""
                
                # 根据分组规则获取主链接
                primary_channel = find_channel_by_rules(channel_name, group_title, all_channels)
                
                if primary_channel:
                    # 获取多个优化源
                    optimized_sources = get_optimized_sources(channel_name, all_channels)
                    
                    new_lines.append(line)
                    
                    # 添加主链接
                    new_lines.append(primary_channel['link'])
                    
                    # 添加备选链接
                    if len(optimized_sources) > 1:
                        new_lines.append(f"# 备选链接 (共{len(optimized_sources)}个源):")
                        for j, source in enumerate(optimized_sources[1:], 1):
                            quality_indicator = "★" * source['quality_score']
                            source_info = f"源{source['source']+1}"
                            new_lines.append(f"#备用{j}{quality_indicator}[{source_info}]: {source['link']}")
                    
                    updated_count += 1
                    print(f"✓ {channel_name}: 主链接来自源{primary_channel['source']+1}, 共{len(optimized_sources)}个源")
                    
                    # 跳过原来的链接行
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        i += 1
                else:
                    # 没有找到主链接，尝试使用优化源
                    optimized_sources = get_optimized_sources(channel_name, all_channels)
                    if optimized_sources:
                        new_lines.append(line)
                        new_lines.append(optimized_sources[0]['link'])
                        
                        if len(optimized_sources) > 1:
                            new_lines.append(f"# 备选链接 (共{len(optimized_sources)}个源):")
                            for j, source in enumerate(optimized_sources[1:], 1):
                                quality_indicator = "★" * source['quality_score']
                                source_info = f"源{source['source']+1}"
                                new_lines.append(f"#备用{j}{quality_indicator}[{source_info}]: {source['link']}")
                        
                        updated_count += 1
                        print(f"✓ {channel_name}: 使用优化源，共{len(optimized_sources)}个源")
                        
                        if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                            i += 1
                    else:
                        # 完全没找到源，保持原样
                        new_lines.append(line)
                        if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                            new_lines.append(lines[i + 1])
                            i += 1
            else:
                # 保留文件头注释，过滤掉旧的备选链接
                if i == 0 and line.startswith('#'):
                    new_lines.append(line)
                elif not line.startswith('#备用'):
                    new_lines.append(line)
            
            i += 1
        
        # 确保文件以EXTM3U开头
        if not new_lines or not new_lines[0].startswith('#EXTM3U'):
            new_lines.insert(0, '#EXTM3U')
            new_lines.insert(1, '# 自动生成的直播源文件 - 多源优化版')
        
        with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        print(f"✓ 优化完成: 共更新 {updated_count} 个频道")
        
    except Exception as e:
        print(f"✗ 更新目标文件时出错: {e}")

def main():
    print("开始优化直播源...")
    print(f"可用源数量: {len(CONFIG['m3u_sources'])}")
    print("分组规则:")
    for group, source_index in CONFIG["group_rules"].items():
        print(f"  {group} -> 从源{source_index+1}获取")
    print("其他分组 -> 从所有源中综合获取")
    print(f"每个频道最多提供 {CONFIG['max_backup_sources']} 个备选源")
    
    # 从目标文件中提取所有频道信息
    target_channels = extract_target_channels()
    
    # 下载m3u文件
    downloaded_files = download_m3u_files()
    
    if not downloaded_files:
        print("✗ 没有成功下载任何文件，终止流程")
        return
    
    # 从所有源文件中提取频道信息
    all_channels = []
    for source_index, file_path in enumerate(downloaded_files):
        channels = extract_all_channels_from_m3u(file_path, source_index)
        all_channels.extend(channels)
        print(f"从源{source_index+1}找到 {len(channels)} 个频道")
    
    # 使用优化版本更新目标文件
    update_target_file_optimized(all_channels, target_channels)
    
    # 统计信息
    total_sources = len(all_channels)
    unique_channels = len(set(channel['name'] for channel in all_channels))
    print(f"\n统计信息:")
    print(f"总源数量: {total_sources}")
    print(f"唯一频道数: {unique_channels}")
    print(f"源文件数量: {len(downloaded_files)}")
    print("优化流程完成")

if __name__ == "__main__":
    main()
