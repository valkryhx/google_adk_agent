#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能文件分析器 - Smart File Analyzer
===================================
一个功能强大的目录分析与报告生成工具，展示多方面的编程能力。

功能特性：
- 📊 目录结构扫描与分析
- 📈 文件类型统计与可视化
- 🔍 重复文件检测（基于内容哈希）
- 📏 代码行数统计（支持多种语言）
- ⚡ 多线程并发处理
- 📝 配置文件支持
- 🎨 ASCII 图表生成
- 📋 日志记录
- 🛡️ 完善的错误处理
"""

import os
import sys
import hashlib
import json
import logging
import argparse
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, Counter
from enum import Enum
import mmap


# ==================== 核心数据类 ====================

class FileCategory(Enum):
    """文件分类枚举"""
    CODE = "code"
    DOCUMENT = "document"
    IMAGE = "image"
    DATA = "data"
    CONFIG = "config"
    OTHER = "other"


@dataclass
class FileInfo:
    """文件信息数据结构"""
    path: Path
    size: int
    category: FileCategory
    extension: str
    lines: int = 0
    hash: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of: Optional[Path] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['path'] = str(self.path)
        data['category'] = self.category.value
        if self.duplicate_of:
            data['duplicate_of'] = str(self.duplicate_of)
        return data


@dataclass
class AnalysisResult:
    """分析结果数据结构"""
    target_path: Path
    scan_time: datetime
    total_files: int = 0
    total_size: int = 0
    files_by_category: Dict[str, int] = field(default_factory=dict)
    files_by_extension: Dict[str, int] = field(default_factory=dict)
    code_files: List[FileInfo] = field(default_factory=list)
    duplicate_files: List[Tuple[FileInfo, FileInfo]] = field(default_factory=list)
    top_largest_files: List[FileInfo] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'target_path': str(self.target_path),
            'scan_time': self.scan_time.isoformat(),
            'total_files': self.total_files,
            'total_size': self.total_size,
            'files_by_category': self.files_by_category,
            'files_by_extension': dict(self.files_by_extension),
            'code_stats': {
                'total_code_files': len(self.code_files),
                'total_code_lines': sum(f.lines for f in self.code_files),
                'languages': self._extract_languages()
            },
            'duplicate_count': len(self.duplicate_files),
            'top_largest': [f.to_dict() for f in self.top_largest_files[:10]]
        }
    
    def _extract_languages(self) -> Dict[str, int]:
        """提取编程语言统计"""
        lang_map = {
            '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
            '.java': 'Java', '.cpp': 'C++', '.c': 'C', '.cs': 'C#',
            '.go': 'Go', '.rs': 'Rust', '.rb': 'Ruby', '.php': 'PHP',
            '.swift': 'Swift', '.kt': 'Kotlin', '.scala': 'Scala',
            '.html': 'HTML', '.css': 'CSS', '.sql': 'SQL',
            '.sh': 'Shell', '.bat': 'Batch', '.ps1': 'PowerShell'
        }
        counter = Counter()
        for f in self.code_files:
            lang = lang_map.get(f.extension, f.extension.lstrip('.').capitalize())
            counter[lang] += 1
        return dict(counter)


# ==================== 配置管理 ====================

@dataclass
class Config:
    """配置类"""
    max_workers: int = 4
    min_file_size: int = 0
    exclude_dirs: List[str] = field(default_factory=lambda: [
        '.git', '__pycache__', 'node_modules', '.venv', 'venv',
        '.idea', '.vscode', 'dist', 'build', 'target'
    ])
    exclude_extensions: List[str] = field(default_factory=lambda: [
        '.pyc', '.class', '.o', '.obj', '.exe', '.dll', '.so',
        '.dylib', '.zip', '.tar', '.gz', '.rar'
    ])
    enable_duplicate_detection: bool = True
    duplicate_threshold: int = 1024  # 至少1KB才检测重复
    
    @classmethod
    def from_file(cls, config_path: Path) -> 'Config':
        """从JSON文件加载配置"""
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls(**data)
        return cls()
    
    def save(self, config_path: Path) -> None:
        """保存配置到文件"""
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)


# ==================== 文件分类器 ====================

class FileCategorizer:
    """智能文件分类器"""
    
    # 扩展名映射表
    CATEGORY_MAP = {
        FileCategory.CODE: {
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs', '.go',
            '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.m',
            '.h', '.hpp', '.hh', '.hxx', '.lua', '.pl', '.pm', '.r',
            '.jl', '.dart', '.groovy', '.vb', '.ada', '.f', '.f90'
        },
        FileCategory.DOCUMENT: {
            '.md', '.txt', '.rst', '.tex', '.doc', '.docx', '.pdf',
            '.odt', '.rtf', '.wiki', '.org', '.pub'
        },
        FileCategory.IMAGE: {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
            '.ico', '.tiff', '.tif', '.psd', '.ai', '.eps'
        },
        FileCategory.DATA: {
            '.csv', '.json', '.xml', '.yml', '.yaml', '.toml', '.ini',
            '.cfg', '.conf', '.sqlite', '.db', '.parquet', '.feather',
            '.xlsx', '.xls', '.ods', '.avro', '.orc', '.hdf5'
        },
        FileCategory.CONFIG: {
            '.cfg', '.conf', '.config', '.ini', '.env', '.properties',
            '.toml', '.yaml', '.yml', '.json', '.xml'
        }
    }
    
    @classmethod
    def categorize(cls, file_path: Path) -> FileCategory:
        """根据扩展名分类文件"""
        ext = file_path.suffix.lower()
        
        for category, extensions in cls.CATEGORY_MAP.items():
            if ext in extensions:
                return category
        
        # 特殊处理：某些文件可能没有扩展名但有特征
        return FileCategory.OTHER


# ==================== 核心分析器 ====================

class SmartFileAnalyzer:
    """智能文件分析器主类"""
    
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self._lock = threading.Lock()
        self.file_infos: List[FileInfo] = []
        self.hash_map: Dict[str, List[FileInfo]] = defaultdict(list)
    
    def analyze(self, target_path: Path) -> AnalysisResult:
        """执行分析主流程"""
        self.logger.info(f"开始分析: {target_path}")
        start_time = time.time()
        
        result = AnalysisResult(
            target_path=target_path,
            scan_time=datetime.now()
        )
        
        if not target_path.exists():
            raise FileNotFoundError(f"路径不存在: {target_path}")
        
        # 第一步：收集所有文件
        self.logger.info("正在扫描文件...")
        all_files = self._collect_files(target_path)
        result.total_files = len(all_files)
        
        # 第二步：多线程处理文件
        self.logger.info(f"正在分析 {len(all_files)} 个文件...")
        self._process_files_parallel(all_files)
        
        # 第三步：统计汇总
        self._aggregate_results(result)
        
        # 第四步：检测重复文件
        if self.config.enable_duplicate_detection:
            self.logger.info("正在检测重复文件...")
            self._detect_duplicates(result)
        
        # 第五步：找出最大文件
        self._find_largest_files(result)
        
        elapsed = time.time() - start_time
        self.logger.info(f"分析完成！耗时: {elapsed:.2f}秒")
        
        return result
    
    def _collect_files(self, target_path: Path) -> List[Path]:
        """收集所有符合条件的文件"""
        files = []
        
        try:
            for root, dirs, filenames in os.walk(target_path):
                # 过滤目录
                dirs[:] = [d for d in dirs if d not in self.config.exclude_dirs]
                
                for filename in filenames:
                    filepath = Path(root) / filename
                    
                    # 过滤扩展名
                    if filepath.suffix.lower() in self.config.exclude_extensions:
                        continue
                    
                    try:
                        # 过滤小文件
                        if filepath.stat().st_size < self.config.min_file_size:
                            continue
                    except (OSError, PermissionError):
                        continue
                    
                    files.append(filepath)
                    
        except (PermissionError, OSError) as e:
            self.logger.error(f"扫描目录时出错: {e}")
        
        return files
    
    def _process_files_parallel(self, files: List[Path]) -> None:
        """并行处理文件"""
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_path = {
                executor.submit(self._process_single_file, filepath): filepath
                for filepath in files
            }
            
            completed = 0
            for future in as_completed(future_to_path):
                filepath = future_to_path[future]
                try:
                    file_info = future.result()
                    if file_info:
                        with self._lock:
                            self.file_infos.append(file_info)
                except Exception as e:
                    self.logger.error(f"处理文件失败 {filepath}: {e}")
                
                completed += 1
                if completed % 100 == 0:
                    self.logger.debug(f"已处理 {completed}/{len(files)} 个文件")
    
    def _process_single_file(self, filepath: Path) -> Optional[FileInfo]:
        """处理单个文件"""
        try:
            stat = filepath.stat()
            category = FileCategorizer.categorize(filepath)
            extension = filepath.suffix.lower()
            
            file_info = FileInfo(
                path=filepath,
                size=stat.st_size,
                category=category,
                extension=extension
            )
            
            # 计算代码行数（仅对代码文件）
            if category == FileCategory.CODE:
                file_info.lines = self._count_lines(filepath)
            
            # 计算文件哈希（用于重复检测）
            if stat.st_size >= self.config.duplicate_threshold:
                file_info.hash = self._calculate_file_hash(filepath)
                if file_info.hash:
                    with self._lock:
                        self.hash_map[file_info.hash].append(file_info)
            
            return file_info
            
        except (OSError, PermissionError) as e:
            self.logger.debug(f"无法读取文件 {filepath}: {e}")
            return None
    
    def _count_lines(self, filepath: Path) -> int:
        """统计文件行数"""
        try:
            with open(filepath, 'rb') as f:
                # 使用mmap高效统计
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    return mm.read().count(b'\n') + 1
        except (OSError, PermissionError, ValueError):
            # 回退到普通读取
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    return sum(1 for _ in f)
            except:
                return 0
    
    def _calculate_file_hash(self, filepath: Path, sample_size: int = 1024 * 1024) -> Optional[str]:
        """计算文件哈希值（采样以提高性能）"""
        hasher = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                # 读取文件开始、中间和结束的采样块
                file_size = os.path.getsize(filepath)
                chunks = []
                
                if file_size <= sample_size * 3:
                    # 小文件，全部读取
                    chunks.append(f.read())
                else:
                    # 大文件，采样
                    chunks.append(f.read(sample_size))
                    f.seek(file_size // 2)
                    chunks.append(f.read(sample_size))
                    f.seek(-sample_size, 2)
                    chunks.append(f.read(sample_size))
                
                for chunk in chunks:
                    hasher.update(chunk)
                
                return hasher.hexdigest()
        except:
            return None
    
    def _detect_duplicates(self, result: AnalysisResult) -> None:
        """检测重复文件"""
        duplicate_groups = []
        for file_list in self.hash_map.values():
            if len(file_list) > 1:
                duplicate_groups.append(file_list)
        
        for group in duplicate_groups:
            # 标记重复文件
            base = group[0]
            for dup in group[1:]:
                dup.is_duplicate = True
                dup.duplicate_of = base.path
                result.duplicate_files.append((base, dup))
    
    def _aggregate_results(self, result: AnalysisResult) -> None:
        """聚合分析结果"""
        result.total_size = sum(f.size for f in self.file_infos)
        
        # 按分类统计
        category_counter = Counter()
        extension_counter = Counter()
        
        for file_info in self.file_infos:
            category_counter[file_info.category.value] += 1
            extension_counter[file_info.extension] += 1
            
            if file_info.category == FileCategory.CODE:
                result.code_files.append(file_info)
        
        result.files_by_category = dict(category_counter)
        result.files_by_extension = dict(extension_counter)
    
    def _find_largest_files(self, result: AnalysisResult) -> None:
        """找出最大的文件"""
        sorted_files = sorted(self.file_infos, key=lambda x: x.size, reverse=True)
        result.top_largest_files = sorted_files[:20]


# ==================== 报告生成器 ====================

class ReportGenerator:
    """报告生成器"""
    
    @staticmethod
    def generate_text_report(result: AnalysisResult) -> str:
        """生成文本报告"""
        lines = []
        lines.append("=" * 70)
        lines.append(f"[*] 文件分析报告")
        lines.append("=" * 70)
        lines.append(f"[-] 分析目录: {result.target_path}")
        lines.append(f"[-] 扫描时间: {result.scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"[-] 总文件数: {result.total_files:,}")
        
        # 计算人类可读的大小
        total_size_human = ReportGenerator._human_size(result.total_size)
        lines.append(f"[-] 总大小: {total_size_human}")
        lines.append("")
        
        # 文件分类
        lines.append("[*] 文件分类统计:")
        for category, count in sorted(result.files_by_category.items()):
            percentage = (count / result.total_files * 100) if result.total_files > 0 else 0
            bar = ReportGenerator._create_bar(percentage, width=20)
            lines.append(f"  {category:12s}: {count:6d} ({percentage:5.1f}%) {bar}")
        lines.append("")
        
        # 扩展名TOP 10
        lines.append("[*] 文件扩展名 TOP 10:")
        top_ext = sorted(result.files_by_extension.items(), 
                        key=lambda x: x[1], reverse=True)[:10]
        for ext, count in top_ext:
            percentage = (count / result.total_files * 100) if result.total_files > 0 else 0
            bar = ReportGenerator._create_bar(percentage, width=20)
            lines.append(f"  {ext:10s}: {count:6d} ({percentage:5.1f}%) {bar}")
        lines.append("")
        
        # 代码统计
        code_stats = result.to_dict()['code_stats']
        lines.append("[*] 代码统计:")
        lines.append(f"  代码文件数: {code_stats['total_code_files']}")
        lines.append(f"  总代码行: {code_stats['total_code_lines']:,}")
        lines.append("  编程语言分布:")
        for lang, count in sorted(code_stats['languages'].items(), 
                                 key=lambda x: x[1], reverse=True)[:10]:
            bar = ReportGenerator._create_bar(
                count / code_stats['total_code_files'] * 100 if code_stats['total_code_files'] > 0 else 0,
                width=20
            )
            lines.append(f"    {lang:12s}: {count:4d} {bar}")
        lines.append("")
        
        # 重复文件
        if result.duplicate_files:
            lines.append("[!] 重复文件:")
            seen = set()
            for base, dup in result.duplicate_files[:10]:
                key = (base.path, base.hash)
                if key not in seen:
                    seen.add(key)
                    dup_count = len([d for d in result.duplicate_files 
                                   if d[0].path == base.path])
                    lines.append(f"  {dup_count} 个副本:")
                    lines.append(f"    [-] {base.path}")
                    lines.append(f"    [-] {ReportGenerator._human_size(base.size)}")
                    for _, dup_file in [d for d in result.duplicate_files 
                                       if d[0].path == base.path][:3]:
                        lines.append(f"    [-] {dup_file[1].path}")
                    if dup_count > 3:
                        lines.append(f"    ... 还有 {dup_count - 3} 个")
            lines.append(f"总计重复文件组: {len(result.duplicate_files)} 组")
        else:
            lines.append("[+] 未发现重复文件")
        lines.append("")
        
        # 最大文件
        if result.top_largest_files:
            lines.append("[*] 最大的 10 个文件:")
            for i, file_info in enumerate(result.top_largest_files[:10], 1):
                human_size = ReportGenerator._human_size(file_info.size)
                lines.append(f"  {i:2d}. {human_size:>10s} - {file_info.path.name}")
        
        lines.append("=" * 70)
        return "\n".join(lines)
    
    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """将字节数转换为人类可读格式"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    @staticmethod
    def _create_bar(percentage: float, width: int = 20) -> str:
        """创建进度条（使用ASCII字符）"""
        filled = int(width * percentage / 100)
        bar = '=' * filled + '-' * (width - filled)
        return f"[{bar}]"


