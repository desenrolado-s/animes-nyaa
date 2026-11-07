#!/usr/bin/env node
import { createRequire } from 'node:module'
import { realpathSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { spawn } from 'node:child_process'

const [cliPath, magnet, indexText, outputPath, mpvPath] = process.argv.slice(2)
const index = Number(indexText)

if (!cliPath || !magnet || !Number.isInteger(index) || index < -1 || !outputPath || !mpvPath) {
  console.error('Uso: stream_episode.mjs <webtorrent-cli> <magnet> <índice> <pasta> <mpv>')
  process.exit(2)
}

try {
  const { writeFileSync } = await import('node:fs')
  const { join } = await import('node:path')
  writeFileSync(join(outputPath, 'session.pid'), String(process.pid))
} catch {}

const requireFromCli = createRequire(realpathSync(cliPath))
const webtorrentModule = requireFromCli.resolve('webtorrent')
const { default: WebTorrent } = await import(pathToFileURL(webtorrentModule).href)
const client = new WebTorrent({ torrentPort: 0, dhtPort: 0 })
const torrent = client.add(magnet, { path: outputPath, deselect: true })
const streamServer = client.createServer({}, 'node')
const server = streamServer.server

function waitFor(emitter, successEvent) {
  return new Promise((resolve, reject) => {
    const onError = error => {
      emitter.removeListener(successEvent, onSuccess)
      reject(error)
    }
    const onSuccess = (...args) => {
      emitter.removeListener('error', onError)
      resolve(args)
    }
    emitter.once('error', onError)
    emitter.once(successEvent, onSuccess)
  })
}

let player
let exitCode = 0

async function cleanupStorage() {
  if (outputPath && outputPath.includes('anime-nyaa-')) {
    try {
      const { rmSync } = await import('node:fs')
      rmSync(outputPath, { recursive: true, force: true })
    } catch {}
  }
}

for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.once(signal, async () => {
    if (player && player.exitCode === null && player.signalCode === null) {
      player.kill('SIGTERM')
    }
    try { await new Promise(resolve => client.destroy(() => resolve())) } catch {}
    try { await new Promise(resolve => streamServer.close(resolve)) } catch {}
    await cleanupStorage()
    process.exit(1)
  })
}

try {
  const ready = torrent.ready ? Promise.resolve() : waitFor(torrent, 'ready')
  const listening = waitFor(server, 'listening')
  server.listen(0)
  await Promise.all([ready, listening])

  const selectedIndex = index === -1
    ? torrent.files.reduce((best, candidate, i, files) => candidate.length > files[best].length ? i : best, 0)
    : index
  const file = torrent.files[selectedIndex]
  if (!file) throw new Error(`Não existe arquivo no índice ${selectedIndex} deste torrent.`)

  // WebTorrent starts ordinary torrents with every file selected. Start deselected
  // and explicitly select only the episode the user chose.
  for (const candidate of torrent.files) candidate.deselect()
  file.select(1)

  const url = `http://127.0.0.1:${server.address().port}${file.streamURL}`
  player = spawn(mpvPath, ['--really-quiet', '--loop=no', '--ontop', url], { stdio: 'inherit' })
  exitCode = await new Promise((resolve, reject) => {
    player.once('error', reject)
    player.once('exit', (code, signal) => resolve(code ?? (signal ? 1 : 0)))
  })
} catch (error) {
  console.error(error?.stack || String(error))
  exitCode = 1
} finally {
  if (player && player.exitCode === null && player.signalCode === null) player.kill('SIGTERM')
  try { await new Promise(resolve => client.destroy(() => resolve())) } catch {}
  try { await new Promise(resolve => streamServer.close(resolve)) } catch {}
  await cleanupStorage()
}

process.exitCode = exitCode
