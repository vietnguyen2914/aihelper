// ═══════════════════════════════════════════════════════════════════════════
//  aihelper VSCode Extension
//  Seamless MCP integration — auto-discovers installation, manages daemon,
//  registers MCP server, and shows status in the status bar.
// ═══════════════════════════════════════════════════════════════════════════

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const cp = require('child_process');
const os = require('os');

// ── Platform helpers ──────────────────────────────────────────────────────

const IS_WINDOWS = os.platform() === 'win32';
const PYTHON_CMDS = IS_WINDOWS ? ['python', 'py', 'python3'] : ['python3', 'python'];
const AIHELPER_DIR_NAMES = ['aihelper'];
const HOME = os.homedir();

// ── State ─────────────────────────────────────────────────────────────────

let statusBarItem = undefined;
let daemonCheckInterval = undefined;
let isDisposing = false;

// ── Discovery ─────────────────────────────────────────────────────────────

/**
 * Find the aihelper installation directory.
 * Priority: 1) user setting  2) AIHELPER_HOME env  3) relative to extension
 *           4) common locations  5) PATH resolution
 */
function findAihelperPath() {
  // 1. User-configured path
  const configured = vscode.workspace.getConfiguration('aihelper').get('path');
  if (configured && fs.existsSync(configured)) {
    const resolved = path.resolve(configured);
    if (isValidAihelperDir(resolved)) return resolved;
  }

  // 2. Environment variable
  const envPath = process.env.AIHELPER_HOME;
  if (envPath && fs.existsSync(envPath)) {
    const resolved = path.resolve(envPath);
    if (isValidAihelperDir(resolved)) return resolved;
  }

  // 3. Relative to this extension's install path
  const extPath = path.resolve(__dirname, '..', '..');
  if (isValidAihelperDir(extPath)) return extPath;

  // 4. Common locations
  const candidates = [
    path.join(HOME, 'aihelper'),
    path.join(HOME, 'github', 'aihelper'),
    path.join(HOME, 'projects', 'aihelper'),
    path.join(HOME, 'dev', 'aihelper'),
    path.join(HOME, 'code', 'aihelper'),
  ];
  // On Windows, also check Program Files
  if (IS_WINDOWS) {
    candidates.push(
      path.join(process.env.LOCALAPPDATA || '', 'aihelper'),
      path.join(process.env.PROGRAMFILES || '', 'aihelper'),
      'C:\\aihelper'
    );
  }
  for (const c of candidates) {
    if (fs.existsSync(c) && isValidAihelperDir(c)) return c;
  }

  // 5. Try to resolve via PATH
  try {
    const launcherName = IS_WINDOWS ? 'aihelper.cmd' : 'aihelper';
    // On Unix: which aihelper ; on Windows: where aihelper
    const whichCmd = IS_WINDOWS ? 'where' : 'which';
    const result = cp.execSync(`${whichCmd} ${launcherName}`, {
      encoding: 'utf-8',
      timeout: 3000,
    }).trim();
    if (result) {
      const launcherPath = result.split('\n')[0].trim();
      const dir = path.dirname(path.dirname(launcherPath));
      if (isValidAihelperDir(dir)) return dir;
    }
  } catch (_) { /* not in PATH */ }

  return null;
}

function isValidAihelperDir(dirPath) {
  try {
    // Check for key files that indicate a valid aihelper installation
    const hasLauncher = fs.existsSync(path.join(dirPath, 'bin', IS_WINDOWS ? 'aihelper.cmd' : 'aihelper'));
    const hasMain = fs.existsSync(path.join(dirPath, 'context_engine', 'main.py'));
    const hasMCP = fs.existsSync(path.join(dirPath, 'context_engine', 'mcp_server.py'));
    return hasLauncher || hasMain || hasMCP;
  } catch {
    return false;
  }
}

/**
 * Get the platform-appropriate Python command.
 */
function resolvePython(pythonSetting) {
  if (pythonSetting && pythonSetting !== 'auto') return pythonSetting;
  for (const cmd of PYTHON_CMDS) {
    try {
      cp.execSync(`${cmd} --version`, { encoding: 'utf-8', timeout: 2000 });
      return cmd;
    } catch { /* try next */ }
  }
  return IS_WINDOWS ? 'python' : 'python3';
}

/**
 * Get the aihelper root path and MCP server script path.
 */
function resolveMCPPaths() {
  const aihelperPath = findAihelperPath();
  if (!aihelperPath) return null;

  const mcpScript = path.join(aihelperPath, 'context_engine', 'mcp_server.py');
  if (!fs.existsSync(mcpScript)) return null;

  const pythonCmd = resolvePython(
    vscode.workspace.getConfiguration('aihelper').get('pythonCommand')
  );

  return { aihelperPath, mcpScript, pythonCmd };
}

