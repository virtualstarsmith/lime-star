#!/usr/bin/env node
// 文档交叉引用守卫：规则、计划、手册之间的相对路径引用不许断链。
// 扫描范围：仓库根 AGENTS.md、根目录 *.md、internal/**/*.md。
// 解析规则：对每个形如 xxx.md / xxx.mjs / xxx.json 的反引号引用或 markdown 链接，
//   依次按 [相对引用文件所在目录, 相对仓库根] 解析，且必须落在仓库根以内；仍找不到时，只有不带目录的裸文件名
//   才按文件名全树搜索。带目录的引用解析失败即违规，防止写错的相对路径被别处的同名文件放行。
// 占位符（含 <、*、空格）与绝对路径、URL 跳过。
// 用法：
//   node scripts/check-doc-links.mjs [--root <dir>]

import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join, relative, isAbsolute, dirname, basename, sep } from 'node:path';

function parseArgs(argv) {
  const args = { root: process.cwd() };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--root') args.root = argv[++i];
    else if (a === '--help' || a === '-h') args.help = true;
    else {
      console.error(`未知参数：${a}`);
      process.exit(2);
    }
  }
  return args;
}

function collectFiles(dir, out) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (['node_modules', '.git', 'dist', 'build', 'out', 'coverage', 'target'].includes(entry.name)) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) collectFiles(full, out);
    else if (entry.isFile()) out.push(full);
  }
}

function isRefCandidate(p) {
  if (!/\.(md|mjs|json)$/.test(p)) return false;
  if (p.includes('<') || p.includes('*') || p.includes(' ')) return false;
  if (isAbsolute(p) || /^(https?:|file:|mailto:)/.test(p)) return false;
  return true;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('用法：node scripts/check-doc-links.mjs [--root <dir>]');
    process.exit(0);
  }
  const root = args.root;
  // 解析结果必须落在仓库根以内：../.. 逃出仓库后碰巧命中的仓库外文件不算数。
  const insideRoot = (abs) => {
    const rel = relative(root, abs);
    return rel !== '' && rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel);
  };

  const all = [];
  collectFiles(root, all);
  // 文件名 -> 全树同名的相对路径列表；只用于裸文件名的兜底和违规提示。
  const byBasename = new Map();
  for (const f of all) {
    const name = basename(f);
    if (!byBasename.has(name)) byBasename.set(name, []);
    byBasename.get(name).push(relative(root, f).split('\\').join('/'));
  }

  // 扫描范围：根 AGENTS.md、根目录 *.md、internal/**/*.md
  const targets = [];
  const rootAgents = join(root, 'AGENTS.md');
  if (existsSync(rootAgents)) targets.push(rootAgents);
  for (const f of readdirSync(root, { withFileTypes: true })) {
    if (f.isFile() && f.name.endsWith('.md')) targets.push(join(root, f.name));
  }
  const internalDir = join(root, 'internal');
  if (existsSync(internalDir)) {
    for (const f of all) {
      const rel = relative(internalDir, f);
      if (!rel.startsWith('..') && f.endsWith('.md')) targets.push(f);
    }
  }

  const backtick = /`([^`\n]+)`/g;
  const mdLink = /\]\(([^)\s]+)\)/g;
  const violations = [];
  let checked = 0;

  for (const f of targets) {
    const text = readFileSync(f, 'utf8');
    const refs = new Set();
    for (const m of text.matchAll(backtick)) refs.add(m[1]);
    for (const m of text.matchAll(mdLink)) refs.add(m[1]);
    for (const p of refs) {
      if (!isRefCandidate(p)) continue;
      checked++;
      const dir = dirname(f);
      // 候选：相对引用文件所在目录、相对仓库根；两者都必须落在仓库根以内。
      const candidates = [join(dir, p), join(root, p)].filter(insideRoot);
      const hasDir = /[\\/]/.test(p);
      if (candidates.some((c) => existsSync(c))) continue;
      // 裸文件名可以按文件名全树查找；带目录的引用解析失败即违规。
      if (!hasDir && byBasename.has(basename(p))) continue;
      const sameName = byBasename.get(basename(p));
      const hint = hasDir && sameName ? `（按路径未找到；同名文件在 ${sameName.join('、')}）` : '';
      violations.push(`${relative(root, f)} -> ${p}${hint}`);
    }
  }

  console.log(`扫描 ${targets.length} 个文档，检查 ${checked} 个路径引用。`);
  if (violations.length > 0) {
    console.error(`\n文档断链 ${violations.length} 处：`);
    for (const v of violations) console.error(`  ✗ ${v}`);
    process.exit(1);
  }
  console.log('文档交叉引用检查通过。');
}

try {
  main();
} catch (err) {
  console.error(`文档引用守卫执行失败：${err.message}`);
  process.exit(2);
}
