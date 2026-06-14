import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

function syncVisualViewport() {
  const viewport = window.visualViewport
  const height = viewport?.height ?? window.innerHeight
  const bottomInset = Math.max(0, window.innerHeight - height - (viewport?.offsetTop ?? 0))
  document.documentElement.style.setProperty('--nox-app-height', `${height}px`)
  document.documentElement.style.setProperty('--nox-browser-bottom', `${bottomInset}px`)
}

syncVisualViewport()
window.visualViewport?.addEventListener('resize', syncVisualViewport)
window.visualViewport?.addEventListener('scroll', syncVisualViewport)
window.addEventListener('resize', syncVisualViewport)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
