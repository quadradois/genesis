export type NoxBackendState = 'INITIALISING' | 'LISTENING' | 'THINKING' | 'SPEAKING' | 'MUTED'
export type ChatRole = 'user' | 'nox' | 'sys' | 'err' | 'file'
export type BrainMode = 'idle' | 'think' | 'speak'

export interface ChatMsg { t: 'chat'; role: ChatRole; text: string }

export type ServerEvent =
  | { t: 'hello'; state: NoxBackendState; muted: boolean; audio_source?: 'pc' | 'phone'; dev_tools: boolean; setup_complete: boolean; history: ChatMsg[] }
  | { t: 'state'; state: NoxBackendState }
  | ChatMsg
  | { t: 'mute'; muted: boolean }
  | { t: 'viz'; level: number }
  | { t: 'tool'; name: string; status: 'start' | 'ok' | 'fail'; ms: number | null }
  | { t: 'dev_tools'; enabled: boolean }
  | { t: 'audio_source'; source: 'pc' | 'phone' }
  | { t: 'err'; message: string }

export function mapStateToMode(state: NoxBackendState): BrainMode {
  if (state === 'SPEAKING') return 'speak'
  if (state === 'THINKING') return 'think'
  return 'idle'
}
