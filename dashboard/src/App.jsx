import React from 'react'
import ActorStage from './components/ActorStage'
import useActorStatus from './hooks/useActorStatus'

function App() {
  const { actors, loading, error, lastUpdate } = useActorStatus()

  return (
    <div className="app">
      <header className="stage-header">
        <h1>Agent System Sahnesi</h1>
        <p className="subtitle">8 Aktor - Canli Izleme Panosu</p>
        {lastUpdate && (
          <p className="last-update">Son guncelleme: {lastUpdate}</p>
        )}
      </header>

      {error && (
        <div className="error-banner">
          Baglanti hatasi: {error}
        </div>
      )}

      <main className="stage-container">
        <ActorStage actors={actors} loading={loading} />
      </main>

      <footer className="stage-footer">
        <div className="stage-floor"></div>
        <p className="footer-text">
          Her 10 saniyede guncellenir | Tum aktorler sahnede
        </p>
      </footer>
    </div>
  )
}

export default App
