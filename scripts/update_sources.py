import requests
import re
from datetime import datetime
import os
import sys

# 配置部分 - 从环境变量获取带token的URL
def get_config():
    # 从环境变量获取URL（在GitHub Secrets中设置）
    m3u_sources = []
    
    # 添加所有配置的源
    for i in range(1, 10):  # 假设最多9个源
        env_name = f"M3U_SOURCE_{i}"
        source_url = os.getenv(env_name)
        if source_url:
            m3u_sources.append(source_url)
            print(f"已加载源 {i}: {source_url.split('?')[0]}...")  # 不打印完整URL避免泄露token
    
    if not m3u_sources:
        print("错误: 未找到任何M3U源URL，请检查GitHub Secrets设置")
        sys.exit(1)
    
    return {
        # 要下载的m3u文件列表（从环境变量获取）
        "m3u_sources": m3u_sources,
        
        # 要提取的关键词列表 - 基于频道名称
        "keywords": [
            "CCTV-1",
            "CCTV-2",
            "CCTV-3",
            "CCTV-4",
            "CCTV-5",
            "CCTV-5+",
            "CCTV-6",
            "CCTV-7",
            "CCTV-8",
            "CCTV-9",
            "CCTV-10",
            "CCTV-11",
            "CCTV-12",
            "CCTV-13",
            "湖南卫视",
            "辽宁卫视",
            "辽宁都市",
            "辽宁影视剧",
            "辽宁体育",
            "辽宁生活",
            "辽宁教育青少",
            "辽宁北方",
            "辽宁宜佳购物",
            "沈阳新闻",
            "辽宁经济",
            "吉林卫视",
            "吉林都市",
            "吉林综艺",
            "吉林影视",
            "吉林生活",
            "吉林乡村",
            "长影频道",
            "吉林教育",
            "延边卫视",
            "松原",
            "松原公共",
            "北京卫视",
            "江苏卫视",
            "东方卫视"
            # 添加您需要的其他频道名称
        ],
        
        # 分组规则映射
        "group_rules": {
            "央视吉林": 0,  # 从第一个源 (M3U_SOURCE_1) 获取
            "央视-辽宁地区": 1,  # 从第二个源 (M3U_SOURCE_2) 获取
            # 可以添加更多分组规则
        },
        
        # 目标文件路径
        "target_file": "live_sources.txt",
        
        # 临时下载目录
        "download_dir": "downloaded_sources"
    }

CONFIG = get_config()

def download_m3u_files():
    """下载所有m3u文件（带token认证）"""
    if not os.path.exists(CONFIG["download_dir"]):
        os.makedirs(CONFIG["download_dir"])
    
    downloaded_files = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for i, url in enumerate(CONFIG["m3u_sources"]):
        try:
            # 安全地打印URL（不显示token）
            safe_url = url.split('?')[0] if '?' in url else url
            print(f"正在下载源 {i+1}: {safe_url}...")
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()  # 如果请求失败则抛出异常
            
            filename = f"{CONFIG['download_dir']}/source_{i+1}_{datetime.now().strftime('%Y%m%d')}.m3u"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(response.text)
            downloaded_files.append(filename)
            print(f"✓ 成功下载源 {i+1}: {safe_url}")
            
        except requests.exceptions.RequestException as e:
            print(f"✗ 下载失败源 {i+1} {safe_url}: {e}")
        except Exception as e:
            print(f"✗ 处理源 {i+1} {safe_url} 时出错: {e}")
    
    return downloaded_files

def extract_all_channels_from_m3u(file_path, source_index):
    """从m3u文件中提取所有频道信息"""
    channels = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # m3u文件格式： #EXTINF 行包含频道信息，下一行是链接
        lines = content.split('\n')
        
        for i in range(len(lines) - 1):
            line = lines[i]
            if line.startswith('#EXTINF'):
                # 提取频道名称（最后一个逗号后面的部分）
                if ',' in line:
                    channel_name = line.split(',')[-1].strip()
                    
                    # 提取group-title
                    group_match = re.search(r'group-title="([^"]*)"', line)
                    group_title = group_match.group(1) if group_match else ""
                    
                    # 下一行就是链接
                    if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                        link = lines[i + 1].strip()
                        
                        # 存储频道信息
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
                # 提取频道名称（最后一个逗号后面的部分）
                if ',' in line:
                    channel_name = line.split(',')[-1].strip()
                    
                    # 提取group-title
                    group_match = re.search(r'group-title="([^"]*)"', line)
                    group_title = group_match.group(1) if group_match else ""
                    
                    # 下一行就是链接
                    if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                        link = lines[i + 1].strip()
                        
                        # 存储频道信息
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

