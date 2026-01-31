import requests
import os
import re

def fetch_and_format():
    # 1. 自动获取 Workflow 中 env 部分定义的所有变量
    sources = {k: v for k, v in os.environ.items() if k.startswith("M3U_SOURCE_")}
    
    if not sources:
        print("❌ 错误：未在环境中找到任何 M3U_SOURCE 变量，请检查 workflow 文件。")
        return

    # 2. 初始化 M3U 内容，第一行必须是这个
    final_output = ["#EXTM3U"]

    # 3. 按照变量名排序处理，确保分组顺序相对固定
    for key in sorted(sources.keys()):
        url = sources[key].strip()
        if not url:
            continue
            
        # 从变量名中提取分组名称，例如 M3U_SOURCE_央视 -> 央视
        group_name = key.replace("M3U_SOURCE_", "")
        
        print(f"正在处理分组：[{group_name}]，链接：{url[:20]}...")
        
        try:
            # 设置请求头，模拟浏览器防止被某些源屏蔽
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=20)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                lines = response.text.splitlines()
                for i in range(len(lines)):
                    line = lines[i].strip()
                    
                    # 如果这一行是信息行
                    if line.startswith("#EXTINF:"):
                        # 处理 group-title
                        if 'group-title="' in line:
                            # 如果原本有分组，替换为我们定义的分组名
                            line = re.sub(r'group-title="[^"]*"', f'group-title="{group_name}"', line)
                        else:
                            # 如果原本没分组，在逗号前插入分组名
                            line = line.replace(",", f' group-title="{group_name}",', 1)
                        
                        final_output.append(line)
                        
                        # 寻找下一行非空的 URL 行
                        for j in range(i + 1, len(lines)):
                            next_line = lines[j].strip()
                            if next_line and not next_line.startswith("#"):
                                final_output.append(next_line)
                                break
            else:
                print(f"⚠️ 无法抓取 {group_name}：状态码 {response.status_code}")
        except Exception as e:
            print(f"❌ 处理 {group_name} 时发生错误：{e}")

    # 4. 将最终结果保存为 index.html
    # 这个文件会保存到仓库根目录下
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write("\n".join(final_output))
    print("✅ 执行完毕，index.html 已生成。")

if __name__ == "__main__":
    fetch_and_format()
