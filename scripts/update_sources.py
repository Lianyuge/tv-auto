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
        
        # 分组规则映射
        "group_rules": {
            "央视吉林": 0,  # 从第一个源 (M3U_SOURCE_1) 获取
            "央视-辽宁地区": 1,  # 从第二个源 (M3U_SOURCE_2) 获取
            # 可以添加更多分组规则
            # "央视北京": 0,
            # "央视上海": 1,
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

def extract_links_by_group_from_m3u(file_path, source_index):
    """从m3u文件中提取所有频道链接，按group-title分类"""
    group_channels = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # m3u文件格式： #EXTINF 行包含频道信息，下一行是链接
        lines = content.split('\n')
        
        for i in range(len(lines) - 1):
            line = lines[i]
            if line.startswith('#EXTINF'):
                # 提取group-title
                group_match = re.search(r'group-title="([^"]*)"', line)
                if group_match:
                    group_title = group_match.group(1)
                    
                    # 提取频道名称（最后一个逗号后面的部分）
                    if ',' in line:
                        channel_name = line.split(',')[-1].strip()
                        
                        # 下一行就是链接
                        if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                            link = lines[i + 1].strip()
                            
                            # 按group-title组织频道
                            if group_title not in group_channels:
                                group_channels[group_title] = {}
                            
                            # 存储频道信息
                            group_channels[group_title][channel_name] = {
                                'link': link,
                                'extinf_line': line,
                                'source': source_index
                            }
    
    except Exception as e:
        print(f"解析文件 {file_path} 时出错: {e}")
    
    return group_channels

def update_target_file_by_group(all_group_channels):
    """根据分组规则更新目标文件中的链接"""
    try:
        # 如果目标文件不存在，报错
        if not os.path.exists(CONFIG["target_file"]):
            print(f"✗ 目标文件 {CONFIG['target_file']} 不存在")
            return
        
        # 读取目标文件
        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()
        
        updated_count = 0
        lines = content.split('\n')
        new_lines = []
        
        i = 0
        current_group = None
        
        while i < len(lines):
            line = lines[i]
            new_lines.append(line)
            
            # 检查当前行是否是EXTINF行，并提取group-title
            if line.startswith('#EXTINF'):
                group_match = re.search(r'group-title="([^"]*)"', line)
                if group_match:
                    current_group = group_match.group(1)
                    
                    # 检查这个group是否在我们的规则中
                    if current_group in CONFIG["group_rules"]:
                        # 提取频道名称
                        if ',' in line:
                            channel_name = line.split(',')[-1].strip()
                            
                            # 确定应该从哪个源获取
                            source_index = CONFIG["group_rules"][current_group]
                            
                            # 检查下一行是否是链接
                            if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                                old_link = lines[i + 1]
                                
                                # 从指定的源中查找相同group和channel的链接
                                if (current_group in all_group_channels and 
                                    channel_name in all_group_channels[current_group] and
                                    all_group_channels[current_group][channel_name]['source'] == source_index):
                                    
                                    new_link = all_group_channels[current_group][channel_name]['link']
                                    
                                    if old_link != new_link:
                                        print(f"更新 {current_group}/{channel_name}: {old_link[:50]}... -> {new_link[:50]}...")
                                        new_lines.append(new_link)
                                        updated_count += 1
                                    else:
                                        # 链接相同，保留原链接
                                        new_lines.append(old_link)
                                    
                                    i += 1  # 跳过链接行
                                else:
                                    # 没有找到新链接，保留原链接
                                    new_lines.append(lines[i + 1])
                                    i += 1
                            else:
                                # 没有链接行，尝试添加新链接
                                if (current_group in all_group_channels and 
                                    channel_name in all_group_channels[current_group] and
                                    all_group_channels[current_group][channel_name]['source'] == source_index):
                                    
                                    new_link = all_group_channels[current_group][channel_name]['link']
                                    new_lines.append(new_link)
                                    print(f"添加 {current_group}/{channel_name}: {new_link[:50]}...")
                                    updated_count += 1
                else:
                    current_group = None
            else:
                current_group = None
            
            i += 1
        
        # 写回文件
        with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        print(f"✓ 目标文件更新完成，共更新 {updated_count} 个频道")
        
    except Exception as e:
        print(f"✗ 更新目标文件时出错: {e}")

def main():
    print("开始更新直播源...")
    print("分组规则:")
    for group, source_index in CONFIG["group_rules"].items():
        print(f"  {group} -> 从源{source_index+1}获取")
    
    # 1. 下载m3u文件
    downloaded_files = download_m3u_files()
    
    if not downloaded_files:
        print("✗ 没有成功下载任何文件，终止流程")
        return
    
    # 2. 从所有文件中提取链接，按group-title组织
    all_group_channels = {}
    for source_index, file_path in enumerate(downloaded_files):
        group_channels = extract_links_by_group_from_m3u(file_path, source_index)
        
        # 合并到总字典中
        for group, channels in group_channels.items():
            if group not in all_group_channels:
                all_group_channels[group] = {}
            all_group_channels[group].update(channels)
    
    # 3. 打印找到的频道统计
    print("\n找到的频道统计:")
    for group in CONFIG["group_rules"]:
        if group in all_group_channels:
            count = len(all_group_channels[group])
            print(f"  {group}: {count} 个频道")
        else:
            print(f"  {group}: 0 个频道")
    
    # 4. 更新目标文件
    update_target_file_by_group(all_group_channels)
    
    print("更新流程完成")

if __name__ == "__main__":
    main()
