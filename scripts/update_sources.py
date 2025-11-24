import requests
import re
from datetime import datetime
import os

# 配置部分 - 您需要修改这些内容
CONFIG = {
    # 要下载的m3u文件列表
    "m3u_sources": [
        "https://gyssi.link/iptv/chinaiptv",
        "https://gyssi.link/iptv/chinaiptv/",
        "https://gyssi.link/live/%E8%BE%BD%E5%AE%81.m3u?t"
    ],
    
    # 要提取的关键词列表
    "keywords": [
        "CCTV1-综合",
        "CCTV2-财经",
        "湖南卫视",
        "浙江卫视",
        "北京卫视"
    ],
    
    # 目标文件路径
    "target_file": "live_sources.txt",
    
    # 临时下载目录
    "download_dir": "downloaded_sources"
}

def download_m3u_files():
    """下载所有m3u文件"""
    if not os.path.exists(CONFIG["download_dir"]):
        os.makedirs(CONFIG["download_dir"])
    
    downloaded_files = []
    for i, url in enumerate(CONFIG["m3u_sources"]):
        try:
            response = requests.get(url, timeout=30)
            filename = f"{CONFIG['download_dir']}/source_{i+1}_{datetime.now().strftime('%Y%m%d')}.m3u"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(response.text)
            downloaded_files.append(filename)
            print(f"成功下载: {url}")
        except Exception as e:
            print(f"下载失败 {url}: {e}")
    
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
                # 检查是否包含目标关键词
                for keyword in CONFIG["keywords"]:
                    if keyword in line:
                        # 下一行就是链接
                        if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                            link = lines[i + 1].strip()
                            keyword_links[keyword] = link
                            print(f"找到频道: {keyword} -> {link}")
                            break
    except Exception as e:
        print(f"解析文件 {file_path} 时出错: {e}")
    
    return keyword_links

def update_target_file(keyword_links):
    """更新目标文件中的链接"""
    try:
        # 读取目标文件
        with open(CONFIG["target_file"], 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 为每个关键词更新链接
        for keyword, new_link in keyword_links.items():
            # 构建正则表达式匹配模式：关键词后跟链接
            pattern = rf'({re.escape(keyword)}.*?\n)(.*?)(\n|$)'
            replacement = rf'\1{new_link}\3'
            content = re.sub(pattern, replacement, content)
            print(f"更新频道 {keyword} 的链接")
        
        # 写回文件
        with open(CONFIG["target_file"], 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("目标文件更新完成")
        
    except Exception as e:
        print(f"更新目标文件时出错: {e}")

def main():
    print("开始更新直播源...")
    
    # 1. 下载m3u文件
    downloaded_files = download_m3u_files()
    
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
        print("未找到任何匹配的频道链接")
    
    print("更新完成")

if __name__ == "__main__":
    main()
