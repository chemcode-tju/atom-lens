const assert=require('node:assert/strict');
const fs=require('node:fs');
const {translate,catalog}=require('../plugin/web/i18n.js');
assert.equal(translate('显示设置'),'Display settings');
assert.equal(translate(' 显示设置 '),' Display settings ');
assert.equal(translate('显示设置','zh-CN'),'显示设置');
assert.equal(translate('已应用：8 个原子 · 参考帧 0'),'Applied: 8 atoms · reference frame 0');
assert.equal(translate('加载停止：第 4 帧不完整（保留已加载的 3 帧）'),'Loading stopped: Incomplete frame 4 (3 loaded frames retained)');
assert.equal(translate('完整读取失败：当前主机 nd3 上没有此文件：/data/结构/POSCAR'),'Could not read full file: File not found on nd3: /data/结构/POSCAR');
assert.equal(translate('距离 1–2：1.2500 Å'),'Distance 1–2: 1.2500 Å');
assert.equal(translate('/data/结构/POSCAR'),'/data/结构/POSCAR');
assert.equal(translate('已保存：/data/结构/快照.png'),'Saved: /data/结构/快照.png');
// Every static UI text/tooltip must have an English translation. Do not test
// user data (filenames, chemical symbols or source) as translatable strings.
const html=fs.readFileSync('plugin/web/index.html','utf8');
for(const match of html.matchAll(/>([^<>]*[\p{Script=Han}][^<>]*)<|(?:title|aria-label|placeholder)="([^"]*[\p{Script=Han}][^"]*)"/gu)){
 const text=(match[1]||match[2]).trim();if(text==='简体中文')continue;
 assert.ok(!/[\p{Script=Han}]/u.test(translate(text)),`Missing UI translation: ${text}`);
}
for(const [key,en] of Object.entries(catalog)){
 assert.ok(!/[\p{Script=Han}]/u.test(en),key);
 assert.deepEqual([...key.matchAll(/\{\d+\}/g)].map(m=>m[0]).sort(),[...en.matchAll(/\{\d+\}/g)].map(m=>m[0]).sort(),key);
}
console.log('Localization: static UI coverage, parameterized errors, nested diagnostics and user paths passed.');
