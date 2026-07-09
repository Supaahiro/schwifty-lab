## Initial Setup

conda create -n rxjs-operators
conda install nodejs
npm install -g pnpm
pnpm install --save-dev ts-node typescript @types/node

## Execute a script

Using `ts-node`:

`pnpm exec ts-node path/to/file.ts`

Run a demo by invoking `tsc` and then `node`:

`tsc -p path/to/directory && node path/to/file.js`

Watch a specific demo directory and autobuild a JavaScript file when the TypeScript file changes:

`tsc -w -p path/to/directory`

and then run with

`node path/to/file.js`