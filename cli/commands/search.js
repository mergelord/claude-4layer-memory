const { execFileSync } = require('child_process');
const path = require('path');
const chalk = require('chalk');
const ora = require('ora');

const PYTHON_BIN =
  process.env.PYTHON_BIN ||
  (process.platform === 'win32' ? 'python' : 'python3');

module.exports = async function search(query, options) {
  const opts = options || {};

  console.log(chalk.blue.bold('\n🔍 Memory Search\n'));
  console.log(chalk.gray(`Query: "${query}"\n`));

  const spinner = ora('Searching...').start();

  try {
    const repoRoot = path.join(__dirname, '..', '..');
    const scriptDir = path.join(repoRoot, 'scripts');

    let pyScript;
    let pyArgs;

    if (opts.global) {
      pyScript = path.join(scriptDir, 'l4_semantic_global.py');
      pyArgs = ['search-global', query];
    } else if (opts.project) {
      const projectName = path.basename(process.cwd());
      pyScript = path.join(scriptDir, 'l4_semantic_global.py');
      pyArgs = ['search-project', projectName, query];
    } else {
      // Default scope: hybrid (FTS5 keyword + semantic)
      pyScript = path.join(scriptDir, 'l4_fts5_search.py');
      pyArgs = ['hybrid', query];
    }

    const result = execFileSync(PYTHON_BIN, [pyScript, ...pyArgs], {
      cwd: repoRoot,
      encoding: 'utf-8',
      maxBuffer: 10 * 1024 * 1024
    });

    spinner.succeed('Search complete');

    console.log(chalk.white('\nResults:\n'));

    const lines = result.split('\n');
    let resultCount = 0;
    const resultLineRe = /^\[\d+\]/;
    const headerRe = /^\[(SEARCH|FTS5|SEMANTIC|HYBRID|RESULTS)/i;

    for (const line of lines) {
      if (headerRe.test(line)) {
        console.log(chalk.blue.bold(line));
      } else if (resultLineRe.test(line)) {
        console.log(chalk.green(line));
        resultCount++;
      } else if (line.trim()) {
        console.log(chalk.gray(line));
      } else {
        console.log();
      }
    }

    if (resultCount === 0) {
      console.log(chalk.yellow('\nNo results found'));
      console.log(chalk.gray('\nTry:'));
      console.log(chalk.gray('  - Using different keywords'));
      console.log(chalk.gray('  - Checking spelling'));
      console.log(
        chalk.gray(
          '  - Searching in a different scope (--global or --project)'
        )
      );
      console.log();
    } else {
      console.log(chalk.green(`\nFound ${resultCount} result(s)\n`));
    }
  } catch (error) {
    spinner.fail('Search failed');
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
        chalk.cyan(
          '  - Python 3.10+ on PATH (or set PYTHON_BIN env var)'
        )
      );
      console.log(chalk.cyan('  - claude-memory-cli init\n'));
    }

    process.exit(1);
  }
};
