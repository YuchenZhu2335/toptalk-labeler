#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TopTalk 标注工具（标注员端）
============================
用法：
  python labeler.py start             # 启动标注（自动检测数据包）
  python labeler.py start --package annotation_package_20260314
  python labeler.py export            # 导出标注结果
  python labeler.py status            # 查看标注进度
  python labeler.py guide             # 打印操作指南
"""

import argparse
import json
import os
import random
import sys
import zipfile
from datetime import datetime
from pathlib import Path


# ── 常量 ──────────────────────────────────────────────────
PACKAGES_DIR  = Path(__file__).parent / "packages"
TOKEN_FILE    = Path(__file__).parent / ".ls_token"
LS_BASE       = "http://localhost:8080"
LS_PORT       = 8080


# ══════════════════════════════════════════════════════════
# 命令：start
# ══════════════════════════════════════════════════════════

def cmd_start(package_name=None):
    """一键启动标注环境。"""

    # ── 1. 查找数据包 ──────────────────────────────────────
    pkg_dir = _find_package(package_name)
    if pkg_dir is None:
        return

    manifest = _load_json(pkg_dir / "manifest.json")
    print(f"数据包: {pkg_dir.name}")
    print(f"  标注任务: {manifest.get('total_tasks', '?')} 条")
    print(f"  录音数:   {manifest.get('total_calls', '?')} 通")
    print(f"  Gold Set: {manifest.get('gold_set_tasks', '?')} 条（已混入普通任务）")

    # ── 2. 验证数据包完整性 ────────────────────────────────
    required = [
        "tasks/ls_import.json",
        "config/label_config.xml",
        "audio",
    ]
    for item in required:
        if not (pkg_dir / item).exists():
            print(f"\n❌ 数据包不完整，缺少: {item}")
            print("   请联系管理员重新发送数据包。")
            return
    print("\n数据包完整 ✅")

    # ── 3. 检查 Label Studio ──────────────────────────────
    _ensure_label_studio()

    # ── 4. 合并普通任务 + Gold Set 考题 ───────────────────
    merged_file = _merge_tasks(pkg_dir)

    # ── 5. 解决 Windows 中文路径问题 ─────────────────────
    audio_dir = str((pkg_dir / "audio").resolve())
    if _has_non_ascii(audio_dir):
        print(f"\n⚠️  音频路径含非 ASCII 字符，Label Studio 可能无法播放音频。")
        print(f"   建议：把 toptalk-labeler 放到纯英文路径，例如 C:/labeler/")
        print(f"   当前路径: {audio_dir}\n")

    os.environ["LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED"] = "true"
    os.environ["LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT"]   = audio_dir

    # ── 6. 清理残留 LS 进程（防止端口冲突）───────────────
    _kill_existing_ls()

    # ── 7. 先启动 LS，等待就绪后调用 API 配置 ─────────────
    import subprocess, time, threading

    label_config_xml = (pkg_dir / "config" / "label_config.xml").read_text(encoding="utf-8")

    ls_proc = subprocess.Popen(
        [sys.executable, "-m", "label_studio", "start", f"--port={LS_PORT}"],
        env={**os.environ},
    )

    print(f"\n  Label Studio 启动中，请稍候（约 15 秒）...")
    time.sleep(15)

    # 后台线程执行 API 配置，不阻塞
    def _setup():
        _try_api_setup(merged_file, label_config_xml, audio_dir, manifest)

    threading.Thread(target=_setup, daemon=True).start()

    # ── 8. 等待用户结束 ───────────────────────────────────
    print(f"\n{'='*50}")
    print(f"✅ 标注平台已启动")
    print(f"")
    print(f"🌐 浏览器: http://localhost:{LS_PORT}")
    print(f"")
    print(f"按 Ctrl+C 停止")
    print(f"{'='*50}\n")

    try:
        ls_proc.wait()
    except KeyboardInterrupt:
        ls_proc.terminate()
        print("\n已停止。")


def _find_package(package_name=None):
    """查找数据包目录。"""
    if package_name:
        pkg_dir = PACKAGES_DIR / package_name
        if not pkg_dir.exists():
            print(f"❌ 指定数据包不存在: {pkg_dir}")
            return None
        return pkg_dir

    pkgs = sorted(
        [d for d in PACKAGES_DIR.iterdir()
         if d.is_dir() and d.name.startswith("annotation_package")],
        reverse=True,
    )
    if not pkgs:
        print("❌ 没有找到数据包。")
        print("   请把管理员发给你的数据包文件夹放到 packages/ 目录下，")
        print("   或者把 .zip 文件解压到 packages/ 目录下。")
        return None

    if len(pkgs) > 1:
        print(f"找到 {len(pkgs)} 个数据包，使用最新的:")
        for p in pkgs:
            print(f"  {'→' if p == pkgs[0] else ' '} {p.name}")
        print()
    return pkgs[0]


def _ensure_label_studio():
    """检查 label-studio 是否已安装，否则提示。"""
    try:
        import label_studio
        print(f"Label Studio {label_studio.__version__} ✅")
    except ImportError:
        print("Label Studio 未安装，正在安装（首次需要几分钟）...")
        os.system(f"{sys.executable} -m pip install label-studio")
        try:
            import label_studio
            print(f"Label Studio {label_studio.__version__} 安装完成 ✅")
        except ImportError:
            print("❌ 安装失败，请手动运行: pip install label-studio")
            sys.exit(1)


def _merge_tasks(pkg_dir):
    """合并普通任务和 Gold Set，随机打乱，保存为 _merged_import.json。"""
    import_file = pkg_dir / "tasks" / "ls_import.json"
    gold_file   = pkg_dir / "gold_set" / "gold_tasks.json"
    merged_file = pkg_dir / "tasks" / "_merged_import.json"

    tasks = _load_json(import_file)

    if gold_file.exists():
        gold_tasks = _load_json(gold_file)
        # 去掉 gold_tasks 里的管理员用字段（标注员不需要看到）
        for t in gold_tasks:
            t.pop("_gold_answer", None)
        all_tasks = tasks + gold_tasks
    else:
        all_tasks = tasks

    # 用日期为 seed，保证同天多次运行顺序一致
    date_seed = int(datetime.now().strftime("%Y%m%d"))
    random.seed(date_seed)
    random.shuffle(all_tasks)

    _save_json(merged_file, all_tasks)
    return merged_file


def _try_api_setup(merged_file, label_config_xml, audio_dir, manifest):
    """尝试通过 Label Studio API 全自动创建项目 + 导入任务。
    失败时打印手动操作步骤。"""
    try:
        import requests
    except ImportError:
        _print_manual_steps(merged_file, label_config_xml)
        return

    token = _get_token()
    if not token:
        _print_manual_steps(merged_file, label_config_xml)
        return

    headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

    try:
        # 检查是否已有项目
        resp = requests.get(f"{LS_BASE}/api/projects/", headers=headers, timeout=5)
        if resp.status_code != 200:
            raise Exception(f"API 返回 {resp.status_code}")

        projects = resp.json().get("results", [])
        project_id = None

        for p in projects:
            if p.get("title") == manifest.get("package_name", "toptalk-annotation"):
                project_id = p["id"]
                print(f"已有项目 #{project_id}，跳过创建。")
                break

        if project_id is None:
            # 创建项目
            settings = {}
            settings_file = Path(merged_file).parent.parent / "config" / "project_settings.json"
            if settings_file.exists():
                settings = _load_json(settings_file)

            create_resp = requests.post(
                f"{LS_BASE}/api/projects/",
                headers=headers,
                json={
                    "title":        manifest.get("package_name", "toptalk-annotation"),
                    "description":  settings.get("description", "电销录音标注"),
                    "label_config": label_config_xml,
                },
                timeout=10,
            )
            if create_resp.status_code not in (200, 201):
                raise Exception(f"创建项目失败: {create_resp.text[:100]}")
            project_id = create_resp.json()["id"]
            print(f"项目已创建 #{project_id} ✅")

            # 创建本地文件存储（必须，否则音频 404）
            storage_resp = requests.post(
                f"{LS_BASE}/api/storages/localfiles/",
                headers=headers,
                json={
                    "project":       project_id,
                    "title":         "audio",
                    "path":          audio_dir,
                    "use_blob_urls": False,
                },
                timeout=10,
            )
            if storage_resp.status_code in (200, 201):
                storage_id = storage_resp.json()["id"]
                # 同步存储
                requests.post(
                    f"{LS_BASE}/api/storages/localfiles/{storage_id}/sync/",
                    headers=headers,
                    timeout=10,
                )
                print(f"音频存储已配置 ✅")
            else:
                print(f"[WARN] 音频存储配置失败（{storage_resp.status_code}），音频可能无法播放")

            # 导入任务
            tasks = _load_json(merged_file)
            # 分批导入（每批 200 条）
            batch_size = 200
            total_imported = 0
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                imp_resp = requests.post(
                    f"{LS_BASE}/api/projects/{project_id}/import",
                    headers=headers,
                    json=batch,
                    timeout=60,
                )
                if imp_resp.status_code in (200, 201):
                    total_imported += len(batch)
                else:
                    print(f"[WARN] 第 {i//batch_size+1} 批导入失败: {imp_resp.status_code}")

            print(f"任务已导入: {total_imported}/{len(tasks)} 条 ✅")

        print(f"\n✅ 全自动配置完成！浏览器打开 http://localhost:{LS_PORT} 即可开始标注。")

    except Exception as e:
        print(f"\n[提示] 自动配置未完成（{e}）")
        print("Label Studio 启动后，请按以下步骤手动操作：")
        _print_manual_steps(merged_file, label_config_xml)


def _get_token():
    """读取 Label Studio API Token。优先从文件，其次让用户输入。"""
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return token

    # 尝试从 Label Studio 数据库读取
    token = _read_token_from_db()
    if token:
        TOKEN_FILE.write_text(token)
        return token

    return None


def _read_token_from_db():
    """尝试从 Label Studio SQLite 数据库读取 token。"""
    import sqlite3

    db_candidates = [
        Path.home() / "AppData" / "Local" / "label-studio" / "label-studio" / "label_studio.sqlite3",
        Path.home() / ".local" / "share" / "label-studio" / "label_studio.sqlite3",
    ]
    for db_path in db_candidates:
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            # LS 1.x 用 authtoken_token，旧版可能是 auth_token_token
            try:
                cursor.execute("SELECT key FROM authtoken_token LIMIT 1")
            except Exception:
                cursor.execute("SELECT key FROM auth_token_token LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            if row:
                return row[0]
        except Exception:
            continue
    return None


def _print_manual_steps(merged_file, label_config_xml):
    """打印手动操作步骤。"""
    xml_path = Path(merged_file).parent.parent / "config" / "label_config.xml"
    print()
    print("  首次使用，请在浏览器中完成以下步骤：")
    print()
    print("  1. 注册账号（随便填邮箱和密码，不需要联网验证）")
    print("  2. 点击 Create Project，名称随便填")
    print("  3. 点击顶部 Labeling Setup → Code 标签页")
    print("  4. 删除默认内容，粘贴以下文件的全部内容：")
    print(f"       {xml_path}")
    print("  5. 点击 Save")
    print("  6. 点击 Import → 上传以下文件：")
    print(f"       {merged_file}")
    print("  7. 开始标注！")
    print()


# ══════════════════════════════════════════════════════════
# 命令：export
# ══════════════════════════════════════════════════════════

def cmd_export():
    """导出标注结果，打包发回给管理员。"""
    print("导出标注结果...")

    annotations = _fetch_annotations_from_api()

    if annotations is None:
        # 尝试读取手动导出的文件
        manual = Path("annotations.json")
        if manual.exists():
            print(f"使用手动导出文件: {manual}")
            annotations = _load_json(manual)
        else:
            print()
            print("无法自动导出。请手动操作：")
            print("  1. 在 Label Studio 中打开项目")
            print("  2. 点右上角 Export")
            print("  3. 格式选 JSON（不是 JSON-MIN）")
            print("  4. 下载后重命名为 annotations.json")
            print("  5. 放到当前目录（和 labeler.py 同一级）")
            print("  6. 重新运行 python labeler.py export")
            return

    # 解析标注结果
    results = []
    for task in annotations:
        task_annots = task.get("annotations", [])
        if not task_annots:
            continue
        annotation = task_annots[-1]  # 取最新的标注
        data = task.get("data", {})

        result_item = {
            "segment_id":          data.get("segment_id"),
            "call_id":             data.get("call_id"),
            "turn_id":             data.get("turn_id"),
            "speaker":             data.get("speaker"),
            "annotator":           _get_annotator(annotation),
            "annotated_at":        annotation.get("created_at", ""),
            "annotation_time_sec": annotation.get("lead_time"),
            "labels":              _parse_labels(annotation.get("result", [])),
            "_is_gold":            data.get("_is_gold", False),
        }
        results.append(result_item)

    total      = len(results)
    gold_count = sum(1 for r in results if r["_is_gold"])

    output = {
        "export_version":       "1.0",
        "exported_at":          datetime.now().isoformat(),
        "total_annotations":    total,
        "gold_set_annotations": gold_count,
        "results":              results,
    }

    date_str    = datetime.now().strftime("%Y%m%d")
    json_name   = f"result_{date_str}.json"
    zip_name    = f"result_{date_str}.zip"

    _save_json(json_name, output)

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(json_name)

    print()
    print(f"{'='*50}")
    print(f"✅ 标注结果已导出")
    print()
    print(f"  标注条数: {total}（含 {gold_count} 条考题）")
    print(f"  文件: {zip_name}")
    print()
    print(f"  请把 {zip_name} 发回给管理员")
    print(f"{'='*50}")

    # 清理临时 json
    Path(json_name).unlink(missing_ok=True)


def _fetch_annotations_from_api():
    """尝试从 Label Studio API 导出标注。返回 None 表示失败。"""
    try:
        import requests
    except ImportError:
        return None

    token = _get_token()
    if not token:
        return None

    headers = {"Authorization": f"Token {token}"}
    try:
        # 获取项目列表
        resp = requests.get(f"{LS_BASE}/api/projects/", headers=headers, timeout=5)
        if resp.status_code != 200:
            return None
        projects = resp.json().get("results", [])
        if not projects:
            return None
        project_id = projects[0]["id"]

        # 导出
        exp_resp = requests.get(
            f"{LS_BASE}/api/projects/{project_id}/export?exportType=JSON",
            headers=headers,
            timeout=60,
        )
        if exp_resp.status_code == 200:
            print(f"从 Label Studio API 导出成功 ✅")
            return exp_resp.json()
    except Exception as e:
        print(f"[提示] API 导出失败: {e}")
    return None


def _get_annotator(annotation):
    """提取标注员标识。"""
    cb = annotation.get("completed_by", {})
    if isinstance(cb, dict):
        return cb.get("email") or cb.get("username") or "unknown"
    return str(cb)


def _parse_labels(result_list):
    """解析 Label Studio annotation result 为简洁 dict。"""
    labels = {}
    for r in result_list:
        from_name = r.get("from_name", "")
        rtype     = r.get("type", "")
        value     = r.get("value", {})
        if rtype == "choices":
            choices = value.get("choices", [])
            labels[from_name] = choices[0] if len(choices) == 1 else choices
        elif rtype == "textarea":
            texts = value.get("text", [])
            labels[from_name] = texts[0] if len(texts) == 1 else texts
    return labels


# ══════════════════════════════════════════════════════════
# 命令：status
# ══════════════════════════════════════════════════════════

def cmd_status():
    """查看标注进度。"""
    try:
        import requests
    except ImportError:
        _print_status_manual()
        return

    token = _get_token()
    if not token:
        _print_status_manual()
        return

    headers = {"Authorization": f"Token {token}"}
    try:
        resp = requests.get(f"{LS_BASE}/api/projects/", headers=headers, timeout=5)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")

        projects = resp.json().get("results", [])
        if not projects:
            print("Label Studio 中没有项目。请先运行 python labeler.py start")
            return

        print(f"\n{'='*50}")
        print(f"标注进度")
        print(f"{'='*50}")
        for p in projects:
            total      = p.get("task_number", 0)
            done       = p.get("num_tasks_with_annotations", 0)
            pct        = round(done / total * 100, 1) if total else 0
            bar_filled = int(pct / 5)
            bar        = "█" * bar_filled + "░" * (20 - bar_filled)
            print(f"\n  项目: {p['title']}")
            print(f"  [{bar}] {done}/{total} ({pct}%)")
        print(f"{'='*50}")

    except Exception as e:
        print(f"[提示] 无法连接 Label Studio ({e})")
        _print_status_manual()


def _print_status_manual():
    print("\n在 Label Studio 界面可以查看进度：")
    print("  http://localhost:8080")
    print("  右下角显示: Tasks X / Y   Submitted annotations: Z")
    print("  完成率 = Z / X")


# ══════════════════════════════════════════════════════════
# 命令：guide
# ══════════════════════════════════════════════════════════

def cmd_guide():
    """打印快速操作指南。"""
    guide = """
