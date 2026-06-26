const { execFileSync } = require('child_process');
const path = require('path');
const chalk = require('chalk');
const ora = require('ora');

const PYTHON_BIN =
  process.env.PYTHON_BIN ||
  (process.platform === 'win32' ? 'python' : 'python3');

function printHealth(health) {
  const status = String(health.status || 'unknown').toUpperCase();
  const statusColor =
    health.status === 'ok'
      ? chalk.green
      : health.status === 'degraded'
      ? chalk.yellow
      : chalk.red;

  console.log(statusColor.bold(`\nStatus: ${status}`));
  console.log(chalk.gray(`Version: ${health.version}\n`));

  const fts = health.fts || {};
  if (fts.ok) {
    console.log(
      chalk.green('\u2713 FTS5 index') +
        chalk.gray(
          `  docs=${fts.total_documents} size_kb=${fts.db_size_kb} exists=${fts.db_exists}`
        )
    );
  } else {
    console.log(chalk.red('\u2717 FTS5 index') + chalk.gray(`  ${fts.error || ''}`));
  }

  if (health.semantic) {
    const s = health.semantic;
    if (s.ok) {
      console.log(
        chalk.green('\u2713 Semantic backend') +
          chalk.gray(
            `  reachable=${s.chroma_reachable} model_cached=${s.model_cached}`
          )
      );
    } else {
      console.log(
        chalk.red('\u2717 Semantic backend') + chalk.gray(`  ${s.error || ''}`)
      );
    }
  }

  const routing = health.routing || {};
  if (routing.ok) {
    console.log(
      chalk.green('\u2713 Routing learner') +
        chalk.gray(`  history=${routing.history_count} phase=${routing.phase}`)
    );
  } else {
    console.log(
      chalk.red('\u2717 Routing learner') + chalk.gray(`  ${routing.error || ''}`)
    );
  }

  const costs = health.costs || {};
  if (costs.ok) {
    console.log(
      chalk.green('\u2713 Cost ledger') +
        chalk.gray(
          `  today=$${costs.spend_today_usd} 7d=$${costs.spend_7d_usd}`
        )
    );
  } else {
    console.log(
      chalk.red('\u2717 Cost ledger') + chalk.gray(`  ${costs.error || ''}`)
    );
  }

  const system = health.system || {};
  console.log(
    chalk.cyan('\u2022 System') +
      chalk.gray(
        `  python=${system.python_version} free_disk_gb=${system.free_disk_gb}`
      )
  );
  console.log();
}

module.exports = async function doctor(options) {
  const opts = options || {};

  console.log(chalk.blue.bold('\n\uD83E\uDE7A Memory Doctor\n'));

  const spinner = ora('Running health checks...').start();

  try {
    const repoRoot = path.join(__dirname, '..', '..');
    const script = path.join(repoRoot, 'scripts', 'health_check.py');

    const args = [script, '--json'];
    if (opts.semantic === false) {
      args.push('--no-semantic');
    }

    const raw = execFileSync(PYTHON_BIN, args, {
      cwd: repoRoot,
      encoding: 'utf-8',
      maxBuffer: 10 * 1024 * 1024,
    });

    spinner.succeed('Health check complete');

    if (opts.json) {
      console.log(raw.trim());
      return;
    }

    let health;
    try {
      health = JSON.parse(raw);
    } catch (parseErr) {
      console.log(raw);
      return;
    }

    printHealth(health);

    if (health.status === 'down') {
      process.exitCode = 1;
    }
  } catch (error) {
    spinner.fail('Health check failed');
    console.error(chalk.red('\nError:'), error.message);

    const msg = String(error.message || '');
    if (
      msg.includes('ENOENT') ||
      msg.toLowerCase().includes('not found') ||
      msg.includes('No such file')
    ) {
      console.log(
        chalk.yellow('\nMake sure Python and the memory system are set up:')
      );
      console.log(
        chalk.cyan('  - Python 3.10+ on PATH (or set PYTHON_BIN env var)')
      );
      console.log(chalk.cyan('  - claude-memory-cli init\n'));
    }

    process.exit(1);
  }
};
