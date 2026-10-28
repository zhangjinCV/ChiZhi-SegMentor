#!/usr/bin/env node
/*
 * Launch Electron with a clean environment.
 *
 * Some shells (including the one used to bootstrap this project) export
 * ELECTRON_RUN_AS_NODE=1 globally.  Electron then behaves like Node and never
 * creates a BrowserWindow, which breaks `electron .` and Playwright's Electron
 * driver.  Strip it for the child process only.
 */
const { spawn } = require("node:child_process");

const electronPath = require("electron");
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electronPath, process.argv.slice(2), {
  stdio: "inherit",
  env,
  cwd: process.cwd(),
});

child.on("error", (error) => {
  console.error(error);
  process.exit(1);
});
child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