════════════════════════════════════════
  TopTalk 标注操作指南（快速版）
════════════════════════════════════════

【启动】
  python labeler.py start
  → 浏览器打开 http://localhost:8080

【标注流程】
  1. 点击任务 → 点击 ► 播放音频
  2. 看上文（蓝色框），了解对话背景
  3. 填写/修正 ASR 转写（如有明显错误）
  4. 选择情感（听声音判断，不只看文字）
  5. 选择销售策略（客户的话选 N/A）
  6. 选择客户意图（销售的话选 N/A）
  7. 勾选副语言事件（多选，听到什么勾什么）
  8. 点击 Submit

【标签速查】
  情感: 0-生气 1-厌恶 2-恐惧 3-高兴 4-中立 5-其他 6-伤心 7-惊讶 8-未知
  副语言: 笑声 叹气 犹豫/吞吐 填充词 语气词 清嗓 拖音 惊声 无

【导出】
  python labeler.py export
  → 生成 result_XXXXXXXX.zip → 发回管理员

【查看进度】
  python labeler.py status
  或看 Label Studio 界面右下角数字

【详细手册】
  docs/HANDBOOK.md

════════════════════════════════════════
"""
    print(guide)


# ══════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════

def _has_non_ascii(path: str) -> bool:
    """检查路径是否含非 ASCII 字符（中文/韩文等）。"""
    try:
        path.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _kill_existing_ls():
    """杀掉已有的 label-studio 进程，防止端口冲突。"""
    import subprocess
    if sys.platform == "win32":
        subprocess.run(
            ["wmic", "process", "where", "name='label-studio.exe'", "delete"],
            capture_output=True,
        )
        subprocess.run(
            ["taskkill", "/F", "/IM", "label-studio.exe"],
            capture_output=True,
        )
    else:
        subprocess.run(["pkill", "-f", "label-studio"], capture_output=True)


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="labeler",
        description="TopTalk 标注工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # start
    start_p = sub.add_parser("start", help="启动标注环境")
    start_p.add_argument(
        "--package", "-p", default=None,
        help="指定数据包名称（默认自动选最新）",
    )

    # export
    sub.add_parser("export", help="导出标注结果")

    # status
    sub.add_parser("status", help="查看标注进度")

    # guide
    sub.add_parser("guide", help="打印操作指南")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "start":
        cmd_start(package_name=args.package)
    elif args.command == "export":
        cmd_export()
    elif args.command == "status":
        cmd_status()
    elif args.command == "guide":
        cmd_guide()


if __name__ == "__main__":
    main()
