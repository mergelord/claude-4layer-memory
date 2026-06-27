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
  .option(
    '--project-name <name>',
    'Override project name (defaults to basename of current directory; only used with --project)'
  )
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

program
  .command('doctor')
  .description('Run health/readiness checks (FTS5, semantic, routing, costs)')
  .option('--json', 'Output the raw JSON health payload')
  .option('--no-semantic', 'Skip the semantic (ChromaDB) probe')
  .action(require('./commands/doctor'));

program
  .command('selftest')
  .description('Run local self-test: health checks + a search smoke test')
  .option('--no-semantic', 'Skip the semantic (ChromaDB) probe')
  .action(require('./commands/selftest'));

program
  .command('release-gate')
  .description('Run production release-gate checks')
  .option('--quick', 'Run a fast gate: guardrails, selftest, doctor, encoding scan')
  .option('--no-semantic', 'Skip semantic/Chroma probes in selftest and doctor')
  .option('--skip-tests', 'Skip pytest checks')
  .option('--skip-static', 'Skip static quality checks')
  .action(require('./commands/release-gate'));

program.parse(process.argv);

if (!process.argv.slice(2).length) {
  program.outputHelp();
}
