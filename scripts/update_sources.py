import requests
import os
import re

def fetch_and_format():
    # 1. 获取排序和源
    order_str = os.environ.get("SOURCE_ORDER", "")
    group_order = [g.strip() for g in order_str.split(",") if g.strip()]
    all_sources = {k.replace("M3U_SOURCE_", ""): v for k, v in os.environ.items() if k.startswith("M3U_SOURCE_")}
    
    if not group_order:
        group_order = sorted(all_sources.keys())

    final_output = ["#EXTM3U"]

    # 2. 遍历处理
    for group_name in group_order:
        if group_name not in all_sources:
            continue
            
        url = all_sources[group_name].strip()
        if not url:
            continue
            
        print(f"正在处理分组：[{group_name}]")
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) IPTV/1.0'}
            response = requests.get(url, headers=headers, timeout=30, verify=False)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                content = response.text.strip()
                lines = content.splitlines()
                count = 0
                
                # 判断是否为 TXT 格式 (即不包含 #EXTM3U 且包含逗号)
                is_txt = "#EXTM3U" not in content and "," in content
                
                if is_txt:
                    # 处理 TXT 格式 (频道名,URL)
                    for line in lines:
                        if "," in line and not line.startswith("#"):
                            name, channel_url = line.split(",", 1)
                            # 生成 M3U 格式行，并注入分组名
                            final_output.append(f'#EXTINF:-1 group-title="{group_name}",{name.strip()}')
                            final_output.append(channel_url.strip())
                            count += 1
                else:
                    # 处理 标准 M3U 格式
                    for i in range(len(lines)):
                        line = lines[i].strip()
                        if line.startswith("#EXTINF:"):
                            # 统一修改分组名
                            if 'group-title="' in line:
                                line = re.sub(r'group-title="[^"]*"', f'group-title="{group_name}"', line)
                            else:
                                line = line.replace(",", f' group-title="{group_name}",', 1)
                            final_output.append(line)
                            
                            # 提取下一行 URL
                            for j in range(i + 1, len(lines)):
                                next_line = lines[j].strip()
                                if next_line and not next_line.startswith("#"):
                                    final_output.append(next_line)
                                    count += 1
                                    break
                print(f"✅ 分组 [{group_name}] 提取了 {count} 个频道")
            else:
                print(f"⚠️ 分组 [{group_name}] 访问失败：HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ 分cius组 [{group_name}] 出错: {e}")

    # 3. 写入 index.html
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write("\n".join(final_output))
    print("\n✨ 兼容性处理完毕，TXT 和 M3U 源均已转换完成！")

if __name__ == "__main__":
    fetch_and_format()
