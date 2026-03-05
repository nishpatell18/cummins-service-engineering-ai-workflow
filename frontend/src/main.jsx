import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import BackOffice from './BackOffice'

const isBackOffice = window.location.pathname === '/backoffice'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {isBackOffice ? <BackOffice /> : <App />}
  </React.StrictMode>
)