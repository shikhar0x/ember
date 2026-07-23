import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const isWindows = process.platform === 'win32';
const resourceFile = isWindows ? '../../dist/ember-backend.exe' : '../../dist/ember-backend';

const config = {
  bundle: {
    resources: {
      [resourceFile]: isWindows ? "ember-backend.exe" : "ember-backend"
    }
  }
};

const configPath = path.join(__dirname, '../src-tauri/tauri.build.conf.json');
fs.writeFileSync(configPath, JSON.stringify(config, null, 2));

console.log(`\n[Ember Builder] Detected OS: ${process.platform}`);
console.log(`[Ember Builder] Configured build to bundle: ${resourceFile}\n`);
