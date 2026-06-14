import { sendAudioSource, sendBinary, setBinaryHandler, setServerEventHandler } from './ws'

const INPUT_RATE = 16000
const OUTPUT_RATE = 24000

let inputCtx: AudioContext | null = null
let outputCtx: AudioContext | null = null
let mediaStream: MediaStream | null = null
let processor: ScriptProcessorNode | null = null
let source: MediaStreamAudioSourceNode | null = null
let silentGain: GainNode | null = null
let nextPlayTime = 0

function audioContext(): AudioContext {
  const Ctx = window.AudioContext || window.webkitAudioContext
  if (!Ctx) throw new Error('AudioContext indisponível neste navegador.')
  return new Ctx()
}

function downsample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input
  const ratio = fromRate / toRate
  const newLength = Math.round(input.length / ratio)
  const result = new Float32Array(newLength)
  let offset = 0
  for (let i = 0; i < newLength; i += 1) {
    const nextOffset = Math.round((i + 1) * ratio)
    let accum = 0
    let count = 0
    for (let j = offset; j < nextOffset && j < input.length; j += 1) {
      accum += input[j]
      count += 1
    }
    result[i] = count ? accum / count : 0
    offset = nextOffset
  }
  return result
}

function floatToPcm16(input: Float32Array): ArrayBuffer {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i += 1) {
    const s = Math.max(-1, Math.min(1, input[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out.buffer
}

function playPcm24(data: ArrayBuffer): void {
  if (!outputCtx) outputCtx = audioContext()
  if (outputCtx.state === 'suspended') void outputCtx.resume()
  const samples = new Int16Array(data)
  if (!samples.length) return
  const buffer = outputCtx.createBuffer(1, samples.length, OUTPUT_RATE)
  const channel = buffer.getChannelData(0)
  for (let i = 0; i < samples.length; i += 1) {
    channel[i] = samples[i] / 0x8000
  }
  const node = outputCtx.createBufferSource()
  node.buffer = buffer
  node.connect(outputCtx.destination)
  const now = outputCtx.currentTime
  nextPlayTime = Math.max(nextPlayTime, now + 0.02)
  node.start(nextPlayTime)
  nextPlayTime += buffer.duration
}

export function isMobileVoiceSupported(): boolean {
  const hasAudioContext = typeof AudioContext !== 'undefined' || typeof window.webkitAudioContext !== 'undefined'
  const hasMic = typeof navigator.mediaDevices?.getUserMedia === 'function'
  return hasMic && hasAudioContext
}

export async function startMobileVoice(): Promise<void> {
  if (!isMobileVoiceSupported()) {
    throw new Error('Microfone indisponível neste navegador. No iPhone, abra em HTTPS ou use um túnel seguro.')
  }
  if (mediaStream) return

  inputCtx = audioContext()
  outputCtx = outputCtx ?? audioContext()
  await inputCtx.resume()
  await outputCtx.resume()

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
  })

  source = inputCtx.createMediaStreamSource(mediaStream)
  processor = inputCtx.createScriptProcessor(4096, 1, 1)
  silentGain = inputCtx.createGain()
  silentGain.gain.value = 0

  processor.onaudioprocess = (event) => {
    const mono = event.inputBuffer.getChannelData(0)
    const pcm = floatToPcm16(downsample(mono, inputCtx?.sampleRate ?? INPUT_RATE, INPUT_RATE))
    sendBinary(pcm)
  }

  source.connect(processor)
  processor.connect(silentGain)
  silentGain.connect(inputCtx.destination)
  setBinaryHandler(playPcm24)
  setServerEventHandler((ev) => {
    if (ev.t === 'err' && ev.message.includes('phone audio')) {
      stopMobileVoice()
    }
  })
  sendAudioSource('phone')
}

export function stopMobileVoice(): void {
  sendAudioSource('pc')
  setBinaryHandler(null)
  setServerEventHandler(null)
  processor?.disconnect()
  source?.disconnect()
  silentGain?.disconnect()
  processor = null
  source = null
  silentGain = null
  mediaStream?.getTracks().forEach(track => track.stop())
  mediaStream = null
  void inputCtx?.close()
  inputCtx = null
  nextPlayTime = outputCtx?.currentTime ?? 0
}

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext
  }
}
