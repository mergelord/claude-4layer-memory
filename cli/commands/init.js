const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const chalk = require('chalk');
const ora = require('ora');

module.exports = async function init() {
  console.log(chalk.blue.bold('\n🚀 Claude 4-Layer Memory System - Initialization\n'));

  const spinner = ora('Checking environment...').start();

  try {
    // Check if Python is available
    try {
      execSync('python --version', { stdio: 'pipe' });
      spinner.succeed('Python detected');
    } catch (error) {
      spinner.fail('Python not found');
      console.log(chalk.red('\n❌ Python 3.10+ is required'));
      console.log(chalk.yellow('Install from: https://www.python.org/downloads/\n'));
      process.exit(1);
    }

    // Check if we're in a git repository
    const isGitRepo = fs.existsSync('.git');
    if (isGitRepo) {
      spinner.succeed('Git repository detected');
    } else {
      spinner.warn('Not a git repository (optional)');
    }

    // Determine installation path
    const homeDir = process.env.HOME || process.env.USERPROFILE;
    const claudeDir = path.join(homeDir, '.claude');
    const memoryDir = path.join(claudeDir, 'memory');

    spinner.text = 'Creating memory directories...';

    // Create directories
    if (!fs.existsSync(claudeDir)) {
      fs.mkdirSync(claudeDir, { recursive: true });
    }
    if (!fs.existsSync(memoryDir)) {
      fs.mkdirSync(memoryDir, { recursive: true });
    }

    spinner.succeed('Memory directories created');

    // Install Python dependencies
    spinner.text = 'Installing Python dependencies...';

    const scriptDir = path.join(__dirname, '..', '..', 'scripts');
    const requirementsPath = path.join(scriptDir, 'requirements.txt');

    if (fs.existsSync(requirementsPath)) {
      try {
        execSync(`python -m pip install -r "${requirementsPath}"`, {
          stdio: 'pipe',
          cwd: scriptDir
        });
        spinner.succeed('Python dependencies installed');
      } catch (error) {
        spinner.warn('Some dependencies failed to install');
        console.log(chalk.yellow('\nYou may need to install manually:'));
        console.log(chalk.gray(`  pip install -r ${requirementsPath}\n`));
      }
    } else {
      spinner.warn('requirements.txt not found');
    }

    // Create initial MEMORY.md if it doesn't exist
    const memoryIndexPath = path.join(memoryDir, 'MEMORY.md');
    if (!fs.existsSync(memoryIndexPath)) {
      const initialContent = `# Global Memory Index

Глобальная память - знания применимые ко всем проектам.

**Последнее обновление:** ${new Date().toISOString().split('T')[0]}

---

## User
- [User Profile](user_profile.md) — Your profile and preferences

## Feedback
- [Development Style](feedback_development_style.md) — General development approach

## Project
- [Active Projects](project_overview.md) — List of active projects

## Reference
- [Useful Resources](reference_resources.md) — External resources and links

---

**Принцип разделения:**
- **Глобальная память** - применимо к любому проекту
- **Проектная память** - специфика конкретного проекта
`;
      fs.writeFileSync(memoryIndexPath, initialContent, 'utf-8');
      spinner.succeed('Created initial MEMORY.md');
    } else {
      spinner.info('MEMORY.md already exists');
    }

    // Success message
    console.log(chalk.green.bold('\n✅ Initialization complete!\n'));
    console.log(chalk.white('Next steps:'));
    console.log(chalk.gray('  1. Run') + chalk.cyan(' claude-memory-cli search "your query"') + chalk.gray(' to test search'));
    console.log(chalk.gray('  2. Run') + chalk.cyan(' claude-memory-cli lint') + chalk.gray(' to validate memory'));
    console.log(chalk.gray('  3. Run') + chalk.cyan(' claude-memory-cli stats') + chalk.gray(' to see statistics\n'));

    console.log(chalk.white('Memory location:'));
    console.log(chalk.gray(`  ${memoryDir}\n`));

  } catch (error) {
    spinner.fail('Initialization failed');
    console.error(chalk.red('\n❌ Error:'), error.message);
    process.exit(1);
  }
};
