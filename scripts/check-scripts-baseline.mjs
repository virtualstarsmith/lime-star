#!/usr/bin/env node
// scripts 目录冻结基线门禁：scripts/ 根目录与一级领域目录是冻结基线。
// 规则：
//   - scripts/ 根目录下的 tracked 文件、一级子目录必须出现在基线清单内，新出现的条目视为违规；
//   - 新增脚本必须进入既有 scripts/<domain>/、scripts/lib/ 或所属 package；
//   - 基线只许收缩（条目迁移退役后从基线删除），不允许随意扩张；
//   - 任何位置出现 __pycache__ / .pyc / .DS_Store 等垃圾产物视为违规。
// 用法：
//   node scripts/check-scripts-baseline.mjs [--root <dir>] [--baseline <file>] [--update]

import { readdirSync, readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join, relative, sep, dirname } from 'node:path';

// lime-star 使用默认位置：scripts/ 目录与 governance/scripts-baseline.json。
const JUNK_NAMES = new Set(['__pycache__', '.DS_Store', 'Thumbs.db', '.pyc']);
const SKIP_DIRS = new Set(['node_modules', '.git']);

function parseArgs(argv) {
  const args = { root: process.cwd(), baseline: null, update: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--root') args.root = argv[++i];
    else if (a === '--baseline') args.baseline = argv[++i];
    else if (a === '--update') args.update = true;
    else if (a === '--help' || a === '-h') args.help = true;
    else {
      console.error(`未知参数：${a}`);
      process.exit(2);
    }
  }
  return args;
}

function hasJunk(dir, root, out) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (JUNK_NAMES.has(entry.name) || entry.name.endsWith('.pyc')) {
      out.push(relative(root, full).split(sep).join('/'));
    } else if (entry.isDirectory() && !SKIP_DIRS.has(entry.name)) {
      hasJunk(full, root, out);
    }
  }
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('用法：node scripts/check-scripts-baseline.mjs [--root <dir>] [--baseline <file>] [--update]');
    process.exit(0);
  }
  const root = args.root;
  const scriptsDir = join(root, 'scripts');
  const baselinePath = args.baseline ?? join(root, 'governance', 'scripts-baseline.json');

  if (!existsSync(scriptsDir)) {
    console.log('未找到 scripts/ 目录，跳过基线检查（接入脚本后请先生成基线）。');
    process.exit(0);
  }

  const baseline = existsSync(baselinePath)
    ? readFileSyncSafe(baselinePath)
    : null;

  const rootFiles = [];
  const topDirs = [];
  for (const entry of readdirSync(scriptsDir, { withFileTypes: true })) {
    if (entry.isFile()) rootFiles.push(entry.name);
    else if (entry.isDirectory()) topDirs.push(entry.name);
  }

  if (!baseline) {
    if (args.update) {
      mkdirSync(dirname(baselinePath), { recursive: true });
      writeFileSync(baselinePath, `${JSON.stringify({ rootFiles, topDirs }, null, 2)}\n`);
      console.log(`基线已生成：${baselinePath}（根文件 ${rootFiles.length} 个，一级目录 ${topDirs.length} 个）`);
      process.exit(0);
    }
    console.error(`缺少基线文件 ${baselinePath}。首次接入请运行 --update 生成当前基线，之后基线进入冻结状态。`);
    process.exit(1);
  }

  const violations = [];
  // --update = 确认当前目录结构并冻结为新基线，评估按更新后的基线进行
  const knownFiles = new Set(args.update ? rootFiles : (baseline.rootFiles ?? []));
  const knownDirs = new Set(args.update ? topDirs : (baseline.topDirs ?? []));

  for (const name of rootFiles) {
    if (!knownFiles.has(name)) {
      violations.push(`scripts/${name}：根目录新文件不在冻结基线内，请移入 scripts/<domain>/、scripts/lib/ 或更新基线论证`);
    }
  }
  for (const name of topDirs) {
    if (!knownDirs.has(name)) {
      violations.push(`scripts/${name}/：一级新目录不在冻结基线内，新增脚本应进入既有领域目录`);
    }
  }
  for (const name of knownFiles) {
    if (!existsSync(join(scriptsDir, name))) {
      console.log(`  i 基线条目 scripts/${name} 已不存在（基线收缩是允许的，建议从基线移除）。`);
    }
  }

  const junk = [];
  hasJunk(scriptsDir, scriptsDir, junk);
  for (const rel of junk) violations.push(`${rel}：构建/缓存垃圾产物不得进入版本库`);

  if (args.update) {
    mkdirSync(dirname(baselinePath), { recursive: true });
    writeFileSync(baselinePath, `${JSON.stringify({ rootFiles, topDirs }, null, 2)}\n`);
    console.log(`基线已更新：${baselinePath}`);
  }

  console.log(`scripts/ 根文件 ${rootFiles.length} 个，一级目录 ${topDirs.length} 个。`);
  if (violations.length > 0) {
    console.error(`\n脚本治理违规 ${violations.length} 处：`);
    for (const v of violations) console.error(`  ✗ ${v}`);
    process.exit(1);
  }
  console.log('脚本冻结基线检查通过。');
}

function readFileSyncSafe(p) {
  try {
    return JSON.parse(readFileSync(p, 'utf8'));
  } catch (err) {
    console.error(`基线文件解析失败：${p}（${err.message}）`);
    process.exit(2);
  }
}

try {
  main();
} catch (err) {
  console.error(`脚本基线门禁执行失败：${err.message}`);
  process.exit(2);
}