def find_channel_by_rules(channel_name, group_title, all_channels):
    """根据规则查找匹配的频道"""
    # 规则1: 如果分组在规则中，从指定源查找相同分组和频道名称的频道
    if group_title in CONFIG["group_rules"]:
        target_source = CONFIG["group_rules"][group_title]
        for channel in all_channels:
            if (channel['group'] == group_title and 
                channel['name'] == channel_name and 
                channel['source'] == target_source):
                return channel
    
    # 规则2: 从所有源中查找相同频道名称的频道
    for channel in all_channels:
        if channel['name'] == channel_name:
            return channel
    
    return None

def update_target_file(all_channels, target_channels):
    """根据规则更新目标文件中的链接"""
    try:
        # 如果目标文件不存在，创建一个模板
        if not os.path.exists(CONFIG["target_file"]):
            print("目标文件不存在，正在创建...")
            with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
                for keyword in CONFIG["keywords"]:
                    f.write(f'#EXTINF:-1,{keyword}\n')
                    f.write('待更新\n')
            return
        
        # 读取目标文件
        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()
        
        updated_count = 0
        lines = content.split('\n')
        new_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            new_lines.append(line)
            
            # 检查当前行是否是EXTINF行
            if line.startswith('#EXTINF'):
                # 提取频道名称和分组
                channel_name = line.split(',')[-1].strip() if ',' in line else ""
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
                            source_info = f" (来自源{matched_channel['source']+1})"
                            print(f"更新 {channel_name} [{group_title}]: {old_link[:50]}... -> {new_link[:50]}...{source_info}")
                            new_lines.append(new_link)
                            updated_count += 1
                        else:
                            # 链接相同，保留原链接
                            new_lines.append(old_link)
                        
                        i += 1  # 跳过链接行
                    else:
                        # 没有找到链接行，添加新链接
                        new_link = matched_channel['link']
                        source_info = f" (来自源{matched_channel['source']+1})"
                        new_lines.append(new_link)
                        print(f"添加 {channel_name} [{group_title}]: {new_link[:50]}...{source_info}")
                        updated_count += 1
                else:
                    # 没有找到匹配的频道，保持原样
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        new_lines.append(lines[i + 1])
                        i += 1
            else:
                # 非EXTINF行，保持原样
                pass
            
            i += 1
        
        # 写回文件
        with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        print(f"✓ 目标文件更新完成，共更新 {updated_count} 个频道")
        
    except Exception as e:
        print(f"✗ 更新目标文件时出错: {e}")

def main():
    print("开始更新直播源...")
    print("关键词列表:", CONFIG["keywords"])
    print("分组规则:")
    for group, source_index in CONFIG["group_rules"].items():
        print(f"  {group} -> 从源{source_index+1}获取")
    
    # 1. 从目标文件中提取所有频道信息
    target_channels = extract_target_channels()
    
    # 2. 下载m3u文件
    downloaded_files = download_m3u_files()
    
    if not downloaded_files:
        print("✗ 没有成功下载任何文件，终止流程")
        return
    
    # 3. 从所有源文件中提取频道信息
    all_channels = []
    for source_index, file_path in enumerate(downloaded_files):
        channels = extract_all_channels_from_m3u(file_path, source_index)
        all_channels.extend(channels)
        print(f"从源{source_index+1}找到 {len(channels)} 个频道")
    
    # 4. 更新目标文件
    update_target_file(all_channels, target_channels)
    
    # 5. 打印统计信息
    print("\n更新统计:")
    # 统计目标文件中所有频道的更新情况
    updated_count = 0
    not_updated_count = 0
    
    for target_channel in target_channels:
        matched = False
        for channel in all_channels:
            if channel['name'] == target_channel['name']:
                matched = True
                break
        
        if matched:
            updated_count += 1
        else:
            not_updated_count += 1
            print(f"✗ 未找到更新: {target_channel['name']} [{target_channel['group']}]")
    
    print(f"✓ 成功更新: {updated_count} 个频道")
    print(f"✗ 未找到更新: {not_updated_count} 个频道")
    print("更新流程完成")

if __name__ == "__main__":
    main()
