#!/usr/bin/env node
import { createRequire } from 'node:module'
import { existsSync, realpathSync, unlinkSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import { randomBytes } from 'node:crypto'
import { createConnection } from 'node:net'
import { pathToFileURL } from 'node:url'
import { spawn } from 'node:child_process'

const [cliPath, magnet, indexText, outputPath, mpvPath] = process.argv.slice(2)
const index = Number(indexText)

if (!cliPath || !magnet || !Number.isInteger(index) || index < -1 || !outputPath || !mpvPath) {
  console.error('Uso: stream_episode.mjs <webtorrent-cli> <magnet> <índice> <pasta> <mpv>')
  process.exit(2)
}

const isWindows = process.platform === 'win32'

// Em Linux, caminhos de Unix domain sockets têm limite estrito de 108 bytes (sun_path).
// No Windows, o mpv requer Named Pipes (\\.\pipe\...) para --input-ipc-server.
const sessionToken = randomBytes(4).toString('hex')
const ipcSocketPath = isWindows
  ? `\\\\.\\pipe\\nyaa-mpv-${process.pid}-${sessionToken}`
  : join(tmpdir(), `nyaa-mpv-${process.pid}-${sessionToken}.sock`)

function cleanupIpcSocket() {
  if (!isWindows) {
    try { unlinkSync(ipcSocketPath) } catch {}
  }
}

function resolveCliEntry(inputPath) {
  const resolved = realpathSync(inputPath)
  const normalized = resolved.replace(/\\/g, '/')
  if (/\.(cmd|bat|ps1)$/i.test(resolved) || normalized.endsWith('/.bin/webtorrent')) {
    const dir = dirname(resolved)
    const candidates = [
      join(dir, '..', 'webtorrent-cli', 'bin', 'cmd.js'),
      join(dir, 'node_modules', 'webtorrent-cli', 'bin', 'cmd.js'),
    ]
    for (const candidate of candidates) {
      if (existsSync(candidate)) return realpathSync(candidate)
    }
  }
  return resolved
}

cleanupIpcSocket()
try {
  const { writeFileSync } = await import('node:fs')
  writeFileSync(join(outputPath, 'session.pid'), String(process.pid))
} catch {}

const requireFromCli = createRequire(resolveCliEntry(cliPath))
const webtorrentModule = requireFromCli.resolve('webtorrent')
const { default: WebTorrent } = await import(pathToFileURL(webtorrentModule).href)
const client = new WebTorrent({ torrentPort: 0, dhtPort: 0 })
console.log('STATUS: Conectando aos peers do torrent…')
const torrent = client.add(magnet, { path: outputPath, deselect: true })

torrent.on('wire', () => {
  if (!torrent.ready) {
    console.log(`STATUS: Conectado a ${torrent.numPeers} peer(s)…`)
  }
})

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
let ipcSocket
let pollInterval
let exitCode = 0

async function cleanupStorage() {
  if (outputPath && outputPath.includes('anime-nyaa-')) {
    try {
      const { rmSync } = await import('node:fs')
      rmSync(outputPath, { recursive: true, force: true })
    } catch {}
  }
}

const signals = isWindows ? ['SIGINT', 'SIGTERM', 'SIGBREAK'] : ['SIGINT', 'SIGTERM', 'SIGHUP']
for (const signal of signals) {
  process.once(signal, async () => {
    if (pollInterval) clearInterval(pollInterval)
    if (ipcSocket && !ipcSocket.destroyed) {
      ipcSocket.destroy()
    }
    if (player && player.exitCode === null && player.signalCode === null) {
      if (isWindows) {
        player.kill()
      } else {
        player.kill('SIGTERM')
      }
      await new Promise(resolve => {
        player.once('exit', resolve)
        setTimeout(resolve, 1500)
      })
    }
    try { await new Promise(resolve => client.destroy(() => resolve())) } catch {}
    try { await new Promise(resolve => streamServer.close(resolve)) } catch {}
    cleanupIpcSocket()
    await cleanupStorage()
    process.exit(1)
  })
}

try {
  const ready = torrent.ready ? Promise.resolve() : waitFor(torrent, 'ready')
  const listening = waitFor(server, 'listening')
  server.listen(0)
  await Promise.all([ready, listening])
  console.log('STATUS: Metadados carregados. Preparando episódio…')

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

  cleanupIpcSocket()
  console.log('STATUS: Abrindo o reprodutor mpv…')
  player = spawn(mpvPath, [
    '--really-quiet',
    '--loop=no',
    '--ontop',
    `--input-ipc-server=${ipcSocketPath}`,
    url,
  ], { stdio: 'inherit' })

  let playingEmitted = false
  let attempts = 0
  let ipcBuffer = ''

  const markPlaying = () => {
    if (playingEmitted) return
    playingEmitted = true
    if (pollInterval) clearInterval(pollInterval)
    console.log('STATUS:PLAYING Reproduzindo no mpv')
    if (ipcSocket && !ipcSocket.destroyed) {
      ipcSocket.destroy()
    }
  }

  const queryPlaybackState = () => {
    if (ipcSocket && !ipcSocket.destroyed && !playingEmitted) {
      try {
        ipcSocket.write(JSON.stringify({ command: ['get_property', 'time-pos'] }) + '\n')
        ipcSocket.write(JSON.stringify({ command: ['get_property', 'playback-time'] }) + '\n')
      } catch {}
    }
  }

  const connectIpc = () => {
    attempts++
    ipcSocket = createConnection(ipcSocketPath)
    ipcSocket.on('connect', () => {
      try {
        ipcSocket.write(JSON.stringify({ command: ['observe_property', 1, 'time-pos'] }) + '\n')
        ipcSocket.write(JSON.stringify({ command: ['observe_property', 2, 'playback-time'] }) + '\n')
        queryPlaybackState()
      } catch {}

      if (pollInterval) clearInterval(pollInterval)
      pollInterval = setInterval(queryPlaybackState, 200)

      ipcSocket.on('data', chunk => {
        ipcBuffer += chunk.toString('utf-8')
        let newlineIndex
        while ((newlineIndex = ipcBuffer.indexOf('\n')) !== -1) {
          const line = ipcBuffer.slice(0, newlineIndex).trim()
          ipcBuffer = ipcBuffer.slice(newlineIndex + 1)
          if (!line) continue

          let isMatch = false
          try {
            const msg = JSON.parse(line)
            if (msg.event === 'playback-restart' || msg.event === 'file-loaded') {
              isMatch = true
            } else if (msg.event === 'property-change' && (msg.name === 'time-pos' || msg.name === 'playback-time') && typeof msg.data === 'number') {
              isMatch = true
            } else if (msg.error === 'success' && typeof msg.data === 'number') {
              isMatch = true
            }
          } catch {}

          if (!isMatch && (line.includes('"playback-restart"') || line.includes('"file-loaded"'))) {
            isMatch = true
          }

          if (isMatch) {
            markPlaying()
            break
          }
        }
      })
    })
    ipcSocket.on('error', () => {
      if (pollInterval) clearInterval(pollInterval)
      ipcSocket.destroy()
      if (!playingEmitted && attempts < 100 && player && player.exitCode === null) {
        setTimeout(connectIpc, 50)
      }
    })
  }
  setTimeout(connectIpc, 50)

  exitCode = await new Promise((resolve, reject) => {
    player.once('error', reject)
    player.once('exit', (code, signal) => resolve(code ?? (signal ? 1 : 0)))
  })
} catch (error) {
  console.error(error?.stack || String(error))
  exitCode = 1
} finally {
  if (pollInterval) clearInterval(pollInterval)
  if (ipcSocket && !ipcSocket.destroyed) {
    ipcSocket.destroy()
  }
  if (player && player.exitCode === null && player.signalCode === null) {
    if (isWindows) {
      player.kill()
    } else {
      player.kill('SIGTERM')
    }
    await new Promise(resolve => {
      player.once('exit', resolve)
      setTimeout(resolve, 1500)
    })
  }
  try { await new Promise(resolve => client.destroy(() => resolve())) } catch {}
  try { await new Promise(resolve => streamServer.close(resolve)) } catch {}
  cleanupIpcSocket()
  await cleanupStorage()
}

process.exitCode = exitCode
