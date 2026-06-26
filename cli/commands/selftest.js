const { execFileSync } = require('child_process');
const path = require('path');
const chalk = require('chalk');
const ora = require('ora');

const PYTHON_BIN =
  process.env.PYTHON_BIN ||
  (process.platform === 'win32' ? 'python' : 'python3');

function runHealthCheck(repoRoot, includeSemantic) {
  const script = path.join(repoRoot, 'scripts', 'health_check.py');
  const args = [script, '--json'];
  if (!includeSemantic) {
    args.push('--no-semantic');
  }
  const raw = execFileSync(PYTHON_BIN, args, {
    cwd: repoRoot,
    encoding: 'utf-8',
    maxBuffer: 10 * 1024 * 1024,
  });
  return JSON.parse(raw);
}

function runFtsSmoke(repoRoot) {
  const code = [
    'import sys',
    'sys.path.insert(0, "scripts")',
    'from l4_fts5_search import L4FTS5Search',
    'res = L4FTS5Search().search("selftest", 1)',
    'print("FTS_OK", 0 if res is None else len(res))',
  ].join('; ');
  const raw = execFileSync(PYTHON_BIN, ['-c', code], {
    cwd: repoRoot,
    encoding: 'utf-8',
    maxBuffer: 10 * 1024 * 1024,
  });
  return raw.includes('FTS_OK');
}

module.exports = async function selftest(options) {
  const opts = options || {};
  const includeSemantic = opts.semantic !== false;
  const repoRoot = path.join(__dirname, '..', '..');

  console.log(chalk.blue.bold('\n\uD83E\uDDEA Memory Self-Test\n'));

  const checks = [];

  const healthSpinner = ora('Running health checks...').start();
  try {
    const health = runHealthCheck(repoRoot, includeSemantic);
    healthSpinner.stop();
    checks.push({
      name: 'Health check (status=' + (health.status || 'unknown') + ')',
      ok: health.status !== 'down',
    });
  } catch (error) {
    healthSpinner.stop();
    checks.push({ name: 'Health check (' + error.message + ')', ok: false });
  }

  const ftsSpinner = ora('Running FTS5 search smoke test...').start();
  try {
    const ok = runFtsSmoke(repoRoot);
    ftsSpinner.stop();
    checks.push({ name: 'FTS5 search smoke test', ok });
  } catch (error) {
    ftsSpinner.stop();
    checks.push({
      name: 'FTS5 search smoke test (' + error.message + ')',
      ok: false,
    });
  }

  let allOk = true;
  checks.forEach((check) => {
    if (check.ok) {
      console.log(chalk.green('\u2713 ') + check.name);
    } else {
      allOk = false;
      console.log(chalk.red('\u2717 ') + check.name);
    }
  });
  console.log();

  if (!allOk) {
    console.log(chalk.red.bold('Self-test FAILED\n'));
    process.exit(1);
  }
  console.log(chalk.green.bold('Self-test PASSED\n'));
};
