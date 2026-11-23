#!/usr/bin/env node
// 契约同步门禁（骨架）：配置、协议和依赖改动必须同步 schema、消费者、文档、锁文件与测试。
// 本脚本用"清单 + 哈希状态"强制一个显式同步动作：
//   - governance/contracts.json 声明每个协议 schema 及其必须同步的消费者（生成类型、fixture、文档等）；
//   - governance/contracts-state.json 记录每个 schema 的 sha256；
//   - schema 变更后若未重新登记哈希，门禁失败并列出需要同步的消费者；
//   - 同步完成后运行 --update 登记新哈希，表示"本轮同步已确认完成"。
// 说明：脚本无法语义级验证消费者内容是否真同步，它强制的是"过期即失败 + 显式确认"纪律。
//       项目可在此基础上扩展：对生成物做快照对比、对命令清单做枚举覆盖等。
// 用法：
//   node scripts/check-contracts.mjs [--root <dir>] [--manifest <file>] [--update]

import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { createHash } from 'node:crypto';

function parseArgs(argv) {
  const args = { root: process.cwd(), manifest: null, update: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--root') args.root = argv[++i];
    else if (a === '--manifest') args.manifest = argv[++i];
    else if (a === '--update') args.update = true;
    else if (a === '--help' || a === '-h') args.help = true;
    else {
      console.error(`未知参数：${a}`);
      process.exit(2);
    }
  }
  return args;
}

function sha256File(p) {
  return createHash('sha256').update(readFileSync(p)).digest('hex');
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('用法：node scripts/check-contracts.mjs [--root <dir>] [--manifest <file>] [--update]');
    process.exit(0);
  }
  const root = args.root;
  const manifestPath = args.manifest ?? join(root, 'governance', 'contracts.json');
  const statePath = join(root, 'governance', 'contracts-state.json');

  if (!existsSync(manifestPath)) {
    console.log('未配置契约清单（governance/contracts.json），跳过契约检查。');
    console.log('  i 接入方式见 scripts/README.md：为每个对外协议 schema 声明其消费者清单。');
    process.exit(0);
  }

  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  const contracts = manifest.contracts ?? [];
  if (contracts.length === 0) {
    console.log('契约清单为空，跳过契约检查。');
    process.exit(0);
  }

  const state = existsSync(statePath) ? JSON.parse(readFileSync(statePath, 'utf8')) : {};
  const hashes = state.hashes ?? {};

  const violations = [];
  const nextHashes = {};

  for (const c of contracts) {
    if (!c.id || !c.schema) {
      violations.push(`契约条目缺少 id 或 schema 字段：${JSON.stringify(c)}`);
      continue;
    }
    const schemaFull = join(root, c.schema);
    if (!existsSync(schemaFull)) {
      violations.push(`[${c.id}] schema 不存在：${c.schema}`);
      continue;
    }
    for (const consumer of c.consumers ?? []) {
      if (!existsSync(join(root, consumer))) {
        violations.push(`[${c.id}] 消费者缺失：${consumer}（schema ${c.schema} 已声明但未落地）`);
      }
    }
    const current = sha256File(schemaFull);
    nextHashes[c.id] = current;
    // --update = 显式确认当前 schema 状态（同步动作已完成），过期检查按确认后的状态进行
    if (!args.update && hashes[c.id] !== current) {
      const stale = hashes[c.id] ? 'schema 已变更但未登记同步' : 'schema 首次纳入但未登记';
      violations.push(
        `[${c.id}] ${stale}：请同步消费者 [${(c.consumers ?? []).join(', ') || '无'}] 与文档/测试，然后运行 --update 确认`,
      );
    }
  }

  if (args.update) {
    mkdirSync(dirname(statePath), { recursive: true });
    writeFileSync(statePath, `${JSON.stringify({ hashes: nextHashes }, null, 2)}\n`);
    console.log(`契约状态已更新：${statePath}（${Object.keys(nextHashes).length} 个 schema）`);
  }

  console.log(`契约 ${contracts.length} 项。`);
  if (violations.length > 0) {
    console.error(`\n契约门禁违规 ${violations.length} 处：`);
    for (const v of violations) console.error(`  ✗ ${v}`);
    process.exit(1);
  }
  console.log('契约同步检查通过。');
}

try {
  main();
} catch (err) {
  console.error(`契约门禁执行失败：${err.message}`);
  process.exit(2);
}
