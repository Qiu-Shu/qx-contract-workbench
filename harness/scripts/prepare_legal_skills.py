"""Install the supplied legal archives as local, lazily loaded Harness skills.

Only reads archive bytes. It never imports or executes archive-provided code and
never changes a user-global skill directory. Python standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import ZipFile


HARNESS_REF = "ce7073d51254c26cd63b22a60835b8f948deb447"
DEFAULT_TEMP = Path(__file__).resolve().parents[1] / "sources"
DOMAINS = {
    "ai-governance-legal": ("ai-governance", "AI 治理"),
    "commercial-legal": ("commercial", "商事合同"),
    "corporate-legal": ("corporate", "公司与并购"),
    "criminal-legal": ("criminal", "刑事辩护与合规"),
    "employment-legal": ("employment", "劳动用工"),
    "ip-legal": ("ip", "知识产权"),
    "law-student": ("law-student", "法学学习与法考"),
    "legal-builder-hub": ("builder-hub", "法律技能运营"),
    "legal-clinic": ("clinic", "法律诊所"),
    "litigation-legal": ("litigation", "诉讼与仲裁"),
    "privacy-legal": ("privacy", "数据合规与隐私"),
    "product-legal": ("product", "产品与营销合规"),
    "regulatory-legal": ("regulatory", "监管合规"),
}
COOKBOOKS = {
    "diligence-grid": "尽调问题表格：读取多份尽调材料、抽取问题、生成尽调表格及披露清单",
    "docket-watcher": "案件期限监控：整理案件期限、待办与变化；仅用户要求时建立定时监控",
    "launch-radar": "产品上线雷达：汇总上线准备、产品法律风险和整改事项",
    "reg-monitor": "监管动态监控：按用户指定范围查证监管变化并整理影响；仅用户要求时定时运行",
    "renewal-watcher": "合同续约监控：整理合同续约、到期和通知期限；仅用户要求时建立提醒",
}


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_preserving(path: Path, content: bytes) -> None:
    """A rerun must not overwrite a user's edited library or skill."""
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Existing file differs; preserved without overwrite: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def archive_files(path: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    with ZipFile(path) as archive:
        for item in archive.infolist():
            parts = PurePosixPath(item.filename).parts
            if item.is_dir():
                continue
            if len(parts) < 2 or any(p in ("..", ".") or ":" in p or "\\" in p for p in parts):
                raise ValueError(f"Unsafe archive member: {item.filename}")
            if PurePosixPath(item.filename).is_absolute() or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError(f"Archive paths must be ordinary relative files: {item.filename}")
            relative = PurePosixPath(*parts[1:]).as_posix()
            if relative in files:
                raise ValueError(f"Duplicate archive member: {relative}")
            files[relative] = archive.read(item)
    return files


def frontmatter(content: bytes) -> tuple[str, str]:
    text = content.decode("utf-8-sig")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)(.*)\Z", text, re.S)
    if not match or not re.search(r"^description\s*:", match[1], re.M):
        raise ValueError("Skill must have YAML frontmatter with description")
    return match[1], match[2]