// ── MCP Config Management ────────────────────────────────────────────────

const MCP_CONFIG_KEY = 'mcp.servers.aihelper';

function getCurrentMCPConfig() {
  const mcpSection = vscode.workspace.getConfiguration('mcp');
  const servers = mcpSection.get('servers', {});
  return servers.aihelper || null;
}

async function setMCPConfig(paths) {
  const config = vscode.workspace.getConfiguration('mcp');
  const servers = config.get('servers', {});

  servers.aihelper = {
    command: paths.pythonCmd,
    args: [paths.mcpScript],
  };

  await config.update('servers', servers, vscode.ConfigurationTarget.Global);
}

async function removeMCPConfig() {
  const config = vscode.workspace.getConfiguration('mcp');
  const servers = config.get('servers', {});
  delete servers.aihelper;
  await config.update('servers', servers, vscode.ConfigurationTarget.Global);
}

function isMCPConfigured() {
  return getCurrentMCPConfig() !== null;
}

// ── Daemon Management ─────────────────────────────────────────────────────

function getAihelperLauncher(aihelperPath) {
  const binDir = path.join(aihelperPath, 'bin');
  if (IS_WINDOWS) {
    const ps1 = path.join(binDir, 'aihelper.ps1');
    const cmd = path.join(binDir, 'aihelper.cmd');
    if (fs.existsSync(ps1)) return { command: 'powershell', args: ['-ExecutionPolicy', 'Bypass', '-File', ps1] };
    if (fs.existsSync(cmd)) return { command: cmd, args: [] };
  }
  const sh = path.join(binDir, 'aihelper');
  if (fs.existsSync(sh)) return { command: sh, args: [] };
  return null;
}

function runAihelperCommand(aihelperPath, subcommand, args = []) {
  return new Promise((resolve, reject) => {
    const launcher = getAihelperLauncher(aihelperPath);
    if (!launcher) {
      return reject(new Error('aihelper launcher not found'));
    }

    const allArgs = [...launcher.args, subcommand, ...args];
    const proc = cp.spawn(launcher.command, allArgs, {
      cwd: aihelperPath,
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 15000,
      windowsHide: true,
    });

    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => { stdout += d.toString(); });
    proc.stderr.on('data', (d) => { stderr += d.toString(); });

    proc.on('close', (code) => {
      if (code === 0) resolve(stdout.trim());
      else reject(new Error(stderr.trim() || `exit code ${code}`));
    });
    proc.on('error', reject);
  });
}

async function isDaemonRunning() {
  try {
    const paths = resolveMCPPaths();
    if (!paths) return false;
    await runAihelperCommand(paths.aihelperPath, 'daemon', ['status']);
    return true;
  } catch {
    return false;
  }
}

async function startDaemon() {
  const paths = resolveMCPPaths();
  if (!paths) throw new Error('aihelper not found. Configure aihelper.path or install aihelper.');
  const result = await runAihelperCommand(paths.aihelperPath, 'daemon', ['start']);
  return result;
}

async function stopDaemon() {
  const paths = resolveMCPPaths();
  if (!paths) throw new Error('aihelper not found.');
  try {
    const result = await runAihelperCommand(paths.aihelperPath, 'daemon', ['stop']);
    return result;
  } catch {
    // Force kill by PID file
    const pidFile = path.join(HOME, '.aihelper', 'aihelperd.pid');
    if (fs.existsSync(pidFile)) {
      try {
        const pid = parseInt(fs.readFileSync(pidFile, 'utf-8').trim(), 10);
        if (!isNaN(pid)) {
          if (IS_WINDOWS) {
            cp.execSync(`taskkill /F /PID ${pid}`, { timeout: 3000 });
          } else {
            process.kill(pid, 'SIGTERM');
          }
        }
      } catch { /* already gone */ }
      try { fs.unlinkSync(pidFile); } catch { /* ignore */ }
    }
    return 'Daemon stopped (forced)';
  }
}

// ── Status Bar ────────────────────────────────────────────────────────────

function createOrUpdateStatusBar() {
  const show = vscode.workspace.getConfiguration('aihelper').get('statusBar');
  if (!show) {
    if (statusBarItem) { statusBarItem.hide(); }
    return;
  }

  if (!statusBarItem) {
    statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    statusBarItem.command = 'aihelper.daemonStatus';
    statusBarItem.tooltip = 'aihelper — click for details';
    statusBarItem.show();
  }

  // Update asynchronously
  updateStatusBarText();
}

