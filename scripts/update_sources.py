import requests
import os
import re

def fetch_and_format():
    # 1. 获取排序规则
    order_str = os.environ.get("SOURCE_ORDER", "")
    group_order = [g.strip() for g in order_str.split(",") if g.strip()]
    
    # 2. 获取所有源
    all_sources = {k.replace("M3U_SOURCE_", ""): v for k, v in os.environ.items() if k.startswith("M3U_SOURCE_")}
    
    # 如果没有指定顺序，则按字母排序
    if not group_order:
        group_order = sorted(all_sources.keys())

    final_output = ["#EXTM3U"]

    # 3. 严格按照指定的 group_order 顺序处理
    for group_name in group_order:
        if group_name not in all_sources:
            continue
            
        url = all_sources[group_name].strip()
        if not url:
            continue
            
        print(f"正在处理分组：[{group_name}]")
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) IPTV/1.0'}
            # verify=False 忽略SSL证书错误，timeout增加到30秒
            response = requests.get(url, headers=headers, timeout=30, verify=False)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                lines = response.text.splitlines()
                count = 0
                for i in range(len(lines)):
                    line = lines[i].strip()
                    if line.startswith("#EXTINF:"):
                        # 强制修改或添加 group-title
                        if 'group-title="' in line:
                            line = re.sub(r'group-title="[^"]*"', f'group-title="{group_name}"', line)
                        else:
                            line = line.replace(",", f' group-title="{group_name}",', 1)
                        
                        final_output.append(line)
                        
                        # 寻找下一行 URL
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
            print(f"❌ 分组 [{group_name}] 出错: {e}")

    # 4. 保存
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write("\n".join(final_output))
    print("\n✨ 排序任务执行完毕！")

if __name__ == "__main__":
    fetch_and_format()
