'use strict';

const {contextBridge, ipcRenderer, webUtils} = require('electron');

contextBridge.exposeInMainWorld('atomLensDesktop', {
  invoke: (action, params) => ipcRenderer.invoke('atomlens:native', action, params),
  pathForFile: file => webUtils.getPathForFile(file),
});