# ==================== 主程序 ====================

def setup_logging(verbose: bool = False) -> logging.Logger:
    """配置日志系统"""
    level = logging.DEBUG if verbose else logging.INFO
    
    logger = logging.getLogger('SmartFileAnalyzer')
    logger.setLevel(level)
    
    # 清除已有处理器
    logger.handlers = []
    
    # 控制台处理器
    console = logging.StreamHandler()
    console.setLevel(level)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    return logger


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='智能文件分析器 - 综合分析目录结构与文件统计',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s .                    # 分析当前目录
  %(prog)s /path/to/dir --json  # 生成JSON报告
  %(prog)s --config config.json # 使用配置文件
  %(prog)s --exclude-dir node_modules,__pycache__
        """
    )
    
    parser.add_argument('path', nargs='?', default='.',
                       help='要分析的目录路径（默认为当前目录）')
    
    parser.add_argument('-o', '--output',
                       help='输出报告文件路径（默认为标准输出）')
    
    parser.add_argument('-j', '--json', action='store_true',
                       help='输出JSON格式报告')
    
    parser.add_argument('--config', type=Path,
                       help='配置文件路径（JSON格式）')
    
    parser.add_argument('--exclude-dir', type=str,
                       help='额外排除的目录（逗号分隔）')
    
    parser.add_argument('--exclude-ext', type=str,
                       help='额外排除的扩展名（逗号分隔）')
    
    parser.add_argument('--min-size', type=int, default=0,
                       help='最小文件大小（字节），小于此值的文件将被忽略')
    
    parser.add_argument('--no-duplicates', action='store_true',
                       help='禁用重复文件检测')
    
    parser.add_argument('--workers', type=int, default=4,
                       help='并发工作线程数（默认: 4）')
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='详细输出')
    
    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')
    
    return parser.parse_args()


def main() -> int:
    """主函数"""
    args = parse_arguments()
    logger = setup_logging(args.verbose)
    
    try:
        # 加载配置
        config_path = args.config or Path('analyzer_config.json')
        config = Config.from_file(config_path)
        
        # 应用命令行参数覆盖配置
        if args.exclude_dir:
            extra_dirs = [d.strip() for d in args.exclude_dir.split(',')]
            config.exclude_dirs.extend(extra_dirs)
        
        if args.exclude_ext:
            extra_exts = [e.strip() for e in args.exclude_ext.split(',')]
            config.exclude_extensions.extend(extra_exts)
        
        config.min_file_size = args.min_size
        config.max_workers = args.workers
        config.enable_duplicate_detection = not args.no_duplicates
        
        # 创建分析器
        target_path = Path(args.path).resolve()
        analyzer = SmartFileAnalyzer(config, logger)
        
        # 执行分析
        result = analyzer.analyze(target_path)
        
        # 生成报告
        if args.json:
            report = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
        else:
            report = ReportGenerator.generate_text_report(result)
        
        # 输出报告
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"报告已保存到: {output_path}")
        else:
            print(report)
        
        # 保存配置（如果不存在）
        if not config_path.exists():
            config.save(config_path)
            logger.debug(f"配置文件已保存到: {config_path}")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("用户中断操作")
        return 130
    except FileNotFoundError as e:
        logger.error(f"路径错误: {e}")
        return 1
    except Exception as e:
        logger.exception(f"程序执行失败: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())