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

const requireFromCli = createRequire(realpathSync(cliPath))
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
let exitCode = 0

for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.once(signal, async () => {
    if (player && player.exitCode === null && player.signalCode === null) {
      player.kill('SIGTERM')
      await new Promise(resolve => {
        player.once('exit', resolve)
        setTimeout(resolve, 1500)
      })
    }
    try { await new Promise(resolve => client.destroy(() => resolve())) } catch {}
    try { await new Promise(resolve => streamServer.close(resolve)) } catch {}
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
  const { createConnection } = await import('node:net')
  const { join } = await import('node:path')
  const ipcSocketPath = join(outputPath, 'mpv.sock')

  console.log('STATUS: Abrindo o reprodutor mpv…')
  player = spawn(mpvPath, [
    '--really-quiet',
    '--loop=no',
    '--ontop',
    `--input-ipc-server=${ipcSocketPath}`,
    url,
  ], { stdio: 'inherit' })

  let ipcSocket
  let playingEmitted = false
  let attempts = 0
  const connectIpc = () => {
    attempts++
    ipcSocket = createConnection(ipcSocketPath)
    ipcSocket.on('connect', () => {
      ipcSocket.on('data', chunk => {
        const text = chunk.toString('utf-8')
        if (!playingEmitted && (text.includes('"playback-restart"') || text.includes('"file-loaded"'))) {
          playingEmitted = true
          console.log('STATUS:PLAYING Reproduzindo no mpv')
          ipcSocket.destroy()
        }
      })
    })
    ipcSocket.on('error', () => {
      ipcSocket.destroy()
      if (!playingEmitted && attempts < 100 && player && player.exitCode === null) {
        setTimeout(connectIpc, 100)
      }
    })
  }
  setTimeout(connectIpc, 100)

  exitCode = await new Promise((resolve, reject) => {
    player.once('error', reject)
    player.once('exit', (code, signal) => resolve(code ?? (signal ? 1 : 0)))
  })
} catch (error) {
  console.error(error?.stack || String(error))
  exitCode = 1
} finally {
  if (player && player.exitCode === null && player.signalCode === null) {
    player.kill('SIGTERM')
    await new Promise(resolve => {
      player.once('exit', resolve)
      setTimeout(resolve, 1500)
    })
  }
  try { await new Promise(resolve => client.destroy(() => resolve())) } catch {}
  try { await new Promise(resolve => streamServer.close(resolve)) } catch {}
  try {
    const { unlinkSync } = await import('node:fs')
    unlinkSync(join(outputPath, 'mpv.sock'))
  } catch {}
}

process.exitCode = exitCode
