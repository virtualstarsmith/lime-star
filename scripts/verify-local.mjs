#!/usr/bin/env node
// 默认本地门禁编排器：按本轮改动的路径匹配任务表，只跑受影响的门禁，fail-fast。
// 与 lime 的 verify:local 同构：
//   - 增量模式（默认）：改动集 = 工作树 diff（含暂存）+ 相对上游 merge-base 的已提交改动 + untracked 文件；
//   - --full：跑全部任务；
//   - --dry-run：只打印将被选中的任务，不执行；
//   - --only a,b：只跑指定任务；
//   - 直接传路径：离线模式，把给定路径当作改动集。
// 不是 git 仓库时回退为"改动集未知 → 运行全部任务"，宁可多跑不可漏跑。
// 用法：
//   node scripts/verify-local.mjs [--full] [--dry-run] [--only <name1,name2>] [paths...]

import { execFileSync, spawnSync } from 'node:child_process';

// 任务表：prefixes 为空数组 = 任何时候都跑；
// 否则是 POSIX 风格路径前缀（相对仓库根）。Python 任务自路线图 P0 起接入。
const TASKS = [
  {
    name: 'file-size-governance',
    prefixes: [], // 行数棘轮全量扫描，任何改动都跑
    cmd: 'node scripts/check-file-size-governance.mjs',
  },
  {
    name: 'scripts-baseline',
    prefixes: ['scripts/'],
    cmd: 'node scripts/check-scripts-baseline.mjs',
  },
  {
    // 密钥可能出现在任何文件里，所以恒跑（路线图 P1 接入）。
    name: 'secrets',
    prefixes: [],
    cmd: 'node scripts/security/check-secrets.mjs',
  },
  {
    name: 'contracts',
    prefixes: ['protocol/', 'src/lime_star/protocol/', 'governance/'],
    cmd: 'node scripts/check-contracts.mjs',
  },
  {
    name: 'doc-links',
    prefixes: ['internal/', 'AGENTS.md', 'README.md', '.codex/'],
    cmd: 'node scripts/check-doc-links.mjs',
  },
  // Python 任务（路线图 P0 接入），命令直接调用 uv，首次运行前需要 uv sync。
  // lock 必须排在其余 Python 任务之前：uv run 遇到过期的锁文件会自动重写它，
  // 排在后面就查不出"提交的锁文件已经过期"。
  {
    name: 'lock',
    prefixes: ['pyproject.toml'],
    cmd: 'uv lock --check',
  },
  // 冒烟脚本是 Python（路线图 P5 起纳入检查范围，技术债 CCD-005）：改 scripts/smoke/ 也要过 lint 和 typecheck。
  {
    name: 'lint',
    prefixes: ['src/', 'tests/', 'scripts/smoke/', 'scripts/harness/'],
    cmd: 'uv run ruff check . && uv run ruff format --check .',
  },
  {
    name: 'typecheck',
    prefixes: ['src/', 'tests/', 'scripts/smoke/', 'scripts/harness/'],
    cmd: 'uv run mypy',
  },
  {
    name: 'test:unit',
    prefixes: ['src/', 'tests/', 'pyproject.toml', 'uv.lock'],
    cmd: 'uv run pytest -q',
  },
  // Gate B 冒烟（路线图 P4 接入）：在真实进程里跑 MVP 主场景，断言对着会话记录和磁盘。
  // 模型为回放夹具，不联网，也不需要密钥。产品代码、冒烟脚本、驱动它的测试工具或夹具变动时才需要重跑。
  {
    name: 'smoke:gate-b',
    prefixes: ['src/lime_star/', 'scripts/smoke/', 'tests/integration/', 'tests/fixtures/provider/'],
    cmd: 'uv run python scripts/smoke/agent_gate_b.py',
  },
  // Harness 反馈层（路线图 P6 接入）：证据、样本和评测的定向入口集成测试。
  {
    name: 'test:harness',
    prefixes: ['scripts/harness/', 'tests/integration/test_harness.py', 'internal/test/', 'tests/fixtures/harness/'],
    cmd: 'uv run pytest tests/integration/test_harness.py -q',
  },
  // 固定任务集摘要（路线图 P6 接入）：manifest 与样本变化时重跑 runner。
  {
    name: 'harness:eval',
    prefixes: ['scripts/harness/', 'internal/test/', 'tests/fixtures/harness/'],
    cmd: 'uv run python scripts/harness/eval_runner.py',
  },
  // 恢复的 Gate B 冒烟（路线图 P5 接入）：真实的 lime-star 进程在批准提示处被强制结束，
  // 新进程带 --resume 恢复。同样默认回放夹具，不联网，不需要密钥。
  {
    name: 'smoke:resume',
    prefixes: ['src/lime_star/', 'scripts/smoke/', 'tests/integration/', 'tests/fixtures/provider/'],
    cmd: 'uv run python scripts/smoke/resume_gate_b.py',
  },
  // 治理脚本的回归用例（路线图 P1 接入）：改了 scripts/ 就要验证脚本的行为，不只是查格式。
  {
    name: 'test:guards',
    prefixes: ['scripts/', 'tests/integration/test_guard_'],
    cmd: 'uv run pytest tests/integration -q -k test_guard_',
  },
  // 架构守卫（路线图 P2 接入，技术债 CCD-002、CCD-003）：依赖方向与 Owner 章节的确认块。
  // 它检查仓库自身，不启动进程；产品代码、架构图或守卫本身变动时才需要重跑。
  {
    name: 'architecture',
    prefixes: ['src/lime_star/', 'internal/aiprompts/architecture.md', 'tests/integration/test_guard_architecture.py'],
    cmd: 'uv run pytest tests/integration/test_guard_architecture.py -q',
  },
];