def header(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n"


def bundle_name(domain: str, leaf: str) -> str:
    return f"legal-zh-{DOMAINS[domain][0]}-{leaf}"


def bridge_context(domain: str) -> str:
    return (
        "## Harness 工作区路径与使用说明\n\n"
        f"- 当前领域上下文：`legal-library/zh/{domain}/CLAUDE.md`（相对于工作区根）。"
        "先按需要读取；它是原库模板，模板占位符不是用户已确认的事实、审查偏好或审批制度。\n"
        "- 用户当前要求优先。缺少机构画像时先完成可完成的通用分析，标明关键假设；"
        "不要仅因模板占位符而强制运行完整入职问卷。必要事实不足时再简短补问。\n"
        "- 原文中的 Claude slash command 表示加载相应工作流。"
        "用 `skill` 工具和下方唯一名称映射，不要尝试执行 Claude 插件命令或安装脚本。\n"
        "- 仅按当前任务需要读取引用；法律材料需要现行性核验时使用实际可用的检索工具。"
        "原库列举的 MCP、账号和外部系统不代表已连接。\n"
        "- 不自动读取工作区外的 Claude 画像或写入用户全局配置；原始库保留在 `legal-library/`，"
        "当前案件输出保存到用户指定位置。\n\n"
    )


def prepare(workspace: Path, zh_path: Path, en_path: Path) -> dict:
    workspace = workspace.resolve()
    archives = {"zh": (zh_path, archive_files(zh_path)), "en": (en_path, archive_files(en_path))}
    sources = {}
    for language, (archive_path, files) in archives.items():
        for relative, content in files.items():
            write_preserving(workspace / "legal-library" / language / relative, content)
        sources[language] = {"archive": archive_path.name, "sha256": sha256(archive_path.read_bytes()),
                             "files": len(files), "license": f"legal-library/{language}/LICENSE"}

    zh = archives["zh"][1]
    leaf_paths = sorted(path for path in zh if len(PurePosixPath(path).parts) == 4
                        and PurePosixPath(path).parts[0] in DOMAINS
                        and PurePosixPath(path).parts[1] == "skills"
                        and PurePosixPath(path).parts[-1] == "SKILL.md")
    leaves: list[dict] = []
    for path in leaf_paths:
        domain, _, leaf, _ = PurePosixPath(path).parts
        name = bundle_name(domain, leaf)
        front, body = frontmatter(zh[path])
        front, count = re.subn(r"^name\s*:.*$", f"name: {name}", front, count=1, flags=re.M)
        if count != 1 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError(f"Invalid skill identity: {path}")
        context = bridge_context(domain)
        context += (
            f"- 原始完整文件：`legal-library/zh/{path}`。英文对应版本（如存在）在 `legal-library/en/{path}`。\n"
            f"- 本 bundle 已复制本技能资源，并合并该领域与仓库公共 `references/`；同名资源优先采用本技能版本。\n"
            f"- 调用同领域 `/{domain}:<skill>` 时，实际名称为 `legal-zh-{DOMAINS[domain][0]}-<skill>`。"
            "其他领域映射见 `legal-library/skill-catalog.json`。\n\n"
            "> 适配变更：仅唯一名称、工作区路径与上述适用说明经过调整；下方为提供 ZIP 中的完整技能正文。"
            "原始源码和 Apache-2.0 许可证保持不变。\n\n"
        )
        # Local resource base is the real directory returned by Harness's loader.
        resources: dict[str, tuple[str, bytes]] = {}
        for prefix in ("references/", f"{domain}/references/", f"{domain}/skills/{leaf}/"):
            for source, content in zh.items():
                if not source.startswith(prefix):
                    continue
                target = source[len(prefix):]
                if prefix.endswith("references/"):
                    target = "references/" + target
                if target == "SKILL.md":
                    continue
                resources[target] = (source, content)
        bundle = workspace / ".dsh" / "skills" / name
        for relative, (_, content) in resources.items():
            write_preserving(bundle / relative, content)
        write_preserving(bundle / "SKILL.md", f"---\n{front}\n---\n\n{context}{body}".encode("utf-8"))
        leaves.append({"name": name, "domain": domain, "original_name": leaf,
                       "source": f"legal-library/zh/{path}", "source_sha256": sha256(zh[path]),
                       "skill": f".dsh/skills/{name}/SKILL.md",
                       "context": f"legal-library/zh/{domain}/CLAUDE.md",
                       "resources": {key: f"legal-library/zh/{value[0]}" for key, value in resources.items()}})

    entries: list[dict] = []
    for domain, (slug, title) in DOMAINS.items():
        name = f"chinese-legal-{slug}"
        original = f".dsh/skills/{name}/SKILL.md"
        if original not in zh:
            raise ValueError(f"Missing original domain adapter: {original}")
        front, _ = frontmatter(zh[original])
        related = [item for item in leaves if item["domain"] == domain]
        contents = f"---\n{front}\n---\n\n# {title} · Harness 工作区入口\n\n" + bridge_context(domain)
        contents += "根据用户任务选择最贴近的一个或少数几个技能，用 `skill` 工具加载完整正文；不要一次加载整个领域。\n\n"
        contents += "\n".join(f"- `{item['name']}`（原工作流：`{item['original_name']}`）" for item in related)
        contents += (f"\n\n原适配器保存在 `legal-library/zh/{original}`。本入口复用其领域路由，"
                     "调整为工作区内路径与无冲突的技能名称；不修改用户全局配置。\n")
        write_preserving(workspace / ".dsh" / "skills" / name / "SKILL.md", contents.encode("utf-8"))
        entries.append({"name": name, "source": f"legal-library/zh/{original}", "type": "domain"})
    for slug, description in COOKBOOKS.items():
        name = f"chinese-legal-{slug}"
        original = f".dsh/skills/{name}/SKILL.md"
        if original not in zh:
            raise ValueError(f"Missing original cookbook adapter: {original}")
        cookbook = f"legal-library/zh/managed-agent-cookbooks/{slug}"
        contents = header(name, description) + f"# {description.split('：')[0]}\n\n"
        contents += (f"先读取工作区中的 `{cookbook}/README.md` 与 `{cookbook}/agent.yaml`，"
                     f"随后只按需读取 `{cookbook}/subagents/` 和 `steering-examples.json`。\n\n"
                     "复用其中完整工作流与输出格式，将 Claude 专用调用转换为 Harness 现有工具；"
                     "原库提到的服务不代表已连接。仅用户要求监控或重复执行时才创建定时任务，"
                     "仅获授权时开展并行工作。用户当前指令优先，缺少画像不自动启动完整问卷。\n\n"
                     f"原入口：`legal-library/zh/{original}`。这是路径适配入口，未执行原库脚本。\n")
        write_preserving(workspace / ".dsh" / "skills" / name / "SKILL.md", contents.encode("utf-8"))
        entries.append({"name": name, "source": f"legal-library/zh/{original}", "type": "cookbook"})
    assert len(leaves) == 157 and len(entries) == 18
    assert len({item["name"] for item in leaves + entries}) == 175
    manifest = {
        "format": 1, "harness_source_ref": HARNESS_REF,
        "official_discovery_reference": f"https://github.com/deepseek-ai/deepseek-harness/blob/{HARNESS_REF}/packages/skill/skill-filesystem/README.zh.md",
        "sources": sources, "entry_count": len(entries), "workflow_count": len(leaves),
        "discoverable_count": len(entries) + len(leaves),
        "domain_counts": dict(sorted(Counter(item["domain"] for item in leaves).items())),
        "english_policy": "Original English source retained for reference. Chinese versions are the active skills. The English-only external CoCounsel plugin is retained as source, not advertised as a connected tool.",
        "entries": entries, "workflows": leaves,
        "verification_scope": "Installation and one real Harness filesystem-provider contract skill load; no claim that all workflows have run against a model.",
    }
    write_preserving(workspace / "legal-library" / "skill-catalog.json",
                     (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    readme = f"""# 法律 Skill 工作区库

中文优先：18 个领域/工作流入口、157 个唯一命名的完整中文技能，共 175 个可发现条目。
Harness 只把名称和简介放入技能目录，调用 `skill` 时才读取所选完整正文及其资源。

- `.dsh/skills/`：适配入口、完整技能及所需引用资源。
- `legal-library/zh/`：中文 ZIP 的原始目录结构、CLAUDE.md、references、许可证与脚本源码。
- `legal-library/en/`：英文 ZIP 原始源码，用于按需参照；不重复注册同名技能。
- `legal-library/skill-catalog.json`：唯一名称、原文件、资源路径、来源 ZIP SHA-256 的对应关系。

合同审查示例：`chinese-legal-commercial` → `legal-zh-commercial-review` → 按协议类型选择 NDA、供应商或 SaaS 审查。
每个细项技能保留原始完整正文，并明确领域 CLAUDE.md 和 references 的读取路径。
原始库安装脚本未运行；没有写入用户全局技能、画像或 MCP 配置。

适配说明：生成版本修改唯一名称、路径及与当前用户任务相容的加载说明；原始库不改写。
两个来源的许可证均保存在各自 `LICENSE` 文件中。原库中外部服务、机构模板和占位符不代表本机已经配置。
英文包独有的 CoCounsel 外部插件保留源码，不列为已连接功能。

发现依据：官方 Harness `{HARNESS_REF}` 的 skill-filesystem。
发现路径为最近 `.git` 祖先下的 `.dsh/skills`；无 `.git` 时用 cwd。
启动会话时应选择此 `workspace`，或者由运行配置显式指定这里的 `.dsh/skills` 为 customSkillDirs。

验证边界：目录发现及一项合同技能加载不代表 157 个法律工作流均已实际运行。
"""
    write_preserving(workspace / "legal-library" / "README.md", readme.encode("utf-8"))
    return {"workspace": str(workspace), "entries": len(entries), "workflows": len(leaves),
            "discoverable": len(entries) + len(leaves), "sources": sources}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1] / "workspace")
    parser.add_argument("--zh-zip", type=Path, default=DEFAULT_TEMP / "claude-for-legal-ZH.zip")
    parser.add_argument("--en-zip", type=Path, default=DEFAULT_TEMP / "claude-for-legal-main.zip")
    args = parser.parse_args()
    print(json.dumps(prepare(args.workspace, args.zh_zip, args.en_zip), ensure_ascii=False, indent=2))
