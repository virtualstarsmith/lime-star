#!/usr/bin/env node
// 密钥守卫：凭证只放 .env 或环境变量，不得进入 Git 跟踪的文件。
// 规则：
//   - .env 必须被 Git 忽略（按忽略规则判断，不看它当前是否已被跟踪）；
//   - .env 及其变体（如 .env.local）不得被 Git 跟踪，.env.example 除外；
//   - 已跟踪文件在磁盘上的内容里不得出现常见格式的密钥，已暂存、未提交的改动也在其内；
//   - 发现即报出文件、行号和规则名，不回显密钥本身。
// 必须在 Git 仓库里运行。零依赖（Node 18 或更高）。
// 用法：
//   node scripts/security/check-secrets.mjs [--root <dir>]

import { spawnSync } from 'node:child_process';
import { readFileSync, statSync } from 'node:fs';
import { basename, join } from 'node:path';

const ENV_FILE = '.env';
const ENV_EXAMPLE = '.env.example';
const MAX_BYTES = 5 * 1024 * 1024;
const MAX_REPORTS = 50;

// [规则名, 匹配常见密钥格式的正则]。新增规则时确认它不会匹配自己的源码或占位值。
const RULES = [
  ['openai-key', /\bsk-(?:proj-|ant-|or-v1-)?[A-Za-z0-9_-]{20,}/g],
  ['github-token', /\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b/g],
  ['aws-access-key', /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g],
  ['google-api-key', /\bAIza[0-9A-Za-z_-]{35}\b/g],
  ['slack-token', /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g],
  ['stripe-key', /\b[sr]k_live_[0-9A-Za-z]{16,}\b/g],
  ['private-key', /-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY(?: BLOCK)?-----/g],
  [
    // 赋值形式的密钥。关键字前面不放 \b：MY_TOKEN、API_SECRET 这类下划线命名里没有词边界。
    'assigned-secret',
    /(?:api[_-]?key|secret|token|password|passwd)["']?\s*[:=]\s*["'][A-Za-z0-9_+/=-]{24,}["']/gi,
  ],
];

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

function git(root, gitArgs) {
  return spawnSync('git', ['-C', root, ...gitArgs], { encoding: 'utf8' });
}

function readText(file) {
  // 已删除但仍在索引里的文件、二进制文件和过大的文件不扫。
  let stat;
  try {
    stat = statSync(file);
  } catch {
    return null;
  }
  if (!stat.isFile() || stat.size > MAX_BYTES) return null;
  const buffer = readFileSync(file);
  if (buffer.subarray(0, 8192).includes(0)) return null;
  return buffer.toString('utf8');
}

function scan(rel, text, violations) {
  for (const [rule, pattern] of RULES) {
    pattern.lastIndex = 0;
    for (let match = pattern.exec(text); match !== null; match = pattern.exec(text)) {
      const line = text.slice(0, match.index).split('\n').length;
      violations.push(`${rel}:${line}：发现疑似密钥（规则 ${rule}）`);
      if (violations.length >= MAX_REPORTS) return;
    }
  }
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('用法：node scripts/security/check-secrets.mjs [--root <dir>]');
    process.exit(0);
  }
  const root = args.root;
  if (git(root, ['rev-parse', '--show-toplevel']).status !== 0) {
    console.error(`不是 Git 仓库，无法判断哪些文件被跟踪：${root}`);
    process.exit(2);
  }

  const violations = [];
  // --no-index：只按忽略规则判断，一个已被跟踪的 .env 仍然算"没有被忽略"。
  const ignored = git(root, ['check-ignore', '--quiet', '--no-index', '--', ENV_FILE]);
  if (ignored.status === 0) {
    // 已被忽略，符合要求。
  } else if (ignored.status === 1) {
    violations.push(`${ENV_FILE} 没有被 Git 忽略：在 .gitignore 里加入一行 ${ENV_FILE}`);
  } else {
    console.error(`git check-ignore 执行失败：${ignored.stderr.trim()}`);
    process.exit(2);
  }

  const listed = git(root, ['ls-files', '-z', '--cached']);
  if (listed.status !== 0) {
    console.error(`git ls-files 执行失败：${listed.stderr.trim()}`);
    process.exit(2);
  }
  const tracked = listed.stdout.split('\0').filter(Boolean);

  let scanned = 0;
  for (const rel of tracked) {
    const name = basename(rel);
    if (name === ENV_FILE || (name.startsWith('.env.') && name !== ENV_EXAMPLE)) {
      violations.push(`${rel}：密钥文件被 Git 跟踪，用 git rm --cached 移出`);
      continue;
    }
    const text = readText(join(root, rel));
    if (text === null) continue;
    scanned++;
    scan(rel, text, violations);
    if (violations.length >= MAX_REPORTS) break;
  }

  console.log(`检查了 ${scanned} 个已跟踪文件，并核对了 ${ENV_FILE} 的忽略与跟踪状态。`);
  if (violations.length > 0) {
    console.error(`\n密钥守卫违规 ${violations.length} 处（这里不回显密钥本身）：`);
    for (const violation of violations) console.error(`  ✗ ${violation}`);
    process.exit(1);
  }
  console.log('密钥守卫通过。');
}

try {
  main();
} catch (err) {
  console.error(`密钥守卫执行失败：${err.message}`);
  process.exit(2);
}