function parseArgs(argv) {
  const args = { full: false, dryRun: false, only: null, paths: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--full') args.full = true;
    else if (a === '--dry-run') args.dryRun = true;
    else if (a === '--only') args.only = argv[++i].split(',').map((s) => s.trim());
    else if (a === '--help' || a === '-h') args.help = true;
    else args.paths.push(a);
  }
  return args;
}

function gitOut(repoArgs) {
  try {
    return execFileSync('git', repoArgs, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  } catch {
    return null;
  }
}

function collectChangedPaths() {
  const isRepo = gitOut(['rev-parse', '--is-inside-work-tree'])?.trim() === 'true';
  if (!isRepo) return { paths: null, note: '当前目录不是 git 仓库，按"改动集未知"处理。' };
  const changed = new Set();
  const add = (out) => {
    for (const line of (out ?? '').split(/\r?\n/)) {
      const p = line.trim();
      if (p) changed.add(p.split('\\').join('/'));
    }
  };
  add(gitOut(['diff', '--name-only', 'HEAD'])); // 工作树 + 暂存区
  const upstream = gitOut(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}']);
  if (upstream) {
    const base = gitOut(['merge-base', 'HEAD', upstream.trim()]);
    if (base) add(gitOut(['diff', '--name-only', `${base.trim()}..HEAD`])); // 已提交未推送
  }
  add(gitOut(['ls-files', '--others', '--exclude-standard'])); // untracked
  return { paths: [...changed], note: null };
}

function selectTasks(tasks, changedPaths, args) {
  if (args.only) {
    const wanted = new Set(args.only);
    return tasks.filter((t) => wanted.has(t.name));
  }
  if (args.full || changedPaths === null) return [...tasks];
  return tasks.filter((t) => {
    if ((t.prefixes?.length ?? 0) === 0) return true; // 空前缀 = 始终运行
    return changedPaths.some((p) => t.prefixes.some((pre) => p === pre || p.startsWith(pre) || p.startsWith(pre.split('/').join('\\'))));
  });
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('用法：node scripts/verify-local.mjs [--full] [--dry-run] [--only <name1,name2>] [paths...]');
    process.exit(0);
  }

  const { paths: changedPaths, note } = args.paths.length > 0
    ? { paths: args.paths.map((p) => p.split('\\').join('/')), note: null }
    : collectChangedPaths();
  if (note) console.warn(`⚠ ${note}`);

  const selected = selectTasks(TASKS, changedPaths, args);
  console.log(`改动文件 ${changedPaths === null ? '未知' : changedPaths.length} 个，选中任务 ${selected.length} 个：`);
  for (const t of selected) console.log(`  - ${t.name}`);
  if (args.dryRun) {
    console.log('（dry-run：不执行）');
    process.exit(0);
  }
  if (selected.length === 0) {
    console.log('无匹配任务，门禁直接通过。');
    process.exit(0);
  }

  let failed = null;
  for (const t of selected) {
    console.log(`\n▶ ${t.name}\n$ ${t.cmd}`);
    const r = spawnSync(t.cmd, {
      shell: true,
      stdio: 'inherit',
      cwd: process.cwd(),
    });
    if (r.status !== 0) {
      failed = t;
      break;
    }
  }

  if (failed) {
    console.error(`\n✗ 本地门禁在任务「${failed.name}」失败，后续任务未执行（fail-fast）。`);
    process.exit(1);
  }
  console.log(`\n✓ 本地门禁通过（${selected.length} 个任务）。`);
}

main();
