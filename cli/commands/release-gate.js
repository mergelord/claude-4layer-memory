const { spawnSync } = require('child_process');
const path = require('path');
const chalk = require('chalk');

const PYTHON_BIN =
  process.env.PYTHON_BIN ||
  (process.platform === 'win32' ? 'python' : 'python3');

function runStep(repoRoot, step) {
  console.log(chalk.blue('\n▶ ') + chalk.bold(step.name));
  console.log(chalk.gray('  ' + [step.command].concat(step.args).join(' ')));

  const result = spawnSync(step.command, step.args, {
    cwd: repoRoot,
    stdio: 'inherit',
    shell: false,
  });

  if (result.error) {
    console.log(chalk.red('✗ ') + step.name + chalk.gray(' (' + result.error.message + ')'));
    return false;
  }

  if (result.status !== 0) {
    console.log(chalk.red('✗ ') + step.name + chalk.gray(' (exit ' + result.status + ')'));
    return false;
  }

  console.log(chalk.green('✓ ') + step.name);
  return true;
}

function pylintArgs() {
  return [
    '-m',
    'pylint',
    'scripts/*.py',
    'audit.py',
    '--disable=C0114,C0115,C0116,R0913,R0914,R0915,R0903,R0904,W0718,R1702,C0415,R0902,R0912,R0801',
    '--max-line-length=110',
    '--good-names=i,j,k,e,f,_,rc',
  ];
}

function mypyArgs() {
  return [
    '-m',
    'mypy',
    'scripts/',
    'audit.py',
    '--explicit-package-bases',
    '--ignore-missing-imports',
    '--no-strict-optional',
    '--allow-untyped-defs',
    '--allow-incomplete-defs',
  ];
}

function buildSteps(repoRoot, options) {
  const opts = options || {};
  const quick = opts.quick === true;
  const includeSemantic = opts.semantic !== false;
  const cli = path.join(repoRoot, 'cli', 'index.js');
  const semanticFlag = includeSemantic ? [] : ['--no-semantic'];

  const steps = [];

  if (!opts.skipTests) {
    if (quick) {
      steps.push({
        name: 'Guardrail regression tests',
        command: PYTHON_BIN,
        args: [
          '-m',
          'pytest',
          'tests/test_p3_guardrails.py',
          'tests/test_mcp_e2e_smoke.py',
          'tests/test_soak.py',
          '-v',
          '--tb=short',
        ],
      });
    } else {
      steps.push({
        name: 'Full pytest suite',
        command: PYTHON_BIN,
        args: ['-m', 'pytest', 'tests/', '-v', '--tb=short'],
      });
    }
  }

  if (!opts.skipStatic && !quick) {
    steps.push(
      { name: 'Pylint', command: PYTHON_BIN, args: pylintArgs() },
      { name: 'MyPy', command: PYTHON_BIN, args: mypyArgs() },
      { name: 'Ruff', command: PYTHON_BIN, args: ['-m', 'ruff', 'check', 'scripts/*.py', 'audit.py'] },
      { name: 'Bandit', command: PYTHON_BIN, args: ['-m', 'bandit', '-r', 'scripts/', 'audit.py', '-l', '--skip', 'B404,B603'] },
      { name: 'Radon complexity', command: PYTHON_BIN, args: ['-m', 'radon', 'cc', 'scripts/*.py', 'audit.py', '-a', '-nb'] },
      { name: 'Radon maintainability', command: PYTHON_BIN, args: ['-m', 'radon', 'mi', 'scripts/*.py', 'audit.py', '-nb'] }
    );
  }

  steps.push(
    {
      name: 'EncodingGate repository scan',
      command: PYTHON_BIN,
      args: [path.join('scripts', 'scan_repo_encoding.py')],
    },
    {
      name: 'Operational selftest',
      command: process.execPath,
      args: [cli, 'selftest'].concat(semanticFlag),
    },
    {
      name: 'Operational doctor',
      command: process.execPath,
      args: [cli, 'doctor'].concat(semanticFlag),
    }
  );

  return steps;
}

module.exports = async function releaseGate(options) {
  const opts = options || {};
  const repoRoot = path.join(__dirname, '..', '..');
  const steps = buildSteps(repoRoot, opts);

  console.log(chalk.blue.bold('\n🚦 Production Release Gate\n'));
  console.log(chalk.gray('Mode: ' + (opts.quick ? 'quick' : 'full')));
  console.log(chalk.gray('Semantic probe: ' + (opts.semantic === false ? 'off' : 'on')));

  const failures = [];
  steps.forEach((step) => {
    if (!runStep(repoRoot, step)) {
      failures.push(step.name);
    }
  });

  console.log();
  if (failures.length > 0) {
    console.log(chalk.red.bold('Release gate FAILED'));
    failures.forEach((name) => console.log(chalk.red('  - ') + name));
    process.exit(1);
  }

  console.log(chalk.green.bold('Release gate PASSED'));
};
