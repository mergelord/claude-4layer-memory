const fs = require('fs');
const path = require('path');
const chalk = require('chalk');
const ora = require('ora');

module.exports = async function stats() {
  console.log(chalk.blue.bold('\n📊 Memory Statistics\n'));

  const spinner = ora('Analyzing memory...').start();

  try {
    const homeDir = process.env.HOME || process.env.USERPROFILE;
    const memoryDir = path.join(homeDir, '.claude', 'memory');

    if (!fs.existsSync(memoryDir)) {
      spinner.fail('Memory directory not found');
      console.log(chalk.yellow('\nRun: claude-memory-cli init\n'));
      process.exit(1);
    }

    // Count files by type
    const files = fs.readdirSync(memoryDir).filter(f => f.endsWith('.md'));

    const stats = {
      total: 0,
      user: 0,
      feedback: 0,
      project: 0,
      reference: 0,
      other: 0,
      totalSize: 0
    };

    for (const file of files) {
      if (file === 'MEMORY.md') continue;

      const filepath = path.join(memoryDir, file);
      const content = fs.readFileSync(filepath, 'utf-8');
      const fileStats = fs.statSync(filepath);

      stats.total++;
      stats.totalSize += fileStats.size;

      // Detect type from filename or frontmatter
      if (file.startsWith('user_')) {
        stats.user++;
      } else if (file.startsWith('feedback_')) {
        stats.feedback++;
      } else if (file.startsWith('project_')) {
        stats.project++;
      } else if (file.startsWith('reference_')) {
        stats.reference++;
      } else {
        stats.other++;
      }
    }

    spinner.succeed('Analysis complete');

    // Display stats
    console.log(chalk.white('\n📁 Memory Files:\n'));
    console.log(chalk.cyan(`  Total:     ${stats.total} files`));
    console.log(chalk.gray(`  User:      ${stats.user}`));
    console.log(chalk.gray(`  Feedback:  ${stats.feedback}`));
    console.log(chalk.gray(`  Project:   ${stats.project}`));
    console.log(chalk.gray(`  Reference: ${stats.reference}`));
    if (stats.other > 0) {
      console.log(chalk.gray(`  Other:     ${stats.other}`));
    }

    // Size stats
    const sizeMB = (stats.totalSize / 1024 / 1024).toFixed(2);
    const sizeKB = (stats.totalSize / 1024).toFixed(2);
    const sizeDisplay = stats.totalSize > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`;

    console.log(chalk.white('\n💾 Storage:\n'));
    console.log(chalk.cyan(`  Total size: ${sizeDisplay}`));
    console.log(chalk.gray(`  Location:   ${memoryDir}`));

    // Check for semantic index
    const chromaDir = path.join(homeDir, '.claude', 'chroma_db');
    if (fs.existsSync(chromaDir)) {
      const chromaStats = fs.statSync(chromaDir);
      const chromaSizeMB = (getDirectorySize(chromaDir) / 1024 / 1024).toFixed(2);
      console.log(chalk.white('\n🔍 Semantic Index:\n'));
      console.log(chalk.green(`  ✅ ChromaDB initialized`));
      console.log(chalk.gray(`  Size: ${chromaSizeMB} MB`));
    } else {
      console.log(chalk.white('\n🔍 Semantic Index:\n'));
      console.log(chalk.yellow(`  ⚠️  Not initialized`));
      console.log(chalk.gray(`  Run: python scripts/l4_semantic_global.py index-global`));
    }

    // Check for FTS5 index
    const fts5DbPath = path.join(homeDir, '.claude', 'memory_fts5.db');
    if (fs.existsSync(fts5DbPath)) {
      const fts5Stats = fs.statSync(fts5DbPath);
      const fts5SizeKB = (fts5Stats.size / 1024).toFixed(2);
      console.log(chalk.white('\n⚡ FTS5 Index:\n'));
      console.log(chalk.green(`  ✅ Initialized`));
      console.log(chalk.gray(`  Size: ${fts5SizeKB} KB`));
    } else {
      console.log(chalk.white('\n⚡ FTS5 Index:\n'));
      console.log(chalk.yellow(`  ⚠️  Not initialized`));
      console.log(chalk.gray(`  Run: python scripts/l4_search.bat init`));
    }

    console.log('');

  } catch (error) {
    spinner.fail('Analysis failed');
    console.error(chalk.red('\n❌ Error:'), error.message);
    process.exit(1);
  }
};

// Helper function to calculate directory size
function getDirectorySize(dirPath) {
  let totalSize = 0;

  function traverse(currentPath) {
    const files = fs.readdirSync(currentPath);
    for (const file of files) {
      const filepath = path.join(currentPath, file);
      const stats = fs.statSync(filepath);
      if (stats.isDirectory()) {
        traverse(filepath);
      } else {
        totalSize += stats.size;
      }
    }
  }

  traverse(dirPath);
  return totalSize;
}
