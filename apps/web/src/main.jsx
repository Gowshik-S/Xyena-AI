import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import LiveArchitecture from './LiveArchitecture.jsx'
import LiveDemo from './LiveDemo.jsx'
import './styles.css'

const page = window.location.pathname === '/architecture-live'
  ? <LiveArchitecture />
  : window.location.pathname === '/live-demo'
    ? <LiveDemo />
    : <App />

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {page}
  </React.StrictMode>,
)
