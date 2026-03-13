# TopTalk 标注工具

电销录音标注工具，标注员端。管理员发给你一个 zip 文件，你解压后用本工具标注，标完再打包发回去。

## 安装（只需一次）

**前提：** 已安装 Python 3.10 或以上版本。不需要 GPU，不需要任何机器学习库。

```bash
# 1. 下载工具（管理员告诉你地址）
git clone https://github.com/YuchenZhu2335/toptalk-labeler.git
cd toptalk-labeler

# 2. 安装依赖（只有一个，需要几分钟）
pip install -r requirements.txt
```

## 使用（每次标注的流程）

```bash
# 第一步：把管理员发的 annotation_package_XXXXXXXX.zip 解压到 packages/ 目录下
#         解压后应该看到 packages/annotation_package_XXXXXXXX/ 文件夹

# 第二步：启动标注环境
python labeler.py start

# 第三步：浏览器会打开 http://localhost:8080，按照提示操作即可

# 第四步：标完之后导出
python labeler.py export

# 第五步：把生成的 result_XXXXXXXX.zip 发回给管理员
```

## 其他命令

```bash
python labeler.py status   # 查看标注进度（已标多少条）
python labeler.py guide    # 打印标注操作指南
```

## 遇到问题？

先看 [docs/FAQ.md](docs/FAQ.md)，解决不了联系管理员。

## 标注指南

- [标注员手册](docs/HANDBOOK.md) — 详细说明每个标签的含义和标注技巧
- [标签速查卡](docs/CHEATSHEET.md) — 可以打印出来放桌上
- [常见问题](docs/FAQ.md)
