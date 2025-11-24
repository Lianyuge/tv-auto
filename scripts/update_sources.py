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
            print(f"正在下载: {safe_url}...")
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()  # 如果请求失败则抛出异常
            
            filename = f"{CONFIG['download_dir']}/source_{i+1}_{datetime.now().strftime('%Y%m%d')}.m3u"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(response.text)
            downloaded_files.append(filename)
            print(f"✓ 成功下载: {safe_url}")
            
        except requests.exceptions.RequestException as e:
            print(f"✗ 下载失败 {safe_url}: {e}")
        except Exception as e:
            print(f"✗ 处理 {safe_url} 时出错: {e}")
    
    return downloaded_files

def extract_links_from_m3u(file_path):
    """从m3u文件中提取关键词对应的链接"""
    keyword_links = {}
    
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
                    
                    # 检查是否包含目标关键词
                    for keyword in CONFIG["keywords"]:
                        if keyword in channel_name:
                            # 下一行就是链接
                            if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                                link = lines[i + 1].strip()
                                # 只存储第一个找到的链接（避免重复）
                                if keyword not in keyword_links:
                                    keyword_links[keyword] = {
                                        'link': link,
                                        'extinf_line': line  # 保存完整的EXTINF行
                                    }
                                    print(f"找到频道: {keyword}")
                                break
    except Exception as e:
        print(f"解析文件 {file_path} 时出错: {e}")
    
    return keyword_links

def update_target_file(keyword_links):
    """更新目标文件中的链接，保持EXTINF行不变"""
    try:
        # 如果目标文件不存在，创建一个模板
        if not os.path.exists(CONFIG["target_file"]):
            print("目标文件不存在，正在创建...")
            with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
                for keyword in CONFIG["keywords"]:
                    f.write(f'#EXTINF:-1,{keyword}\n')
                    f.write('待更新\n')
        
        # 读取目标文件
        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()
        
        updated_count = 0
        lines = content.split('\n')
        new_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 检查当前行是否是EXTINF行
            if line.startswith('#EXTINF'):
                # 提取频道名称
                channel_name = line.split(',')[-1].strip() if ',' in line else ""
                
                # 检查这个频道名称是否匹配我们的关键词
                matched_keyword = None
                for keyword in CONFIG["keywords"]:
                    if keyword in channel_name:
                        matched_keyword = keyword
                        break
                
                if matched_keyword and matched_keyword in keyword_links:
                    # 添加EXTINF行（保持不变）
                    new_lines.append(line)
                    
                    # 检查下一行是否是链接
                    if i + 1 < len(lines) and not lines[i + 1].startswith('#'):
                        old_link = lines[i + 1]
                        new_link = keyword_links[matched_keyword]['link']
                        
                        if old_link != new_link:
                            print(f"更新 {matched_keyword}: {old_link[:50]}... -> {new_link[:50]}...")
                            new_lines.append(new_link)
                            updated_count += 1
                        else:
                            # 链接相同，保留原链接
                            new_lines.append(old_link)
                        
                        i += 1  # 跳过链接行
                    else:
                        # 没有找到链接行，添加新链接
                        new_link = keyword_links[matched_keyword]['link']
                        new_lines.append(new_link)
                        print(f"添加 {matched_keyword}: {new_link[:50]}...")
                        updated_count += 1
                else:
                    # 不匹配的频道，保持原样
                    new_lines.append(line)
            else:
                # 非EXTINF行，保持原样
                new_lines.append(line)
            
            i += 1
        
        # 写回文件
        with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        print(f"✓ 目标文件更新完成，共更新 {updated_count} 个频道")
        
    except Exception as e:
        print(f"✗ 更新目标文件时出错: {e}")

def main():
    print("开始更新直播源...")
    print(f"目标频道: {', '.join(CONFIG['keywords'])}")
    
    # 1. 下载m3u文件
    downloaded_files = download_m3u_files()
    
    if not downloaded_files:
        print("✗ 没有成功下载任何文件，终止流程")
        return
    
    # 2. 从所有文件中提取链接
    all_keyword_links = {}
    for file_path in downloaded_files:
        links = extract_links_from_m3u(file_path)
        all_keyword_links.update(links)
    
    print(f"共找到 {len(all_keyword_links)} 个频道的链接")
    
    # 3. 更新目标文件
    if all_keyword_links:
        update_target_file(all_keyword_links)
    else:
        print("✗ 未找到任何匹配的频道链接")
    
    # 4. 打印更新摘要
    print("\n更新摘要:")
    for keyword in CONFIG["keywords"]:
        if keyword in all_keyword_links:
            link = all_keyword_links[keyword]['link']
            print(f"✓ {keyword}: {link[:60]}...")
        else:
            print(f"✗ {keyword}: 未找到")
    
    print("更新流程完成")

if __name__ == "__main__":
    main()
