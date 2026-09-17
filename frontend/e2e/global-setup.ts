import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const apiOrigin = process.env.E2E_API_URL ?? 'http://localhost:18080'
const databaseUrl =
  process.env.TEST_DATABASE_URL ??
  'postgres://etymologuessr:etymologuessr@localhost:5433/etymologuessr?sslmode=disable'

async function waitForHealth() {
  const deadline = Date.now() + 60_000
  let last = 'unreachable'
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${apiOrigin}/health`)
      if (res.ok) {
        return
      }
      last = `status ${res.status}`
    } catch (error) {
      last = error instanceof Error ? error.message : String(error)
    }
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  throw new Error(`API at ${apiOrigin}/health is not ready: ${last}`)
}

function loadFixtures() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'etymologuessr-e2e-'))
  const python = path.join(repoRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  const exe = fs.existsSync(python) ? python : 'python'
  execFileSync(exe, ['-m', 'etl', 'reset', '--all', '--reload', '--fixtures'], {
    cwd: repoRoot,
    env: {
      ...process.env,
      DATABASE_URL: databaseUrl,
      ETL_DATA_DIR: dataDir,
    },
    stdio: 'inherit',
  })
}

export default async function globalSetup() {
  await waitForHealth()
  loadFixtures()
}
