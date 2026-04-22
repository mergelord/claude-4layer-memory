const { execSync } = require('child_process');
const path = require('path');
const chalk = require('chalk');
const ora = require('ora');

module.exports = async function lint(options) {
  console.log(chalk.blue.bold('\n🔍 Memory Lint\n'));

  const spinner = ora('Running validation...').start();

  try {
    const scriptDir = path.join(__dirname, '..', '..', 'scripts');
    const lintScript = path.join(scriptDir, 'memory_lint.py');

    // Build command
    let args = [];
    if (options.quick) {
      args.push('--quick');
      spinner.text = 'Running quick validation (Layer 1)...';
    } else if (options.checklist) {
      args.push('--checklist');
      spinner.text = 'Running pre-delivery checklist...';
    } else {
      args.push('--layer all');
      spinner.text = 'Running full validation (Layer 1 + 2)...';
    }

    const command = `python "${lintScript}" ${args.join(' ')}`;

    const result = execSync(command, {
      cwd: scriptDir,
      encoding: 'utf-8',
      maxBuffer: 10 * 1024 * 1024
    });

    spinner.stop();

    // Display results with colors
    const lines = result.split('\n');
    for (const line of lines) {
      if (line.includes('[OK]')) {
        console.log(chalk.green(line));
      } else if (line.includes('[ERROR]')) {
        console.log(chalk.red(line));
      } else if (line.includes('[WARN]')) {
        console.log(chalk.yellow(line));
      } else if (line.includes('[INFO]')) {
        console.log(chalk.blue(line));
      } else if (line.includes('===')) {
        console.log(chalk.blue.bold(line));
      } else if (line.includes('---')) {
        console.log(chalk.gray(line));
      } else {
        console.log(line);
      }
    }

    // Check exit status
    if (result.includes('[ERROR]') && result.includes('Fix issues')) {
      console.log(chalk.red('\n❌ Validation failed - fix issues before commit\n'));
      process.exit(1);
    } else if (result.includes('[OK]') && result.includes('Ready for commit')) {
      console.log(chalk.green('\n✅ All checks passed - ready for commit!\n'));
    }

  } catch (error) {
    spinner.fail('Validation failed');

    // Display error output
    if (error.stdout) {
      const lines = error.stdout.toString().split('\n');
      for (const line of lines) {
        if (line.includes('[ERROR]')) {
          console.log(chalk.red(line));
        } else if (line.includes('[WARN]')) {
          console.log(chalk.yellow(line));
        } else if (line.trim()) {
          console.log(line);
        }
      }
    }

    console.error(chalk.red('\n❌ Lint failed\n'));
    process.exit(1);
  }
};
