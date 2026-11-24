'use strict';

const {app, BrowserWindow, dialog, ipcMain, Menu, nativeTheme} = require('electron');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

const resourceRoot = path.join(process.resourcesPath, 'atom-lens');
const python = path.join(resourceRoot, process.platform === 'win32' ? 'python/python.exe' : 'python/bin/python3');
let backend, baseURL, window, ready = false, stopping = false;
let language = 'en';
let pendingPaths = [];

function text(zh, en) {
  return language === 'zh-CN' ? zh : en;
}

function startBackend() {
  const environment = {...process.env};
  delete environment.PYTHONHOME;
  delete environment.PYTHONPATH;
  backend = spawn(python, ['-I', '-X', 'utf8', '-B', '-u', path.join(resourceRoot, 'native/desktop_host.py')], {
    cwd: resourceRoot, env: environment, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
  });
  let diagnostic = '';
  backend.stderr.setEncoding('utf8').on('data', chunk => { diagnostic = (diagnostic + chunk).slice(-4000); });
  backend.stdin.on('error', () => {}); // The worker may exit before its stdin is closed.
  const output = readline.createInterface({input: backend.stdout});
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('The bundled runtime did not start in 30 seconds.')), 30000);
    backend.once('error', reject);
    backend.once('exit', code => {
      clearTimeout(timer);
      reject(new Error(diagnostic.trim() || `The bundled runtime exited (${code}).`));
    });
    output.once('line', line => {
      clearTimeout(timer);
      if (!/^http:\/\/127\.0\.0\.1:\d{1,5}\/[\w-]{43}\/$/.test(line)) {
        reject(new Error('Invalid response from the bundled runtime.'));
      } else {
        resolve(line);
      }
    });
  });
}

function localResource(value) {
  return value === 'about:blank' || value.startsWith(baseURL);
}

function deliverPaths(paths) {
  if (!paths.length) return;
  if (ready && window && !window.isDestroyed()) {
    void window.webContents.executeJavaScript(`window.atomLensOpenPaths(${JSON.stringify(paths)})`);
  } else {
    pendingPaths.push(...paths);
  }
}

async function choosePaths(action, directory) {
  const properties = action === 'openFiles' ? ['openFile', 'multiSelections'] : ['openDirectory'];
  const titles = {
    openFiles: text('打开结构文件', 'Open Structure Files'),
    openFolder: text('打开结构目录', 'Open Structure Folder'),
    chooseDirectory: text('选择保存目录', 'Choose Export Folder'),
  };
  const defaultPath = typeof directory === 'string' && path.isAbsolute(directory) ? directory : app.getPath('documents');
  const {canceled, filePaths} = await dialog.showOpenDialog(window, {title: titles[action], properties, defaultPath});
  const paths = canceled ? [] : filePaths;
  return action === 'chooseDirectory' ? {path: paths[0] || ''} : {paths};
}

function registerBridge(preferences) {
  ipcMain.handle('atomlens:native', (event, action, params = {}) => {
    const contents = window?.webContents;
    if (!contents || event.sender !== contents || event.senderFrame !== contents.mainFrame ||
        event.senderFrame.url !== baseURL) throw new Error('Invalid Atom Lens window.');
    switch (action) {
      case 'openFiles':
      case 'openFolder':
      case 'chooseDirectory':
        return choosePaths(action, params.directory);
      case 'readLanguage':
        return {language};
      case 'setLanguage':
        if (['en', 'zh-CN'].includes(params.language) && language !== params.language) {
          language = params.language;
          fs.mkdirSync(path.dirname(preferences), {recursive: true});
          fs.writeFileSync(preferences, language, 'utf8');
        }
        return {};
      case 'setAppearance':
        if (['light', 'dark', 'system'].includes(params.mode)) nativeTheme.themeSource = params.mode;
        window.setBackgroundColor(params.dark === true ? '#151517' : '#ffffff');
        return {};
      case 'ready':
        ready = true;
        deliverPaths(pendingPaths.splice(0));
        return {};
      default:
        throw new Error('Unsupported Atom Lens action.');
    }
  });
}

async function createWindow() {
  language = app.getLocale().startsWith('zh') ? 'zh-CN' : 'en';
  const preferences = path.join(app.getPath('userData'), 'language.txt');
  try {
    const saved = fs.readFileSync(preferences, 'utf8');
    if (['en', 'zh-CN'].includes(saved)) language = saved;
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  baseURL = await startBackend();
  Menu.setApplicationMenu(null);
  window = new BrowserWindow({
    title: 'Atom Lens', width: 1160, height: 780, minWidth: 850, minHeight: 600,
    icon: path.join(resourceRoot, 'AtomLens.ico'), show: false,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#151517' : '#ffffff',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, sandbox: true,
      nodeIntegration: false, partition: 'atom-lens',
    },
  });
  registerBridge(preferences);
  const contents = window.webContents;
  const session = contents.session;
  session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.setPermissionCheckHandler(() => false);
  session.webRequest.onBeforeRequest({urls: ['http://*/*', 'https://*/*']}, (details, callback) => {
    callback({cancel: !localResource(details.url)});
  });
  contents.on('will-frame-navigate', event => { if (!localResource(event.url)) event.preventDefault(); });
  contents.setWindowOpenHandler(() => ({action: 'deny'}));
  contents.on('before-input-event', (event, input) => {
    if (!ready || input.type !== 'keyDown' || !(input.control || input.meta) || input.alt || input.shift || input.isAutoRepeat) return;
    const shortcut = {o: 'atomLensOpenLocal', k: 'atomLensShowServers'}[input.key.toLowerCase()];
    if (!shortcut) return;
    event.preventDefault();
    void contents.executeJavaScript(`window.${shortcut}()`);
  });
  window.once('ready-to-show', () => window.show());
  await contents.loadURL(baseURL);
}

app.setAppUserModelId('org.atom-lens.desktop');
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', (_event, argv) => {
    if (window?.isMinimized()) window.restore();
    window?.focus();
    deliverPaths(argv.slice(1).filter(item => path.isAbsolute(item) && fs.existsSync(item)));
  });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', event => {
    if (!backend?.pid || backend.exitCode !== null || backend.signalCode !== null) return;
    event.preventDefault();
    if (stopping) return;
    stopping = true;
    const timeout = setTimeout(() => backend.kill(), 8000);
    backend.once('close', () => { clearTimeout(timeout); app.quit(); });
    backend.stdin.end();
  });
  if (app.isPackaged) pendingPaths = process.argv.slice(1).filter(item => path.isAbsolute(item) && fs.existsSync(item));
  app.whenReady().then(createWindow).catch(error => {
    dialog.showErrorBox('Atom Lens', error.message);
    app.quit();
  });
}
