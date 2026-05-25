import { copyFileSync, mkdirSync, readdirSync, rmSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const sharedDir = dirname(fileURLToPath(import.meta.url))
const sourceDir = join(sharedDir, "src")
const targetDir = join(process.cwd(), "src", "shared", "src")

rmSync(join(process.cwd(), "src", "shared"), { force: true, recursive: true })

function copyTypescriptSources(source, target) {
  mkdirSync(target, { recursive: true })
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    const sourcePath = join(source, entry.name)
    const targetPath = join(target, entry.name)
    if (entry.isDirectory()) {
      copyTypescriptSources(sourcePath, targetPath)
    } else if (entry.isFile() && entry.name.endsWith(".ts") && !entry.name.endsWith(".d.ts")) {
      copyFileSync(sourcePath, targetPath)
    }
  }
}

copyTypescriptSources(sourceDir, targetDir)