async function updateStatusBarText() {
  if (!statusBarItem || isDisposing) return;

  const configured = isMCPConfigured();
  if (!configured) {
    statusBarItem.text = '$(circuit-board) aihelper: unconfigured';
    statusBarItem.tooltip = 'aihelper — not configured. Run "aihelper: Enable MCP Integration"';
    return;
  }

  try {
    const running = await isDaemonRunning();
    if (running) {
      statusBarItem.text = '$(zap) aihelper: ⚡';
      statusBarItem.tooltip = 'aihelper daemon is running • Click for options';
    } else {
      statusBarItem.text = '$(zap) aihelper: ⏸';
      statusBarItem.tooltip = 'aihelper daemon is stopped • Click to start';
    }
  } catch {
    statusBarItem.text = '$(warning) aihelper: ?';
    statusBarItem.tooltip = 'aihelper — status unknown';
  }
}

// ── Commands ──────────────────────────────────────────────────────────────

async function enableMCP() {
  const paths = resolveMCPPaths();
  if (!paths) {
    const action = await vscode.window.showErrorMessage(
      'aihelper installation not found. Choose an option:',
      'Configure Path Manually',
      'Open Installation Guide'
    );
    if (action === 'Configure Path Manually') {
      await vscode.commands.executeCommand('workbench.action.openSettings', 'aihelper.path');
    } else if (action === 'Open Installation Guide') {
      vscode.env.openExternal(
        vscode.Uri.parse('https://github.com/vietnguyen2914/aihelper/blob/main/docs/INSTALLATION.md')
      );
    }
    return;
  }

  // Check daemon and start if needed
  const running = await isDaemonRunning();
  if (!running) {
    vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: 'Starting aihelper daemon...',
    }, async () => {
      await startDaemon();
    });
  }

  // Write MCP config
  await setMCPConfig(paths);
  updateStatusBarText();

  vscode.window.showInformationMessage(
    `✅ aihelper MCP enabled! Daemon running at ${paths.aihelperPath}`,
    'View Logs', 'OK'
  ).then(selection => {
    if (selection === 'View Logs') viewLogs();
  });
}

async function disableMCP() {
  await removeMCPConfig();
  updateStatusBarText();
  vscode.window.showInformationMessage('aihelper MCP integration disabled.');
}

async function showDaemonStatus() {
  const paths = resolveMCPPaths();
  if (!paths) {
    vscode.window.showWarningMessage('aihelper not found. Run "aihelper: Enable MCP Integration" to configure.');
    return;
  }

  const configured = isMCPConfigured();
  const running = await isDaemonRunning();
  const launcher = getAihelperLauncher(paths.aihelperPath);

  const items = [];

  if (!running) {
    items.push({ label: '$(play) Start Daemon', command: 'aihelper.daemonStart' });
  } else {
    items.push({ label: '$(stop) Stop Daemon', command: 'aihelper.daemonStop' });
  }

  if (configured) {
    items.push({ label: '$(close) Disable MCP', command: 'aihelper.disable' });
  } else {
    items.push({ label: '$(plug) Enable MCP', command: 'aihelper.enable' });
  }

  items.push(
    { label: '$(file-text) View Logs', command: 'aihelper.openLogs' },
    { label: '$(settings-gear) Open Settings', command: 'set aihelper' }
  );

  const detail = [
    `Install path: ${paths.aihelperPath}`,
    `Daemon: ${running ? '🟢 running' : '🔴 stopped'}`,
    `MCP: ${configured ? '✅ configured' : '❌ not configured'}`,
    `Python: ${paths.pythonCmd}`,
    `Launcher: ${launcher ? launcher.command : 'N/A'}`,
    `Platform: ${os.platform()} ${os.release()}`,
  ].join('\n');

  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: 'aihelper — choose action',
    detail: detail,
  });

  if (picked) {
    if (picked.command.startsWith('set ')) {
      vscode.commands.executeCommand('workbench.action.openSettings', picked.command.slice(4));
    } else {
      vscode.commands.executeCommand(picked.command);
    }
  }
}

async function viewLogs() {
  const logFile = path.join(HOME, '.aihelper', 'daemon.log');
  if (fs.existsSync(logFile)) {
    const doc = await vscode.workspace.openTextDocument(logFile);
    vscode.window.showTextDocument(doc);
  } else {
    vscode.window.showInformationMessage('No daemon log found yet. Start the daemon first.');
  }
}

