#!/usr/bin/env node

const { Command } = require('commander');
const chalk = require('chalk');
const packageJson = require('../package.json');

const program = new Command();

program
  .name('claude-memory-cli')
  .description('CLI tool for Claude 4-Layer Memory System')
  .version(packageJson.version);

program
  .command('init')
  .description('Initialize memory system in current directory')
  .action(require('./commands/init'));

program
  .command('search <query>')
  .description('Search memory using FTS5 + semantic search')
  .option('-g, --global', 'Search global memory only')
  .option('-p, --project', 'Search project memory only')
  .option('-l, --limit <number>', 'Limit results', '10')
  .action(require('./commands/search'));

program
  .command('lint')
  .description('Validate memory structure and content')
  .option('-q, --quick', 'Quick validation (Layer 1 only)')
  .option('-c, --checklist', 'Run pre-delivery checklist')
  .action(require('./commands/lint'));

program
  .command('build')
  .description('Create or update memory file')
  .option('-t, --type <type>', 'Memory type (user/feedback/project/reference)')
  .option('-n, --name <name>', 'Memory name')
  .action(require('./commands/build'));

program
  .command('stats')
  .description('Show memory statistics')
  .action(require('./commands/stats'));

program.parse(process.argv);

if (!process.argv.slice(2).length) {
  program.outputHelp();
}
