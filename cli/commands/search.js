const { execSync } = require('child_process');
const path = require('path');
const chalk = require('chalk');
const ora = require('ora');

module.exports = async function search(query, options) {
  console.log(chalk.blue.bold('\n🔍 Memory Search\n'));
  console.log(chalk.gray(`Query: "${query}"\n`));

  const spinner = ora('Searching...').start();

  try {
    const scriptDir = path.join(__dirname, '..', '..', 'scripts');
    const searchScript = path.join(scriptDir, 'l4_hybrid.bat');

    // Determine scope
    let scope = 'all';
    if (options.global) scope = 'global';
    if (options.project) scope = 'project';

    const limit = parseInt(options.limit) || 10;

    // Execute search
    let command;
    if (process.platform === 'win32') {
      command = `"${searchScript}" "${query}" ${limit}`;
    } else {
      const searchScriptSh = path.join(scriptDir, 'l4_hybrid.sh');
      command = `bash "${searchScriptSh}" "${query}" ${limit}`;
    }

    const result = execSync(command, {
      cwd: scriptDir,
      encoding: 'utf-8',
      maxBuffer: 10 * 1024 * 1024
    });

    spinner.succeed('Search complete');

    // Parse and display results
    console.log(chalk.white('\nResults:\n'));

    const lines = result.split('\n');
    let resultCount = 0;

    for (const line of lines) {
      if (line.includes('===')) {
        console.log(chalk.blue(line));
      } else if (line.includes('Score:')) {
        console.log(chalk.green(line));
        resultCount++;
      } else if (line.trim()) {
        console.log(chalk.gray(line));
      }
    }

    if (resultCount === 0) {
      console.log(chalk.yellow('No results found'));
      console.log(chalk.gray('\nTry:'));
      console.log(chalk.gray('  - Using different keywords'));
      console.log(chalk.gray('  - Checking spelling'));
      console.log(chalk.gray('  - Searching in different scope (--global or --project)\n'));
    } else {
      console.log(chalk.green(`\n✅ Found ${resultCount} result(s)\n`));
    }

  } catch (error) {
    spinner.fail('Search failed');
    console.error(chalk.red('\n❌ Error:'), error.message);

    if (error.message.includes('not found')) {
      console.log(chalk.yellow('\nMake sure the memory system is initialized:'));
      console.log(chalk.cyan('  claude-memory-cli init\n'));
    }

    process.exit(1);
  }
};
