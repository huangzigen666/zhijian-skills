import { access, rename } from 'node:fs/promises';
import path from 'node:path';

const dependencySkillPaths = [
  'node_modules/playwright-core/lib/tools/cli-client/skill/SKILL.md',
  'node_modules/playwright-core/lib/tools/trace/SKILL.md',
];

for (const relativePath of dependencySkillPaths) {
  const source = path.resolve(relativePath);
  const destination = path.join(path.dirname(source), 'PLAYWRIGHT_TOOL_GUIDE.md');

  try {
    await access(source);
    await rename(source, destination);
    console.log(`Hid dependency-only skill metadata: ${relativePath}`);
  } catch (error) {
    if (error.code !== 'ENOENT') {
      throw error;
    }
  }
}
