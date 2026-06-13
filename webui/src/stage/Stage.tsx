// Seleciona o palco: robô Spline (padrão) ou cérebro 3D (?stage=brain).
// Se a cena Spline falhar (sem internet, runtime quebrado), cai no cérebro.
import { Component, type ReactNode } from 'react'
import BrainStage from './brain3d'
import RobotStage from './RobotStage'

const PARAM = new URLSearchParams(window.location.search).get('stage')

class SplineBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export default function Stage() {
  if (PARAM === 'brain') return <BrainStage />
  return (
    <SplineBoundary fallback={<BrainStage />}>
      <RobotStage />
    </SplineBoundary>
  )
}
