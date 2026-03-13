# 常见问题

---

## 安装问题

**Q：运行 `pip install -r requirements.txt` 报错**

A：先检查 Python 版本：
```bash
python --version
```
需要 3.10 或以上。如果版本正确但还是报错，把报错截图发给管理员。

---

**Q：`python labeler.py start` 提示"找不到数据包"**

A：检查数据包是否放对地方：
- 解压后的文件夹名应该是 `annotation_package_XXXXXXXX`
- 这个文件夹要放在 `packages/` 目录里
- 正确路径：`toptalk-labeler/packages/annotation_package_XXXXXXXX/`

---

## Label Studio 问题

**Q：浏览器打开后一直转圈，或者打不开 http://localhost:8080**

A：
1. 等一会，第一次启动需要 1-2 分钟
2. 如果超过 3 分钟：关掉命令行，重新运行 `python labeler.py start`
3. 还不行：检查 8080 端口是否被占用，联系管理员

---

**Q：音频播放失败，显示错误或没有声音**

A：
1. 检查浏览器是否允许播放音频（地址栏左边的锁图标）
2. 尝试换浏览器（推荐 Chrome）
3. 如果一直报错，联系管理员（这是配置问题，你不需要解决）

---

**Q：标注到一半，浏览器崩了，数据丢了吗？**

A：不会丢。Label Studio 每次点 Submit 都会保存，崩溃之前提交的都在。
重新打开浏览器，进入 http://localhost:8080 继续就行。

---

**Q：任务列表里有很多"Skipped"状态，正常吗？**

A：正常。你可以跳过难以判断的任务，之后再回来标。

---

## 导出问题

**Q：`python labeler.py export` 报错**

A：
1. 确保 Label Studio 还在运行（命令行里没有关掉）
2. 如果关掉了，重新运行 `python labeler.py start`，再运行 `python labeler.py export`

---

**Q：生成的 zip 文件太小，是不是没导出完？**

A：zip 里只有标注结果的文字数据，不含音频，所以文件会比较小，这是正常的。

---

**Q：导出后发现有些任务忘记标了怎么办？**

A：联系管理员说明情况。管理员可以让你补标，重新导出。

---

## 其他

**Q：有任务的对话我听不懂（方言/术语），怎么办？**

A：按你能理解的部分标，在备注栏写"方言/听不懂"，情感选 8-未知。

**Q：电脑关机了，下次怎么继续？**

A：重新运行 `python labeler.py start`，之前的进度会自动保留。
