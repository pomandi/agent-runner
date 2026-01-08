import React from 'react'
import Actor from './Actor'

function ActorStage({ actors, loading }) {
  if (loading && actors.every(a => a.status === 'loading')) {
    return (
      <div className="stage loading-stage">
        <div className="loading-message">
          <span className="loading-emoji">🎭</span>
          <p>Aktorler sahneye cikiyor...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="stage">
      <div className="spotlight-left"></div>
      <div className="spotlight-right"></div>

      <div className="actors-row">
        {actors.map((actor, index) => (
          <Actor
            key={actor.name}
            actor={actor}
            index={index}
            total={actors.length}
          />
        ))}
      </div>

      <div className="stage-lights">
        {actors.map((actor, i) => (
          <div
            key={`light-${actor.name}`}
            className={`stage-light ${actor.status}`}
            style={{
              left: `${(i + 0.5) * (100 / actors.length)}%`,
              backgroundColor: actor.color
            }}
          />
        ))}
      </div>
    </div>
  )
}

export default ActorStage