async function reinstall() {
  const paths = resolveMCPPaths();
  if (!paths) {
    vscode.window.showErrorMessage('aihelper not found. Please install it first.');
    return;
  }

  const confirm = await vscode.window.showWarningMessage(
    'This will re-run the aihelper bootstrap. Continue?',
    { modal: true },
    'Yes, Reinstall'
  );
  if (confirm !== 'Yes, Reinstall') return;

  try {
    await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: 'Reinstalling aihelper...',
    }, async (progress) => {
      progress.report({ message: 'Installing Python dependencies...' });
      const launcher = getAihelperLauncher(paths.aihelperPath);
      if (!launcher) throw new Error('Launcher not found');

      const scriptDir = IS_WINDOWS ? 'scripts\\bootstrap.ps1' : 'scripts/bootstrap.sh';
      const bootstrapScript = path.join(paths.aihelperPath, scriptDir);

      if (fs.existsSync(bootstrapScript)) {
        if (IS_WINDOWS) {
          cp.execSync(
            `powershell -ExecutionPolicy Bypass -File "${bootstrapScript}"`,
            { cwd: paths.aihelperPath, stdio: 'inherit', timeout: 120000 }
          );
        } else {
          cp.execSync(`bash "${bootstrapScript}"`, {
            cwd: paths.aihelperPath, stdio: 'inherit', timeout: 120000
          });
        }
      }

      progress.report({ message: 'Starting daemon...' });
      await startDaemon();

      progress.report({ message: 'Configuring MCP...' });
      await setMCPConfig(paths);
    });

    updateStatusBarText();
    vscode.window.showInformationMessage('✅ aihelper reinstalled and ready!');
  } catch (err) {
    vscode.window.showErrorMessage(`Reinstall failed: ${err.message}`);
  }
}

// ── Activation ────────────────────────────────────────────────────────────

function activate(context) {
  console.log('[aihelper] Activating extension...');

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('aihelper.enable', enableMCP),
    vscode.commands.registerCommand('aihelper.disable', disableMCP),
    vscode.commands.registerCommand('aihelper.daemonStart', async () => {
      try {
        await startDaemon();
        updateStatusBarText();
        vscode.window.showInformationMessage('aihelper daemon started');
      } catch (err) {
        vscode.window.showErrorMessage(`Failed to start daemon: ${err.message}`);
      }
    }),
    vscode.commands.registerCommand('aihelper.daemonStop', async () => {
      try {
        await stopDaemon();
        updateStatusBarText();
        vscode.window.showInformationMessage('aihelper daemon stopped');
      } catch (err) {
        vscode.window.showErrorMessage(`Failed to stop daemon: ${err.message}`);
      }
    }),
    vscode.commands.registerCommand('aihelper.daemonStatus', showDaemonStatus),
    vscode.commands.registerCommand('aihelper.openLogs', viewLogs),
    vscode.commands.registerCommand('aihelper.reinstall', reinstall),
  );

  // Create status bar
  createOrUpdateStatusBar();

  // Auto-enable on startup
  const autoEnable = vscode.workspace.getConfiguration('aihelper').get('enableOnStartup');
  if (autoEnable && !isMCPConfigured()) {
    const paths = resolveMCPPaths();
    if (paths) {
      // Don't block activation — fire-and-forget
      (async () => {
        try {
          const running = await isDaemonRunning();
          if (!running) {
            try {
              await startDaemon();
            } catch {
              // Daemon might not be ready yet, that's OK
            }
          }
          await setMCPConfig(paths);
          updateStatusBarText();
          console.log('[aihelper] Auto-configured MCP successfully');
        } catch (err) {
          console.warn('[aihelper] Auto-config failed:', err.message);
        }
      })();
    }
  }

  // Periodic daemon health check (every 30s)
  daemonCheckInterval = setInterval(() => {
    updateStatusBarText();
  }, 30000);

  // Re-check when settings change
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(e => {
      if (e.affectsConfiguration('aihelper')) {
        createOrUpdateStatusBar();
      }
      if (e.affectsConfiguration('aihelper.path') || e.affectsConfiguration('aihelper.pythonCommand')) {
        // Re-run auto-config if path changed
        if (isMCPConfigured()) {
          const paths = resolveMCPPaths();
          if (paths) setMCPConfig(paths);
        }
      }
    })
  );

  context.subscriptions.push({
    dispose: () => {
      isDisposing = true;
      if (daemonCheckInterval) clearInterval(daemonCheckInterval);
    }
  });

  console.log('[aihelper] Extension activated');
}

function deactivate() {
  isDisposing = true;
  if (daemonCheckInterval) clearInterval(daemonCheckInterval);
  console.log('[aihelper] Extension deactivated');
}

module.exports = { activate, deactivate };
