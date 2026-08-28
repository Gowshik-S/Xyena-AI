import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import LiveArchitecture from './LiveArchitecture.jsx'
import './styles.css'

const isLiveArchitecture = window.location.pathname === '/architecture-live'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {isLiveArchitecture ? <LiveArchitecture /> : <App />}
  </React.StrictMode>,
)
