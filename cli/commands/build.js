const fs = require('fs');
const path = require('path');
const chalk = require('chalk');
const inquirer = require('inquirer');
const ora = require('ora');

module.exports = async function build(options) {
  console.log(chalk.blue.bold('\n📝 Memory Builder\n'));

  try {
    // Determine memory directory
    const homeDir = process.env.HOME || process.env.USERPROFILE;
    const memoryDir = path.join(homeDir, '.claude', 'memory');

    if (!fs.existsSync(memoryDir)) {
      console.log(chalk.yellow('Memory directory not found. Run: claude-memory-cli init\n'));
      process.exit(1);
    }

    // Prompt for memory details if not provided
    let type = options.type;
    let name = options.name;

    if (!type) {
      const typeAnswer = await inquirer.prompt([
        {
          type: 'list',
          name: 'type',
          message: 'Memory type:',
          choices: [
            { name: 'User - Information about the user', value: 'user' },
            { name: 'Feedback - Guidance on how to work', value: 'feedback' },
            { name: 'Project - Ongoing work and goals', value: 'project' },
            { name: 'Reference - External resources', value: 'reference' }
          ]
        }
      ]);
      type = typeAnswer.type;
    }

    if (!name) {
      const nameAnswer = await inquirer.prompt([
        {
          type: 'input',
          name: 'name',
          message: 'Memory name (e.g., "testing_workflow"):',
          validate: (input) => {
            if (!input.trim()) return 'Name is required';
            if (!/^[a-z0-9_]+$/.test(input)) {
              return 'Name must be lowercase with underscores only';
            }
            return true;
          }
        }
      ]);
      name = nameAnswer.name;
    }

    const descAnswer = await inquirer.prompt([
      {
        type: 'input',
        name: 'description',
        message: 'One-line description:',
        validate: (input) => input.trim() ? true : 'Description is required'
      }
    ]);

    const contentAnswer = await inquirer.prompt([
      {
        type: 'editor',
        name: 'content',
        message: 'Memory content (opens editor):'
      }
    ]);

    // Build frontmatter
    const filename = `${type}_${name}.md`;
    const filepath = path.join(memoryDir, filename);

    const frontmatter = `---
name: ${name}
description: ${descAnswer.description}
type: ${type}
---

${contentAnswer.content}
`;

    // Write file
    const spinner = ora('Creating memory file...').start();
    fs.writeFileSync(filepath, frontmatter, 'utf-8');
    spinner.succeed('Memory file created');

    console.log(chalk.green(`\n✅ Created: ${filename}`));
    console.log(chalk.gray(`Location: ${filepath}`));

    // Update MEMORY.md index
    const memoryIndexPath = path.join(memoryDir, 'MEMORY.md');
    if (fs.existsSync(memoryIndexPath)) {
      const indexContent = fs.readFileSync(memoryIndexPath, 'utf-8');
      const newEntry = `- [${name}](${filename}) — ${descAnswer.description}`;

      if (!indexContent.includes(newEntry)) {
        const updatedIndex = indexContent + '\n' + newEntry;
        fs.writeFileSync(memoryIndexPath, updatedIndex, 'utf-8');
        console.log(chalk.green('✅ Updated MEMORY.md index\n'));
      }
    }

  } catch (error) {
    console.error(chalk.red('\n❌ Error:'), error.message);
    process.exit(1);
  }
};
