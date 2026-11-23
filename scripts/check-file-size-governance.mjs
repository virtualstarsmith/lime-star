#!/usr/bin/env node
// 行数棘轮门禁：非生成文件接近 800 行必须拆分，超过 1000 行不得继续堆叠业务逻辑。
// 规则：
//   - 新文件（不在基线内）超过 WARN_LINES 视为违规；
//   - 已在基线内的超线文件只许收缩（允许 ±5% 容差回弹）；
//   - 任何文件超过 MAX_LINES 直接违规，不受基线保护；
//   - 文件头部带 @generated 标记的生成文件豁免。
// 用法：
//   node scripts/check-file-size-governance.mjs [--root <dir>] [--baseline <file>] [--update]
//   --update 重新生成基线（只应用于已同步完成的收敛结果，不是赦免工具）。

import { readdirSync, readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join, relative, extname, sep, dirname } from 'node:path';

// lime-star 使用默认位置；路线图 P3 起把运行时产物目录 .lime-star 加入 SKIP_DIRS。
const WARN_LINES = 800;
const MAX_LINES = 1000;
const GROWTH_TOLERANCE = 0.05; // 基线文件允许的最大回弹比例
const GENERATED_MARKER = '@generated';
const SKIP_DIRS = new Set([
  'node_modules', '.git', '.hg', 'dist', 'build', 'out', 'coverage',
  '.next', '.nuxt', 'target', '__pycache__', '.venv', 'venv', '.cache',
]);
const SKIP_EXTS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.pdf', '.zip',
  '.woff', '.woff2', '.ttf', '.mp4', '.mp3', '.wasm',
]);

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

function listFiles(dir, root, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      listFiles(full, root, out);
    } else if (entry.isFile()) {
      if (SKIP_EXTS.has(extname(entry.name).toLowerCase())) continue;
      out.push(relative(root, full).split(sep).join('/'));
    }
  }
}

function countLines(file) {
  const raw = readFileSync(file, 'utf8');
  const lines = raw.split(/\r?\n/);
  if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
  const isGenerated = lines.slice(0, 5).some((l) => l.includes(GENERATED_MARKER));
  return { lines: lines.length, isGenerated };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('用法：node scripts/check-file-size-governance.mjs [--root <dir>] [--baseline <file>] [--update]');
    process.exit(0);
  }
  const root = args.root;
  const baselinePath = args.baseline ?? join(root, 'governance', 'file-size-baseline.json');

  const files = [];
  listFiles(root, root, files);

  const baseline = existsSync(baselinePath)
    ? JSON.parse(readFileSync(baselinePath, 'utf8'))
    : { files: {} };

  // 第一遍：统计行数，确定本轮基线内容
  const infos = new Map();
  const nextBaseline = {};
  let generatedSkipped = 0;
  for (const rel of files) {
    const { lines, isGenerated } = countLines(join(root, rel));
    infos.set(rel, { lines, isGenerated });
    if (isGenerated) continue;
    if (lines > WARN_LINES) nextBaseline[rel] = lines;
  }

  // --update = 显式确认当前状态并冻结为新基线，评估按更新后的基线进行
  const effectiveBaseline = args.update ? nextBaseline : (baseline.files ?? {});
  const violations = [];

  for (const [rel, { lines, isGenerated }] of infos) {
    if (isGenerated) {
      generatedSkipped++;
      continue;
    }

    if (lines > MAX_LINES) {
      violations.push({ rel, lines, rule: `超过硬上限 ${MAX_LINES} 行，必须拆分` });
      continue;
    }
    if (lines <= WARN_LINES) continue;

    if (rel in effectiveBaseline) {
      const allowed = Math.ceil(effectiveBaseline[rel] * (1 + GROWTH_TOLERANCE));
      if (lines > allowed) {
        violations.push({
          rel,
          lines,
          rule: `基线 ${effectiveBaseline[rel]} 行，只许收缩（允许回弹至 ${allowed} 行）`,
        });
      }
    } else {
      violations.push({ rel, lines, rule: `新文件超过 ${WARN_LINES} 行，优先拆分或登记退出条件` });
    }
  }

  if (args.update) {
    mkdirSync(dirname(baselinePath), { recursive: true });
    writeFileSync(baselinePath, `${JSON.stringify({ files: nextBaseline }, null, 2)}\n`);
    console.log(`基线已更新：${baselinePath}（${Object.keys(nextBaseline).length} 个超线文件）`);
  }

  console.log(`扫描文件 ${files.length} 个；生成文件豁免 ${generatedSkipped} 个；超线跟踪 ${Object.keys(nextBaseline).length} 个。`);
  if (violations.length > 0) {
    console.error(`\n行数门禁违规 ${violations.length} 处：`);
    for (const v of violations) {
      console.error(`  ✗ ${v.rel}（${v.lines} 行）：${v.rule}`);
    }
    process.exit(1);
  }
  console.log('行数门禁通过。');
}

try {
  main();
} catch (err) {
  console.error(`行数门禁执行失败：${err.message}`);
  process.exit(2);
}
